"""Versioned, read-only projections over pinned research evidence and platform records."""
from __future__ import annotations
import hashlib,json,re,sqlite3
from pathlib import Path
from . import contracts as c
from . import schema_adapters as a
from .schema_v2 import ArtifactRecord,ArtifactProvenance,ProvenanceHop,ProjectDomainView,LegacyHistoryEntry
from .legacy import observe_experiment,read_verified_file,_checked_path
from .persistence import Missing,Conflict,encoded

class Domain:
    def __init__(self,service):
        self.s=service
        with service.store.connect() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS p4_provenance(artifact_id TEXT PRIMARY KEY REFERENCES artifacts(id),document TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS p4_projection_batches(id TEXT PRIMARY KEY,document TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS p4_context_projections(turn_id TEXT PRIMARY KEY REFERENCES turns(id),batch_id TEXT NOT NULL REFERENCES p4_projection_batches(id),source_digest TEXT NOT NULL,document TEXT NOT NULL);''')
    def artifact(self,pid,aid):
        raw=self.s.store.artifact(aid,pid);s=self.s
        with s.store.connect() as db:
            saved=db.execute('SELECT document FROM p4_provenance WHERE artifact_id=?',(aid,)).fetchone()
            transfers=[json.loads(r[0]) for r in db.execute('SELECT h.document FROM handoffs h JOIN conversations c ON c.id=h.conversation_id WHERE c.project_id=?',(pid,))]
        hop=ProvenanceHop(environment=s.config.get('execution_environment','bxn-server'),project_id=pid,artifact_id=aid,sha256=raw['sha256'])
        provenance=ArtifactProvenance.model_validate_json(saved[0]) if saved else ArtifactProvenance(origin=hop,basis='local_record')
        if not saved:
            matches=[(h,old) for h in transfers for old,new in h['artifact_map'].items() if new==aid]
            if len(matches)>1:raise Conflict('ambiguous_artifact_provenance')
            if matches:
                h,old=matches[0]
                provenance=ArtifactProvenance(origin=ProvenanceHop(environment=h['source_environment'],project_id=h['source_project_id'],artifact_id=old,sha256=raw['sha256']),transfers=[hop.model_copy(update={'handoff_digest':h['digest']})],basis='p3_handoff_record')
        return ArtifactRecord(artifact=a.parse_artifact(raw),identity=a.artifact_identity(raw),source=a.reference(raw['source_ref']),run=a.reference(raw['run_ref'],'run') if raw.get('run_ref') else None,provenance=provenance)
    def resolve(self,pid,aid):
        matches=[]
        for item in self.s.store.artifacts(pid):
            record=self.artifact(pid,item['id'])
            if aid==item['id'] or aid in [h.artifact_id for h in [record.provenance.origin,*record.provenance.transfers]]:matches.append(record)
        if len(matches)>1:raise Conflict('ambiguous_artifact_reference')
        if not matches:raise Missing('artifact_not_found')
        return matches[0]
    def definitions(self,pid):
        project=self.s.store.project(pid);result=[]
        for ref in project['resources']:
            if ref['adapter']!='auto_research.experiment':continue
            root=Path(self.s.config.get('legacy_experiments_root','/data/bxn/auto-research/experiments'))
            observation=observe_experiment(root,ref['resource_id'])
            if observation['ref']!=ref:raise Conflict('legacy_revision_changed')
            documents={name:json.loads(read_verified_file(root,ref['resource_id']+'/'+name,digest)) for name,digest in observation['files'].items()}
            result.append(a.experiment_definition(ref['resource_id'],documents,observation['files']))
        path=self.s.data/'research'/pid/'task.json'
        if path.exists():
            root=self.s.data/'research';relative=pid+'/task.json';digest=hashlib.sha256(_checked_path(root,relative).read_bytes()).hexdigest()
            state=json.loads(read_verified_file(root,relative,digest));plan_id=state.get('plan')
            if state.get('project_id')!=pid:raise Conflict('research_project_mismatch')
            if plan_id:
                if not isinstance(plan_id,str) or not re.fullmatch('[0-9a-f]{64}',plan_id):raise ValueError('invalid_plan_reference')
                plan_rel=pid+'/plans/'+plan_id+'.json';blob=_checked_path(root,plan_rel).read_bytes();plan_hash=hashlib.sha256(blob).hexdigest()
                plan=json.loads(read_verified_file(root,plan_rel,plan_hash))
                if c.canonical_digest(plan)!=plan_id:raise Conflict('plan_revision_changed')
                read_verified_file(root,relative,digest)
                result.append(a.synthetic_definition(pid,plan,state,{'task.json':digest,'plans/'+plan_id+'.json':plan_hash}))
        return result
    def history(self,pid):
        entries=[]
        for definition in self.definitions(pid):
            if definition.source_kind!='legacy_experiment':continue
            ref=next(r for r in self.s.store.project(pid)['resources'] if r['resource_id']==definition.source_id)
            for index,raw in enumerate(definition.source_payload['state.json'].get('review_messages',[])):
                digest=c.canonical_digest(raw)
                entries.append(LegacyHistoryEntry(id='legacy_'+c.canonical_digest([pid,definition.source_id,index,digest])[:32],project_id=pid,source_kind='review',source_ref=ref,source_record_id=str(index),source_record_digest=digest,occurred_at=raw.get('submitted_at'),question=raw.get('comment',''),status=str(raw.get('decision','unknown'))))
        return entries
    def view(self,pid):
        project=self.s.store.project(pid)
        return ProjectDomainView(project_id=pid,project_revision=project['revision'],definitions=self.definitions(pid),artifact_records=[self.artifact(pid,x['id']) for x in self.s.store.artifacts(pid)],legacy_history_count=len(self.history(pid)))
    def context(self,tid):
        row=self.s.store.turn(tid);turn=json.loads(row['document'])
        with self.s.store.connect() as db:
            raw=json.loads(db.execute('SELECT document FROM context_snapshots WHERE turn_id=?',(tid,)).fetchone()[0])
            cfg=db.execute('SELECT document FROM runtime_configs WHERE digest=?',(turn['config_digest'],)).fetchone()
        frozen=json.loads(cfg[0]) if cfg else {}
        if frozen and c.canonical_digest(frozen)!=turn['config_digest']:raise Conflict('runtime_configuration_changed')
        return a.snapshot(raw,[self.s.store.artifact(aid,row['project_id']) for aid in raw['artifact_ids']],frozen.get('business_context'))
    def migrate(self,apply=False,fail_after=None):
        """Explicit additive materialization; whole batch commits or nothing changes."""
        with self.s.store.connect(True) as db:
            if db.execute("SELECT 1 FROM turns WHERE status IN ('queued','running','interrupt_requested','recovery_required')").fetchone():raise Conflict('runtime_busy')
            sources=db.execute('SELECT turn_id,document FROM context_snapshots ORDER BY turn_id').fetchall()
            rows=[(r['turn_id'],hashlib.sha256(r['document'].encode()).hexdigest(),self.context(r['turn_id'])) for r in sources]
            batch='p4_'+c.canonical_digest([(tid,sha,view.digest) for tid,sha,view in rows])[:32]
            receipt={'id':batch,'schema':'pathoreason.context/2','count':len(rows),'source_rows_unchanged':True}
            if apply:
                db.execute('INSERT OR IGNORE INTO p4_projection_batches VALUES(?,?)',(batch,encoded(receipt)))
                for index,(tid,sha,view) in enumerate(rows):
                    old=db.execute('SELECT source_digest,document FROM p4_context_projections WHERE turn_id=?',(tid,)).fetchone()
                    if old and (old['source_digest']!=sha or old['document']!=encoded(view)):raise Conflict('projection_revision_changed')
                    db.execute('INSERT OR IGNORE INTO p4_context_projections VALUES(?,?,?,?)',(tid,batch,sha,encoded(view)))
                    if fail_after is not None and index>=fail_after:raise RuntimeError('injected_migration_failure')
            return receipt|{'applied':apply}
    def rollback(self,batch):
        with self.s.store.connect(True) as db:
            db.execute('DELETE FROM p4_context_projections WHERE batch_id=?',(batch,));db.execute('DELETE FROM p4_projection_batches WHERE id=?',(batch,))
        return {'id':batch,'rolled_back':True,'source_rows_unchanged':True}


def repair_history(database,*,project_id,source_ref,owner,target):
    """Explicit, scoped read-only import projection. Never creates native conversations."""
    path=Path(database)
    if not path.is_file():return []
    rows=[]
    with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row
        for row in db.execute('SELECT id,owner,target,status,payload,answer,updated FROM jobs WHERE owner=?',(owner,)):
            if json.loads(row['target'])!=target:continue
            raw=dict(row);payload=json.loads(raw['payload']);digest=c.canonical_digest(raw)
            rows.append(LegacyHistoryEntry(id='legacy_'+c.canonical_digest([project_id,raw['id'],digest])[:32],project_id=project_id,source_kind='repair',source_ref=source_ref,source_record_id=raw['id'],source_record_digest=digest,occurred_at=str(raw['updated']) if raw['updated'] is not None else None,question=payload.get('question',''),answer=raw['answer'],status=raw['status']))
    return rows
