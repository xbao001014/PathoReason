"""Project archive and resumable deletion with explicit, bounded asset ownership."""
from __future__ import annotations
import asyncio,json,os,re,shutil
from pathlib import Path
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field
from . import contracts as c
from .persistence import Conflict,encoded,now
from .training_account import boot_id,identity

class ManagedProject(c.ResearchProject):
    deletion_state:Literal['deleting','failed']|None=None
    open_conversations:int=0
    archived_conversations:int=0

class ProjectLifecycleView(BaseModel):
    project_id:str
    revision:int
    state:Literal['active','archived','deleting','failed','deleted']
    conversation_ids:list[str]=Field(default_factory=list)
    conversations_deleted:int=0
    delete_assets:bool=False
    assets_removed:bool=False
    budget_preserved:bool=True
    error_code:str|None=None
    requested_at:str|None=None
    completed_at:str|None=None

class ProjectActionInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    expected_revision:int=Field(ge=1)

class DeleteProjectInput(ProjectActionInput):
    confirm:Literal[True]
    confirmation_title:str
    delete_assets:bool

class ProjectLifecycle:
    def __init__(self,service):self.s=service

    def list(self,include_archived=False):
        with self.s.store.connect() as db:
            rows=db.execute('SELECT p.document,d.state FROM projects p LEFT JOIN project_deletions d ON d.project_id=p.id ORDER BY p.rowid').fetchall()
            counts={}
            for row in db.execute("SELECT c.project_id,c.document,d.state FROM conversations c LEFT JOIN conversation_deletions d ON d.conversation_id=c.id WHERE d.state IS NULL OR d.state<>'deleted'"):
                key='open' if row['state'] else json.loads(row['document'])['status']
                counts.setdefault(row['project_id'],{'open':0,'archived':0})[key]+=1
        result=[]
        for row in rows:
            p=json.loads(row['document'])
            if row['state']=='deleted' or (p['status']=='archived' and not include_archived and not row['state']):continue
            n=counts.get(p['id'],{'open':0,'archived':0})
            result.append(ManagedProject(**p,deletion_state=row['state'],open_conversations=n['open'],archived_conversations=n['archived']))
        return result

    def view(self,pid):
        p=self.s.store.project(pid,include_removed=True)
        with self.s.store.connect() as db:
            row=db.execute('SELECT document FROM project_deletions WHERE project_id=?',(pid,)).fetchone()
            ids=[r[0] for r in db.execute('SELECT id FROM conversations WHERE project_id=?',(pid,))]
        return ProjectLifecycleView(**json.loads(row[0])) if row else ProjectLifecycleView(project_id=pid,revision=p['revision'],state=p['status'],conversation_ids=ids)

    def _check_idle(self,db,pid):
        for row in db.execute('SELECT id FROM conversations WHERE project_id=?',(pid,)):
            self.s.conversations._check_idle(db,row[0])
        for row in db.execute('SELECT id,document FROM training_experiments WHERE project_id=?',(pid,)):
            d=json.loads(row['document']);controller=d.get('controller')
            if d['status'] in ('queued','running','waiting_resource','stopping','needs_reconciliation') or (controller and controller.get('boot_id')==boot_id() and identity(controller['pid'])==controller['identity']):raise Conflict('project_training_busy')
            for a in db.execute('SELECT document FROM training_attempts WHERE experiment_id=?',(row['id'],)):
                if json.loads(a[0]).get('status') in ('running','unknown'):raise Conflict('project_training_unresolved')
        task=self.s.data/'research'/pid/'task.json'
        if task.exists() and json.loads(task.read_text()).get('status') in ('running','needs_reconciliation'):raise Conflict('project_research_busy')
        if db.execute("SELECT 1 FROM task_code_actions WHERE project_id=? AND status IN ('running','started','pending')",(pid,)).fetchone():raise Conflict('project_research_busy')

    async def _native_idle(self,pid):
        with self.s.store.connect() as db:rows=[dict(r) for r in db.execute('SELECT * FROM conversations WHERE project_id=?',(pid,))]
        for row in rows:await self.s.conversations._native_idle(row)
        return rows

    async def archive(self,pid,body,restore=False):
        async with self.s.lock:
            p=self.s.store.project(pid)
            if p['revision']!=body.expected_revision:raise Conflict('project_changed')
            with self.s.store.connect() as db:self._check_idle(db,pid)
            await self._native_idle(pid)
            with self.s.store.connect(True) as db:
                self.s.store.check_project(db,pid)
                self._check_idle(db,pid)
                if not restore:
                    for row in db.execute('SELECT id FROM conversations WHERE project_id=?',(pid,)):self.s.goals.archive(db,row[0])
                p.update(status='active' if restore else 'archived',revision=p['revision']+1)
                db.execute('UPDATE projects SET document=? WHERE id=?',(encoded(p),pid))
            return self.view(pid)

    def _owned_paths(self,db,pid):
        if not re.fullmatch(r'[A-Za-z0-9_-]+',pid):raise Conflict('project_asset_scope_invalid')
        paths=[self.s.data/k/pid for k in ('projects','studies','research','artifacts','manuscript_reviews')]
        runs=set()
        for row in db.execute('SELECT id,document FROM training_experiments WHERE project_id=?',(pid,)):
            d=json.loads(row['document'])
            if d.get('run_id'):runs.add(d['run_id'])
            for table in ('training_attempts','training_events'):
                for a in db.execute('SELECT document FROM '+table+' WHERE experiment_id=?',(row['id'],)):
                    run=json.loads(a[0]).get('run_id')
                    if run:runs.add(run)
        for run in sorted(runs):
            if not re.fullmatch(r'train_[a-zA-Z0-9_-]+',run):raise Conflict('project_asset_scope_invalid')
            for row in db.execute('SELECT document FROM training_experiments WHERE project_id<>?',(pid,)):
                if json.loads(row[0]).get('run_id')==run:raise Conflict('project_assets_shared')
            paths.append(self.s.data/'training/runs'/run)
        for path in paths:self._safe_path(path)
        # Other projects may explicitly bind an existing project's input or output.
        def references(value):
            if isinstance(value,dict):return any(references(x) for x in value.values())
            if isinstance(value,list):return any(references(x) for x in value)
            return isinstance(value,str) and value.startswith('/') and any(Path(value).is_relative_to(p) for p in paths)
        for table in ('training_experiments','task_code_tasks'):
            for row in db.execute('SELECT document FROM '+table+' WHERE project_id<>?',(pid,)):
                if references(json.loads(row[0])):raise Conflict('project_assets_shared')
        for row in db.execute('SELECT document FROM artifacts WHERE project_id<>?',(pid,)):
            d=json.loads(row[0])
            if references(d) or (d.get('storage_root')!='legacy_evidence' and str(d.get('relative_path','')).startswith(pid+'/')):raise Conflict('project_assets_shared')
        return paths

    def _safe_path(self,path):
        root=self.s.data.absolute();path=Path(path).absolute()
        if not path.is_relative_to(root) or path==root:raise Conflict('project_asset_scope_invalid')
        for parent in [path,*path.parents]:
            if parent==root:break
            if parent.is_symlink():raise Conflict('project_asset_symlink')
        if path.exists():
            if not path.is_dir():raise Conflict('project_asset_scope_invalid')
            for current,dirs,_ in os.walk(path,followlinks=False):
                if os.path.ismount(current):raise Conflict('project_asset_mount')
        return path

    def _save(self,view,paths):
        with self.s.store.connect(True) as db:
            db.execute('INSERT INTO project_deletions VALUES(?,?,?) ON CONFLICT(project_id) DO UPDATE SET state=excluded.state,document=excluded.document',(view.project_id,view.state,encoded({**view.model_dump(),'cleanup_paths':[str(p) for p in paths]})))

    def _remove_assets(self,paths):
        for path in paths:
            path=self._safe_path(path)
            if path.exists():shutil.rmtree(path) # Linux fd-based implementation does not follow child symlinks.

    def _purge_records(self,db,pid):
        # Preserve accounting identities and amounts, not research plans, inputs,
        # source code, logs or patient-level input/exposure registries.
        for row in db.execute('SELECT id,document FROM training_experiments WHERE project_id=?',(pid,)).fetchall():
            eid=row['id'];old=json.loads(row['document'])
            keep={k:v for k,v in old.items() if k in {'id','project_id','revision','status','run_id','budget','created_at','updated_at'}}
            keep.update(authorized=False,controller=None)
            db.execute('UPDATE training_experiments SET document=? WHERE id=?',(encoded(keep),eid))
            for a in db.execute('SELECT id,document FROM training_attempts WHERE experiment_id=?',(eid,)).fetchall():
                old=json.loads(a['document'])
                keep={k:v for k,v in old.items() if k in {'id','experiment_id','unit_id','run_id','status','allowance','gpu','started_at','finished_at','started_monotonic','boot_id','charged_seconds','observed_seconds'}}
                db.execute('UPDATE training_attempts SET document=? WHERE id=?',(encoded(keep),a['id']))
            for table in ('training_events','training_plan_revisions'):
                db.execute('DELETE FROM '+table+' WHERE experiment_id=?',(eid,))
        for table in ('manuscript_workflows','manuscript_review_events','manuscript_review_commands','training_requests','training_environments','training_input_registry','training_exposure','task_code_actions','task_code_events','budget_changes'):
            db.execute('DELETE FROM '+table+' WHERE project_id=?',(pid,))
        for table in ('task_code_revisions','task_code_checks','task_code_snapshots'):
            db.execute('DELETE FROM '+table+' WHERE task_id IN (SELECT id FROM task_code_tasks WHERE project_id=?)',(pid,))
        db.execute('DELETE FROM task_code_tasks WHERE project_id=?',(pid,))
        # Membership in formal_studies keeps these turns out of the global
        # non-formal budget. Removing the row would change other projects' budget.
        row=db.execute('SELECT document FROM formal_studies WHERE project_id=?',(pid,)).fetchone()
        if row:
            old=json.loads(row[0]);keep={k:v for k,v in old.items() if k in {'project_id','budget','revision','created_at'}}
            db.execute("UPDATE formal_studies SET document=?,input_digest='' WHERE project_id=?",(encoded(keep),pid))
        for row in db.execute('SELECT revision,document FROM study_budget_revisions WHERE project_id=?',(pid,)).fetchall():
            old=json.loads(row['document']);keep={k:v for k,v in old.items() if k in {'budget','revision','at','created_at'}}
            db.execute('UPDATE study_budget_revisions SET document=? WHERE project_id=? AND revision=?',(encoded(keep),pid,row['revision']))
        for table in ('conversation_gpu_settings','handoffs'):
            db.execute('DELETE FROM '+table+' WHERE conversation_id IN (SELECT id FROM conversations WHERE project_id=?)',(pid,))
        db.execute("UPDATE conversations SET directory='' WHERE project_id=?",(pid,))

    async def delete(self,pid,body):
        async with self.s.lock:
            p=self.s.store.project(pid,include_removed=True);previous=self.view(pid)
            if previous.state=='deleted':return previous
            if body.confirmation_title!=p['title']:raise Conflict('project_title_confirmation_required')
            resuming=previous.state in ('deleting','failed')
            if resuming and body.delete_assets!=previous.delete_assets:raise Conflict('project_delete_scope_changed')
            if not resuming and body.expected_revision!=p['revision']:raise Conflict('project_changed')
            with self.s.store.connect() as db:
                self._check_idle(db,pid)
                paths=self._owned_paths(db,pid) if body.delete_assets else []
            rows=await self._native_idle(pid)
            for row in rows:
                if row['native_session'] and not hasattr(self.s.runtime,'delete_session'):raise Conflict('native_deletion_unsupported')
                if row['native_session']:
                    with self.s.store.connect() as db:
                        if db.execute('SELECT 1 FROM conversations WHERE native_session=? AND id<>?',(row['native_session'],row['id'])).fetchone():raise Conflict('native_session_shared')
            view=ProjectLifecycleView(project_id=pid,revision=p['revision'] if resuming else p['revision']+1,state='deleting',conversation_ids=[r['id'] for r in rows],delete_assets=body.delete_assets,requested_at=previous.requested_at or now())
            with self.s.store.connect(True) as db:
                self._check_idle(db,pid)
                p.update(status='archived',revision=view.revision)
                db.execute('UPDATE projects SET document=? WHERE id=?',(encoded(p),pid))
                for row in rows:self.s.goals.archive(db,row['id'])
                db.execute('INSERT INTO project_deletions VALUES(?,?,?) ON CONFLICT(project_id) DO UPDATE SET state=excluded.state,document=excluded.document',(pid,'deleting',encoded({**view.model_dump(),'cleanup_paths':[str(p) for p in paths]})))
            try:
                for row in rows:
                    result=await self.s.conversations._delete_locked(row['id'])
                    if result.state!='deleted':raise Conflict(result.error_code or 'project_cleanup_incomplete')
                    view.conversations_deleted+=1;self._save(view,paths)
                if body.delete_assets:
                    self._remove_assets(paths);view.assets_removed=True
                with self.s.store.connect(True) as db:
                    # Delete public asset indexes and conversational stage summaries.
                    self._purge_records(db,pid)
                    db.execute('DELETE FROM p4_provenance WHERE artifact_id IN (SELECT id FROM artifacts WHERE project_id=?)',(pid,))
                    db.execute('DELETE FROM artifacts WHERE project_id=?',(pid,))
                    db.execute('DELETE FROM research_stage_events WHERE project_id=?',(pid,))
                    db.execute('DELETE FROM research_workflows WHERE project_id=?',(pid,))
                    db.execute('DELETE FROM research_stage_transfers WHERE source_conversation IN (SELECT id FROM conversations WHERE project_id=?)',(pid,))
                    p.update(title='已删除项目',objective='已删除',resources=[])
                    db.execute('UPDATE projects SET document=? WHERE id=?',(encoded(p),pid))
                    view.state='deleted';view.completed_at=now();view.error_code=None
                    db.execute('UPDATE project_deletions SET state=?,document=? WHERE project_id=?',(view.state,encoded(view),pid))
            except asyncio.CancelledError:raise
            except Exception as exc:
                view.state='failed';view.error_code=str(exc) if isinstance(exc,Conflict) else 'project_cleanup_incomplete';self._save(view,paths)
            return self.view(pid)
