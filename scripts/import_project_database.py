"""Add an exported project's rows to an OFFLINE database, without replacing rows.

Export first with export_client_database.py. Rehearse on a backup, stop the
target application, and check native/research activity before using --apply.
This command does not copy artifacts or native sessions; verify those separately.
"""
import argparse
import json
import sqlite3
from pathlib import Path


def merge(source, destination, project, apply=False):
    source, destination = Path(source), Path(destination)
    if source.resolve() == destination.resolve() or not destination.is_file():
        raise ValueError('invalid destination')
    with sqlite3.connect(source.resolve().as_uri()+'?mode=ro',uri=True) as src, \
            sqlite3.connect(destination.resolve().as_uri()+'?mode=rw',uri=True) as dst:
        src.row_factory=sqlite3.Row
        if [r[0] for r in src.execute('SELECT id FROM projects')] != [project]:
            raise ValueError('source must contain exactly the selected project')
        for db in (src,dst):
            if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or db.execute('PRAGMA foreign_key_check').fetchall():
                raise ValueError('invalid database')
            if db.execute("SELECT 1 FROM turns WHERE status IN ('queued','running','interrupt_requested','recovery_required') LIMIT 1").fetchone():
                raise ValueError('active turns must be resolved first')
        def schema(db):
            return {r[0]:r[1] for r in db.execute("SELECT name,sql FROM sqlite_master WHERE type IN ('table','index','trigger','view') AND sql IS NOT NULL")}
        if schema(src)!=schema(dst):raise ValueError('schema mismatch')
        tables=[r[0] for r in src.execute("SELECT name FROM sqlite_master WHERE type='table' AND name<>'sqlite_sequence'")]
        receipt={'project_id':project,'applied':apply,'tables':{}}
        dst.execute('PRAGMA foreign_keys=ON')
        dst.execute('BEGIN IMMEDIATE')
        dst.execute('PRAGMA defer_foreign_keys=ON')
        try:
            for table in tables:
                columns=list(src.execute('PRAGMA table_info("'+table+'")'))
                keys=[r[1] for r in sorted(columns,key=lambda r:r[5]) if r[5]]
                if not keys:raise ValueError('table lacks primary key: '+table)
                added=shared=0
                for row in src.execute('SELECT * FROM "'+table+'"'):
                    where=' AND '.join('"'+key+'"=?' for key in keys)
                    existing=dst.execute('SELECT * FROM "'+table+'" WHERE '+where,tuple(row[key] for key in keys)).fetchone()
                    if existing is not None:
                        if tuple(existing)!=tuple(row):raise ValueError('conflicting existing row: '+table)
                        shared+=1
                    else:
                        dst.execute('INSERT INTO "'+table+'" VALUES ('+','.join('?' for _ in row)+')',tuple(row));added+=1
                receipt['tables'][table]={'added':added,'identical_existing':shared}
            if dst.execute('PRAGMA foreign_key_check').fetchall():raise ValueError('foreign key mismatch')
            if dst.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('integrity mismatch')
            if apply:dst.commit()
            else:dst.rollback()
        except BaseException:
            dst.rollback();raise
        return receipt


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--destination',type=Path,required=True)
    parser.add_argument('--project',required=True)
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--receipt',type=Path,required=True)
    args=parser.parse_args()
    # Reserve the new receipt before any database write; never overwrite an audit.
    with args.receipt.open('x') as output:
        result=merge(args.source,args.destination,args.project,args.apply)
        json.dump(result,output,indent=2);output.write('\n')
    print(json.dumps({'project':args.project,'applied':args.apply,'added_rows':sum(t['added'] for t in result['tables'].values())}))
