from __future__ import annotations
import json, sqlite3, uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from .contracts import ResearchProject, Conversation, RuntimeEvent, RuntimePayload

ACTIVE=("queued","running","interrupt_requested","recovery_required")
def now():return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
def uid(prefix):return prefix+"_"+uuid.uuid4().hex

def encoded(value):
    if hasattr(value,"model_dump"):value=value.model_dump(mode="json")
    return json.dumps(value,ensure_ascii=False,separators=(",",":"))

class Conflict(Exception):pass
class Missing(Exception):pass
class Gone(Exception):pass

class Store:
    def __init__(self,path:Path):
        self.path=path;path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
            CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY);
            INSERT OR IGNORE INTO schema_migrations VALUES(1);
            CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY,document TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS conversations(id TEXT PRIMARY KEY,project_id TEXT NOT NULL REFERENCES projects(id),document TEXT NOT NULL,native_session TEXT,directory TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS turns(id TEXT PRIMARY KEY,conversation_id TEXT NOT NULL REFERENCES conversations(id),project_id TEXT NOT NULL REFERENCES projects(id),request_key TEXT NOT NULL,input_digest TEXT NOT NULL,status TEXT NOT NULL,document TEXT NOT NULL,user_text TEXT NOT NULL,text TEXT NOT NULL DEFAULT '',tools TEXT NOT NULL DEFAULT '[]',usage TEXT NOT NULL DEFAULT '{}',artifact_ids TEXT NOT NULL,skill_digest TEXT,native_message_id TEXT NOT NULL,dispatch_state TEXT NOT NULL DEFAULT 'pending',report_id TEXT,created_at TEXT NOT NULL,UNIQUE(conversation_id,request_key));
            CREATE UNIQUE INDEX IF NOT EXISTS one_active_turn ON turns(conversation_id) WHERE status IN ('queued','running','interrupt_requested','recovery_required');
            CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT,conversation_id TEXT NOT NULL REFERENCES conversations(id),seq INTEGER NOT NULL,document TEXT NOT NULL,UNIQUE(conversation_id,seq));
            CREATE TABLE IF NOT EXISTS artifacts(id TEXT PRIMARY KEY,project_id TEXT NOT NULL REFERENCES projects(id),document TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS bindings(id TEXT PRIMARY KEY,conversation_id TEXT NOT NULL UNIQUE REFERENCES conversations(id),document TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS context_snapshots(turn_id TEXT PRIMARY KEY REFERENCES turns(id),document TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS runtime_configs(digest TEXT PRIMARY KEY,document TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS skill_invocations(turn_id TEXT PRIMARY KEY REFERENCES turns(id),document TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS conversation_deletions(conversation_id TEXT PRIMARY KEY REFERENCES conversations(id),state TEXT NOT NULL,document TEXT NOT NULL);
            """)
    @contextmanager
    def connect(self,write=False):
        db=sqlite3.connect(self.path,timeout=20);db.row_factory=sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON");db.execute("PRAGMA busy_timeout=20000")
        try:
            if write:db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except Exception:db.rollback();raise
        finally:db.close()
    def project(self,pid):
        with self.connect() as db:row=db.execute("SELECT document FROM projects WHERE id=?",(pid,)).fetchone()
        if not row:raise Missing("project_not_found")
        return json.loads(row[0])
    def projects(self):
        with self.connect() as db:return [json.loads(r[0]) for r in db.execute("SELECT document FROM projects ORDER BY rowid")]
    def create_project(self,title,objective,resources=(),project_id=None):
        p=ResearchProject(id=project_id or uid("prj"),title=title,objective=objective,revision=1,created_at=now(),status="active",resources=list(resources))
        with self.connect(True) as db:db.execute("INSERT INTO projects VALUES(?,?)",(p.id,encoded(p)))
        return p.model_dump(mode="json")
    def create_conversation(self,pid,title,directory):
        self.project(pid);cid=uid("conv")
        c=Conversation(id=cid,project_id=pid,title=title,status="open",active_runtime_binding_id=uid("bind"),created_at=now())
        with self.connect(True) as db:db.execute("INSERT INTO conversations VALUES(?,?,?,?,?)",(cid,pid,encoded(c),None,str(directory)))
        return c.model_dump(mode="json")
    def check_conversation(self,db,cid,*,writable=False,include_removed=False):
        row=db.execute('SELECT * FROM conversations WHERE id=?',(cid,)).fetchone()
        if not row:raise Missing('conversation_not_found')
        removed=db.execute('SELECT state FROM conversation_deletions WHERE conversation_id=?',(cid,)).fetchone()
        if removed and not include_removed:
            if removed[0]=='deleted':raise Gone('conversation_deleted')
            raise Conflict('conversation_deletion_pending')
        if writable and json.loads(row['document'])['status']=='archived':raise Conflict('conversation_archived')
        return dict(row)
    def conversation(self,cid,*,writable=False,include_removed=False):
        with self.connect() as db:return self.check_conversation(db,cid,writable=writable,include_removed=include_removed)
    def conversations(self,pid):
        self.project(pid)
        with self.connect() as db:return [json.loads(r[0]) for r in db.execute("SELECT document FROM conversations WHERE project_id=? ORDER BY rowid DESC",(pid,))]
    def bind(self,cid,binding):
        with self.connect(True) as db:
            db.execute("UPDATE conversations SET native_session=? WHERE id=?",(binding.native_session_id,cid))
            db.execute("INSERT INTO bindings VALUES(?,?,?) ON CONFLICT(conversation_id) DO UPDATE SET document=excluded.document",(binding.id,cid,encoded(binding)))
    def artifacts(self,pid):
        self.project(pid)
        with self.connect() as db:return [json.loads(r[0]) for r in db.execute("SELECT document FROM artifacts WHERE project_id=? ORDER BY rowid DESC",(pid,))]
    def artifact(self,aid,pid):
        with self.connect() as db:row=db.execute("SELECT document FROM artifacts WHERE id=? AND project_id=?",(aid,pid)).fetchone()
        if not row:raise Missing("artifact_not_found")
        return json.loads(row[0])
    def add_artifact(self,artifact):
        with self.connect(True) as db:db.execute("INSERT OR IGNORE INTO artifacts VALUES(?,?,?)",(artifact.id,artifact.project_id,encoded(artifact)))
    def turn(self,tid):
        with self.connect() as db:row=db.execute("SELECT * FROM turns WHERE id=?",(tid,)).fetchone()
        if not row:raise Missing("turn_not_found")
        self.conversation(row['conversation_id'])
        return dict(row)
    def existing(self,cid,key,digest):
        self.conversation(cid,writable=True)
        with self.connect() as db:row=db.execute("SELECT * FROM turns WHERE conversation_id=? AND request_key=?",(cid,key)).fetchone()
        if row and row['input_digest']!=digest:raise Conflict("idempotency_key_conflict")
        return dict(row) if row else None
    def budget_rows(self,db,project_id=None):
        if project_id:return db.execute('SELECT created_at,document FROM turns WHERE project_id=?',(project_id,)).fetchall()
        has_formal=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='formal_studies'").fetchone()
        if has_formal:return db.execute('SELECT created_at,document FROM turns WHERE project_id NOT IN (SELECT project_id FROM formal_studies)').fetchall()
        return db.execute('SELECT created_at,document FROM turns').fetchall()
    def create_turn(self,turn,text,artifact_ids,skill_digest,digest,native_id,context,invocation,max_turns=12,max_wall_seconds=1200,runtime_config=None,budget_project_id=None,on_create=None):
        with self.connect(True) as db:
            self.check_conversation(db,turn.conversation_id,writable=True)
            row=db.execute("SELECT * FROM turns WHERE conversation_id=? AND request_key=?",(turn.conversation_id,turn.request_key)).fetchone()
            if row:
                if row['input_digest']!=digest:raise Conflict("idempotency_key_conflict")
                return dict(row),False
            previous=self.budget_rows(db,budget_project_id)
            if len(previous)>=max_turns:raise Conflict("acceptance_budget_exhausted")
            used=sum(max(0,(datetime.fromisoformat(json.loads(item['document']).get('finished_at') or now())-datetime.fromisoformat(item['created_at'])).total_seconds()) for item in previous)
            if used>=max_wall_seconds:raise Conflict("acceptance_budget_exhausted")
            if db.execute("SELECT 1 FROM turns WHERE status IN ('queued','running','interrupt_requested','recovery_required')").fetchone():raise Conflict("runtime_busy")
            db.execute("INSERT INTO turns(id,conversation_id,project_id,request_key,input_digest,status,document,user_text,artifact_ids,skill_digest,native_message_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",(turn.id,turn.conversation_id,turn.project_id,turn.request_key,digest,turn.status,encoded(turn),text,encoded(artifact_ids),skill_digest,native_id,now()))
            db.execute("INSERT INTO context_snapshots VALUES(?,?)",(turn.id,encoded(context)))
            if runtime_config is not None:db.execute("INSERT OR IGNORE INTO runtime_configs VALUES(?,?)",(turn.config_digest,encoded(runtime_config)))
            if invocation:db.execute("INSERT INTO skill_invocations VALUES(?,?)",(turn.id,encoded(invocation)))
            if on_create:on_create(db)
            self._event(db,turn.conversation_id,{"kind":"turn_status","turn_id":turn.id,"status":"queued"})
        return self.turn(turn.id),True
    def _event(self,db,cid,payload):
        seq=db.execute("SELECT COALESCE(MAX(seq),0)+1 FROM events WHERE conversation_id=?",(cid,)).fetchone()[0]
        row=db.execute('SELECT project_id,document FROM turns WHERE id=?',(payload['turn_id'],)).fetchone()
        turn=json.loads(row['document'])
        document=RuntimeEvent(id=uid('evt'),project_id=row['project_id'],conversation_id=cid,turn_id=payload['turn_id'],runtime_binding_id=turn['runtime_binding_id'],seq=seq,occurred_at=now(),source_event_key=payload['turn_id']+':'+str(seq),payload=RuntimePayload(kind='turn_status',turn_status=payload['status'])).model_dump(mode='json')
        db.execute("INSERT INTO events(conversation_id,seq,document) VALUES(?,?,?)",(cid,seq,encoded(document)))
    def update(self,tid,**values):
        allowed={'status','document','text','tools','usage','dispatch_state','report_id'}
        assert set(values)<=allowed
        with self.connect(True) as db:
            row=db.execute("SELECT * FROM turns WHERE id=?",(tid,)).fetchone()
            if not row:raise Missing("turn_not_found")
            self.check_conversation(db,row['conversation_id'])
            if not any(row[k]!=v for k,v in values.items()):return
            db.execute("UPDATE turns SET "+','.join(k+'=?' for k in values)+" WHERE id=?",(*values.values(),tid))
            self._event(db,row['conversation_id'],{"kind":"turn_updated","turn_id":tid,"status":values.get('status',row['status'])})
    def turns(self,cid):
        self.conversation(cid)
        with self.connect() as db:return [dict(r) for r in db.execute("SELECT * FROM turns WHERE conversation_id=? ORDER BY rowid",(cid,))]
    def active(self):
        with self.connect() as db:return [dict(r) for r in db.execute("SELECT * FROM turns WHERE status IN ('queued','running','interrupt_requested','recovery_required')")]
    def events(self,cid,after):
        self.conversation(cid)
        with self.connect() as db:return [json.loads(r[0]) for r in db.execute("SELECT document FROM events WHERE conversation_id=? AND seq>? ORDER BY seq LIMIT 100",(cid,after))]
