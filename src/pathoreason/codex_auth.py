"""Authentication-only Codex bridge. No thread or inference endpoints are exposed."""
import asyncio,json,os
from pathlib import Path

class CodexAuth:
    def __init__(self,binary):
        self.binary=binary;self.process=None;self.reader=None;self.pending={};self.serial=0;self.lock=asyncio.Lock();self.login={'state':'not_checked'}
    async def ensure(self):
        async with self.lock:
            if self.process and self.process.returncode is None:return
            env=dict(os.environ);env['PATH']=str(Path(self.binary).parent)+':'+env.get('PATH','')
            self.process=await asyncio.create_subprocess_exec(self.binary,'app-server',stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL,env=env)
            self.reader=asyncio.create_task(self.consume())
            await self.rpc('initialize',{'clientInfo':{'name':'pathoreason_auth','version':'0.1.0'}})
            self.process.stdin.write(b'{"method":"initialized","params":{}}\n');await self.process.stdin.drain()
    async def consume(self):
        try:
            while line:=await self.process.stdout.readline():
                data=json.loads(line)
                if 'id' in data and data['id'] in self.pending:
                    fut=self.pending.pop(data['id'])
                    if not fut.done():fut.set_result(data)
                elif data.get('method')=='account/login/completed':
                    self.login={'state':'authenticated' if data.get('params',{}).get('success') else 'failed','message':None if data.get('params',{}).get('success') else '服务器登录未完成；可重新检查或稍后重试。'}
        finally:
            for future in self.pending.values():
                if not future.done():future.set_exception(RuntimeError('codex_connection_closed'))
            self.pending.clear()
    async def rpc(self,method,params):
        self.serial+=1;key=self.serial;future=asyncio.get_running_loop().create_future();self.pending[key]=future
        self.process.stdin.write((json.dumps({'id':key,'method':method,'params':params})+'\n').encode());await self.process.stdin.drain()
        try:
            data=await asyncio.wait_for(future,15)
            if 'error' in data:raise RuntimeError('codex_auth_unavailable')
            return data.get('result',{})
        finally:self.pending.pop(key,None)
    async def status(self):
        try:
            await self.ensure();result=await self.rpc('account/read',{'refreshToken':False})
            return {'state':'authenticated' if result.get('account') else self.login.get('state','not_authenticated') if self.login.get('state') in ('pending','failed','cancelled') else 'not_authenticated','account_type':(result.get('account') or {}).get('type'),'server_inference_enabled':False,**{k:v for k,v in self.login.items() if k not in ('state',)}}
        except Exception:return {'state':'unavailable','message':'服务器暂时无法连接 Codex 登录服务。OpenCode 不受影响。','server_inference_enabled':False}
    async def start(self):
        if self.login.get('state')=='pending':return self.login
        try:
            await self.ensure();result=await self.rpc('account/login/start',{'type':'chatgptDeviceCode'})
            self.login={'state':'pending','login_id':result['loginId'],'verification_url':result['verificationUrl'],'user_code':result['userCode']}
        except Exception:self.login={'state':'failed','message':'服务器设备登录暂不可用。请确认网络与账户设置后重试。'}
        return self.login
    async def cancel(self):
        try:
            if self.login.get('login_id'):
                await self.ensure();await self.rpc('account/login/cancel',{'loginId':self.login['login_id']})
        finally:self.login={'state':'cancelled'}
        return self.login
    async def close(self):
        if self.process and self.process.returncode is None:
            self.process.terminate()
            try:await asyncio.wait_for(self.process.wait(),5)
            except TimeoutError:self.process.kill();await self.process.wait()
        if self.reader:self.reader.cancel()
