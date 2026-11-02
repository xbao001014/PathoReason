import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_p1_service import fixture, settled
from test_p5_entry import study, formal_runtime
from pathoreason.goals import GoalCheckpoint, GoalControl
from pathoreason.guidance import OfferInput
from pathoreason.persistence import Conflict
from pathoreason.service import Service


async def accepted(s,tid):
    for _ in range(100):
        if s.store.turn(tid)['dispatch_state']=='accepted':return
        await asyncio.sleep(.01)
    raise AssertionError('not accepted')


async def start(fixture, limit=12):
    s,_,request,r=fixture;formal_runtime(r);v=study(s,turns=limit)
    cid=s.store.conversations(v.project_id)[0]['id']
    s.goals.start=lambda:None  # deterministic ticks, same persisted controller
    r.hold=True
    body={**request,'request_key':'goal_initial','text':'完成两个连续准备节点，保留原证据','skill_id':None,
          'artifact_ids':[],'execution_mode':'research','goal_mode':'continuous'}
    result=await s.submit(cid,body);tid=result['turn']['id'];await accepted(s,tid)
    return s,r,v,cid,tid,body


def checkpoint(s,cid,tid,**kwargs):
    return s.goals.checkpoint(GoalCheckpoint(turn_id=tid,grant=s.guidance.grant(tid),
        expected_revision=s.goals.view(cid).revision,outcome='continue',summary='节点完成',next_action='推进下一节点',**kwargs))


async def finish(s,r,tid):
    r.hold=False;await settled(s,tid);s.goals.process(tid);r.hold=True


def test_goal_continues_without_user_turn_and_completes_on_evidence(fixture):
    async def case():
        s,r,v,cid,tid,body=await start(fixture)
        path=Path(v.workspace)/'outputs/first.json';path.write_text('{"stage":1}')
        receipt=checkpoint(s,cid,tid,evidence={'files':['outputs/first.json']})
        assert checkpoint(s,cid,tid,evidence={'files':['outputs/first.json']})==receipt
        await finish(s,r,tid)
        await asyncio.gather(s.goals.tick(),s.goals.tick())
        rows=s.store.turns(cid);assert len(rows)==2
        follow=rows[-1];await accepted(s,follow['id'])
        view=s.view(follow)
        assert view['origin']=='goal' and view['goal_id']==s.goals.view(cid).id
        assert 'NOT a new user instruction' in r.calls[-1][3]
        path2=Path(v.workspace)/'outputs/second.json';path2.write_text('{"stage":2}')
        s.goals.checkpoint(GoalCheckpoint(turn_id=follow['id'],grant=s.guidance.grant(follow['id']),
            expected_revision=s.goals.view(cid).revision,outcome='completed',summary='两个节点已完成',
            evidence={'files':['outputs/second.json']}))
        await finish(s,r,follow['id']);await s.goals.tick()
        assert s.goals.view(cid).state=='completed' and len(s.store.turns(cid))==2
        assert s.formal.view(v.project_id).used_turns==2
        assert s.store.turn(tid)['text']==rows[0]['text']
        assert s.goals.view(cid).scientific_approval is False
        await s.close()
    asyncio.run(case())


def test_restart_keeps_goal_and_does_not_duplicate_continuation(fixture):
    async def case():
        s,r,v,cid,tid,body=await start(fixture)
        checkpoint(s,cid,tid)
        await finish(s,r,tid);await s.goals.tick()
        auto=s.store.turns(cid)[-1]['id'];await accepted(s,auto)
        await s.close()
        restored=Service(s.store,r,s.config);restored.goals.start=lambda:None
        r.hold=False;await restored.recover();await settled(restored,auto)
        await restored.goals.tick()
        assert len(r.calls)==2 and len(restored.store.turns(cid))==2
        assert restored.goals.view(cid).state=='blocked'  # two no-progress turns
        await restored.close()
    asyncio.run(case())


def test_pause_invalidates_checkpoint_and_stops_automatic_turns(fixture):
    async def case():
        s,r,v,cid,tid,body=await start(fixture)
        old=s.goals.view(cid).revision
        await s.goals.control(cid,GoalControl(expected_revision=old,action='pause'))
        assert s.goals.view(cid).state=='paused' and r.abort_called
        with pytest.raises(Conflict):checkpoint(s,cid,tid)
        r.hold=False;await settled(s,tid);await s.goals.tick()
        assert len(s.store.turns(cid))==1
        with pytest.raises(Conflict,match='goal_changed'):
            await s.goals.control(cid,GoalControl(expected_revision=old,action='resume'))
        await s.close()
    asyncio.run(case())


