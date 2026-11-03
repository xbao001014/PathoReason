"""Legacy choice recovery and deterministic scope failures, without widening gates."""
import asyncio,json
from pathlib import Path
import pytest
from test_p1_service import fixture
from test_goals import start,accepted,finish
from test_task_progression import config,report,decision
from pathoreason.guidance import OfferInput
from pathoreason.goals import GoalCheckpoint,GoalControl
from pathoreason.persistence import Conflict,encoded
from pathoreason.permission_settings import PermissionSettings,PermissionSettingsUpdate,formal_rules
from pathoreason.service import Service

async def legacy_choice(fixture,source_scope='standard'):
    if source_scope=='standard':s,r,v,cid,tid,body=await start(fixture)
    else:
        from test_guidance import offered
        s,r,v,cid,_,_,initial,_,body=await offered(fixture,options=[dict(id='inspect',label='只检查已有文件',scope='inspect')])
        s.goals.start=lambda:None;r.hold=True
        body={**body,'goal_mode':'continuous'}
        turn=await s.submit(cid,{**body,'request_key':'inspection_goal','text':'只检查已有文件',
            'guidance_selection':dict(guidance_id=initial['guidance_id'],option_id='inspect')})
        tid=turn['turn']['id'];await accepted(s,tid)
    receipt=decision(s,tid)
    # Simulate an immutable offer made by the previous release, before validation.
    with s.store.connect(True) as db:
        row=db.execute('SELECT payload FROM conversation_guidance WHERE id=?',(receipt['guidance_id'],)).fetchone()
        payload=json.loads(row[0]);payload['options'][0]['scope']='clarify'
        db.execute('UPDATE conversation_guidance SET payload=? WHERE id=?',(encoded(payload),receipt['guidance_id']))
    await finish(s,r,tid)
    result=await s.submit(cid,{**body,'request_key':'legacy_choice','text':'中文',
        'guidance_selection':{'guidance_id':receipt['guidance_id'],'option_id':'cn'}})
    selected=result['turn']['id'];await accepted(s,selected)
    assert config(s,selected)['execution_scope']=='dialogue'
    return s,r,v,cid,tid,selected,body


def test_active_goal_rejects_direction_only_offer_without_silently_granting_work(fixture):
    async def case():
        s,r,v,cid,tid,body=await start(fixture)
        offer=OfferInput(turn_id=tid,grant=s.guidance.grant(tid),kind='clarification',question='Next?',
            options=[dict(id='save',label='Save a report without running experiments',scope='clarify')])
        with pytest.raises(Conflict,match='guidance_goal_scope_conflict'):s.guidance.publish(offer)
        assert s.guidance.view(tid) is None
        offer.options[0].scope='continue'
        assert s.guidance.publish(offer)['status']=='saved'
        await finish(s,r,tid);await s.goals.tick()
        assert len(s.store.turns(cid))==1 and s.goals.view(cid).state=='waiting_input'
        await s.close()
    asyncio.run(case())


def test_scope_rejection_is_durable_and_stops_first_turn_not_second(fixture):
    async def case():
        s,r,v,cid,source,tid,body=await legacy_choice(fixture)
        with pytest.raises(Conflict,match='goal_outside_turn_scope'):
            report(s,cid,tid,'blocked',evidence={'files':['outputs/not-read.md']})
        with s.store.connect() as db:
            rejected=db.execute('SELECT * FROM goal_checkpoint_rejections').fetchall()
            assert len(rejected)==1 and rejected[0]['turn_id']==tid
            assert s.goals.link(tid)['checkpoint'] is None
        await finish(s,r,tid)
        restored=Service(s.store,r,s.config);restored.goals.start=lambda:None
        await restored.goals.tick();await restored.goals.tick()
        goal=restored.goals.view(cid)
        assert goal.reason=='goal_scope_blocked' and goal.state=='blocked'
        assert goal.scope_recovery.source_turn_id==source
        assert len(r.calls)==2 and goal.turns_used==2
        assert restored.formal.view(v.project_id).used_turns==2
        await s.close();await restored.close()
    asyncio.run(case())


