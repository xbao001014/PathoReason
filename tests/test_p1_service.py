import asyncio,hashlib,json
from pathlib import Path
import pytest
from pathoreason.contracts import ArtifactIndex,LegacyResourceRef,RuntimeEvent
from pathoreason.persistence import Store,Conflict
from pathoreason.service import Service,NotReady
from pathoreason.runtime import visible_response

class FakeRuntime:
    def __init__(self):self.sessions={};self.calls=[];self.polls={};self.abort_called=False;self.hold=False;self.creates=0
    async def health(self):return {'healthy':True}
    async def create(self,directory,title):
        self.creates+=1;sid='ses_'+str(self.creates);self.sessions[sid]=None;return {'id':sid}
    async def prompt(self,sid,directory,mid,model,prompt,reasoning_effort=None):
        self.last_effort=reasoning_effort
        self.calls.append((sid,mid,model,prompt));self.sessions[sid]=mid;self.polls[sid]=0
    async def messages(self,sid,directory):
        mid=self.sessions[sid]
        if not mid:return []
        self.polls[sid]+=1;done=self.polls[sid]>1 and not self.hold
        return [{'info':{'id':mid,'role':'user'},'parts':[]},{'info':{'id':'msg_assistant','role':'assistant','parentID':mid,'time':{'completed':123} if done else {},'tokens':{'input':100,'output':20,'reasoning':4,'cache':{'read':5,'write':0}}},'parts':[{'id':'prt_text','type':'text','text':'结果尚未达到完整研究目标。[证据](artifact:art_test)' if done else '正在解释'},{'id':'prt_reason','type':'reasoning','text':'PRIVATE_REASONING'},{'id':'prt_tool','type':'tool','tool':'skill','state':{'status':'completed','input':{'secret':'HIDDEN'},'output':'HIDDEN_OUTPUT'}}]}]
    async def status(self,directory):return {sid:{'type':'idle' if self.abort_called or self.polls.get(sid,0)>1 and not self.hold else 'busy'} for sid in self.sessions}
    async def abort(self,sid,directory):self.abort_called=True

@pytest.fixture
def fixture(tmp_path,monkeypatch):
    monkeypatch.setattr('pathoreason.service.credential',lambda:'synthetic-test-credential')
    for n in ['projects','artifacts','state']: (tmp_path/n).mkdir()
    blob=b'{"goal_achieved_dev":false}'
    (tmp_path/'artifacts/result.json').write_bytes(blob);sha=hashlib.sha256(blob).hexdigest()
    ref=LegacyResourceRef(adapter='auto_research.evidence_file',resource_id='synthetic/result.json',revision=sha,revision_kind='file_sha256')
    store=Store(tmp_path/'state/test.sqlite3');project=store.create_project('Synthetic','Keep evidence boundaries',[ref])
    runtime=FakeRuntime();svc=Service(store,runtime,{'data_root':str(tmp_path),'opencode_port':8522,'p1_test_limits':{'max_wall_seconds':30}})
    conv=svc.new_conversation(project['id'],'Synthetic conversation')
    artifact=ArtifactIndex(id='art_test',project_id=project['id'],title='Synthetic source',kind='report',media_type='application/json',storage_root='pathoreason_artifacts',relative_path='result.json',sha256=sha,size_bytes=len(blob),source_ref=ref,run_ref=None,stage_ref=None,verification_scope='bytes_verified',evidence_role='synthetic')
    store.add_artifact(artifact)
    request={'request_key':'req_once','text':'解释已有证据','model':'deepseek-v4-pro','skill_id':'results_explanation','artifact_ids':['art_test']}
    return svc,conv,request,runtime

async def settled(svc,tid):
    for _ in range(50):
        if svc.store.turn(tid)['status'] not in ('queued','running','interrupt_requested'):return
        await asyncio.sleep(.05)
    raise AssertionError('turn did not settle')

