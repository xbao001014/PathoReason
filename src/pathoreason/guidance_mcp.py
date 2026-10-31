"""Structured dialogue tool; no filesystem or compute execution surface."""
import sys,json,urllib.request,urllib.error
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from pathoreason.guidance import OfferInput
from pathoreason.settings import settings

def main():
    cfg=settings()
    for line in sys.stdin:
        try:
            req=json.loads(line)
            if 'id' not in req:continue
            method=req.get('method')
            if method=='initialize':result={'protocolVersion':'2024-11-05','capabilities':{'tools':{}},'serverInfo':{'name':'pathoreason_dialogue','version':'0.1.0'}}
            elif method=='ping':result={}
            elif method=='tools/list':result={'tools':[{'name':'offer','description':'Save a brief clarification or useful next-step choice in the UI. Use early when context already reveals a missing decision; do not audit files first. Use after actual delivery for a next step. One offer per turn; finish your reply after success. Never executes research or grants training. Copy turn_id/grant from current trusted dialogue capability. options carry visible labels, optional descriptions and clarify/plan/inspect scope. artifact_ids bind relevant registered artifacts.','inputSchema':OfferInput.model_json_schema()}]}
            elif method=='tools/call':
                if req['params']['name']!='offer':raise ValueError('unknown_tool')
                args=OfferInput.model_validate(req['params']['arguments']).model_dump(mode='json')
                token=Path(cfg['data_root'])/'runtime/control/guidance-token'
                if token.is_symlink() or token.stat().st_mode&0o077:raise ValueError('bridge_token_unavailable')
                request=urllib.request.Request(f"http://127.0.0.1:{cfg['api_port']}/internal/guidance",data=json.dumps(args).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+token.read_text().strip()})
                try:
                    with urllib.request.urlopen(request,timeout=15) as response:value=json.load(response)
                    result={'content':[{'type':'text','text':json.dumps(value,ensure_ascii=False)}],'isError':False}
                except urllib.error.HTTPError as exc:
                    result={'content':[{'type':'text','text':json.dumps({'error':json.load(exc).get('detail','guidance_failed')})}],'isError':True}
            else:raise ValueError('unsupported_method')
            print(json.dumps({'jsonrpc':'2.0','id':req['id'],'result':result}),flush=True)
        except Exception as exc:
            print(json.dumps({'jsonrpc':'2.0','id':req.get('id'),'error':{'code':-32603,'message':type(exc).__name__}}),flush=True)
if __name__=='__main__':main()