def test_cancel_is_terminal_and_new_goal_retains_project_usage(fixture):
    async def case():
        s,r,v,cid,tid,body=await start(fixture)
        old=s.goals.view(cid)
        await s.goals.control(cid,GoalControl(expected_revision=old.revision,action='cancel'))
        assert s.goals.view(cid).state=='cancelled' and r.abort_called
        r.hold=False;await settled(s,tid);await s.goals.tick()
        assert len(s.store.turns(cid))==1
        await s.goals.control(cid,GoalControl(expected_revision=old.revision,action='pause'))
        assert s.goals.view(cid).state=='cancelled'
        with pytest.raises(Conflict,match='already_terminal'):
            await s.goals.control(cid,GoalControl(expected_revision=s.goals.view(cid).revision,action='resume'))
        r.hold=True
        new=await s.submit(cid,{**body,'request_key':'new_goal','text':'新的独立目标'})
        await accepted(s,new['turn']['id'])
        assert s.goals.view(cid).id!=old.id and s.goals.view(cid).turns_used==1
        assert s.formal.view(v.project_id).used_turns==2
        await s.close()
    asyncio.run(case())


def test_missing_checkpoint_has_only_one_repair_continuation(fixture):
    async def case():
        s,r,v,cid,tid,body=await start(fixture)
        await finish(s,r,tid);await s.goals.tick()
        auto=s.store.turns(cid)[-1]['id'];await accepted(s,auto)
        await finish(s,r,auto);await s.goals.tick()
        assert len(s.store.turns(cid))==2
        assert s.goals.view(cid).reason=='goal_no_progress'
        await s.close()
    asyncio.run(case())


def test_repeated_evidence_stops_even_with_new_summary(fixture):
    async def case():
        s,r,v,cid,tid,body=await start(fixture)
        (Path(v.workspace)/'outputs/same.txt').write_text('same evidence')
        for index in range(3):
            checkpoint(s,cid,tid,evidence={'files':['outputs/same.txt']})
            await finish(s,r,tid);await s.goals.tick()
            if index<2:
                tid=s.store.turns(cid)[-1]['id'];await accepted(s,tid)
        assert s.goals.view(cid).reason=='goal_no_progress' and len(s.store.turns(cid))==3
        await s.close()
    asyncio.run(case())


def test_existing_project_budget_stops_goal_without_reset(fixture):
    async def case():
        s,r,v,cid,tid,body=await start(fixture,limit=1)
        checkpoint(s,cid,tid);await finish(s,r,tid);await s.goals.tick()
        assert s.goals.view(cid).state=='budget_exhausted'
        assert s.formal.view(v.project_id).used_turns==1 and len(r.calls)==1
        await s.close()
    asyncio.run(case())


def test_changed_evidence_and_cross_project_claims_are_rejected(fixture):
    async def case():
        s,r,v,cid,tid,body=await start(fixture)
        with pytest.raises(Exception):checkpoint(s,cid,tid,evidence={'artifact_ids':['art_test']})
        with pytest.raises(ValueError):checkpoint(s,cid,tid,evidence={'files':['../secret']})
        path=Path(v.workspace)/'outputs/change.txt';path.write_text('v1')
        checkpoint(s,cid,tid,evidence={'files':['outputs/change.txt']});path.write_text('v2')
        await finish(s,r,tid);await s.goals.tick()
        assert s.goals.view(cid).reason=='goal_evidence_changed' and len(r.calls)==1
        await s.close()
    asyncio.run(case())


def test_clarification_does_not_get_automatically_selected(fixture):
    async def case():
        s,r,v,cid,tid,body=await start(fixture)
        s.guidance.publish(OfferInput(turn_id=tid,grant=s.guidance.grant(tid),kind='clarification',
            question='使用哪种目标？',options=[{'id':'a','label':'方向 A','scope':'plan'},{'id':'b','label':'方向 B','scope':'plan'}]))
        await finish(s,r,tid);await s.goals.tick()
        assert s.goals.view(cid).state=='waiting_input' and len(r.calls)==1
        next_turn=await s.submit(cid,{**body,'request_key':'user_choice','text':'采用方向 A'})
        await accepted(s,next_turn['turn']['id'])
        assert s.goals.view(cid).turns_used==2 and s.view(s.store.turn(next_turn['turn']['id']))['origin']=='user'
        await s.close()
    asyncio.run(case())


def test_single_turn_pauses_goal_and_scope_is_inherited(fixture):
    async def case():
        s,r,v,cid,tid,body=await start(fixture)
        checkpoint(s,cid,tid);await finish(s,r,tid)
        single=await s.submit(cid,{**body,'request_key':'single','text':'只解释现状','goal_mode':'single'})
        assert s.goals.view(cid).state=='paused' and s.goals.link(single['turn']['id']) is None
        await s.close()
    asyncio.run(case())


