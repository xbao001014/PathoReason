from __future__ import annotations
import httpx,json
from pathlib import Path

class OpenCode:
    name="opencode"
    def __init__(self,data_root:Path,port:int):
        self.root=data_root;self.port=port
    def client(self):
        password=(self.root/"runtime/control/opencode-password").read_text().strip()
        return httpx.AsyncClient(base_url=f"http://127.0.0.1:{self.port}",auth=("opencode",password),timeout=15,trust_env=False)
    async def call(self,method,path,directory=None,body=None):
        async with self.client() as client:
            response=await client.request(method,path,params={"directory":directory} if directory else None,json=body)
            response.raise_for_status()
            return response.json() if response.content else None
    async def health(self):
        import json
        health=await self.call("GET","/global/health")
        record=self.root/"runtime/control/opencode.json"
        health["credential_loaded"]=bool(json.loads(record.read_text()).get("credential_loaded")) if record.exists() else False
        health["output_token_max"]=json.loads(record.read_text()).get("output_token_max",32000) if record.exists() else 32000
        return health
    async def delete_session(self,session,directory):
        from .persistence import Conflict
        path=f'/session/{session}'
        try:
            current=await self.call('GET',path,directory)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code==404:return
            raise
        if current.get('id')!=session or Path(current.get('directory','')).resolve()!=Path(directory).resolve():
            raise Conflict('native_session_scope_mismatch')
        if await self.call('GET',path+'/children',directory):
            raise Conflict('native_child_sessions_exist')
        await self.call('DELETE',path,directory)
        try:
            await self.call('GET',path,directory)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code==404:return
            raise
        raise Conflict('native_deletion_unconfirmed')
    async def create(self,directory,title):
        return await self.call("POST","/session",directory,{"title":title,"permission":[{"permission":"*","pattern":"*","action":"deny"},{"permission":"skill","pattern":"results-explanation","action":"allow"},{"permission":"pathoreason_research","pattern":"*","action":"allow"}]})
    async def create_formal(self,directory,title):
        from .permission_settings import formal_rules
        return await self.call('POST','/session',directory,{'title':title,'agent':'pathoreason-formal','permission':formal_rules(directory)})
    async def configure_formal_permissions(self,session,directory,settings,execution_scope="standard"):
        from .permission_settings import formal_rules
        rules=formal_rules(directory,settings,execution_scope)
        # OpenCode 1.18 appends PATCH rules; last matching rule wins.
        current=await self.call('GET',f'/session/{session}',directory)
        if current.get('permission', [])[-len(rules):] != rules:
            await self.call('PATCH',f'/session/{session}',directory,{'permission':rules})
            current=await self.call('GET',f'/session/{session}',directory)
        if current.get('permission', [])[-len(rules):] != rules:
            raise ValueError('permission_settings_native_mismatch')
    async def prompt_formal(self,session,directory,message_id,model,prompt,reasoning_effort=None,output_limit_tokens=None):
        if output_limit_tokens is not None:
            model=await self.output_profile(model,output_limit_tokens,directory)
        await self.call('POST',f'/session/{session}/prompt_async',directory,{**await self.reasoning_variant(model,reasoning_effort,directory),'messageID':message_id,'model':{'providerID':self.provider(model),'modelID':model},'agent':'pathoreason-formal','parts':[{'type':'text','text':prompt}]})
    async def prompt(self,session,directory,message_id,model,prompt,reasoning_effort=None,output_limit_tokens=None):
        if output_limit_tokens is not None:
            model=await self.output_profile(model,output_limit_tokens,directory)
        current=await self.call("GET",f"/session/{session}",directory)
        if not any(p.get('permission')=='pathoreason_research' and p.get('action')=='allow' for p in current.get('permission',[])):
            await self.call("PATCH",f"/session/{session}",directory,{"permission":[{"permission":"pathoreason_research","pattern":"*","action":"allow"}]})
        await self.call("POST",f"/session/{session}/prompt_async",directory,{**await self.reasoning_variant(model,reasoning_effort,directory),"messageID":message_id,"model":{"providerID":self.provider(model),"modelID":model},"agent":"pathoreason","parts":[{"type":"text","text":prompt}]})
    async def output_profile(self,model,limit,directory):
        from .output_settings import validate_output
        profile=validate_output(model,limit)
        if limit>(await self.health()).get('output_token_max',32000):raise ValueError('output_profile_reload_required')
        providers=await self.call('GET','/provider',directory)
        provider=next((p for p in providers['all'] if p['id']==self.provider(model)),{})
        current=provider.get('models',{}).get(profile,{})
        if current.get('limit',{}).get('output')!=limit or (profile!=model and current.get('api',{}).get('id')!=model):
            raise ValueError('output_profile_reload_required')
        return profile
    async def reasoning_variant(self,model,effort,directory):
        if effort is None:return {}
        from .reasoning import EFFORTS
        if effort not in EFFORTS:raise ValueError('reasoning_effort_not_supported')
        providers=await self.call('GET','/provider',directory)
        provider=next((p for p in providers['all'] if p['id']==self.provider(model)),{})
        variant=provider.get('models',{}).get(model,{}).get('variants',{}).get(effort)
        if variant!={'reasoningEffort':effort}:raise ValueError('reasoning_variant_reload_required')
        return {'variant':effort}
    def provider(self,model):
        from .settings import ROOT
        config=json.loads((ROOT/'config/opencode.json').read_text())
        providers=[pid for pid,p in config['provider'].items() if model in p.get('models',{})]
        if len(providers)!=1:raise ValueError('ambiguous_model_provider')
        return providers[0]
    async def compaction_marker(self,session,directory):
        return sorted(m['info']['id'] for m in await self.messages(session,directory) if m['info'].get('summary') is True and m['info'].get('time',{}).get('completed') and not m['info'].get('error'))
    async def compacted_context(self,session,directory,summary_ids):
        return compacted_context_estimate(await self.messages(session,directory),summary_ids)
    async def compact(self,session,directory,model):
        import asyncio
        before=await self.messages(session,directory)
        ids={m['info']['id'] for m in before if m['info'].get('summary') is True}
        async with self.client() as client:
            response=await client.post(f'/session/{session}/summarize',params={'directory':directory},json={'providerID':self.provider(model),'modelID':model,'auto':False},timeout=65)
            response.raise_for_status()
        for _ in range(300):
            messages=await self.messages(session,directory)
            summaries=[m['info'] for m in messages if m['info'].get('summary') is True and m['info']['id'] not in ids]
            if any(m.get('time',{}).get('completed') and not m.get('error') for m in summaries):return {'observed':True,'source':'opencode_summary_message'}
            if any(m.get('error') for m in summaries):raise ValueError('compaction_failed')
            await asyncio.sleep(.2)
        raise TimeoutError('compaction_outcome_unknown')
    async def messages(self,session,directory):return await self.call("GET",f"/session/{session}/message",directory)
    async def status(self,directory):return await self.call("GET","/session/status",directory)
    async def abort(self,session,directory):return await self.call("POST",f"/session/{session}/abort",directory,{})

    async def public_text_updates(self,session,directory,ready):
        """Consume only explicit public text events; never persist reasoning/tool arguments."""
        blocks={};seen=set();public_parts=set();legacy_messages=set()
        async with self.client() as client:
            async with client.stream('GET','/event',params={'directory':directory},timeout=None) as response:
                response.raise_for_status();ready.set()
                async for line in response.aiter_lines():
                    if not line.startswith('data:'):continue
                    event=json.loads(line[5:].strip());kind=event.get('type');data=event.get('properties',event.get('data',{}))
                    if data.get('sessionID')!=session:continue
                    if kind not in ('session.next.text.delta','message.part.updated','message.part.delta'):continue
                    eid=event.get('id')
                    if eid and eid in seen:continue
                    if eid:seen.add(eid)
                    if kind=='message.part.updated':
                        part=data['part']
                        if part.get('type')!='text':continue
                        mid=part['messageID'];key=(mid,part['id']);public_parts.add(key);legacy_messages.add(mid)
                        blocks[key]=part.get('text','')
                    elif kind=='message.part.delta':
                        mid=data['messageID'];key=(mid,data['partID'])
                        if data.get('field')!='text' or key not in public_parts:continue
                        blocks[key]=blocks.get(key,'')+data['delta']
                    else:
                        mid=data['assistantMessageID'];key=(mid,data['textID'])
                        if mid in legacy_messages:continue
                        blocks[key]=blocks.get(key,'')+data['delta']
                    yield {m:'\n\n'.join(text for (message,_),text in blocks.items() if message==m) for m,_ in blocks}



