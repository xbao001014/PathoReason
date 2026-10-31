"""Small stdio MCP bridge. Newline JSON-RPC; no shell or filesystem tool surface."""
from pathlib import Path
import json,sys,urllib.request,urllib.error
ROOT=Path(__file__).resolve().parents[2]
CFG=json.loads((ROOT/'config/pathoreason.local.json').read_text())
SCHEMA={'type':'object','additionalProperties':False,'properties':{
    'turn_id':{'type':'string'},'grant':{'type':'string'},'target':{'type':'string'},
    'operation':{'type':'string','enum':['inspect','intake','plan','revise','execute','recover','stop']},
    'expected_revision':{'type':'string'},'idempotency_key':{'type':'string'},
    'parameters':{'type':'object','properties':{'question':{'type':'string'},'feedback':{'type':'string'},
        'learning_rate':{'type':'number','minimum':.00001,'maximum':.001}},'additionalProperties':False}},
    'required':['turn_id','grant','target','operation']}
TOOL={'name':'research','description':'Read or act on the current synthetic MIL workflow. Copy turn_id, grant, target from trusted turn context. Inspect first for revision; mutations require expected_revision and a unique stable idempotency_key. Intake takes question; plan/revise accept learning_rate; revise requires feedback. Execution requires a later user turn after the plan/revision. Never operates on legacy experiments. Returns authoritative business status, not scientific approval.','inputSchema':SCHEMA}

def call(arguments):
    token=Path(CFG['data_root'])/'runtime/control/business-token'
    if token.is_symlink() or token.stat().st_mode & 0o077:raise ValueError('Bridge token unavailable')
    req=urllib.request.Request(f"http://127.0.0.1:{CFG['api_port']}/internal/business",data=json.dumps(arguments).encode(),
        headers={'Content-Type':'application/json','Authorization':'Bearer '+token.read_text().strip()})
    try:
        with urllib.request.urlopen(req,timeout=65) as response:result=json.load(response)
        return {'content':[{'type':'text','text':json.dumps(result,ensure_ascii=False)}],'isError':False}
    except urllib.error.HTTPError as exc:
        try:detail=json.load(exc).get('detail','business_request_failed')
        except ValueError:detail='business_request_failed'
        return {'content':[{'type':'text','text':json.dumps({'error':detail},ensure_ascii=False)}],'isError':True}

def dispatch(message):
    method=message.get('method')
    if method=='initialize':return {'protocolVersion':'2024-11-05','capabilities':{'tools':{}},'serverInfo':{'name':'pathoreason-business','version':'0.1.0'}}
    if method=='ping':return {}
    if method=='tools/list':return {'tools':[TOOL]}
    if method=='tools/call':
        params=message.get('params',{})
        if params.get('name')!='research':raise ValueError('Unknown tool')
        return call(params.get('arguments',{}))
    raise ValueError('Unsupported method')

def main():
    for line in sys.stdin:
        try:message=json.loads(line)
        except ValueError:continue
        if 'id' not in message:continue
        response={'jsonrpc':'2.0','id':message['id']}
        try:response['result']=dispatch(message)
        except Exception as exc:response['error']={'code':-32603,'message':type(exc).__name__}
        print(json.dumps(response,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
