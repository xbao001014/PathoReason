import asyncio
import json
import pytest
from pydantic import ValidationError
from test_p1_service import fixture,settled
from test_goals import start,accepted
from pathoreason.goals import GoalControl
from pathoreason.runtime import visible_response


def message(finish='length',text='',parent='msg_user',completed=True):
    return {'info':{'role':'assistant','parentID':parent,'finish':finish,
        'time':{'completed':1} if completed else {},'tokens':{'input':200000,'output':0,'reasoning':8192}},
        'parts':[{'type':'reasoning','text':'PRIVATE_REASONING'},*([{'type':'text','text':text}] if text else [])]}


@pytest.mark.parametrize('text',['','Partial public response'])
def test_length_is_failed_and_preserves_public_partial_output(text):
    result=visible_response([message(text=text)],'msg_user')
    assert result['error']=='runtime_output_limit' and result['complete']
    assert result['text']==text and result['usage']['context_tokens']==208192
    assert 'PRIVATE_REASONING' not in json.dumps(result)


def test_length_from_other_parent_or_earlier_step_does_not_poison_final():
    result=visible_response([message(parent='other'),message(),message('stop','Actual answer')],'msg_user')
    assert result['error'] is None and result['text']=='Actual answer'
    assert not visible_response([message(completed=False)],'msg_user')['error']
    assert not visible_response([message('tool-calls')],'msg_user')['error']


def test_reasoning_only_stop_is_empty_but_tool_only_response_is_not():
    assert visible_response([message('stop')],'msg_user')['error']=='runtime_empty_response'
    m=message('stop');m['parts'].append({'id':'tool1','type':'tool','tool':'pathoreason_dialogue_checkpoint','state':{'status':'completed','input':{},'time':{'start':1,'end':2}}})
    assert visible_response([m],'msg_user')['error'] is None


@pytest.mark.parametrize('finish,expected',[('length','runtime_output_limit'),('stop','runtime_empty_response')])
def test_failed_native_output_blocks_goal_without_automatic_retry(fixture,finish,expected):
    async def case():
        s,r,v,cid,tid,body=await start(fixture)
        original=r.messages
        async def truncated(sid,directory):
            messages=await original(sid,directory)
            return [m for m in messages if m['info']['role']=='user']+[message(finish,parent=s.store.turn(tid)['native_message_id'])]
        r.messages=truncated;r.hold=False
        await settled(s,tid);s.goals.process(tid)
        row=s.store.turn(tid);assert row['status']=='failed' and json.loads(row['document'])['error_code']==expected
        goal=s.goals.view(cid);assert goal.state=='blocked' and goal.reason==expected
        assert goal.next_action=='' and '停止自动接续' in goal.summary
        await s.goals.tick();await s.goals.tick();assert len(r.calls)==1
        assert s.formal.view(v.project_id).used_turns==1
        if finish=='length':assert goal.suggested_reasoning_effort=='low'
        await s.close()
    asyncio.run(case())


def test_resume_effort_changes_next_dispatch_only_and_keeps_goal_and_usage(fixture):
    async def case():
        s,r,v,cid,tid,body=await start(fixture)
        original=s.store.turn(tid);digest=json.loads(original['document'])['config_digest']
        with s.store.connect() as db:frozen=db.execute('SELECT document FROM runtime_configs WHERE digest=?',(digest,)).fetchone()[0]
        s.state(tid,'failed','runtime_output_limit');s.goals.process(tid)
        goal=s.goals.view(cid)
        await s.goals.control(cid,GoalControl(expected_revision=goal.revision,action='resume',reasoning_effort='low'))
        await s.goals.tick();next_id=s.store.turns(cid)[-1]['id'];await accepted(s,next_id)
        assert next_id!=tid and r.last_effort=='low'
        assert s.goals.view(cid).id==goal.id and s.goals.view(cid).turns_used==2
        with s.store.connect() as db:
            assert db.execute('SELECT document FROM runtime_configs WHERE digest=?',(digest,)).fetchone()[0]==frozen
        assert s.formal.view(v.project_id).used_turns==2
        assert s.view(s.store.turn(next_id))['reasoning_effort']=='low'
        assert s.store.turn(tid)['status']=='failed'
        await s.close()
    asyncio.run(case())


def test_invalid_resume_effort_is_rejected_without_goal_mutation(fixture,monkeypatch):
    async def case():
        s,r,v,cid,tid,body=await start(fixture)
        s.state(tid,'failed','runtime_output_limit');s.goals.process(tid)
        before=s.goals.view(cid)
        monkeypatch.setattr(s,'reasoning_options',lambda:[])
        with pytest.raises(ValueError,match='not_supported'):
            await s.goals.control(cid,GoalControl(expected_revision=before.revision,action='resume',reasoning_effort='low'))
        assert s.goals.view(cid).revision==before.revision and len(r.calls)==1
        await s.close()
    asyncio.run(case())
    with pytest.raises(ValidationError,match='requires_resume'):
        GoalControl(expected_revision=1,action='pause',reasoning_effort='low')