def test_success_report_skill_snapshot_and_durable_events(fixture):
    svc,conv,request,runtime=fixture
    async def case():
        result=await svc.submit(conv['id'],request);tid=result['turn']['id'];await settled(svc,tid)
        row=svc.store.turn(tid);assert row['status']=='completed';assert row['report_id']
        assert 'PRIVATE_REASONING' not in json.dumps(row) and 'HIDDEN_OUTPUT' not in json.dumps(row)
        assert 'First use the results-explanation skill' in runtime.calls[0][3]
        assert 'goal_achieved_dev' in runtime.calls[0][3]
        events=svc.store.events(conv['id'],0);assert len(events)>2
        assert [x['seq'] for x in events]==list(range(1,len(events)+1))
        for event in events:RuntimeEvent.model_validate(event)
        assert svc.store.events(conv['id'],events[0]['seq'])==events[1:]
        artifact=svc.store.artifact(row['report_id'],row['project_id']);assert '结果尚未'.encode() in svc.artifact_bytes(artifact)
        restored=Store(svc.store.path);assert restored.turn(tid)['text']==row['text']
        with restored.connect() as db:
            assert db.execute('SELECT COUNT(*) FROM context_snapshots').fetchone()[0]==1
            assert db.execute('SELECT COUNT(*) FROM skill_invocations').fetchone()[0]==1
            config=json.loads(db.execute('SELECT document FROM runtime_configs').fetchone()[0]);assert config['opencode']['compaction']['auto']
            assert config['skill']['version']=='0.2.0'
        await svc.close()
    asyncio.run(case())

def test_duplicate_request_never_dispatches_twice(fixture):
    svc,conv,request,runtime=fixture
    async def case():
        one=await svc.submit(conv['id'],request);two=await svc.submit(conv['id'],request)
        assert one['turn']['id']==two['turn']['id'];await settled(svc,one['turn']['id'])
        three=await svc.submit(conv['id'],request);assert three['turn']['id']==one['turn']['id'];assert len(runtime.calls)==1
        with pytest.raises(Conflict):await svc.submit(conv['id'],{**request,'text':'different payload'})
        await svc.close()
    asyncio.run(case())

def test_cross_project_reference_rejected(fixture):
    svc,conv,request,runtime=fixture
    async def case():
        p=svc.store.create_project('Other','Other');other=svc.new_conversation(p['id'],'Other')
        from pathoreason.persistence import Missing
        with pytest.raises(Missing):await svc.submit(other['id'],request)
        assert not runtime.calls
    asyncio.run(case())

def test_credential_failure_has_no_turn_or_dispatch(fixture,monkeypatch):
    svc,conv,request,runtime=fixture;monkeypatch.setattr('pathoreason.service.credential',lambda:'')
    async def case():
        with pytest.raises(NotReady):await svc.submit(conv['id'],request)
        assert svc.store.turns(conv['id'])==[] and runtime.calls==[]
    asyncio.run(case())

def test_stop_preserves_partial_response(fixture):
    svc,conv,request,runtime=fixture;runtime.hold=True
    async def case():
        turn=await svc.submit(conv['id'],request);tid=turn['turn']['id']
        for _ in range(30):
            if svc.store.turn(tid)['text']:break
            await asyncio.sleep(.05)
        await svc.interrupt(tid);await settled(svc,tid)
        assert runtime.abort_called and svc.store.turn(tid)['status']=='interrupted'
        assert svc.store.turn(tid)['text']=='正在解释'
        await svc.close()
    asyncio.run(case())

def test_restart_recovers_native_turn_without_reprompt(fixture):
    svc,conv,request,runtime=fixture;runtime.hold=True
    async def case():
        turn=await svc.submit(conv['id'],request);tid=turn['turn']['id']
        for _ in range(30):
            if svc.store.turn(tid)['dispatch_state']=='accepted':break
            await asyncio.sleep(.05)
        await svc.close();runtime.hold=False
        restored=Service(Store(svc.store.path),runtime,svc.config);await restored.recover();await settled(restored,tid)
        assert restored.store.turn(tid)['status']=='completed';assert len(runtime.calls)==1 and runtime.creates==1
        await restored.close()
    asyncio.run(case())

def test_unknown_dispatch_is_not_replayed(fixture):
    svc,conv,request,runtime=fixture
    async def case():
        original=runtime.prompt
        async def uncertain(*args,**kwargs):raise TimeoutError('lost receipt')
        runtime.prompt=uncertain
        turn=await svc.submit(conv['id'],request);tid=turn['turn']['id'];await settled(svc,tid)
        assert svc.store.turn(tid)['status']=='recovery_required'
        assert svc.store.turn(tid)['dispatch_state']=='dispatching'
        await svc.close();runtime.prompt=original
        assert len(runtime.calls)==0
    asyncio.run(case())

def test_single_active_turn_is_enforced(fixture):
    svc,conv,request,runtime=fixture;runtime.hold=True
    async def case():
        await svc.submit(conv['id'],request)
        with pytest.raises(Conflict):await svc.submit(conv['id'],{**request,'request_key':'req_second'})
        await svc.close()
    asyncio.run(case())

