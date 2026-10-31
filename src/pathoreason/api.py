from __future__ import annotations
import asyncio,json,fcntl,os,hmac
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit
from fastapi import FastAPI,HTTPException,Request
from fastapi.responses import JSONResponse,Response,StreamingResponse,FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel,ConfigDict,Field
from .settings import ROOT,settings,credential
from .service import Service,NotReady
from .persistence import Conflict,Missing,Gone,encoded
from .conversation_lifecycle import ManagedConversation,ConversationLifecycleView,DeleteConversationInput
from .codex_auth import CodexAuth
from . import contracts as c
from .context import ContextView,HandoffBundle
from .formal_contracts import FormalArtifact
from .formal import StudyCreate,StudyView,EntryStatus,NativePermission,PermissionReply
from .permission_settings import PermissionSettingsView,PermissionSettingsUpdate
from .schema_v2 import ProjectDomainView,ArtifactRecord,ContextSnapshotV2,LegacyHistoryEntry,TransferBundle,RuntimeConfiguration
from .business import BusinessRequest,BusinessView,BusinessArtifact
from typing import Literal

class ProjectInput(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    title:str=Field(min_length=1,max_length=120)
    objective:str=Field(min_length=1,max_length=4000)
class ConversationInput(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    title:str=Field(default='新的研究对话',min_length=1,max_length=120)
from .reasoning import ReasoningEffort,ReasoningOptions

class TurnInput(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    request_key:c.Identifier
    text:str=Field(min_length=1,max_length=16000)
    model:str=Field(default='deepseek-v4-pro',max_length=100)
    reasoning_effort:ReasoningEffort|None=None
    skill_id:str|None=None
    execution_mode:Literal['discuss','synthetic','research']='discuss'
    artifact_ids:list[c.Identifier]=Field(default_factory=list,max_length=20)
class ToolSummary(BaseModel):
    id:str;name:str;status:str
    summary:str|None=None
    duration_ms:int|None=Field(default=None,ge=0)
class Usage(BaseModel):
    activity_phase:Literal['waiting','thinking','tool','responding']|None=None
    input_tokens:int|None=None
    output_tokens:int|None=None
    context_tokens:int|None=None
    context_limit_tokens:int|None=None
    context_source:str|None=None
    source:str|None=None
    scope:str|None=None
    compaction_observed:bool=False
    cumulative_input_tokens:int|None=None
    cumulative_output_tokens:int|None=None
    cached_input_tokens:int|None=None
    cost:float|None=None
class TurnView(BaseModel):
    turn:c.Turn
    reasoning_effort:ReasoningEffort|None=None
    user_text:str
    text:str
    tools:list[ToolSummary]
    usage:Usage
    artifact_ids:list[str]
    report_id:str|None
class ConversationView(BaseModel):
    context:ContextView|None=None
    conversation:c.Conversation
    turns:list[TurnView]

class SkillStage(BaseModel):
    id:str;title:str;description:str;skill_ids:list[str];cross_stage:bool=False
class SkillCategory(BaseModel):
    id:str;title:str;description:str;stages:list[SkillStage]

class Fact(BaseModel):
    label:str;value:str
class StageView(BaseModel):
    id:str;title:str;kind:str;current:bool
class WorkbenchView(BaseModel):
    project_id:str;facts:list[Fact];stages:list[StageView];stage_note:str
class CompactionView(BaseModel):
    auto:bool;prune:bool;reserved_tokens:int
class RuntimeStatus(BaseModel):
    environment:str="bxn-server"
    business_enabled:bool=True
    runtime:str;version:str|None=None;connected:bool;credential_present:bool;model:str;readiness:str;compaction:CompactionView;inference_verified:bool;codex_server_inference_enabled:bool
class AuthStatus(BaseModel):
    state:str;account_type:str|None=None;server_inference_enabled:bool=False;login_id:str|None=None;verification_url:str|None=None;user_code:str|None=None;message:str|None=None

@asynccontextmanager
async def lifespan(app):
    cfg=settings();lock_path=Path(cfg['data_root'])/'runtime/control/app.lock';lock_path.parent.mkdir(parents=True,exist_ok=True)
    with lock_path.open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        app.state.service=Service();app.state.service.seed();app.state.auth=CodexAuth(cfg['codex_binary'])
        if cfg.get('primary_runtime')=='codex':
            try:await app.state.service.runtime.health()
            except Exception:pass
        await app.state.service.recover()
        yield
        await app.state.service.close();await app.state.auth.close()

app=FastAPI(title='PathoReason',version='0.6.5',lifespan=lifespan)
def service():return app.state.service

@app.middleware('http')
async def security(request,call_next):
    host=request.headers.get('host','').split(':')[0]
    if host not in ('127.0.0.1','localhost','testserver'):return JSONResponse({'detail':'host_not_allowed'},status_code=403)
    origin=request.headers.get('origin')
    if request.method not in ('GET','HEAD','OPTIONS') and origin and urlsplit(origin).netloc!=request.headers.get('host'):
        return JSONResponse({'detail':'origin_not_allowed'},status_code=403)
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff';response.headers['Referrer-Policy']='same-origin'
    return response

@app.exception_handler(Missing)
async def missing(_,exc):return JSONResponse({'detail':str(exc)},status_code=404)
@app.exception_handler(Gone)
async def gone(_,exc):return JSONResponse({'detail':str(exc)},status_code=410)
@app.exception_handler(Conflict)
async def conflict(_,exc):return JSONResponse({'detail':str(exc)},status_code=409)
@app.exception_handler(NotReady)
async def not_ready(_,exc):return JSONResponse({'detail':str(exc)},status_code=503)
@app.exception_handler(ValueError)
async def bad_input(_,exc):return JSONResponse({'detail':str(exc)},status_code=422)


@app.get('/api/v1/research-projects/{pid}/business',response_model=BusinessView)
async def business_view(pid:str):
    if not service().config.get('business_enabled',True):
        service().store.project(pid)
        return BusinessView(project_id=pid,status='unavailable',revision='0'*64,error_type='business_environment_unavailable')
    return await asyncio.to_thread(service().business.inspect,pid)

@app.post('/internal/business',response_model=BusinessView,include_in_schema=False)
async def business_call(body:BusinessRequest,request:Request):
    if not service().config.get('business_enabled',True):raise HTTPException(403,'business_environment_unavailable')
    expected='Bearer '+service().business.token()
    if not hmac.compare_digest(request.headers.get('authorization',''),expected):raise HTTPException(403,'business_bridge_auth_required')
    return await asyncio.to_thread(service().business.call,body)

@app.get('/health')
async def health():return {'status':'ok','name':'PathoReason','phase':'P5-entry','release':'0.6.6-p5-benchmark'}
@app.get('/api/v1/research-projects',response_model=list[c.ResearchProject])
async def projects():return service().store.projects()
@app.post('/api/v1/research-projects',response_model=c.ResearchProject,status_code=201)
async def create_project(body:ProjectInput):return service().store.create_project(body.title,body.objective)
@app.get('/api/v1/research-projects/{pid}/conversations',response_model=list[ManagedConversation])
async def conversations(pid:str,include_archived:bool=False):return service().conversations.list(pid,include_archived)
@app.post('/api/v1/research-projects/{pid}/conversations',response_model=c.Conversation,status_code=201)
async def create_conversation(pid:str,body:ConversationInput):return service().new_conversation(pid,body.title)
@app.get('/api/v1/conversations/{cid}/lifecycle',response_model=ConversationLifecycleView)
async def conversation_lifecycle(cid:str):return service().conversations.view(cid)
@app.post('/api/v1/conversations/{cid}/archive',response_model=ConversationLifecycleView)
async def archive_conversation(cid:str):return await service().conversations.archive(cid)
@app.post('/api/v1/conversations/{cid}/restore',response_model=ConversationLifecycleView)
async def restore_conversation(cid:str):return await service().conversations.archive(cid,restore=True)
@app.delete('/api/v1/conversations/{cid}',response_model=ConversationLifecycleView)
async def delete_conversation(cid:str,body:DeleteConversationInput):return await service().conversations.delete(cid)
@app.post('/api/v1/conversations/{cid}/deletion/reconcile',response_model=ConversationLifecycleView)
async def reconcile_conversation_deletion(cid:str,body:DeleteConversationInput):return await service().conversations.delete(cid)
@app.get('/api/v1/conversations/{cid}',response_model=ConversationView)
async def conversation(cid:str):
    row=service().store.conversation(cid)
    return {'context':service().context.view(cid),'conversation':json.loads(row['document']),'turns':[service().view(r) for r in service().store.turns(cid)]}
@app.post('/api/v1/conversations/{cid}/turns',response_model=TurnView,status_code=202)
async def submit(cid:str,body:TurnInput):return await service().submit(cid,body.model_dump(exclude={'reasoning_effort'} if body.reasoning_effort is None else set()))
@app.post('/api/v1/turns/{tid}/interrupt',response_model=TurnView)
async def interrupt(tid:str):return await service().interrupt(tid)
@app.post('/api/v1/turns/{tid}/reconcile',response_model=TurnView)
async def reconcile(tid:str):
    row=service().store.turn(tid)
    if row['status']=='recovery_required':service().schedule(tid)
    return service().view(row)
@app.get('/api/v1/conversations/{cid}/events')
async def events(cid:str,request:Request,after:int=0):
    service().store.conversation(cid)
    try:header_cursor=int(request.headers.get('last-event-id','0'))
    except ValueError:raise HTTPException(400,'invalid_event_cursor')
    if after<0 or header_cursor<0:raise HTTPException(400,'invalid_event_cursor')
    cursor=max(after,header_cursor)
    async def stream():
        nonlocal cursor
        ticks=0
        while not await request.is_disconnected():
            try:batch=service().store.events(cid,cursor)
            except (Gone,Conflict):return
            for event in batch:
                cursor=event['seq'];yield f'id: {cursor}\ndata: {encoded(event)}\n\n'
            ticks+=1
            if ticks%30==0:yield ': keepalive\n\n'
            await asyncio.sleep(.4)
    return StreamingResponse(stream(),media_type='text/event-stream',headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})
@app.get('/api/v1/skills',response_model=list[c.SkillDefinition])
async def skills():return service().skills()
@app.get('/api/v1/skill-categories',response_model=list[SkillCategory])
async def skill_categories():return json.loads((ROOT/'config/skill-navigation.json').read_text())
@app.get('/api/v1/models',response_model=list[c.ModelDescriptor])
async def models():return service().models()
@app.get('/api/v1/models/reasoning',response_model=list[ReasoningOptions])
async def reasoning_models():return service().reasoning_options()
@app.get('/api/v1/research-projects/{pid}/artifacts',response_model=list[c.ArtifactIndex|BusinessArtifact|FormalArtifact])
async def artifacts(pid:str):return service().store.artifacts(pid)
@app.get('/api/v1/research-projects/{pid}/artifacts/{aid}/content')
async def content(pid:str,aid:str,download:bool=False):
    artifact=service().store.artifact(aid,pid)
    try:raw=service().artifact_bytes(artifact)
    except ValueError:raise HTTPException(409,'artifact_revision_changed')
    suffix=Path(artifact['relative_path']).suffix
    disposition='attachment' if download else 'inline'
    return Response(raw,media_type=artifact['media_type'],headers={'Content-Disposition':f'{disposition}; filename="{aid}{suffix}"','Cache-Control':'private, no-store','Content-Security-Policy':"sandbox; default-src 'none'"})
@app.get('/api/v1/research-projects/{pid}/workbench',response_model=WorkbenchView)
async def workbench(pid:str):
    project=service().store.project(pid);artifacts=service().store.artifacts(pid)
    facts=[];stages=[]
    for artifact in artifacts:
        if artifact['id']=='art_conclusions':
            data=json.loads(service().artifact_bytes(artifact));facts.extend([{'label':'已完成开发单元','value':str(data['execution']['completed_cells'])},{'label':'完整研究目标','value':'已达成' if data['goal_achieved_dev'] else '尚未达成'},{'label':'独立科学审核','value':'尚未完成'}])
        if artifact['id']=='art_pipeline':
            data=json.loads(service().artifact_bytes(artifact));facts.extend([{'label':'论文状态','value':'可供作者审阅' if data['status']=='review_delivery_ready' else data['status']},{'label':'投稿就绪','value':'是' if data['submission_ready'] else '否'}])
    for definition in service().domain.definitions(pid):
        if definition.workflow:
            stages=[{'id':n.id,'title':n.title,'kind':n.kind,'current':n.current} for n in definition.workflow.nodes]
    return {'project_id':pid,'facts':facts,'stages':stages,'stage_note':'历史实验冻结流程；独立复验与稿件各自保留来源和状态。' if stages else '尚未绑定研究流程。'}
@app.get('/api/v1/settings/status',response_model=RuntimeStatus)
async def runtime_status():
    try:health=await service().runtime.health()
    except Exception:health={'healthy':False}
    s=service();ready=s.credential_ready()
    return {'runtime':s.runtime_name,'environment':s.config.get('execution_environment','bxn-server'),'business_enabled':s.config.get('business_enabled',True),'version':health.get('version'),'connected':health.get('healthy',False),'credential_present':ready,'model':s.config.get('codex',{}).get('model','deepseek-v4-pro') if s.runtime_name=='codex' else s.config.get('provider',{}).get('model','deepseek-v4-pro'),'readiness':'credential_missing' if not ready else 'runtime_unavailable' if not health.get('healthy') else 'reload_required' if not health.get('credential_loaded',True) else 'ready_for_inference_check','compaction':{'auto':True,'prune':False,'reserved_tokens':20000 if s.runtime_name=='opencode' else 0},'inference_verified':s.inference_verified(),'codex_server_inference_enabled':False}

@app.post('/api/v1/settings/provider/reload')
async def reload_provider():
    async with service().lock:
        if service().store.active():raise Conflict('runtime_busy')
        if service().runtime_name=='codex':
            await service().runtime.health();return {'status':'checked'}
        process=await asyncio.create_subprocess_exec(str(ROOT/'.venv/bin/python'),str(ROOT/'scripts/service.py'),'restart-runtime',cwd=ROOT,env=dict(os.environ,PYTHONPATH=str(ROOT/'src')),stdout=asyncio.subprocess.DEVNULL,stderr=asyncio.subprocess.DEVNULL)
        await asyncio.wait_for(process.wait(),15)
        if process.returncode:raise NotReady('runtime_restart_failed')
        return {'status':'reloading'}

@app.get('/api/v1/settings/codex',response_model=AuthStatus)
async def codex_status():return await app.state.auth.status()
@app.post('/api/v1/settings/codex/login',response_model=AuthStatus)
async def codex_start():return await app.state.auth.start()
@app.post('/api/v1/settings/codex/cancel',response_model=AuthStatus)
async def codex_cancel():return await app.state.auth.cancel()

class CompactInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    request_key:c.Identifier
    model:str=Field(max_length=100)

@app.get('/api/v1/conversations/{cid}/context',response_model=ContextView)
async def context_view(cid:str):return service().context.view(cid)
@app.post('/api/v1/conversations/{cid}/context/reconcile',response_model=ContextView)
async def reconcile_context(cid:str):return await service().context.reconcile(cid)
@app.post('/api/v1/conversations/{cid}/compact')
async def compact_context(cid:str,body:CompactInput):return await service().context.compact(cid,body.request_key,body.model)
@app.get('/api/v1/conversations/{cid}/handoff',response_model=TransferBundle)
async def export_handoff(cid:str):return service().context.export(cid)
@app.post('/api/v1/handoffs/import')
async def import_handoff(body:HandoffBundle|TransferBundle):
    async with service().lock:
        if service().store.active():raise Conflict('runtime_busy')
        return service().context.import_bundle(body.model_dump(mode="json"))

@app.get('/api/v2/research-projects/{pid}/domain',response_model=ProjectDomainView)
async def domain_view(pid:str):return await asyncio.to_thread(service().domain.view,pid)
@app.get('/api/v2/research-projects/{pid}/legacy-history',response_model=list[LegacyHistoryEntry])
async def legacy_history(pid:str):return await asyncio.to_thread(service().domain.history,pid)
@app.get('/api/v2/research-projects/{pid}/artifacts/{aid}',response_model=ArtifactRecord)
async def artifact_record(pid:str,aid:str):return service().domain.resolve(pid,aid)
@app.get('/api/v2/turns/{tid}/context',response_model=ContextSnapshotV2)
async def context_snapshot(tid:str):return service().domain.context(tid)

@app.get('/api/v2/formal-entry',response_model=EntryStatus)
async def formal_entry():return service().formal.status()
@app.post('/api/v2/formal-studies',response_model=StudyView,status_code=201)
async def create_study(body:StudyCreate):
    async with service().lock:return service().formal.create(body)
@app.get('/api/v2/research-projects/{pid}/study',response_model=StudyView|None)
async def study_view(pid:str):return service().formal.view(pid)
@app.get('/api/v2/conversations/{cid}/permission-settings',response_model=PermissionSettingsView)
async def permission_settings(cid:str):return service().formal.permissions.view(cid)
@app.put('/api/v2/conversations/{cid}/permission-settings',response_model=PermissionSettingsView)
async def update_permission_settings(cid:str,body:PermissionSettingsUpdate):
    async with service().lock:return await service().formal.permissions.update(cid,body)

@app.get('/api/v2/conversations/{cid}/permissions',response_model=list[NativePermission])
async def native_permissions(cid:str):return await service().formal.pending(cid)
@app.post('/api/v2/conversations/{cid}/permissions/{rid}')
async def permission_reply(cid:str,rid:str,body:PermissionReply):
    async with service().lock:return await service().formal.reply(cid,rid,body.reply)

class PublishInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    project_id:c.Identifier
    relative_path:str=Field(min_length=1,max_length=1000)
    title:str=Field(min_length=1,max_length=200)
@app.post('/internal/formal/artifacts',response_model=FormalArtifact,include_in_schema=False)
async def publish_study_artifact(body:PublishInput,request:Request):
    expected='Bearer '+service().business.token()
    if not hmac.compare_digest(request.headers.get('authorization',''),expected):raise HTTPException(403,'business_bridge_auth_required')
    from .study_io import publish_artifact
    return await asyncio.to_thread(publish_artifact,service(),body.project_id,body.relative_path,body.title)

static=ROOT/'apps/web/dist'
if static.exists():
    app.mount('/assets',StaticFiles(directory=static/'assets'),name='assets')
@app.get('/')
async def index():
    if not (static/'index.html').exists():raise HTTPException(503,'frontend_not_built')
    return FileResponse(static/'index.html')
