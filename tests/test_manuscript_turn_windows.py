"""Review decisions renew bounded execution, never cumulative accounting."""
import asyncio
import json
from pathlib import Path

import pytest
from test_p1_service import fixture
from test_manuscript_review import setup, request_review, decision, accepted, finish
from test_goals import checkpoint
from test_budget_settings import change, goal as goal_limit
from pathoreason.goals import GoalControl, turns_in_window
from pathoreason.persistence import Conflict
from pathoreason.service import Service


async def next_turn(s,r,cid):
    r.hold=True
    await s.goals.tick()
    tid=s.store.turns(cid)[-1]['id']
    await accepted(s,tid)
    return tid


def test_each_gate_can_proceed_at_its_limit_without_erasing_usage(fixture):
    async def case():
        s,r,v,cid,tid,_=await setup(fixture)
        await s.budgets.update(cid,change(goal=goal_limit(s,cid,1)))
        original_budget=s.formal.view(v.project_id).budget.model_dump()
        for index,next_gate in enumerate(['draft','review','scientific','delivery','handoff']):
            request_review(s,v,cid,tid);await finish(s,r,tid)
            before=s.formal.view(v.project_id)
            await s.manuscripts.decide(cid,decision(s,cid))
            g=s.goals.view(cid)
            assert g.turns_used==index+1 and g.max_turns==1
            assert g.turn_window.start_turns==g.turns_used and g.turn_window.gate==next_gate
            assert turns_in_window(g.model_dump())==0
            assert s.formal.view(v.project_id).used_budget_seconds==before.used_budget_seconds
            assert s.formal.view(v.project_id).budget.model_dump()==original_budget
            tid=await next_turn(s,r,cid)
            assert s.goals.view(cid).turns_used==index+2
            assert s.formal.view(v.project_id).used_turns==index+2
            assert '"turns_in_window": 1' in r.calls[-1][3]
        await s.close()
    asyncio.run(case())


@pytest.mark.parametrize('action',['revise','clarify','reopen'])
def test_feedback_retries_stale_requests_and_model_packets_do_not_renew_twice(fixture,action):
    async def case():
        s,r,v,cid,tid,body=await setup(fixture)
        await s.budgets.update(cid,change(goal=goal_limit(s,cid,1)))
        request_review(s,v,cid,tid);await finish(s,r,tid)
        feedback=decision(s,cid,action,**({'target_gate':'blueprint'} if action=='reopen' else {}))
        await s.manuscripts.decide(cid,feedback)
        first=s.goals.view(cid)
        assert first.turn_window.gate=='blueprint' and first.turn_window.action==action
        tid=await next_turn(s,r,cid)
        # Agent replacement packets do not renew the node allowance.
        request_review(s,v,cid,tid);await finish(s,r,tid)
        await s.manuscripts.decide(cid,feedback)  # Lost-response retry after work.
        current=s.goals.view(cid)
        assert current.turn_window==first.turn_window
        assert turns_in_window(current.model_dump())==1 and current.turns_used==2
        stale=feedback.model_copy(update={'request_key':'stale_new_key'})
        with pytest.raises(Conflict,match='review_changed'):
            await s.manuscripts.decide(cid,stale)
        with pytest.raises(Conflict,match='goal_turn_limit'):
            await s.submit(cid,{**body,'request_key':'ordinary_chat'})
        assert s.goals.view(cid).turn_window==first.turn_window
        # A distinct valid feedback creates exactly one new window at this node.
        await s.manuscripts.decide(cid,decision(s,cid,'revise'))
        assert s.goals.view(cid).turn_window.start_turns==2
        assert s.goals.view(cid).turns_used==2
        await s.close()
    asyncio.run(case())


