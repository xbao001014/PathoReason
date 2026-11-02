import asyncio
import json
from pathlib import Path
import pytest
from test_p1_service import fixture
from test_p5_entry import study
from test_goals import start,checkpoint,finish,accepted
from pathoreason.budget_settings import BudgetSettingsUpdate
from pathoreason.goals import GoalControl
from pathoreason.persistence import Conflict
from pathoreason.service import Service


def change(key='budget_change',**kwargs):
    return BudgetSettingsUpdate(request_key=key,**kwargs)


def project(max_turns=20,revision=0,seconds=120):
    return dict(expected_revision=revision,max_turns=max_turns,max_wall_seconds=seconds)


def goal(s,cid,max_turns=12,revision=None):
    v=s.goals.view(cid)
    return dict(goal_id=v.id,expected_revision=v.limit_revision if revision is None else revision,max_turns=max_turns)


def test_project_shared_append_only_idempotent_and_restart(fixture):
    async def case():
        s,_,_,r=fixture;v=study(s);cid=s.store.conversations(v.project_id)[0]['id']
        before={p:p.read_bytes() for p in Path(v.workspace).rglob('*') if p.is_file()}
        with s.store.connect() as db:original=db.execute('SELECT document FROM formal_studies WHERE project_id=?',(v.project_id,)).fetchone()[0]
        body=change(project=project())
        result=await s.budgets.update(cid,body)
        assert result.project.budget_revision==1 and result.project.used_turns==0
        assert (await s.budgets.update(cid,body)).project.budget_revision==1
        other=s.store.create_conversation(v.project_id,'Another',v.workspace)
        assert s.budgets.view(other['id']).project.budget.max_turns==20
        with pytest.raises(Conflict,match='idempotency'):await s.budgets.update(cid,change(project=project(21)))
        with pytest.raises(Conflict,match='revision'):await s.budgets.update(cid,change('stale',project=project(21)))
        with s.store.connect() as db:
            assert db.execute('SELECT document FROM formal_studies WHERE project_id=?',(v.project_id,)).fetchone()[0]==original
            assert db.execute('SELECT count(*) FROM budget_changes').fetchone()[0]==1
        assert all(p.read_bytes()==content for p,content in before.items())
        restored=Service(s.store,r,s.config)
        assert restored.budgets.view(cid).project.budget.max_turns==20
        assert study(s).project_id==v.project_id # original create key remains valid
        assert not r.calls
        await restored.close();await s.close()
    asyncio.run(case())


def test_running_edits_preserve_grant_and_frozen_configuration(fixture):
    async def case():
        s,r,v,cid,tid,body=await start(fixture)
        old=s.goals.view(cid);old_prompt=s.formal.prompt(s.store.turn(tid))
        def frozen(tid):
            with s.store.connect() as db:return json.loads(db.execute('SELECT document FROM runtime_configs WHERE digest=?',(json.loads(s.store.turn(tid)['document'])['config_digest'],)).fetchone()[0])
        first=frozen(tid)
        result=await s.budgets.update(cid,change(project=project(24),goal=goal(s,cid,16)))
        assert result.goal.revision==old.revision and result.goal.limit_revision==1
        assert result.goal.state=='active' and not r.abort_called
        assert frozen(tid)==first and s.formal.prompt(s.store.turn(tid))==old_prompt
        checkpoint(s,cid,tid);await finish(s,r,tid);await s.goals.tick()
        follow=s.store.turns(cid)[-1]['id'];await accepted(s,follow)
        assert len(s.store.turns(cid))==2 and frozen(follow)['invocation_policy']['max_turns']==24
        assert frozen(follow)['study_budget_revision']==1
        assert s.goals.view(cid).max_turns==16
        await s.close()
    asyncio.run(case())


def test_atomic_cas_usage_and_terminal_rejections(fixture):
    async def case():
        s,r,v,cid,tid,body=await start(fixture)
        await s.budgets.update(cid,change(goal=goal(s,cid,12)))
        with pytest.raises(Conflict,match='goal_limit_revision'):
            await s.budgets.update(cid,change('bad_cas',project=project(),goal=goal(s,cid,14,revision=0)))
        assert s.formal.view(v.project_id).budget_revision==0
        await s.goals.control(cid,GoalControl(expected_revision=s.goals.view(cid).revision,action='revise',max_turns=14))
        assert s.goals.view(cid).limit_revision==2
        with pytest.raises(Conflict,match='goal_limit_revision'):
            await s.budgets.update(cid,change('old_editor',goal=goal(s,cid,16,revision=1)))
        await s.goals.control(cid,GoalControl(expected_revision=s.goals.view(cid).revision,action='cancel'))
        with pytest.raises(Conflict,match='terminal'):
            await s.budgets.update(cid,change('terminal',project=project(),goal=goal(s,cid,16)))
        assert s.formal.view(v.project_id).budget_revision==0
        await s.close()
    asyncio.run(case())


