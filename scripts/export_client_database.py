"""Export a project's existing rows without rewriting evidence or native IDs.

Only writes a NEW database. Source must be a consistent offline/SQLite backup.
Unknown tables fail closed so future schema changes require explicit review.
"""
import argparse
import hashlib
import json
import sqlite3
from pathlib import Path


def export(source, destination, project):
    source, destination = Path(source), Path(destination)
    if destination.exists():
        raise ValueError('destination already exists')
    src = sqlite3.connect(source.resolve().as_uri() + '?mode=ro', uri=True)
    src.row_factory = sqlite3.Row
    tables = [r[0] for r in src.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    rows = {t: list(src.execute('SELECT * FROM "' + t + '"')) for t in tables}
    def ids(table, key='id', predicate=lambda r: True):
        return {r[key] for r in rows[table] if predicate(r)}
    if project not in ids('projects'):
        raise ValueError('project not found')
    project_ids = {project}
    conversations = ids('conversations', predicate=lambda r:r['project_id']==project)
    turns = ids('turns', predicate=lambda r:r['project_id']==project)
    references = {
        'project_id': project_ids,
        'conversation_id': conversations,
        'source_conversation': conversations,
        'turn_id': turns,
        'task_id': ids('task_code_tasks', predicate=lambda r:r['project_id']==project),
        'goal_id': ids('research_goals', predicate=lambda r:r['project_id']==project),
        'experiment_id': ids('training_experiments', predicate=lambda r:r['project_id']==project),
        'artifact_id': ids('artifacts', predicate=lambda r:r['project_id']==project),
    }
    config_ids = {json.loads(r['document'])['config_digest'] for r in rows['turns'] if r['id'] in turns}
    batch_ids = {r['batch_id'] for r in rows['p4_context_projections'] if r['turn_id'] in turns}
    kept = {}
    for table in tables:
        columns = [r[1] for r in src.execute('PRAGMA table_info("' + table + '")')]
        if table == 'projects': predicate = lambda r:r['id']==project
        elif table == 'runtime_configs': predicate = lambda r:r['digest'] in config_ids
        elif table == 'p4_projection_batches': predicate = lambda r:r['id'] in batch_ids
        elif table in {'schema_migrations','task_code_schema','sqlite_sequence'}: predicate = lambda r:True
        else:
            # Prefer explicit owner over optional historical links to other rows.
            key = next((k for k in references if k in columns), None)
            if key is None: raise ValueError('unclassified table: ' + table)
            predicate = lambda r, key=key:r[key] in references[key]
        kept[table] = [r for r in rows[table] if predicate(r)]
    dst = sqlite3.connect(destination)
    try:
        src.backup(dst)
        dst.execute('PRAGMA foreign_keys=OFF')
        with dst:
            for table in tables:
                if table == 'sqlite_sequence': continue
                dst.execute('DELETE FROM "' + table + '"')
                if kept[table]:
                    dst.executemany('INSERT INTO "' + table + '" VALUES (' + ','.join('?' for _ in kept[table][0]) + ')',
                                    [tuple(r) for r in kept[table]])
        assert dst.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert not dst.execute('PRAGMA foreign_key_check').fetchall()
        def digest(records):
            raw = sorted(json.dumps(list(r), ensure_ascii=False, separators=(',',':')) for r in records)
            return hashlib.sha256('\n'.join(raw).encode()).hexdigest()
        receipt = {'project_id':project, 'tables':{}}
        for table in tables:
            actual = list(dst.execute('SELECT * FROM "' + table + '"'))
            if table != 'sqlite_sequence': assert digest(actual)==digest(kept[table]), table
            receipt['tables'][table] = {'source':len(rows[table]),'exported':len(actual),'sha256':digest(actual)}
        # Remove deleted pages from the exported database (no other-project payloads).
        dst.execute('VACUUM')
        dst.execute('PRAGMA journal_mode=DELETE')
        destination.with_suffix('.receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
        return receipt
    finally:
        dst.close()
        src.close()


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',required=True,type=Path)
    parser.add_argument('--destination',required=True,type=Path)
    parser.add_argument('--project',required=True)
    args=parser.parse_args()
    result=export(args.source,args.destination,args.project)
    print(json.dumps({'project_id':result['project_id'],'tables':len(result['tables'])}))
