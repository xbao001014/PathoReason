import asyncio,json
import pytest
from test_p1_service import fixture
from test_goals import start,finish,accepted
from pathoreason.goals import GoalCheckpoint,GoalControl
from pathoreason.permission_settings import PermissionSettings,PermissionSettingsUpdate,TOOLS
from pathoreason.persistence import Conflict


def policy(**overrides):
    return PermissionSettings(mode='custom',**{t:overrides.get(t,'deny') for t in TOOLS})


async def blocked(fixture,kind='permission'):
    s,r,v,cid,tid,body=await start(fixture)
    s.goals.checkpoint(GoalCheckpoint(turn_id=tid,grant=s.guidance.grant(tid),expected_revision=s.goals.view(cid).revision,
        outcome='blocked',summary='Original Agent blocker',blocker={'kind':kind,'required_action':'Original remedy',**({'capability':'training_execution'} if kind=='platform' else {})}))
    await finish(s,r,tid);r.hold=False
    async def no_pending(*args,**kwargs):return []
    r.call=no_pending
    return s,r,v,cid,tid,body


def test_same_custom_actions_do_not_change_goal(fixture):
    async def case():
        s,r,v,cid,tid,body=await blocked(fixture)
        initial=await s.formal.permissions.update(cid,PermissionSettingsUpdate(expected_revision=0,settings=PermissionSettings(mode='custom',**{t:'deny' for t in TOOLS})))
        before=s.goals.view(cid)
        saved=await s.formal.permissions.update(cid,PermissionSettingsUpdate(expected_revision=initial.revision,settings=policy()))
        assert saved.effective_actions=={t:'deny' for t in TOOLS}
        assert s.goals.view(cid)==before
        assert len(r.calls)==1
        await s.close()
    asyncio.run(case())


def test_effective_change_marks_permission_blocker_for_review_without_dispatch(fixture):
    async def case():
        s,r,v,cid,tid,body=await blocked(fixture)
        await s.formal.permissions.update(cid,PermissionSettingsUpdate(expected_revision=0,settings=policy()))
        original=s.store.turn(tid);g=s.goals.view(cid)
        with s.store.connect() as db:old_events=[tuple(x) for x in db.execute('SELECT * FROM goal_events ORDER BY id')]
        saved=await s.formal.permissions.update(cid,PermissionSettingsUpdate(expected_revision=1,settings=PermissionSettings(mode='auto',**{t:'deny' for t in TOOLS})))
        assert saved.effective_actions=={t:'allow' for t in TOOLS}
        updated=s.goals.view(cid)
        assert updated.state=='blocked' and updated.reason=='goal_permissions_updated'
        assert updated.id==g.id and updated.turns_used==g.turns_used
        await s.goals.tick();assert len(r.calls)==1
        assert s.store.turn(tid)==original
        with s.store.connect() as db:
            assert [tuple(x) for x in db.execute('SELECT * FROM goal_events ORDER BY id')][:len(old_events)]==old_events
        with pytest.raises(Conflict,match='revision_conflict'):
            await s.formal.permissions.update(cid,PermissionSettingsUpdate(expected_revision=1,settings=policy()))
        await s.goals.control(cid,GoalControl(expected_revision=updated.revision,action='resume'))
        r.hold=True
        await s.goals.tick();follow=s.store.turns(cid)[-1];await accepted(s,follow['id'])
        doc=json.loads(follow['document'])
        with s.store.connect() as db:cfg=json.loads(db.execute('SELECT document FROM runtime_configs WHERE digest=?',(doc['config_digest'],)).fetchone()[0])
        assert cfg['permission_revision']==2 and cfg['permission_settings']['bash']=='allow'
        assert 'Effective tool actions for this turn' in r.calls[-1][3] and '先按本轮冻结' in r.calls[-1][3]
        assert '"bash":"ask"' in s.formal.prompt(original).split('Effective tool actions for this turn')[1]
        assert s.formal.view(v.project_id).used_turns==2
        await s.close()
    asyncio.run(case())


@pytest.mark.parametrize('state,kind',[('blocked','platform'),('paused','permission'),('completed','permission'),('budget_exhausted','permission')])
def test_permission_save_does_not_clear_unrelated_or_user_stopped_goals(fixture,state,kind):
    async def case():
        s,r,v,cid,tid,body=await blocked(fixture,kind)
        if state!='blocked':
            with s.store.connect(True) as db:
                g=s.goals._latest(db,cid);g['state']=state;s.goals._save(db,g,'fixture_state')
        before=s.goals.view(cid)
        await s.formal.permissions.update(cid,PermissionSettingsUpdate(expected_revision=0,settings=PermissionSettings(mode='auto',**{t:'deny' for t in TOOLS})))
        assert s.goals.view(cid)==before and len(r.calls)==1
        await s.close()
    asyncio.run(case())


def test_permission_and_goal_projection_rollback_together(fixture,monkeypatch):
    async def case():
        s,r,v,cid,tid,body=await blocked(fixture)
        before=s.formal.permissions.view(cid);goal=s.goals.view(cid)
        def fail(*args):raise RuntimeError('receipt unavailable')
        monkeypatch.setattr(s.goals,'_save',fail)
        with pytest.raises(RuntimeError,match='receipt unavailable'):
            await s.formal.permissions.update(cid,PermissionSettingsUpdate(expected_revision=0,settings=PermissionSettings(mode='auto',**{t:'deny' for t in TOOLS})))
        assert s.formal.permissions.view(cid)==before and s.goals.view(cid)==goal
        await s.close()
    asyncio.run(case())
