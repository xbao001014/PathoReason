import asyncio
import json
from pathlib import Path

import pytest
from test_p1_service import fixture
from test_goals import start, accepted, finish
from test_guidance import offered
from pathoreason.guidance import OfferInput
from pathoreason.goals import GoalCheckpoint, GoalControl
from pathoreason.permission_settings import formal_rules, PermissionSettings
from pathoreason.persistence import Conflict


def config(s, tid):
    digest=json.loads(s.store.turn(tid)['document'])['config_digest']
    with s.store.connect() as db:
        return json.loads(db.execute('SELECT document FROM runtime_configs WHERE digest=?',(digest,)).fetchone()[0])


def report(s, cid, tid, outcome, **kwargs):
    return s.goals.checkpoint(GoalCheckpoint(turn_id=tid,grant=s.guidance.grant(tid),
        expected_revision=s.goals.view(cid).revision,outcome=outcome,summary='Actual fixture result',**kwargs))


def decision(s, tid, scope='continue', kind='clarification'):
    return s.guidance.publish(OfferInput(turn_id=tid,grant=s.guidance.grant(tid),kind=kind,
        question='选择报告语言',options=[{'id':'cn','label':'中文','scope':scope},{'id':'en','label':'英文','scope':scope}]))


@pytest.mark.parametrize('source_scope',['standard','inspection'])
@pytest.mark.parametrize('freeform',[False,True])
def test_decision_resumes_same_goal_without_widening_scope(fixture, source_scope, freeform):
    async def case():
        if source_scope=='standard':
            s,r,v,cid,tid,body=await start(fixture)
        else:
            s,r,v,cid,old,offer,receipt,art,body=await offered(fixture,options=[{'id':'read','label':'只读检查','scope':'inspect'}])
            s.goals.start=lambda:None;r.hold=True
            first=await s.submit(cid,{**body,'request_key':'inspect_goal','text':'只读检查','goal_mode':'continuous',
                'guidance_selection':{'guidance_id':receipt['guidance_id'],'option_id':'read'}})
            tid=first['turn']['id'];await accepted(s,tid)
        original=s.goals.view(cid)
        receipt=decision(s,tid)
        report(s,cid,tid,'needs_input')
        await finish(s,r,tid)
        assert s.goals.view(cid).state=='waiting_input'
        await s.goals.tick();count=s.formal.view(v.project_id).used_turns
        request={**body,'request_key':'resolve_choice','text':'中文','goal_mode':'continuous'}
        if not freeform:request['guidance_selection']={'guidance_id':receipt['guidance_id'],'option_id':'cn'}
        result=await s.submit(cid,request);selected=result['turn']['id'];await accepted(s,selected)
        assert s.goals.view(cid).id==original.id
        assert config(s,selected)['execution_scope']==source_scope
        assert s.guidance.view(tid).selected_option_id=='cn'
        assert (await s.submit(cid,request))['turn']['id']==selected
        assert s.formal.view(v.project_id).used_turns==count+1
        assert 'Apply it and advance the existing goal now' in r.calls[-1][3]
        rules=formal_rules(v.workspace,PermissionSettings(mode='custom',bash='deny'),source_scope)
        assert [x for x in rules if x['permission']=='bash'][-1]['action']=='deny'
        path=Path(v.workspace)/'outputs/progress.txt';path.write_text('fixture progress')
        report(s,cid,selected,'continue',next_action='Complete the remaining authorized node',evidence={'files':['outputs/progress.txt']})
        await finish(s,r,selected);await s.goals.tick()
        follow=s.store.turns(cid)[-1]['id'];await accepted(s,follow)
        assert s.goals.link(follow)['origin']=='goal'
        assert config(s,follow)['execution_scope']==source_scope
        path2=Path(v.workspace)/'outputs/done.txt';path2.write_text('fixture complete')
        report(s,cid,follow,'completed',evidence={'files':['outputs/done.txt']})
        await finish(s,r,follow);await s.goals.tick()
        assert s.goals.view(cid).state=='completed'
        await s.close()
    asyncio.run(case())


def test_routine_next_step_rejected_but_new_task_after_completion_is_available(fixture):
    async def case():
        s,r,v,cid,tid,body=await start(fixture)
        with pytest.raises(Conflict,match='guidance_routine_confirmation'):
            decision(s,tid,scope='plan',kind='next_step')
        path=Path(v.workspace)/'outputs/done.txt';path.write_text('actual fixture deliverable')
        report(s,cid,tid,'completed',evidence={'files':['outputs/done.txt']})
        with pytest.raises(Conflict,match='requires_current_goal'):decision(s,tid)
        decision(s,tid,scope='plan',kind='next_step')
        await finish(s,r,tid);await s.goals.tick()
        assert s.goals.view(cid).state=='completed'
        assert s.guidance.view(tid).status=='available'
        assert len(s.store.turns(cid))==1
        await s.close()
    asyncio.run(case())