def test_unregistered_wait_and_false_completion_are_rejected(fixture,monkeypatch):
    async def case():
        s,r,v,cid,tid,body=await start(fixture)
        monkeypatch.setattr(s.business,'inspect',lambda _:SimpleNamespace(run_id=None))
        base=dict(turn_id=tid,grant=s.guidance.grant(tid),expected_revision=s.goals.view(cid).revision,summary='done')
        with pytest.raises(ValueError,match='evidence_required'):
            s.goals.checkpoint(GoalCheckpoint(**base,outcome='completed'))
        with pytest.raises(Conflict,match='not_registered'):
            s.goals.checkpoint(GoalCheckpoint(**base,outcome='waiting',wait_for={'kind':'synthetic_run','run_id':'fake'}))
        with pytest.raises(Conflict,match='grant_invalid'):
            s.goals.checkpoint(GoalCheckpoint(**{**base,'grant':'wrong'},outcome='blocked'))
        await s.close()
    asyncio.run(case())


def test_registered_wait_wakes_without_model_polling(fixture,monkeypatch):
    async def case():
        s,r,v,cid,tid,body=await start(fixture)
        view=SimpleNamespace(run_id='synthetic_registered',status='running')
        monkeypatch.setattr(s.business,'inspect',lambda _:view)
        s.goals.checkpoint(GoalCheckpoint(turn_id=tid,grant=s.guidance.grant(tid),
            expected_revision=s.goals.view(cid).revision,outcome='waiting',summary='等待平台作业',
            wait_for={'kind':'synthetic_run','run_id':view.run_id},next_action='读取真实作业回执'))
        await finish(s,r,tid)
        for _ in range(3):await s.goals.tick()
        assert len(r.calls)==1 and s.goals.view(cid).state=='waiting'
        view.status='completed';await s.goals.tick();await s.goals.tick()
        assert len(s.store.turns(cid))==2
        await s.close()
    asyncio.run(case())


def test_paused_goal_is_not_resumed_by_a_status_message(fixture):
    async def case():
        s,r,v,cid,tid,body=await start(fixture)
        checkpoint(s,cid,tid);await finish(s,r,tid)
        await s.goals.control(cid,GoalControl(expected_revision=s.goals.view(cid).revision,action='pause'))
        status=await s.submit(cid,{**body,'request_key':'status_question','text':'目前什么情况？'})
        await accepted(s,status['turn']['id'])
        assert s.goals.view(cid).state=='paused' and s.goals.link(status['turn']['id']) is None
        assert 'persistent goal is PAUSED' in r.calls[-1][3]
        await s.close()
    asyncio.run(case())


def test_user_can_revise_goal_limit_without_erasing_usage(fixture):
    async def case():
        s,r,v,cid,tid,body=await start(fixture)
        checkpoint(s,cid,tid);await finish(s,r,tid)
        edited=await s.goals.control(cid,GoalControl(expected_revision=s.goals.view(cid).revision,
            action='revise',objective='只完成源代码准备',max_turns=12))
        assert edited.objective=='只完成源代码准备' and edited.turns_used==1 and edited.max_turns==12 and edited.state=='paused'
        with s.store.connect() as db:
            history=[json.loads(r[0]) for r in db.execute('SELECT document FROM goal_events')]
        assert history[0]['snapshot']['objective']==body['text']
        await s.goals.control(cid,GoalControl(expected_revision=edited.revision,action='resume'))
        await s.goals.tick();assert len(s.store.turns(cid))==2
        await s.close()
    asyncio.run(case())


def test_goal_archive_and_delete_do_not_resurrect_or_erase_budget(fixture):
    async def case():
        s,r,v,cid,tid,body=await start(fixture)
        checkpoint(s,cid,tid);await finish(s,r,tid)
        r.hold=False
        async def native_call(*args):return []
        r.call=native_call
        await s.conversations.archive(cid)
        assert s.goals.view(cid).state=='paused'
        await s.conversations.archive(cid,restore=True);await s.goals.tick()
        assert len(s.store.turns(cid))==1
        async def delete_session(*args):pass
        r.delete_session=delete_session
        await s.conversations.delete(cid)
        with s.store.connect() as db:
            for table in ['goal_turns','research_goals','goal_events']:
                assert db.execute('SELECT count(*) FROM '+table).fetchone()[0]==0
            assert db.execute('SELECT count(*) FROM turns WHERE project_id=?',(v.project_id,)).fetchone()[0]==1
        await s.close()
    asyncio.run(case())