def test_invalid_grant_or_stale_revision_cannot_poison_settling(fixture):
    async def case():
        s,r,v,cid,source,tid,body=await legacy_choice(fixture)
        for grant,rev in [('wrong',s.goals.view(cid).revision),(s.guidance.grant(tid),1)]:
            with pytest.raises(Conflict):s.goals.checkpoint(GoalCheckpoint(turn_id=tid,grant=grant,
                expected_revision=rev,outcome='blocked',summary='Invalid',evidence={'files':['outputs/no.md']}))
        with s.store.connect() as db:assert db.execute('SELECT count(*) FROM goal_checkpoint_rejections').fetchone()[0]==0
        await s.close()
    asyncio.run(case())


def test_corrected_checkpoint_wins_but_rejection_history_remains(fixture):
    async def case():
        s,r,v,cid,source,tid,body=await legacy_choice(fixture)
        with pytest.raises(Conflict):report(s,cid,tid,'blocked',evidence={'files':['outputs/no.md']})
        report(s,cid,tid,'blocked',blocker={'kind':'input','required_action':'Resolve dialogue-only scope before file work'})
        await finish(s,r,tid);await s.goals.tick()
        assert s.goals.view(cid).reason=='agent_blocked' and s.goals.view(cid).blocker.kind=='input'
        with s.store.connect() as db:assert db.execute('SELECT count(*) FROM goal_checkpoint_rejections').fetchone()[0]==1
        assert len(r.calls)==2
        await s.close()
    asyncio.run(case())


def test_explicit_recovery_preserves_frozen_history_current_denies_and_budgets(fixture):
    async def case():
        s,r,v,cid,source,tid,body=await legacy_choice(fixture)
        original=config(s,tid)
        await finish(s,r,tid)
        r.hold=False
        async def native_get(method,path,directory=None,body=None):
            assert method=='GET' and path=='/permission';return []
        r.call=native_get
        # Permission changes are independent and may narrow access before recovery.
        await s.formal.permissions.update(cid,PermissionSettingsUpdate(expected_revision=0,
            settings=PermissionSettings(mode='custom',bash='deny',edit='allow')))
        r.hold=True
        goal=s.goals.view(cid);before=s.formal.view(v.project_id)
        with pytest.raises(Conflict,match='goal_scope_recovery_required'):
            await s.goals.control(cid,GoalControl(expected_revision=goal.revision,action='resume'))
        with pytest.raises(Conflict,match='not_available'):
            await s.goals.control(cid,GoalControl(expected_revision=goal.revision,action='resume',resume_scope='inspection'))
        control=GoalControl(expected_revision=goal.revision,action='resume',resume_scope='standard')
        await s.goals.control(cid,control)
        assert s.formal.view(v.project_id)==before  # control itself consumes nothing
        with pytest.raises(Conflict,match='goal_changed'):await s.goals.control(cid,control)
        await asyncio.gather(s.goals.tick(),s.goals.tick())
        follow=s.store.turns(cid)[-1]['id'];await accepted(s,follow)
        cfg=config(s,follow)
        assert cfg['execution_scope']=='standard' and cfg['permission_settings']['bash']=='deny'
        assert config(s,tid)==original and original['execution_scope']=='dialogue'
        assert s.goals.view(cid).turns_used==goal.turns_used+1
        assert s.goals.view(cid).max_turns==goal.max_turns
        assert s.formal.view(v.project_id).used_turns==before.used_turns+1
        assert json.loads((Path(v.workspace)/'compute.json').read_text())['real_training_authorized'] is False
        rules=formal_rules(v.workspace,PermissionSettings(**cfg['permission_settings']),cfg['execution_scope'])
        assert [x['action'] for x in rules if x['permission']=='bash'][-1]=='deny'
        path=Path(v.workspace)/'outputs/done.md';path.write_text('Fixture report, not scientific validation')
        report(s,cid,follow,'completed',evidence={'files':['outputs/done.md']})
        await finish(s,r,follow);await s.goals.tick()
        assert len(r.calls)==3 and s.goals.view(cid).state=='completed'
        await s.close()
    asyncio.run(case())