def test_continue_choice_cannot_resume_a_paused_goal(fixture):
    async def case():
        s,r,v,cid,tid,body=await start(fixture)
        receipt=decision(s,tid);await finish(s,r,tid)
        await s.goals.control(cid,GoalControl(expected_revision=s.goals.view(cid).revision,action='pause'))
        with pytest.raises(Conflict,match='requires_current_goal'):
            await s.submit(cid,{**body,'request_key':'paused_choice','text':'中文',
                'guidance_selection':{'guidance_id':receipt['guidance_id'],'option_id':'cn'}})
        assert s.goals.view(cid).state=='paused' and len(s.store.turns(cid))==1
        await s.close()
    asyncio.run(case())


@pytest.mark.parametrize('single',[False,True])
def test_short_acceptance_only_selects_a_unique_proposal(fixture,single):
    async def case():
        options=[{'id':'read','label':'只读检查','scope':'inspect'}]
        if not single:options.append({'id':'plan','label':'修改方案','scope':'plan'})
        s,r,v,cid,tid,offer,receipt,art,body=await offered(fixture,options=options)
        r.hold=True
        result=await s.submit(cid,{**body,'request_key':'short_reply','text':'好，就这样。'})
        follow=result['turn']['id'];await accepted(s,follow)
        assert config(s,follow)['execution_scope']==('inspection' if single else 'dialogue')
        assert s.guidance.view(tid).selected_option_id==('read' if single else None)
        await s.close()
    asyncio.run(case())


def test_platform_blocker_does_not_become_resumable_by_adding_budget(fixture,monkeypatch):
    monkeypatch.setattr("pathoreason.training_sandbox.availability",lambda:{"available":False})
    monkeypatch.setattr("pathoreason.training_service.availability",lambda:{"available":False})
    from test_budget_settings import change,project
    async def case():
        s,r,v,cid,tid,body=await start(fixture)
        report(s,cid,tid,'blocked',blocker={'kind':'platform','capability':'training_execution',
            'required_action':'平台接通执行器；准备材料已保留，无需重复确认训练。'})
        await finish(s,r,tid)
        assert s.goals.view(cid).blocker.kind=='platform'
        await s.budgets.update(cid,change(project=project(24)))
        with pytest.raises(Conflict,match='goal_training_backend_not_ready'):
            await s.goals.control(cid,GoalControl(expected_revision=s.goals.view(cid).revision,action='resume'))
        assert s.goals.view(cid).state=='blocked' and len(r.calls)==1
        await s.goals.control(cid,GoalControl(expected_revision=s.goals.view(cid).revision,action='revise',objective='只整理已有准备材料'))
        assert s.goals.view(cid).blocker is None and s.goals.view(cid).state=='paused'
        await s.close()
    asyncio.run(case())


def test_continue_scope_requires_a_persistent_goal(fixture):
    async def case():
        s,r,v,cid,tid,offer,receipt,art,body=await offered(fixture)
        r.hold=True
        result=await s.submit(cid,{**body,'request_key':'ordinary','text':'解释当前材料'})
        follow=result['turn']['id'];await accepted(s,follow)
        with pytest.raises(Conflict,match='requires_current_goal'):decision(s,follow)
        await s.close()
    asyncio.run(case())


def test_ambiguous_reply_can_reask_then_return_to_original_goal_scope(fixture):
    async def case():
        s,r,v,cid,tid,body=await start(fixture)
        decision(s,tid);await finish(s,r,tid)
        result=await s.submit(cid,{**body,'request_key':'ambiguous','text':'按你说的来'})
        ambiguous=result['turn']['id'];await accepted(s,ambiguous)
        assert config(s,ambiguous)['execution_scope']=='dialogue'
        assert config(s,ambiguous)['goal_execution_scope']=='standard'
        decision(s,ambiguous);await finish(s,r,ambiguous)
        result=await s.submit(cid,{**body,'request_key':'resolved','text':'中文'})
        selected=result['turn']['id'];await accepted(s,selected)
        assert config(s,selected)['execution_scope']=='standard'
        assert s.goals.view(cid).turns_used==3
        await s.close()
    asyncio.run(case())
