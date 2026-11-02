"""Combined budget/context recovery regressions; isolated fake runtime only."""
import asyncio
import json

import pytest
from test_p1_service import fixture
from test_goals import accepted, checkpoint, finish
from test_context_recovery import blocked, native_compactor
from test_budget_settings import change, project, goal
from pathoreason.goals import GoalControl, GoalRecoveryInput
from pathoreason.persistence import Conflict
from pathoreason.service import Service


@pytest.mark.parametrize('action', ['compact', 'new_conversation'])
def test_budget_then_context_recovery_survives_restart_without_duplicate_dispatch(fixture, action):
    async def case():
        s, r, v, cid, tid, body = await blocked(fixture)
        calls = native_compactor(r)
        original_turn = s.store.turn(tid)
        original_goal = s.goals.view(cid)
        await s.budgets.update(cid, change('exhaust_project', project=project(1)))
        req = GoalRecoveryInput(goal_id=original_goal.id, expected_revision=original_goal.revision, action=action)
        with pytest.raises(Conflict, match='acceptance_budget_exhausted'):
            await s.goals.recover_context(cid, req)
        assert not calls and len(s.store.conversations(v.project_id)) == 1
        update = change('add_capacity', project=project(3, revision=1))
        result = await s.budgets.update(cid, update)
        assert result.goal.state == 'blocked'
        assert result.goal.reason == 'context_window_requires_compaction_or_handoff'
        assert result.goal.revision == original_goal.revision
        await s.goals.tick()
        assert len(r.calls) == 1 and s.store.turn(tid) == original_turn
        with pytest.raises(Conflict, match='context_recovery_required'):
            await s.goals.control(cid, GoalControl(expected_revision=original_goal.revision, action='resume'))
        await s.close()
        restored = Service(s.store, r, s.config)
        restored.goals.start = lambda: None
        await restored.recover()
        # Lost-save retry after restart uses the same receipt, not another revision.
        again = await restored.budgets.update(cid, update)
        assert again.project.budget_revision == 2 and again.project.used_turns == 1
        assert again.goal.state == 'blocked'
        resumed = await restored.goals.recover_context(cid, req)
        replay = await restored.goals.recover_context(cid, req)
        assert resumed.id == replay.id == original_goal.id
        assert resumed.conversation_id == replay.conversation_id
        assert resumed.turns_used == original_goal.turns_used == 1
        assert resumed.completion_criteria == original_goal.completion_criteria
        assert len(calls) == (1 if action == 'compact' else 0)
        assert len(restored.store.conversations(v.project_id)) == (2 if action == 'new_conversation' else 1)
        r.hold = True
        await asyncio.gather(restored.goals.tick(), restored.goals.tick())
        dest = resumed.conversation_id
        follow = restored.store.turns(dest)[-1]['id']
        await accepted(restored, follow)
        assert follow != tid and len(r.calls) == 2
        assert restored.goals.link(follow)['origin'] == 'goal'
        assert restored.goals.link(follow)['parent_turn_id'] == tid
        assert restored.formal.view(v.project_id).used_turns == 2
        assert restored.goals.view(dest).turns_used == 2
        assert restored.store.turn(tid) == original_turn
        with restored.store.connect() as db:
            digest = json.loads(restored.store.turn(follow)['document'])['config_digest']
            frozen = json.loads(db.execute('SELECT document FROM runtime_configs WHERE digest=?', (digest,)).fetchone()[0])
            assert frozen['study_budget_revision'] == 2
            assert frozen['invocation_policy']['max_turns'] == 3
        await restored.close()
    asyncio.run(case())


def test_limit_changed_during_compaction_prevents_followup_without_rewriting_usage(fixture, monkeypatch):
    async def case():
        s, r, v, cid, tid, body = await blocked(fixture)
        calls = native_compactor(r)
        compact = s.context.compact
        before = s.store.turn(tid)
        async def lower_during_compaction(*args):
            await s.budgets.update(cid, change('limit_during_recovery', goal=goal(s, cid, 1)))
            return await compact(*args)
        monkeypatch.setattr(s.context, 'compact', lower_during_compaction)
        g = s.goals.view(cid)
        result = await s.goals.recover_context(cid, GoalRecoveryInput(goal_id=g.id, expected_revision=g.revision, action='compact'))
        await s.goals.tick()
        assert result.max_turns == 1
        assert s.goals.view(cid).state == 'budget_exhausted'
        assert s.goals.view(cid).reason == 'goal_turn_limit'
        assert len(calls) == 1 and len(r.calls) == 1 and s.store.turn(tid) == before
        await s.budgets.update(cid, change('reopen_limit', goal=goal(s, cid, 3)))
        assert s.goals.view(cid).state == 'paused'
        await s.goals.tick()
        assert len(r.calls) == 1
        await s.goals.control(cid, GoalControl(expected_revision=s.goals.view(cid).revision, action='resume'))
        r.hold = True
        await s.goals.tick()
        await accepted(s, s.store.turns(cid)[-1]['id'])
        assert len(r.calls) == 2 and s.formal.view(v.project_id).used_turns == 2
        await s.close()
    asyncio.run(case())