def test_unknown_dispatch_blocks_without_new_request(fixture):
    async def case():
        s,r,v,cid,tid,body=await start(fixture)
        s.state(tid,'recovery_required','dispatch_outcome_unknown')
        await s.goals.tick()
        assert s.goals.view(cid).state=='blocked'
        assert s.goals.view(cid).reason=='dispatch_outcome_unknown' and len(r.calls)==1
        await s.close()
    asyncio.run(case())


def test_answer_only_cannot_close_an_existing_goal(fixture):
    async def case():
        s,r,v,cid,tid,body=await start(fixture)
        checkpoint(s,cid,tid);await finish(s,r,tid);await s.goals.tick()
        auto=s.store.turns(cid)[-1]['id'];await accepted(s,auto)
        with pytest.raises(Conflict,match='answer_cannot'):
            s.goals.checkpoint(GoalCheckpoint(turn_id=auto,grant=s.guidance.grant(auto),
                expected_revision=s.goals.view(cid).revision,outcome='completed',summary='一句回复',answer_only=True))
        await s.close()
    asyncio.run(case())


def test_native_checkpoint_remains_available_without_shell_permission():
    from pathoreason.permission_settings import formal_rules,PermissionSettings
    for scope in ('standard','dialogue','inspection'):
        rules=formal_rules('/synthetic',PermissionSettings(mode='custom',bash='deny'),scope)
        assert [r for r in rules if r['permission']=='pathoreason_dialogue_checkpoint'][-1]['action']=='allow'
        assert [r for r in rules if r['permission']=='bash'][-1]['action']=='deny'


def test_explicit_single_mode_preserves_old_idempotency(fixture):
    async def case():
        s,conv,body,r=fixture
        first=await s.submit(conv['id'],body)
        again=await s.submit(conv['id'],{**body,'goal_mode':'single'})
        assert first['turn']['id']==again['turn']['id'] and s.goals.view(conv['id']) is None
        await s.close()
    asyncio.run(case())


def test_auto_continuation_cannot_widen_selected_readonly_scope(fixture):
    from test_guidance import offered,choice_body
    async def case():
        s,r,v,cid,tid,offer,receipt,art,body=await offered(fixture,options=[{'id':'read','label':'检查当前材料','scope':'inspect'}])
        s.goals.start=lambda:None;r.hold=True
        request={**choice_body(body,receipt,option='read'),'text':'检查当前材料','goal_mode':'continuous'}
        selected=await s.submit(cid,request);tid=selected['turn']['id'];await accepted(s,tid)
        checkpoint(s,cid,tid);await finish(s,r,tid);await s.goals.tick()
        auto=s.store.turns(cid)[-1]
        with s.store.connect() as db:
            frozen=json.loads(db.execute('SELECT document FROM runtime_configs WHERE digest=?',
                (json.loads(auto['document'])['config_digest'],)).fetchone()[0])
        assert frozen['execution_scope']=='inspection'
        await s.close()
    asyncio.run(case())


def test_goal_http_routes_require_bridge_and_preserve_user_pause(fixture,monkeypatch):
    import time
    from fastapi.testclient import TestClient
    import pathoreason.api as api_module
    s,_,request,r=fixture;formal_runtime(r);v=study(s,turns=5);r.hold=True
    cid=s.store.conversations(v.project_id)[0]['id']
    monkeypatch.setattr(api_module,'Service',lambda:s)
    original=api_module.settings()
    monkeypatch.setattr(api_module,'settings',lambda:{**original,'data_root':str(s.data)})
    with TestClient(api_module.app) as client:
        body={**request,'goal_mode':'continuous','skill_id':None,'artifact_ids':[]}
        sent=client.post('/api/v1/conversations/'+cid+'/turns',json=body)
        assert sent.status_code==202
        tid=sent.json()['turn']['id']
        for _ in range(40):
            if s.store.turn(tid)['status']=='running':break
            time.sleep(.02)
        goal=client.get('/api/v2/conversations/'+cid+'/goal').json()
        check=dict(turn_id=tid,grant=s.guidance.grant(tid),expected_revision=goal['revision'],
            outcome='blocked',summary='执行后端尚未接通')
        assert client.post('/internal/goal-checkpoint',json=check).status_code==403
        result=client.post('/internal/goal-checkpoint',json=check,headers={'Authorization':'Bearer '+s.guidance.token()})
        assert result.status_code==200 and 'grant' not in result.text
        # Stop must remain effective even if the visible revision is slightly old.
        stopped=client.post('/api/v2/conversations/'+cid+'/goal',json={'action':'pause','expected_revision':1})
        assert stopped.status_code==200 and stopped.json()['state']=='paused'
        assert client.post('/internal/goal-checkpoint',json=check,headers={'Authorization':'Bearer '+s.guidance.token()}).status_code==409
