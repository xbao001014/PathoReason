"""Read-only project context MCP, scoped to the single active application turn."""
import json,sys
from types import SimpleNamespace
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from pathoreason.domain import Domain
from pathoreason.settings import settings
from pathoreason.persistence import Store
from pathoreason.legacy import read_verified_file

def read_context(arguments):
    cfg=settings();store=Store(Path(cfg['data_root'])/'state/pathoreason.sqlite3');active=store.active()
    if len(active)!=1:raise ValueError('no_unique_active_turn')
    row=active[0];pid=row['project_id'];project=store.project(pid)
    if arguments.get('project_id')!=pid:raise ValueError('cross_project_denied')
    with store.connect() as db:snapshot=json.loads(db.execute('SELECT document FROM context_snapshots WHERE turn_id=?',(row['id'],)).fetchone()[0])
    with store.connect() as db:handoff=db.execute('SELECT document FROM handoffs WHERE conversation_id=?',(row['conversation_id'],)).fetchone()
    result={'handoff_source':json.loads(handoff[0]) if handoff else None,'project':project,'constraints':snapshot['constraints'],'artifact_ids':[a['id'] for a in store.artifacts(pid)],'research_mutations_available':False}
    domain=Domain(SimpleNamespace(store=store,data=Path(cfg['data_root']),config=cfg))
    result['context_snapshot']=domain.context(row['id']).model_dump(mode='json')
    aid=arguments.get('artifact_id')
    if aid:
        record=domain.resolve(pid,aid)
        art=record.artifact.model_dump(mode='json')
        result['artifact_provenance']=record.provenance.model_dump(mode='json')
        root=Path(cfg['data_root'])/'artifacts' if art['storage_root']=='pathoreason_artifacts' else Path('/data/bxn/auto-research/acceptance')
        content=read_verified_file(root,art['relative_path'],art['sha256'])
        text=content.decode('utf8') if art['media_type'].startswith('text/') or art['media_type']=='application/json' else '(binary; inspect workbench)'
        result['artifact']={**art,'content':text[:12000],'truncated':len(text)>12000,'truncation_is_not_compaction':True}
    return result

def main():
    for line in sys.stdin:
        try:
            req=json.loads(line);method=req.get('method');rid=req.get('id')
            if rid is None:continue
            if method=='initialize':result={'protocolVersion':'2024-11-05','capabilities':{'tools':{}},'serverInfo':{'name':'pathoreason_context','version':'0.5.0'}}
            elif method=='ping':result={}
            elif method=='tools/list':result={'tools':[{'name':'read_project','annotations':{'readOnlyHint':True,'destructiveHint':False,'idempotentHint':True,'openWorldHint':False},'description':'Read authoritative current project constraints and optionally a verified artifact. Read-only; cannot execute historical actions.','inputSchema':{'type':'object','properties':{'project_id':{'type':'string'},'artifact_id':{'type':'string'}},'required':['project_id'],'additionalProperties':False}}]}
            elif method=='tools/call':
                try:
                    if req['params']['name']!='read_project':raise ValueError('tool_not_available')
                    value=read_context(req['params'].get('arguments',{}));result={'content':[{'type':'text','text':json.dumps(value,ensure_ascii=False)}],'isError':False}
                except Exception as exc:result={'content':[{'type':'text','text':str(exc) if isinstance(exc,ValueError) else 'context_read_failed'}],'isError':True}
            else:raise ValueError('method_not_supported')
            print(json.dumps({'jsonrpc':'2.0','id':rid,'result':result}),flush=True)
        except Exception:print(json.dumps({'jsonrpc':'2.0','id':req.get('id'),'error':{'code':-32603,'message':'request_failed'}}),flush=True)
if __name__=='__main__':main()
