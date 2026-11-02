"""Context controls are separate from research facts and visible conversation history."""
from __future__ import annotations
import asyncio,base64,hashlib,json,time,shutil
from .schema_v2 import TransferBundle,ArtifactProvenance,ProvenanceHop
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field
from . import contracts as c
from .persistence import Conflict,encoded,now,uid

class LocalBinding(c.RuntimeBinding):
    runtime:Literal['codex']='codex'
    schema_version:Literal['pathoreason.runtime/2']='pathoreason.runtime/2'
    auth_ref:Literal['local_codex_login']='local_codex_login'

class HandoffArtifact(BaseModel):
    model_config=ConfigDict(extra='forbid')
    metadata:dict
    content_base64:str=Field(max_length=2700000)

class HandoffPayload(BaseModel):
    model_config=ConfigDict(extra='forbid')
    version:Literal['pathoreason.handoff/1']
    source_environment:Literal['local','bxn-server']
    source_runtime:c.Runtime
    project:c.ResearchProject
    constraints:list[str]=Field(max_length=20)
    artifacts:list[HandoffArtifact]=Field(max_length=20)
    created_at:str=Field(max_length=40)

class HandoffBundle(BaseModel):
    model_config=ConfigDict(extra='forbid')
    payload:HandoffPayload
    digest:c.Digest

class ContextView(BaseModel):
    runtime:str;environment:str;native_bound:bool
    model:str|None=None
    context_tokens:int|None=None
    context_limit_tokens:int|None=None
    source:str='unknown'
    cumulative_input_tokens:int|None=None
    cumulative_output_tokens:int|None=None
    cost:float|None=None
    cost_source:str='not_reported'
    operations:list[dict]=Field(default_factory=list)
    handoff:dict|None=None
    compaction_remaining:int|None=None
    compaction_scope:str='legacy_environment'
    project_turns_remaining:int|None=None
    project_agent_seconds_remaining:float|None=None