def compacted_context_estimate(messages, summary_ids):
    """Byte estimate, not token telemetry. Matches OpenCode 1.18.33 retained history.

    filterCompacted keeps the summary's compaction user message, optional
    tail_start_id suffix and subsequent messages. Count all retained JSON;
    never use summary input tokens, which measure the OLD context.
    """
    candidates=[(i,m) for i,m in enumerate(messages) if m.get('info',{}).get('id') in summary_ids
        and m['info'].get('summary') is True and m['info'].get('finish')
        and m['info'].get('time',{}).get('completed') and not m['info'].get('error')]
    if not candidates:raise ValueError('compaction_summary_not_verified')
    index,summary=candidates[-1]
    parent=next((i for i,m in enumerate(messages[:index]) if m.get('info',{}).get('id')==summary['info'].get('parentID') and m['info'].get('role')=='user'),None)
    if parent is None:raise ValueError('compaction_parent_not_verified')
    part=next((p for p in messages[parent].get('parts',[]) if p.get('type')=='compaction'),None)
    if part is None:raise ValueError('compaction_parent_not_verified')
    start=parent
    if part.get('tail_start_id'):
        tail=next((i for i,m in enumerate(messages[:parent+1]) if m.get('info',{}).get('id')==part['tail_start_id']),None)
        if tail is None:raise ValueError('compaction_tail_not_verified')
        start=tail
    payload=json.dumps(messages[start:],ensure_ascii=False,separators=(',',':')).encode()
    import hashlib
    return {'context_tokens':len(payload)+16384,'context_source':'post_compaction_bytes_estimate',
            'summary_id':summary['info']['id'],'retained_messages':len(messages)-start,
            'retained_bytes':len(payload),'sha256':hashlib.sha256(payload).hexdigest()}