def test_runtime_view_excludes_reasoning_and_detects_compression():
    messages=[{'info':{'role':'user','id':'msg_u'},'parts':[{'type':'compaction'}]},{'info':{'role':'assistant','parentID':'msg_u','time':{'completed':1}},'parts':[{'type':'reasoning','text':'PRIVATE'},{'type':'text','text':'visible'}]}]
    response=visible_response(messages,'msg_u');assert response['compacted'] and response['text']=='visible';assert 'PRIVATE' not in json.dumps(response)


def test_acceptance_turn_limit_prevents_new_dispatch(fixture):
    svc,conv,request,runtime=fixture;svc.config['p1_test_limits']['max_turns']=1
    async def case():
        turn=await svc.submit(conv['id'],request);await settled(svc,turn['turn']['id'])
        with pytest.raises(Conflict,match='acceptance_budget_exhausted'):
            await svc.submit(conv['id'],{**request,'request_key':'second'})
        assert len(runtime.calls)==1
        await svc.close()
    asyncio.run(case())


def test_public_api_and_project_isolation(fixture,monkeypatch):
    from fastapi.testclient import TestClient
    import pathoreason.api as api_module
    svc,conv,request,runtime=fixture
    monkeypatch.setattr(api_module,'Service',lambda:svc)
    original=api_module.settings()
    monkeypatch.setattr(api_module,'settings',lambda:{**original,'data_root':str(svc.data)})
    with TestClient(api_module.app) as client:
        assert client.get('/health').status_code==200
        response=client.get('/api/v1/research-projects');assert response.status_code==200
        other=client.post('/api/v1/research-projects',json={'title':'Separate','objective':'Independent'}).json()
        assert client.get('/api/v1/research-projects/'+other['id']+'/artifacts').json()==[]
        assert client.get('/api/v1/research-projects/'+other['id']+'/artifacts/art_test/content').status_code==404
        assert client.get('/api/v1/research-projects/'+conv['project_id']+'/artifacts/art_test/content').content==b'{"goal_achieved_dev":false}'
        assert client.post('/api/v1/research-projects',json={'title':'bad','objective':'bad'},headers={'Origin':'https://other.example'}).status_code==403
        assert client.get('/health',headers={'Host':'evil.example'}).status_code==403
        assert client.post('/api/v1/conversations/'+conv['id']+'/turns',json={**request,'api_key':'not-allowed'}).status_code==422
        assert client.get('/api/v1/conversations/'+conv['id']+'/events?after=-1').status_code==400
        monkeypatch.setattr('pathoreason.service.credential',lambda:'')
        assert client.post('/api/v1/conversations/'+conv['id']+'/turns',json=request).status_code==503
        assert svc.store.turns(conv['id'])==[]


def test_stop_during_prompt_receipt_is_not_lost(fixture):
    svc,conv,request,runtime=fixture;runtime.hold=True
    async def case():
        entered=asyncio.Event();release=asyncio.Event();original=runtime.prompt
        async def delayed(*args,**kwargs):
            await original(*args,**kwargs);entered.set();await release.wait()
        runtime.prompt=delayed
        turn=await svc.submit(conv['id'],request);tid=turn['turn']['id'];await entered.wait()
        await svc.interrupt(tid);release.set();await settled(svc,tid)
        assert svc.store.turn(tid)['status']=='interrupted' and runtime.abort_called
        assert len(runtime.calls)==1
        await svc.close()
    asyncio.run(case())


def test_codex_auth_protocol_is_auth_only(monkeypatch):
    from pathoreason.codex_auth import CodexAuth
    auth=CodexAuth('unused');calls=[]
    async def ensure():pass
    async def rpc(method,params):
        calls.append((method,params))
        if method=='account/login/start':return {'loginId':'login_test','verificationUrl':'https://auth.openai.com/test','userCode':'TEST-CODE'}
        if method=='account/read':return {'account':None}
        return {}
    monkeypatch.setattr(auth,'ensure',ensure);monkeypatch.setattr(auth,'rpc',rpc)
    async def case():
        assert (await auth.status())['state']=='not_authenticated'
        assert (await auth.start())['state']=='pending'
        await auth.start();assert sum(m=='account/login/start' for m,_ in calls)==1
        assert (await auth.status())['server_inference_enabled'] is False
        assert (await auth.cancel())['state']=='cancelled'
        assert {m for m,_ in calls}=={'account/read','account/login/start','account/login/cancel'}
    asyncio.run(case())


def test_native_user_summary_is_not_context_compaction():
    messages=[{'info':{'id':'msg_u','role':'user','summary':{'diffs':[]}},'parts':[]},{'info':{'role':'assistant','parentID':'msg_u','finish':'tool-calls','time':{'completed':1}},'parts':[]}]
    result=visible_response(messages,'msg_u');assert result['compacted'] is False and result['complete'] is False
    messages.append({'info':{'role':'assistant','parentID':'msg_u','summary':True,'time':{'completed':2},'finish':'stop'},'parts':[]})
    assert visible_response(messages,'msg_u')['compacted'] is True