def test_exhausted_limits_require_explicit_resume(fixture):
    async def case():
        s,r,v,cid,tid,body=await start(fixture,limit=1)
        await s.budgets.update(cid,change('one_goal',goal=goal(s,cid,1)))
        checkpoint(s,cid,tid);await finish(s,r,tid);await s.goals.tick()
        assert s.goals.view(cid).state=='budget_exhausted'
        await s.budgets.update(cid,change('project_only',project=project(3)))
        assert s.goals.view(cid).state=='budget_exhausted'
        await s.budgets.update(cid,change('both_available',goal=goal(s,cid,3)))
        assert s.goals.view(cid).state=='paused'
        await s.goals.tick();assert len(s.store.turns(cid))==1
        await s.goals.control(cid,GoalControl(expected_revision=s.goals.view(cid).revision,action='resume'))
        await s.goals.tick();follow=s.store.turns(cid)[-1]['id'];await accepted(s,follow)
        with pytest.raises(Conflict,match='budget_below_usage'):
            await s.budgets.update(cid,change('below_project',project=project(1,revision=1)))
        with pytest.raises(Conflict,match='goal_limit_below_usage'):
            await s.budgets.update(cid,change('below_goal',goal=goal(s,cid,1)))
        assert s.goals.view(cid).turns_used==2 and s.formal.view(v.project_id).used_turns==2
        await s.close()
    asyncio.run(case())


def test_http_validation_archive_and_no_model_calls(fixture,monkeypatch):
    from fastapi.testclient import TestClient
    import pathoreason.api as api
    s,_,_,r=fixture;v=study(s);cid=s.store.conversations(v.project_id)[0]['id']
    monkeypatch.setattr(api,'Service',lambda:s)
    original=api.settings();monkeypatch.setattr(api,'settings',lambda:{**original,'data_root':str(s.data)})
    url='/api/v2/conversations/'+cid+'/budget-settings'
    with TestClient(api.app) as client:
        assert client.get(url).json()['project']['budget_revision']==0
        assert client.put(url,json={'request_key':'empty'}).status_code==422
        assert client.put(url,json={'request_key':'too_large','project':project(1001)}).status_code==422
        result=client.put(url,json=change(project=project()).model_dump())
        assert result.status_code==200 and result.json()['project']['budget_revision']==1
        assert client.put(url,json=change('old',project=project()).model_dump()).status_code==409
        with s.store.connect(True) as db:
            row=s.store.conversation(cid);doc=json.loads(row['document']);doc['status']='archived'
            db.execute('UPDATE conversations SET document=? WHERE id=?',(json.dumps(doc),cid))
        assert client.put(url,json=change('archive',project=project(30,1)).model_dump()).status_code==409
        assert not r.calls


def test_active_turn_keeps_original_time_cap(fixture,monkeypatch):
    from test_p1_service import settled
    async def case():
        s,r,v,cid,tid,body=await start(fixture)
        await s.budgets.update(cid,change(project=project(seconds=120)))
        import pathoreason.timing as timing
        original=timing.totals
        monkeypatch.setattr(timing,'totals',lambda rows,at=None:{**original(rows,at),'budget_seconds':65.})
        monkeypatch.setattr('pathoreason.budget_settings.totals',timing.totals)
        await settled(s,tid)
        assert s.store.turn(tid)['status']=='failed' and r.abort_called
        assert s.formal.view(v.project_id).budget.max_wall_seconds==120
        with pytest.raises(Conflict,match='budget_below_usage'):
            await s.budgets.update(cid,change('below_time',project=project(revision=1,seconds=60)))
        await s.close()
    asyncio.run(case())


def test_context_blocker_survives_budget_update_and_cross_conversation_goal_is_rejected(fixture):
    async def case():
        s,r,v,cid,tid,body=await start(fixture)
        await finish(s,r,tid)
        with s.store.connect(True) as db:
            doc=s.goals._latest(db,cid);doc.update(state='blocked',reason='context_budget_exhausted')
            s.goals._save(db,doc,'test_context_blocker')
        await s.budgets.update(cid,change(project=project(),goal=goal(s,cid)))
        assert s.goals.view(cid).state=='blocked' and s.goals.view(cid).reason=='context_budget_exhausted'
        other=s.store.create_conversation(v.project_id,'Another',v.workspace)
        with pytest.raises(Conflict,match='goal_limit_revision'):
            await s.budgets.update(other['id'],change('wrong_conversation',goal=goal(s,cid)))
        await s.close()
    asyncio.run(case())
