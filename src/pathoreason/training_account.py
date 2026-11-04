"""Durable training ledger shared by API and detached supervisors.

An experiment owns its allowance across plans, processes and retries. No turn or
Agent timing table is read or modified. Unknown attempts retain their reservation.
"""
from contextlib import contextmanager
import json,os,sqlite3,time,uuid


def identity(pid):
    try:
        fields=open('/proc/'+str(pid)+'/stat').read().rsplit(')',1)[1].split()
        return None if fields[0]=='Z' else fields[19]
    except (OSError,IndexError):return None

class TrainingAccount:
    def __init__(self,path):
        self.path=str(path)
        with self.db() as db:
            db.executescript('''
CREATE TABLE IF NOT EXISTS training_experiments(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,document TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS training_attempts(id TEXT PRIMARY KEY,experiment_id TEXT NOT NULL,unit_id TEXT NOT NULL,document TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS training_events(id INTEGER PRIMARY KEY AUTOINCREMENT,experiment_id TEXT NOT NULL,document TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS training_requests(project_id TEXT NOT NULL,key TEXT NOT NULL,digest TEXT NOT NULL,result TEXT,PRIMARY KEY(project_id,key));
CREATE TABLE IF NOT EXISTS training_environments(id TEXT NOT NULL,project_id TEXT NOT NULL,document TEXT NOT NULL,PRIMARY KEY(project_id,id));
CREATE TABLE IF NOT EXISTS training_plan_revisions(experiment_id TEXT NOT NULL,revision INTEGER NOT NULL,document TEXT NOT NULL,PRIMARY KEY(experiment_id,revision));
CREATE TABLE IF NOT EXISTS training_input_registry(project_id TEXT NOT NULL,sha256 TEXT NOT NULL,subject_id TEXT NOT NULL,PRIMARY KEY(project_id,sha256));
CREATE TABLE IF NOT EXISTS training_exposure(project_id TEXT NOT NULL,subject_id TEXT NOT NULL,document TEXT NOT NULL,PRIMARY KEY(project_id,subject_id));
''')
    @contextmanager
    def db(self):
        db=sqlite3.connect(self.path,timeout=30);db.row_factory=sqlite3.Row
        try:
            db.execute('BEGIN IMMEDIATE');yield db;db.commit()
        except BaseException:db.rollback();raise
        finally:db.close()
    def get(self,db,eid,pid=None):
        row=db.execute('SELECT project_id,document FROM training_experiments WHERE id=?',(eid,)).fetchone()
        if not row or (pid and row['project_id']!=pid):raise ValueError('training_experiment_not_found')
        return json.loads(row['document'])
    def save(self,db,doc):
        db.execute('UPDATE training_experiments SET document=? WHERE id=?',(json.dumps(doc),doc['id']))
    def event(self,db,eid,kind,**value):
        db.execute('INSERT INTO training_events(experiment_id,document) VALUES(?,?)',(eid,json.dumps({'at':time.time(),'kind':kind,**value})))
    def attempts(self,db,eid):return [json.loads(x[0]) for x in db.execute('SELECT document FROM training_attempts WHERE experiment_id=? ORDER BY rowid',(eid,))]
    def usage(self,db,eid):
        wall=gpu=0.
        for a in self.attempts(db,eid):
            elapsed=a.get('charged_seconds')
            if elapsed is None:elapsed=max(a.get('observed_seconds',0),time.monotonic()-a['started_monotonic']) if a.get('boot_id')==boot_id() else a['allowance']
            wall+=max(0,elapsed)
            if a['gpu']:gpu+=max(0,elapsed)
        return wall,gpu
    def view(self,eid,pid=None):
        with self.db() as db:
            doc=self.get(db,eid,pid);wall,gpu=self.usage(db,eid)
            return {**doc,'used_wall_seconds':wall,'used_gpu_seconds':gpu,'attempts':self.attempts(db,eid),'events':[json.loads(x[0]) for x in db.execute('SELECT document FROM training_events WHERE experiment_id=? ORDER BY id DESC LIMIT 30',(eid,))]}
    def claim(self,eid,run_id):
        with self.db() as db:
            d=self.get(db,eid)
            if d['run_id']!=run_id or d['status']!='queued':return None
            d.update(status='running',controller={'pid':os.getpid(),'identity':identity(os.getpid()),'boot_id':boot_id()},error=None)
            self.save(db,d);self.event(db,eid,'controller_started',run_id=run_id)
            return d
    def begin(self,eid,run_id,unit,output):
        with self.db() as db:
            d=self.get(db,eid)
            if d['run_id']!=run_id or d['status']!='running' or not d['authorized']:raise ValueError('training_stop_requested')
            prior=self.attempts(db,eid)
            if any(a['status']=='running' for a in prior):raise ValueError('training_attempt_still_active')
            if any(a['unit_id']==unit['id'] and a['status']=='completed' and a.get('scope_digest')==d['scope_digest'] for a in prior):return None
            count=sum(a['unit_id']==unit['id'] for a in prior)
            if count>=d['budget']['max_attempts_per_unit']:raise ValueError('training_unit_attempt_limit')
            wall,gpu=self.usage(db,eid);b=d['budget'];remaining=min(b['max_unit_seconds'],b['max_wall_seconds']-wall)
            if d['plan']['gpu_uuid']:remaining=min(remaining,b['max_gpu_seconds']-gpu)
            if remaining<=0:raise ValueError('training_budget_exhausted')
            # Fit completion is checked from authoritative attempts, never Agent prose.
            if unit['phase']=='evaluate':
                done={a['unit_id'] for a in prior if a['status']=='completed' and a.get('scope_digest')==d['scope_digest']}
                if any(u['phase']=='fit' and u['id'] not in done for u in d['plan']['units']):raise ValueError('training_complete_fit_matrix_required')
                ids=set(unit['input_ids'])
                exposed_subjects=set()
                for f in d['plan']['inputs']:
                    if f['id'] in ids and f['role']=='sealed' and f['subject_id'] not in exposed_subjects:
                        exposed_subjects.add(f['subject_id'])
                        row=db.execute('SELECT document FROM training_exposure WHERE project_id=? AND subject_id=?',(d['project_id'],f['subject_id'])).fetchone()
                        rec=json.loads(row[0]) if row else {'count':f['prior_test_exposures'],'attempts':[]}
                        if d['plan']['evaluation']=='independent_holdout':
                            own=[x for x in rec['attempts'] if x['experiment_id']==eid]
                            if rec['count']!=len(own) or any(x['unit_id']==unit['id'] for x in own):raise ValueError('training_test_already_exposed')
                        rec['count']=None if rec['count'] is None else rec['count']+1
                        rec['attempts'].append({'experiment_id':eid,'run_id':run_id,'unit_id':unit['id'],'at':time.time()})
                        db.execute('INSERT OR REPLACE INTO training_exposure VALUES(?,?,?)',(d['project_id'],f['subject_id'],json.dumps(rec)))
            a={'id':'attempt_'+uuid.uuid4().hex,'experiment_id':eid,'unit_id':unit['id'],'phase':unit['phase'],'run_id':run_id,'status':'running','allowance':remaining,'gpu':bool(d['plan']['gpu_uuid']),'started_at':time.time(),'started_monotonic':time.monotonic(),'boot_id':boot_id(),'charged_seconds':None,'observed_seconds':0.,'plan_digest':d['plan_digest'],'scope_digest':d['scope_digest'],'output':output,'error':None}
            db.execute('INSERT INTO training_attempts VALUES(?,?,?,?)',(a['id'],eid,unit['id'],json.dumps(a)));self.event(db,eid,'attempt_started',attempt_id=a['id'],unit_id=unit['id'],allowance=remaining)
            return a
    def record_launch(self,eid,aid,value):
        """Trusted pre-dispatch specification; a sandboxed task cannot write it."""
        from .training_files import digest
        with self.db() as db:
            row=db.execute('SELECT document FROM training_attempts WHERE id=? AND experiment_id=?',(aid,eid)).fetchone()
            if not row:raise ValueError('training_attempt_not_found')
            a=json.loads(row[0]);d=self.get(db,eid)
            if a['status']!='running' or d['status']!='running' or d['run_id']!=a['run_id']:raise InterruptedError('training_stop_requested')
            if 'launch_spec' in a:raise ValueError('training_launch_spec_already_recorded')
            a['launch_spec']=value
            db.execute('UPDATE training_attempts SET document=? WHERE id=?',(json.dumps(a),aid))
            self.event(db,eid,'launch_spec_recorded',attempt_id=aid,digest=digest(value))
    def finish(self,eid,aid,elapsed,status,error=None,files=None):
        with self.db() as db:
            row=db.execute('SELECT document FROM training_attempts WHERE id=? AND experiment_id=?',(aid,eid)).fetchone()
            if not row:raise ValueError('training_attempt_not_found')
            a=json.loads(row[0])
            if a['charged_seconds'] is not None:return a
            if status=='unknown':elapsed=max(elapsed,a['allowance'])
            a.update(charged_seconds=max(elapsed,a['observed_seconds']),status=status,error=error,files=files or {},finished_at=time.time())
            db.execute('UPDATE training_attempts SET document=? WHERE id=?',(json.dumps(a),aid));self.event(db,eid,'attempt_finished',attempt_id=aid,status=status,charged_seconds=a['charged_seconds'],error=error)
            return a
    def limits(self,eid,aid):
        with self.db() as db:
            d=self.get(db,eid);a=next(x for x in self.attempts(db,eid) if x['id']==aid)
            elapsed=max(0,time.monotonic()-a['started_monotonic']);wall,gpu=self.usage(db,eid);b=d['budget']
            a['observed_seconds']=max(a['observed_seconds'],elapsed)
            db.execute('UPDATE training_attempts SET document=? WHERE id=?',(json.dumps(a),aid))
            return d['status']=='running',min(a['allowance']-elapsed,b['max_wall_seconds']-wall,(b['max_gpu_seconds']-gpu) if a['gpu'] else float('inf'))
    def state(self,eid,run_id,status,error=None):
        with self.db() as db:
            d=self.get(db,eid)
            if d['run_id']!=run_id:return
            if d['status']=='cancelled':status='cancelled'
            elif d['status'] in ('stopping','stopped') and status!='completed':status='stopped'
            d.update(status=status,error=error);self.save(db,d);self.event(db,eid,'run_finished',run_id=run_id,status=status,error=error)
    def reconcile(self,eid):
        with self.db() as db:
            d=self.get(db,eid);controller=d.get('controller')
            if d['status'] not in ('queued','running','waiting_resource','stopping'):return
            alive=bool(controller and controller.get('boot_id')==boot_id() and identity(controller['pid'])==controller['identity'])
            if alive:return
            if d['status']=='queued' and time.time()-d['queued_at']<15:return
            # Revoke the run before reconciling unknown attempts. A delayed worker
            # cannot claim it; an old worker has parent-death-bound children.
            d.update(status='needs_reconciliation',error='training_controller_lost');self.save(db,d)
            for a in self.attempts(db,eid):
                if a['charged_seconds'] is None:
                    a.update(status='unknown',charged_seconds=max(a['observed_seconds'],a['allowance']),error='controller_lost')
                    db.execute('UPDATE training_attempts SET document=? WHERE id=?',(json.dumps(a),a['id']))
            self.event(db,eid,'controller_lost',run_id=d['run_id'])

def boot_id():return open('/proc/sys/kernel/random/boot_id').read().strip()