def test_failed_approval_and_paused_feedback_preserve_state(fixture):
    async def case():
        s,r,v,cid,tid,_=await setup(fixture)
        request_review(s,v,cid,tid,issues=[dict(id='block',finding='Needs correction',blocking=True)])
        await finish(s,r,tid)
        with pytest.raises(Conflict,match='unresolved_blockers'):
            await s.manuscripts.decide(cid,decision(s,cid))
        assert s.goals.view(cid).turn_window is None
        await s.goals.control(cid,GoalControl(expected_revision=s.goals.view(cid).revision,action='pause'))
        feedback=decision(s,cid,'revise')
        await s.manuscripts.decide(cid,feedback)
        saved=s.goals.view(cid)
        assert saved.state=='paused' and saved.turn_window.start_turns==1
        await s.goals.tick();assert len(r.calls)==1
        # Loading the new service must neither clear the window nor auto-resume.
        restored=Service(s.store,r,s.config);restored.goals.start=lambda:None
        assert restored.goals.view(cid).turn_window==saved.turn_window
        await restored.goals.tick();assert len(r.calls)==1
        await restored.goals.control(cid,GoalControl(expected_revision=saved.revision,action='resume'))
        await next_turn(restored,r,cid)
        assert restored.goals.view(cid).turns_used==2
        await restored.close();await s.close()
    asyncio.run(case())


@pytest.mark.parametrize('exhaustion',['turns','time'])
def test_project_limits_still_stop_after_review_reset(fixture,exhaustion):
    async def case():
        s,r,v,cid,tid,_=await setup(fixture,turns=1 if exhaustion=='turns' else 12)
        request_review(s,v,cid,tid);await finish(s,r,tid)
        if exhaustion=='time':
            # Synthetic fixture only: account a completed 61-second Agent turn.
            with s.store.connect(True) as db:
                row=s.store.turn(tid);doc=json.loads(row['document'])
                doc['finished_at']='2020-01-01T00:01:01Z'
                db.execute('UPDATE turns SET created_at=?,document=? WHERE id=?',('2020-01-01T00:00:00Z',json.dumps(doc),tid))
                db.execute('DELETE FROM turn_timing WHERE turn_id=?',(tid,))
        before=s.formal.view(v.project_id)
        await s.manuscripts.decide(cid,decision(s,cid,'revise'))
        assert turns_in_window(s.goals.view(cid).model_dump())==0
        await s.goals.tick()
        assert len(r.calls)==1 and s.goals.view(cid).reason=='acceptance_budget_exhausted'
        after=s.formal.view(v.project_id)
        assert after.used_turns==before.used_turns
        assert after.used_budget_seconds==before.used_budget_seconds
        await s.close()
    asyncio.run(case())


def test_window_limit_edits_use_current_usage_and_invalidate_old_editors(fixture):
    async def case():
        s,r,v,cid,tid,_=await setup(fixture)
        old_edit=change('old_editor',goal=goal_limit(s,cid,3))
        request_review(s,v,cid,tid);await finish(s,r,tid)
        await s.manuscripts.decide(cid,decision(s,cid,'approve'))
        with pytest.raises(Conflict,match='goal_limit_revision'):
            await s.budgets.update(cid,old_edit)
        await s.budgets.update(cid,change('node_limit',goal=goal_limit(s,cid,2)))
        tid=await next_turn(s,r,cid)
        # Lifetime is now two; a one-turn window limit is valid at window usage one.
        await s.budgets.update(cid,change('lower_to_one',goal=goal_limit(s,cid,1)))
        await s.budgets.update(cid,change('back_to_two',goal=goal_limit(s,cid,2)))
        (Path(v.workspace)/'outputs/window-first.txt').write_text('First evidence')
        checkpoint(s,cid,tid,evidence={'files':['outputs/window-first.txt']});await finish(s,r,tid)
        tid=await next_turn(s,r,cid)
        assert s.goals.view(cid).turns_used==3
        with pytest.raises(Conflict,match='goal_limit_below_usage'):
            await s.budgets.update(cid,change('too_low',goal=goal_limit(s,cid,1)))
        (Path(v.workspace)/'outputs/window-second.txt').write_text('Second evidence')
        checkpoint(s,cid,tid,evidence={'files':['outputs/window-second.txt']});await finish(s,r,tid)
        assert s.goals.view(cid).reason=='goal_turn_limit'
        assert turns_in_window(s.goals.view(cid).model_dump())==2
        await s.budgets.update(cid,change('add_one',goal=goal_limit(s,cid,3)))
        g=s.goals.view(cid);assert g.state=='paused'
        await s.goals.control(cid,GoalControl(expected_revision=g.revision,action='resume'))
        await next_turn(s,r,cid)
        assert s.goals.view(cid).turns_used==4
        await s.close()
    asyncio.run(case())
