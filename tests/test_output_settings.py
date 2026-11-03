import asyncio,json
import pytest
from pydantic import ValidationError
from test_p1_service import fixture,settled
from test_goals import start,accepted
from test_output_recovery import message
from pathoreason.api import TurnInput
from pathoreason.goals import GoalControl
from pathoreason.persistence import Conflict
from pathoreason.output_settings import configured_options,turn_output
from pathoreason.runtime import OpenCode,visible_response


def capture(runtime):
    original=runtime.prompt
    async def prompt(*args,output_limit_tokens=None,**kwargs):
        runtime.last_output_limit=output_limit_tokens
        return await original(*args,**kwargs)
    runtime.prompt=runtime.prompt_formal=prompt


@pytest.mark.parametrize('limit',[8192,32768,65536])
def test_output_choice_freezes_dispatches_and_does_not_raise_budget(fixture,limit):
    s,c,request,r=fixture;capture(r)
    async def case():
        before=dict(s.config['p1_test_limits'])
        request['output_limit_tokens']=limit
        v=await s.submit(c['id'],request);await settled(s,v['turn']['id'])
        assert s.store.turn(v['turn']['id'])['status']=='completed'
        assert r.last_output_limit==limit
        assert v['turn']['model']['output_limit_tokens']==limit
        assert v['turn']['model']['input_limit_tokens']==1000000-limit
        with s.store.connect() as db:
            frozen=json.loads(db.execute('SELECT document FROM runtime_configs WHERE digest=?',(v['turn']['config_digest'],)).fetchone()[0])
        assert frozen['output_limit_tokens']==limit
        assert (await s.submit(c['id'],request))['turn']['id']==v['turn']['id']
        with pytest.raises(Conflict):await s.submit(c['id'],{**request,'output_limit_tokens':16384})
        assert len(r.calls)==1 and s.config['p1_test_limits']==before
        assert {m['model'] for m in s.models()}=={'deepseek-v4-pro','deepseek-flash'}
        await s.close()
    asyncio.run(case())


def test_defaults_and_invalid_request_do_not_raise_limits(fixture):
    s,c,request,r=fixture;capture(r)
    assert all(o.default==8192 and o.choices==[8192,32768,65536] for o in configured_options())
    for value in [True,'32768',0,65537,1.5]:
        with pytest.raises(ValidationError):TurnInput(**request,output_limit_tokens=value)
    with pytest.raises(ValueError,match='output_limit_not_supported'):
        asyncio.run(s.submit(c['id'],{**request,'output_limit_tokens':16384}))
    assert not s.store.turns(c['id'])
    async def case():
        v=await s.submit(c['id'],request);await settled(s,v['turn']['id'])
        assert r.last_output_limit is None and v['turn']['model']['output_limit_tokens']==8192
        await s.close()
    asyncio.run(case())


def test_recovery_preserves_failed_turn_cas_and_stops_again_on_length(fixture):
    async def case():
        s,r,study,cid,tid,body=await start(fixture);capture(r)
        s.state(tid,'failed','runtime_output_limit');s.goals.process(tid)
        original=dict(s.store.turn(tid));before=s.formal.view(study.project_id)
        g=s.goals.view(cid);change=GoalControl(expected_revision=g.revision,action='resume',reasoning_effort='high',output_limit_tokens=32768)
        await s.goals.control(cid,change)
        with pytest.raises(Conflict):await s.goals.control(cid,change)
        await s.goals.tick();tid2=s.store.turns(cid)[-1]['id'];await accepted(s,tid2)
        assert r.last_output_limit==32768 and r.last_effort=='high'
        assert dict(s.store.turn(tid))==original
        after=s.formal.view(study.project_id)
        assert after.budget==before.budget and after.budget_revision==before.budget_revision
        assert after.used_turns==before.used_turns+1
        s.state(tid2,'failed','runtime_output_limit');s.goals.process(tid2)
        await s.goals.tick();await s.goals.tick()
        assert len(r.calls)==2 and s.goals.view(cid).state=='blocked'
        with pytest.raises(ValueError):await s.goals.control(cid,GoalControl(expected_revision=s.goals.view(cid).revision,action='resume',output_limit_tokens=16384))
        assert s.goals.view(cid).state=='blocked'
        await s.close()
    asyncio.run(case())