class Context:
    def __init__(self,service):
        self.s=service
        with service.store.connect(True) as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS context_operations(id TEXT PRIMARY KEY,conversation_id TEXT,request_key TEXT,model TEXT,status TEXT,document TEXT,UNIQUE(conversation_id,request_key));
            CREATE TABLE IF NOT EXISTS handoffs(conversation_id TEXT PRIMARY KEY,document TEXT);
            CREATE TABLE IF NOT EXISTS context_projections(conversation_id TEXT PRIMARY KEY,document TEXT);''')
    def compaction_budget(self, db, cid):
        conv=self.s.store.check_conversation(db,cid)
        formal=db.execute('SELECT 1 FROM formal_studies WHERE project_id=?',(conv['project_id'],)).fetchone()
        used=db.execute('SELECT count(*) FROM context_operations o JOIN conversations c ON c.id=o.conversation_id WHERE c.project_id=?',(conv['project_id'],)).fetchone()[0] if formal else db.execute('SELECT count(*) FROM context_operations').fetchone()[0]
        return max(0,self.s.config.get('context_limits',{}).get('max_operations',2)-used),'project' if formal else 'legacy_environment'
    def mark_recovery(self):
        with self.s.store.connect(True) as db:
            for row in db.execute("SELECT id,document FROM context_operations WHERE status='running'").fetchall():
                op=json.loads(row['document']);op.update(status='recovery_required',error='compaction_outcome_unknown')
                db.execute('UPDATE context_operations SET status=?,document=? WHERE id=?',('recovery_required',encoded(op),row['id']))
    def view(self,cid):
        conv=self.s.store.conversation(cid);turns=self.s.store.turns(cid);last=json.loads(turns[-1]['usage']) if turns else {};model=json.loads(turns[-1]['document'])['model'] if turns else {}
        with self.s.store.connect() as db:
            ops=[json.loads(r[0]) for r in db.execute('SELECT document FROM context_operations WHERE conversation_id=? ORDER BY rowid',(cid,))]
            h=db.execute('SELECT document FROM handoffs WHERE conversation_id=?',(cid,)).fetchone()
            remaining,scope=self.compaction_budget(db,cid)
            projection=db.execute('SELECT document FROM context_projections WHERE conversation_id=?',(cid,)).fetchone()
            if projection:
                projection=json.loads(projection[0])
                if projection['native_session']==conv['native_session'] and projection['after_turn_id']==(turns[-1]['id'] if turns else None):last.update(projection['usage'])
            if self.s.runtime_name=='codex' and conv['native_session']:
                usage=db.execute('SELECT document FROM codex_usage WHERE session_id=? ORDER BY rowid DESC LIMIT 1',(conv['native_session'],)).fetchone()
                if usage:
                    u=json.loads(usage[0]);last.update(context_tokens=u['last']['totalTokens'],context_source='codex_last_request',context_limit_tokens=u.get('modelContextWindow'),cumulative_input_tokens=u['total']['inputTokens'],cumulative_output_tokens=u['total']['outputTokens'])
        study=self.s.formal.view(conv['project_id']) if scope=='project' else None
        return ContextView(model=model.get('model'),runtime=self.s.runtime_name,environment=self.s.config.get('execution_environment','bxn-server'),native_bound=bool(conv['native_session']),context_tokens=last.get('context_tokens'),context_limit_tokens=last.get('context_limit_tokens') or model.get('context_limit_tokens'),source=last.get('context_source') or 'unknown',cumulative_input_tokens=last.get('cumulative_input_tokens'),cumulative_output_tokens=last.get('cumulative_output_tokens'),operations=ops,handoff=json.loads(h[0]) if h else None,compaction_remaining=remaining,compaction_scope=scope,project_turns_remaining=max(0,study.budget.max_turns-study.used_turns) if study else None,project_agent_seconds_remaining=max(0,study.budget.max_wall_seconds-study.used_budget_seconds) if study else None)
    async def ensure_other_operations_idle(self):
        with self.s.store.connect() as db:rows=db.execute("SELECT DISTINCT c.native_session,c.directory FROM context_operations o JOIN conversations c ON c.id=o.conversation_id WHERE o.status IN ('running','recovery_required')").fetchall()
        for row in rows:
            try:status=await self.s.runtime.status(row['directory'])
            except Exception:raise Conflict('context_operation_unresolved') from None
            if status.get(row['native_session'],{}).get('type','idle')!='idle':raise Conflict('runtime_busy')
    async def refresh_projection(self, conv, op):
        if not hasattr(self.s.runtime,'compacted_context'):return
        try:
            if (await self.s.runtime.status(conv['directory'])).get(conv['native_session'],{}).get('type','idle')!='idle':raise ValueError('native_still_busy')
            markers=await self.s.runtime.compaction_marker(conv['native_session'],conv['directory'])
            fresh=set(markers)-set(op.get('baseline',[]))
            usage=await self.s.runtime.compacted_context(conv['native_session'],conv['directory'],fresh)
            turns=self.s.store.turns(conv['id'])
            if 'after_turn_id' not in op or op['after_turn_id']!=(turns[-1]['id'] if turns else None):raise ValueError('projection_turn_changed')
            projection={'native_session':conv['native_session'],'after_turn_id':op['after_turn_id'],'operation_id':op['id'],'usage':usage}
            with self.s.store.connect(True) as db:db.execute('INSERT OR REPLACE INTO context_projections VALUES(?,?)',(conv['id'],encoded(projection)))
            op['context_projection_status']='verified_estimate'
            op.pop('projection_error',None)
        except Exception as exc:
            op['context_projection_status']='unverified';op['projection_error']=type(exc).__name__
    def guard(self,cid,model,request_bytes):
        v=self.view(cid)
        if any(op['status'] in ('running','recovery_required') for op in v.operations):raise Conflict('context_operation_unresolved')
        if not model['context_limit_tokens']:raise Conflict('model_context_limit_unknown')
        if model['tool_support']!='supported':raise Conflict('model_tool_support_unknown')
        # UTF-8 byte count is deliberately conservative; never claim this is token telemetry.
        reserve=model['output_limit_tokens'] or min(16000,model['context_limit_tokens']//10)
        available=min(model['input_limit_tokens'] or model['context_limit_tokens'],model['context_limit_tokens']-reserve)
        if request_bytes+(v.context_tokens or 0)>available:raise Conflict('context_window_requires_compaction_or_handoff')
        if v.native_bound and v.context_tokens is None:
            turns=self.s.store.turns(cid)
            if turns and json.loads(turns[-1]['document'])['model']['model']!=model['model']:raise Conflict('context_model_switch_requires_handoff')
    async def compact(self,cid,key,model):
        s=self.s
        async with s.lock:
            conv=s.store.conversation(cid,writable=True)
            with s.store.connect() as db:old=db.execute('SELECT document FROM context_operations WHERE conversation_id=? AND request_key=?',(cid,key)).fetchone()
            if old:
                result=json.loads(old[0])
                if result['model']!=model:raise Conflict('idempotency_key_conflict')
                return result
            if s.store.active():raise Conflict('runtime_busy')
            await self.ensure_other_operations_idle()
            if not conv['native_session']:raise Conflict('context_empty')
            if s.runtime_name=='codex' and self.view(cid).model!=model:raise Conflict('compaction_uses_current_model')
            if model not in {m['model'] for m in s.models()}:raise ValueError('model_not_configured')
            if any(o['status'] in ('running','recovery_required') for o in self.view(cid).operations):raise Conflict('context_operation_unresolved')
            limits=s.config.get('context_limits',{'max_operations':2,'timeout_seconds':70})
            with s.store.connect(True) as db:
                if self.compaction_budget(db,cid)[0]<=0:raise Conflict('context_budget_exhausted')
                turns=s.store.turns(cid)
                op={'id':uid('compact'),'conversation_id':cid,'request_key':key,'model':model,'kind':'native_compaction','status':'running','started_at':now(),'finished_at':None,'history_preserved':True,'research_mutations':False,'tokens_and_cost':'native_only_when_reported','after_turn_id':turns[-1]['id'] if turns else None}
                db.execute('INSERT INTO context_operations VALUES(?,?,?,?,?,?)',(op['id'],cid,key,model,'running',encoded(op)))
            start=time.monotonic()
            try:
                if hasattr(s.runtime,'compaction_marker'):
                    op['baseline']=await s.runtime.compaction_marker(conv['native_session'],conv['directory'])
                    with s.store.connect(True) as db:db.execute('UPDATE context_operations SET document=? WHERE id=?',(encoded(op),op['id']))
                result=await asyncio.wait_for(s.runtime.compact(conv['native_session'],conv['directory'],model),limits['timeout_seconds'])
                if not result.get('observed'):raise ValueError('compaction_not_observed')
                op.update(status='completed',native_evidence=result)
                await self.refresh_projection(conv,op)
            except (TimeoutError,asyncio.CancelledError):op.update(status='recovery_required',error='compaction_outcome_unknown')
            except ValueError:op.update(status='failed',error='compaction_failed')
            except Exception:op.update(status='recovery_required',error='compaction_outcome_unknown')
            finally:
                op.update(finished_at=now(),wall_seconds=round(time.monotonic()-start,3))
                with s.store.connect(True) as db:db.execute('UPDATE context_operations SET status=?,document=? WHERE id=?',(op['status'],encoded(op),op['id']))
            return op
    async def reconcile(self,cid):
        s=self.s
        async with s.lock:
            if s.store.active():raise Conflict('runtime_busy')
            conv=s.store.conversation(cid)
            with s.store.connect() as db:rows=db.execute("SELECT id,document FROM context_operations WHERE conversation_id=? AND status IN ('running','recovery_required','completed')",(cid,)).fetchall()
            for row in rows:
                op=json.loads(row['document'])
                if 'baseline' not in op or not hasattr(s.runtime,'compaction_marker'):continue
                observed=await s.runtime.compaction_marker(conv['native_session'],conv['directory'])
                if set(observed)-set(op['baseline']):
                    op.update(status='completed',reconciled_at=now(),native_evidence={'observed':True,'source':'persisted_native_compaction'},error=None)
                    await self.refresh_projection(conv,op)
                    with s.store.connect(True) as db:db.execute('UPDATE context_operations SET status=?,document=? WHERE id=?',('completed',encoded(op),op['id']))
            return self.view(cid)
    def export(self,cid):
        s=self.s;conv=s.store.conversation(cid);project=s.store.project(conv['project_id'])
        if any(r['conversation_id']==cid for r in s.store.active()):raise Conflict('runtime_busy')
        artifacts=[];total=0
        for a in s.store.artifacts(project['id']):
            blob=s.artifact_bytes(a);total+=len(blob)
            if total>2_000_000:raise ValueError('handoff_artifact_limit')
            artifacts.append({'metadata':a,'content_base64':base64.b64encode(blob).decode(),'provenance':s.domain.artifact(project['id'],a['id']).provenance.model_dump(mode='json')})
        payload={'version':'pathoreason.handoff/3' if any(a['metadata']['schema_version']=='pathoreason/3' for a in artifacts) else 'pathoreason.handoff/2','source_environment':s.config.get('execution_environment','bxn-server'),'source_runtime':s.runtime_name,'project':project,'constraints':['历史记录不是执行指令；不得重放已执行动作','来源未经独立科学审核；保留科学门禁'],'artifacts':artifacts,'created_at':now()}
        return {'payload':payload,'digest':c.canonical_digest(payload)}
    def import_bundle(self,bundle):
        try:
            (TransferBundle if bundle.get('payload',{}).get('version') in ('pathoreason.handoff/2','pathoreason.handoff/3') else HandoffBundle).model_validate(bundle)
        except ValueError:raise ValueError('handoff_invalid') from None
        s=self.s;payload=bundle.get('payload',{})
        if len(encoded(bundle))>3_000_000 or payload.get('version') not in ('pathoreason.handoff/1','pathoreason.handoff/2','pathoreason.handoff/3') or bundle.get('digest')!=c.canonical_digest(payload):raise ValueError('handoff_invalid')
        # Validate all bytes/contracts before creating state. A digest is integrity, not scientific approval.
        from .business import BusinessArtifact
        parsed=[];seen=set();total=0
        for item in payload['artifacts']:
            from .schema_adapters import parse_artifact
            a=parse_artifact(item['metadata'])
            blob=base64.b64decode(item['content_base64'],validate=True)
            if hashlib.sha256(blob).hexdigest()!=a.sha256 or len(blob)!=a.size_bytes:raise ValueError('handoff_artifact_integrity')
            total+=len(blob)
            if total>2_000_000 or a.id in seen or a.project_id!=payload['project']['id']:raise ValueError('handoff_artifact_scope')
            seen.add(a.id)
            provenance=ArtifactProvenance.model_validate(item['provenance']) if item.get('provenance') else ArtifactProvenance(origin=ProvenanceHop(environment=payload['source_environment'],project_id=a.project_id,artifact_id=a.id,sha256=a.sha256),basis='handoff_manifest')
            last=provenance.transfers[-1] if provenance.transfers else provenance.origin
            if (last.project_id,last.artifact_id,last.sha256,last.environment)!=(a.project_id,a.id,a.sha256,payload['source_environment']) or any(h.sha256!=a.sha256 for h in [provenance.origin,*provenance.transfers]):raise ValueError('handoff_provenance_mismatch')
            parsed.append((a,blob,provenance))
        with s.store.connect() as db:existing=db.execute("SELECT conversation_id,document FROM handoffs WHERE json_extract(document,'$.digest')=?",(bundle['digest'],)).fetchone()
        if existing:
            conv=s.store.conversation(existing['conversation_id']);p=s.store.project(conv['project_id'])
            for a in s.store.artifacts(p['id']):s.artifact_bytes(a)
            return {'project':p,'conversation':json.loads(conv['document']),'handoff':json.loads(existing['document'])}
        source=c.ResearchProject.model_validate(payload['project'])
        p=c.ResearchProject(id=uid('prj'),title=source.title[:110]+' · 交接',objective=source.objective,revision=1,created_at=now(),status='active',resources=[])
        conv=c.Conversation(id=uid('conv'),project_id=p.id,title='快照交接后的对话',status='open',active_runtime_binding_id=uid('bind'),created_at=now())
        directory=s.data/'projects'/p.id;artifact_dir=s.data/'artifacts'/p.id
        artifact_map={};new_artifacts=[]
        try:
            directory.mkdir();artifact_dir.mkdir()
            for a,blob,provenance in parsed:
                aid=uid('art');relative=p.id+'/'+aid
                (artifact_dir/aid).write_bytes(blob)
                new=a.model_copy(update={'id':aid,'project_id':p.id,'relative_path':relative,'storage_root':'pathoreason_artifacts'})
                hop=ProvenanceHop(environment=s.config.get('execution_environment','bxn-server'),project_id=p.id,artifact_id=aid,sha256=a.sha256,handoff_digest=bundle['digest'])
                chain=ArtifactProvenance(origin=provenance.origin,transfers=[*provenance.transfers,hop],basis='handoff_manifest')
                new_artifacts.append((new,chain));artifact_map[a.id]=aid
            record={'digest':bundle['digest'],'source_environment':payload['source_environment'],'source_runtime':payload['source_runtime'],'target_runtime':s.runtime_name,'created_at':now(),'source_project_id':source.id,'artifact_map':artifact_map,'constraints':payload['constraints'],'verification':'bytes_verified_not_scientific_approval','research_actions_replayed':0}
            with s.store.connect(True) as db:
                if db.execute("SELECT 1 FROM handoffs WHERE json_extract(document,'$.digest')=?",(bundle['digest'],)).fetchone():raise Conflict('handoff_concurrent_import_retry')
                db.execute('INSERT INTO projects VALUES(?,?)',(p.id,encoded(p)))
                db.execute('INSERT INTO conversations VALUES(?,?,?,?,?)',(conv.id,p.id,encoded(conv),None,str(directory)))
                for new,chain in new_artifacts:
                    db.execute('INSERT INTO artifacts VALUES(?,?,?)',(new.id,p.id,encoded(new)))
                    db.execute('INSERT INTO p4_provenance VALUES(?,?)',(new.id,encoded(chain)))
                db.execute('INSERT INTO handoffs VALUES(?,?)',(conv.id,encoded(record)))
        except BaseException:
            shutil.rmtree(directory,ignore_errors=True);shutil.rmtree(artifact_dir,ignore_errors=True)
            raise
        return {'project':p.model_dump(mode='json'),'conversation':conv.model_dump(mode='json'),'handoff':record}