def visible_response(messages,parent_id):
    """No reasoning text, raw command arguments, tool output or provider secrets leave this adapter."""
    from .activity import tool_summary, activity_phase
    selected=[m for m in messages if m.get('info',{}).get('role')=='assistant' and m['info'].get('parentID')==parent_id]
    text=[];tools=[];usage={'input_tokens':0,'output_tokens':0,'context_tokens':None,'source':'runtime','scope':'turn','context_source':'estimate_from_runtime_usage'};complete=False;error=None;compacted=any((m.get('info',{}).get('role')=='assistant' and m.get('info',{}).get('summary') is True) or any(p.get('type')=='compaction' for p in m.get('parts',[])) for m in messages)
    for message in selected:
        info=message['info'];tokens=info.get('tokens',{})
        usage['input_tokens']+=tokens.get('input',0);usage['output_tokens']+=tokens.get('output',0)
        usage.update(last_reasoning_tokens=tokens.get('reasoning'),last_output_tokens=tokens.get('output'),finish_reason=info.get('finish'))
        if tokens:
            cache=tokens.get('cache',{});usage['context_tokens']=tokens.get('input',0)+tokens.get('output',0)+tokens.get('reasoning',0)+cache.get('read',0)+cache.get('write',0)
        if info.get('context_usage'):usage.update(info['context_usage'])
        if info.get('error'):error=info['error'].get('name','runtime_error')
        complete=bool(info.get('time',{}).get('completed')) and info.get('finish')!='tool-calls'
        for part in message.get('parts',[]):
            kind=part.get('type')
            if kind=='text':text.append(part.get('text',''))
            elif kind=='tool':tools.append(tool_summary(part))
            elif kind=='compaction':compacted=True
    usage['activity_phase']=activity_phase(selected)
    if complete and not error:
        if selected[-1]['info'].get('finish')=='length':
            error='runtime_output_limit'
        elif not any(value.strip() for value in text) and not tools:
            error='runtime_empty_response'
    return {'text':'\n\n'.join(text),'tools':tools,'usage':usage,'complete':complete,'error':error,'compacted':compacted,'assistant_seen':bool(selected),'user_seen':any(m.get('info',{}).get('id')==parent_id for m in messages)}
