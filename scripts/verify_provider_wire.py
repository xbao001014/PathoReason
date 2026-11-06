"""Real OpenCode + local synthetic OpenAI endpoint; no paid model/network inference."""
import asyncio,json,os,socket,subprocess,threading,time,argparse,sys
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from pathoreason.provider_config import initialize,private_directory,native_config
from pathoreason.settings import settings
from pathoreason.runtime import OpenCode

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    root=args.output;root.mkdir(parents=True,exist_ok=False);calls=[]
    class Mock(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))))
            tool_results=[m for m in body.get('messages',[]) if m.get('role')=='tool']
            request_tools=[t['function']['name'] for t in body.get('tools',[])]
            calls.append({'model':body.get('model'),'max_tokens':body.get('max_tokens'),
                'reasoning_effort':body.get('reasoning_effort'),'enable_thinking':body.get('enable_thinking'),
                'thinking':body.get('thinking'),'request_keys':list(body),'tool_results':len(tool_results),'tool_names':request_tools})
            self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
            use_tool=not tool_results and 'read' in request_tools
            delta={'role':'assistant','tool_calls':[{'index':0,'id':'call_fixture','type':'function','function':{'name':'read','arguments':json.dumps({'filePath':str(root/'workspace/evidence.txt')})}}]} if use_tool else {'role':'assistant','content':'Fixture complete.'}
            chunks=[{'id':'chatcmpl-fixture','object':'chat.completion.chunk','created':int(time.time()),'model':body['model'],'choices':[{'index':0,'delta':delta,'finish_reason':None}]},
                    {'id':'chatcmpl-fixture','object':'chat.completion.chunk','created':int(time.time()),'model':body['model'],'choices':[{'index':0,'delta':{},'finish_reason':'tool_calls' if use_tool else 'stop'}],'usage':{'prompt_tokens':10,'completion_tokens':3,'total_tokens':13}}]
            for c in chunks:self.wfile.write(('data: '+json.dumps(c)+'\n\n').encode())
            self.wfile.write(b'data: [DONE]\n\n');self.wfile.flush()
    server=ThreadingHTTPServer(('127.0.0.1',0),Mock);threading.Thread(target=server.serve_forever,daemon=True).start()
    cfg={'data_root':str(root)};initialize(cfg,'fixture-only-key');cfg['provider_profiles_enabled']=True
    statefile=private_directory(cfg)/'profiles.json';value=json.loads(statefile.read_text());value['active']='dashscope-deepseek';statefile.write_text(json.dumps(value))
    full=native_config(cfg);pid='dashscope-deepseek';provider=full['provider'][pid]
    provider['options']={'baseURL':f'http://127.0.0.1:{server.server_port}/v1','apiKey':'fixture-only-key'}
    config={'$schema':'https://opencode.ai/config.json','provider':{pid:provider},'enabled_providers':[pid],
        'model':pid+'/deepseek-v4-pro','small_model':pid+'/deepseek-v4-pro','autoupdate':False,'share':'disabled',
        'agent':{'pathoreason-formal':{'mode':'primary','prompt':'Synthetic fixture. Read only the supplied fixture file if requested.',
            'permission':{'*':'deny','read':'allow','external_directory':'allow'}}}}
    (root/'config.json').write_text(json.dumps(config));(root/'workspace').mkdir();(root/'workspace/evidence.txt').write_text('Synthetic fixture only.\n')
    (root/'runtime/control').mkdir(parents=True,exist_ok=True);(root/'runtime/control/opencode-password').write_text('fixture-password')
    (root/'runtime/control/opencode.json').write_text(json.dumps({'output_token_max':65536}))
    env=dict(os.environ,OPENCODE_CONFIG=str(root/'config.json'),OPENCODE_SERVER_PASSWORD='fixture-password',
        OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX='65536',OPENCODE_DISABLE_PROJECT_CONFIG='true',OPENCODE_DISABLE_EXTERNAL_SKILLS='true',OPENCODE_DISABLE_AUTOUPDATE='true')
    for key in ['DEEPSEEK_API_KEY','DASHSCOPE_API_KEY','OPENAI_API_KEY','PATHOREASON_PROVIDER_API_KEY']:env.pop(key,None)
    for category in ['config','data','cache','state']:
        path=root/('xdg-'+category);path.mkdir();env['XDG_'+category.upper()+'_HOME']=str(path)
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    log=(root/'native.log').open('ab')
    proc=subprocess.Popen([settings()['opencode_binary'],'serve','--pure','--hostname','127.0.0.1','--port',str(port)],cwd=root/'workspace',env=env,stdout=log,stderr=log)
    async def run():
        r=OpenCode(root,port,{'opencode_config_file':str(root/'config.json')})
        for _ in range(60):
            try:await r.call('GET','/global/health');break
            except Exception:await asyncio.sleep(.3)
        for index,(model,effort,cap) in enumerate([('deepseek-v4-pro','none',8192),('deepseek-v4-pro','high',32768),('deepseek-v4-pro','max',65536),('deepseek-v4.1-flash','low',8192)]):
            before=len(calls)
            s=await r.call('POST','/session',str(root/'workspace'),{'title':'Synthetic provider fixture','permission':[{'permission':'*','pattern':'*','action':'deny'},{'permission':'read','pattern':'*','action':'allow'},{'permission':'external_directory','pattern':'*','action':'allow'}]})
            await r.prompt_formal(s['id'],str(root/'workspace'),'msg_wirefixture'+str(index),model,'Read the supplied synthetic fixture file and finish.',effort,output_limit_tokens=cap)
            for _ in range(160):
                if len(calls)>before and not await r.status(str(root/'workspace')):break
                await asyncio.sleep(.25)
            batch=calls[before:];assert batch,'missing wire request'
            (root/'wire-metadata.json').write_text(json.dumps(calls,indent=2))
            for c in batch:
                assert c['model']==model and c['max_tokens']==cap,c
                assert c['enable_thinking']==(effort!='none'),c
                if effort!='none':assert c['reasoning_effort']==effort,c
            assert any(c['tool_results'] for c in batch),'tool result was not returned to model'
        compacted=await r.compact(s['id'],str(root/'workspace'),'deepseek-v4-pro')
        assert compacted['observed']
        (root/'wire-metadata.json').write_text(json.dumps(calls,indent=2))
        result={'requests':len(calls),'variants':4,'tool_roundtrip':True,'compaction':True,'paid_requests':0}
        (root/'result.json').write_text(json.dumps(result,indent=2))
        print(json.dumps(result))
    try:asyncio.run(run())
    finally:
        proc.terminate()
        try:proc.wait(timeout=10)
        except subprocess.TimeoutExpired:proc.kill();proc.wait()
        log.close();server.shutdown()

if __name__=='__main__':main()
