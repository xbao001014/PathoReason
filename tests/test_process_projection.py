import asyncio,json
import pytest
from pathoreason.process_projection import refresh_process
from pathoreason.persistence import Conflict
from test_p1_service import fixture,settled


def test_projection_keeps_original_records_and_budget_and_deletes_with_chat(fixture):
    s,c,request,r=fixture
    async def case():
        result=await s.submit(c['id'],request);tid=result['turn']['id'];await settled(s,tid)
        original=s.store.turn(tid);before=s.store.timing(tid)
        result=await refresh_process(s.store,r,tid)
        assert result['tool_count']==1 and result['original_records_unchanged']
        assert s.store.turn(tid)==original and s.store.timing(tid)==before
        assert s.view(original)['tools'][0]['kind']=='skill'
        with s.store.connect() as db:assert db.execute('SELECT 1 FROM turn_process_projection WHERE turn_id=?',(tid,)).fetchone()
        # A changed original record invalidates the projection instead of hiding new state.
        s.store.update(tid,tools='[]');assert s.view(s.store.turn(tid))['tools']==[]
        async def call(*args):return []
        async def delete(sid,directory):r.sessions.pop(sid,None)
        r.call=call;r.delete_session=delete
        await s.conversations.delete(c['id'])
        with s.store.connect() as db:assert not db.execute('SELECT 1 FROM turn_process_projection WHERE turn_id=?',(tid,)).fetchone()
    asyncio.run(case())


def test_missing_native_parts_cannot_fabricate_historical_actions(fixture):
    s,c,request,r=fixture
    async def case():
        result=await s.submit(c['id'],request);tid=result['turn']['id'];await settled(s,tid)
        original=s.store.turn(tid)
        async def missing(*args):return []
        r.messages=missing
        with pytest.raises(Conflict,match='source_incomplete'):await refresh_process(s.store,r,tid)
        assert s.store.turn(tid)==original
    asyncio.run(case())
