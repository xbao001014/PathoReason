import asyncio
import json
import pytest
from test_p1_service import fixture,settled
from test_p5_entry import study,formal_runtime
from pathoreason.persistence import Conflict
from pathoreason.task_workspaces import TaskCodeRequest


def test_tool_binds_active_turn_project_and_rejects_stale_grant(fixture):
    async def case():
        s,_,req,r=fixture;formal_runtime(r);v=study(s);cid=s.store.conversations(v.project_id)[0]['id']
        r.hold=True
        result=await s.submit(cid,{**req,'request_key':'tasks','skill_id':None,'artifact_ids':[]})
        tid=result['turn']['id']
        for _ in range(50):
            if s.store.turn(tid)['status']=='running':break
            await asyncio.sleep(.01)
        body=TaskCodeRequest(turn_id=tid,grant=s.guidance.grant(tid),operation='list')
        assert s.task_code.call(body)['tasks']==[]
        with pytest.raises(Conflict,match='grant_invalid'):
            s.task_code.call(body.model_copy(update={'grant':'wrong'}))
        assert s.task_code.prompt() in s.prompt(s.store.turn(tid))
        r.hold=False;await settled(s,tid)
        with pytest.raises(Conflict,match='inactive'):s.task_code.call(body)
    asyncio.run(case())


def test_read_only_selection_blocks_repository_mutation(fixture):
    async def case():
        s,_,req,r=fixture;formal_runtime(r);v=study(s);cid=s.store.conversations(v.project_id)[0]['id'];r.hold=True
        result=await s.submit(cid,{**req,'request_key':'tasks','skill_id':None,'artifact_ids':[]});tid=result['turn']['id']
        for _ in range(50):
            if s.store.turn(tid)['status']=='running':break
            await asyncio.sleep(.01)
        with s.store.connect(True) as db:
            db.execute('INSERT INTO turn_guidance_context VALUES(?,?)',(tid,json.dumps({'selected_option_id':'read','proposal':{'options':[{'id':'read','scope':'inspect'}]}})))
        body=TaskCodeRequest(turn_id=tid,grant=s.guidance.grant(tid),operation='create',idempotency_key='blocked',objective='new task')
        with pytest.raises(Conflict,match='outside_turn_scope'):s.task_code.call(body)
        assert s.task_code.workspaces.list(v.project_id)==[]
        r.hold=False;await settled(s,tid)
    asyncio.run(case())