def test_last_response_tokens_are_not_aggregate_and_no_reasoning_leaks():
    early=message('tool-calls');early['info']['tokens'].update(output=80,reasoning=12)
    result=visible_response([early,message()],'msg_user')
    assert result['usage']['output_tokens']==80
    assert result['usage']['last_output_tokens']==0
    assert result['usage']['last_reasoning_tokens']==8192
    assert result['usage']['finish_reason']=='length'
    assert 'PRIVATE_REASONING' not in json.dumps(result)


def test_legacy_diagnostic_reads_native_without_rewriting_history(fixture):
    async def case():
        s,r,study,cid,tid,body=await start(fixture)
        s.state(tid,'failed','runtime_output_limit')
        s.store.update(tid,usage=json.dumps({'output_tokens':0}))
        original=dict(s.store.turn(tid));native_parent=original['native_message_id']
        async def messages(*args):return [message(parent=native_parent),message(parent='other')]
        r.messages=messages
        v=await turn_output(s,tid)
        assert v.reasoning_tokens==8192 and v.output_tokens==0 and v.output_limit_tokens==8192
        assert v.source=='native_read_only' and 'PRIVATE' not in v.model_dump_json()
        assert dict(s.store.turn(tid))==original
        async def unavailable(*args):raise OSError('offline')
        r.messages=unavailable
        assert (await turn_output(s,tid)).reasoning_tokens is None
        await s.close()
    asyncio.run(case())


def test_native_stale_profile_fails_before_prompt(tmp_path):
    r=OpenCode(tmp_path,1);calls=[]
    async def call(method,path,directory=None,body=None):
        calls.append(path);return {'all':[{'id':'deepseek-direct','models':{}}]}
    r.call=call
    with pytest.raises(ValueError,match='output_profile_reload_required'):
        asyncio.run(r.prompt_formal('ses_test','/test','msg_test','deepseek-flash','hello','high',32768))
    assert all(not p.endswith('prompt_async') for p in calls)
    with pytest.raises(ValidationError,match='requires_resume'):
        GoalControl(expected_revision=1,action='pause',output_limit_tokens=32768)


def test_larger_output_reserves_context_before_consuming_a_turn(fixture,monkeypatch):
    from types import SimpleNamespace
    s,c,request,r=fixture
    monkeypatch.setattr(s.context,'view',lambda cid:SimpleNamespace(operations=[],context_tokens=950000,native_bound=False))
    with pytest.raises(Conflict,match='context_window_requires_compaction_or_handoff'):
        asyncio.run(s.submit(c['id'],{**request,'output_limit_tokens':65536}))
    assert not s.store.turns(c['id']) and not r.calls


def test_http_output_options_and_diagnostics_are_read_only(fixture,monkeypatch):
    from fastapi.testclient import TestClient
    import pathoreason.api as api
    s,c,request,r=fixture
    async def setup():
        result=await s.submit(c['id'],request);await settled(s,result['turn']['id']);return result['turn']['id']
    tid=asyncio.run(setup());before=dict(s.store.turn(tid))
    monkeypatch.setattr(api,'Service',lambda:s)
    original=api.settings();monkeypatch.setattr(api,'settings',lambda:{**original,'data_root':str(s.data)})
    with TestClient(api.app) as client:
        options=client.get('/api/v2/models/output');assert options.status_code==200
        assert all(v['default']==8192 for v in options.json())
        result=client.get('/api/v2/turns/'+tid+'/output');assert result.status_code==200
        assert result.json()['reasoning_tokens']==4 and result.json()['output_tokens']==20
        assert client.get('/api/v2/turns/turn_missing/output').status_code==404
    assert dict(s.store.turn(tid))==before and len(r.calls)==1