def test_ambiguous_acceptance_stops_without_offering_scope_escalation(fixture):
    async def case():
        s,r,v,cid,source,body=await start(fixture)
        decision(s,source);await finish(s,r,source)
        result=await s.submit(cid,{**body,'request_key':'ambiguous','text':'好'})
        tid=result['turn']['id'];await accepted(s,tid);await finish(s,r,tid);await s.goals.tick()
        goal=s.goals.view(cid)
        assert goal.reason=='goal_scope_blocked' and goal.scope_recovery is None
        with pytest.raises(Conflict,match='not_available'):
            await s.goals.control(cid,GoalControl(expected_revision=goal.revision,action='resume',resume_scope='standard'))
        assert len(r.calls)==2
        await s.close()
    asyncio.run(case())


def test_freeform_work_instruction_uses_normal_scope_and_keeps_goal(fixture):
    async def case():
        s,r,v,cid,source,tid,body=await legacy_choice(fixture)
        await finish(s,r,tid);previous=s.goals.view(cid)
        result=await s.submit(cid,{**body,'request_key':'new_instruction','text':'保存已有汇总，不新增训练或评估'})
        follow=result['turn']['id'];await accepted(s,follow)
        assert config(s,follow)['execution_scope']=='standard'
        assert s.goals.view(cid).id==previous.id and s.goals.view(cid).turns_used==previous.turns_used+1
        await s.close()
    asyncio.run(case())


def test_bridge_returns_actionable_scope_feedback_without_raw_input():
    from io import BytesIO
    from urllib.error import HTTPError
    from pathoreason.bridge_feedback import http_failure
    for code in ('guidance_goal_scope_conflict','goal_outside_turn_scope'):
        error=HTTPError('http://fixture',409,'Conflict',{},BytesIO(json.dumps({'detail':code}).encode()))
        result=http_failure(error)
        assert result['error']==code and result['next']
        assert 'grant' not in json.dumps(result)


def test_original_inspection_scope_cannot_be_upgraded_to_standard(fixture):
    async def case():
        s,r,v,cid,source,tid,body=await legacy_choice(fixture,'inspection')
        await finish(s,r,tid);goal=s.goals.view(cid)
        assert goal.scope_recovery.execution_scope=='inspection'
        with pytest.raises(Conflict,match='not_available'):
            await s.goals.control(cid,GoalControl(expected_revision=goal.revision,action='resume',resume_scope='standard'))
        await s.goals.control(cid,GoalControl(expected_revision=goal.revision,action='resume',resume_scope='inspection'))
        await s.goals.tick();follow=s.store.turns(cid)[-1]['id'];await accepted(s,follow)
        assert config(s,follow)['execution_scope']=='inspection'
        rules=formal_rules(v.workspace,PermissionSettings(mode='auto'),'inspection')
        assert [x['action'] for x in rules if x['permission']=='edit'][-1]=='deny'
        await s.close()
    asyncio.run(case())


def test_scope_recovery_cannot_increase_goal_turn_allowance(fixture):
    async def case():
        s,r,v,cid,source,tid,body=await legacy_choice(fixture)
        await finish(s,r,tid);goal=s.goals.view(cid)
        await s.goals.control(cid,GoalControl(expected_revision=goal.revision,action='revise',max_turns=goal.turns_used))
        goal=s.goals.view(cid)
        with pytest.raises(Conflict,match='goal_turn_limit'):
            await s.goals.control(cid,GoalControl(expected_revision=goal.revision,action='resume',resume_scope='standard'))
        assert s.goals.view(cid).turns_used==2 and len(r.calls)==2
        await s.close()
    asyncio.run(case())