def test_skill_navigation_covers_catalog_in_workflow_order(fixture):
    from pathoreason.settings import ROOT
    from pathoreason.api import SkillCategory
    groups=[SkillCategory.model_validate(x) for x in json.loads((ROOT/'config/skill-navigation.json').read_text())]
    assert len({g.id for g in groups})==len(groups)
    ids=[sid for group in groups for stage in group.stages for sid in stage.skill_ids]
    assert len(set(ids))==len(ids)
    assert set(ids)=={s['id'] for s in fixture[0].skills()}
    assert ids.index('dataset_intake')<ids.index('mil_baseline')<ids.index('mechanism_study')<ids.index('results_explanation')<ids.index('manuscript')<ids.index('figures_typesetting')
    assert groups[0].stages[-1].cross_stage


def test_native_public_stream_filters_reasoning_and_duplicate_events(monkeypatch,tmp_path):
    from pathoreason.runtime import OpenCode
    events=[
        {'id':'e1','type':'session.next.reasoning.delta','properties':{'sessionID':'ses_test','assistantMessageID':'msg_a','textID':'r','delta':'PRIVATE'}},
        {'id':'e2','type':'session.next.text.delta','properties':{'sessionID':'ses_other','assistantMessageID':'msg_a','textID':'t','delta':'OTHER_PROJECT'}},
        {'id':'e3','type':'session.next.text.delta','properties':{'sessionID':'ses_test','assistantMessageID':'msg_a','textID':'t','delta':'Hello'}},
        {'id':'e3','type':'session.next.text.delta','properties':{'sessionID':'ses_test','assistantMessageID':'msg_a','textID':'t','delta':'Hello'}},
        {'id':'e4','type':'session.next.text.delta','properties':{'sessionID':'ses_test','assistantMessageID':'msg_a','textID':'t','delta':' world'}},
        {'id':'e5','type':'message.part.updated','properties':{'sessionID':'ses_test','part':{'type':'reasoning','messageID':'msg_b','id':'r','text':'SECRET'}}},
        {'id':'e6','type':'message.part.delta','properties':{'sessionID':'ses_test','messageID':'msg_b','partID':'r','field':'text','delta':'SECRET'}},
        {'id':'e7','type':'message.part.updated','properties':{'sessionID':'ses_test','part':{'type':'text','messageID':'msg_b','id':'t2','text':''}}},
        {'id':'e8','type':'message.part.delta','properties':{'sessionID':'ses_test','messageID':'msg_b','partID':'t2','field':'text','delta':'Public legacy'}}]
    class Response:
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        def raise_for_status(self):pass
        async def aiter_lines(self):
            for event in events:yield 'data: '+json.dumps(event)
    class Client:
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        def stream(self,*args,**kwargs):return Response()
    runtime=OpenCode(tmp_path,8522);monkeypatch.setattr(runtime,'client',Client)
    async def case():
        ready=asyncio.Event();values=[v async for v in runtime.public_text_updates('ses_test','test',ready)]
        assert ready.is_set() and values==[{'msg_a':'Hello'},{'msg_a':'Hello world'},{'msg_a':'Hello world','msg_b':''},{'msg_a':'Hello world','msg_b':'Public legacy'}]
    asyncio.run(case())


def test_live_text_is_kept_when_snapshot_has_not_materialized(fixture):
    svc,conv,request,runtime=fixture;runtime.hold=True
    original_messages=runtime.messages
    async def messages(sid,directory):
        result=await original_messages(sid,directory)
        for message in result:
            message['parts']=[p for p in message['parts'] if p['type']!='text']
        return result
    runtime.messages=messages
    async def public_text_updates(sid,directory,ready):
        ready.set()
        while not runtime.sessions[sid]:await asyncio.sleep(.01)
        yield {'msg_assistant':'Incremental public response'}
        await asyncio.sleep(10)
    runtime.public_text_updates=public_text_updates
    async def case():
        turn=await svc.submit(conv['id'],request);tid=turn['turn']['id']
        for _ in range(50):
            if svc.store.turn(tid)['text']:break
            await asyncio.sleep(.02)
        await asyncio.sleep(.6)
        assert svc.store.turn(tid)['text']=='Incremental public response'
        await svc.interrupt(tid);await settled(svc,tid)
        assert svc.store.turn(tid)['status']=='interrupted'
        assert svc.store.turn(tid)['text']=='Incremental public response'
        await svc.close()
    asyncio.run(case())
