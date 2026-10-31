import asyncio
import json

import pytest

from pathoreason.activity import tool_summary
from pathoreason.api import ToolSummary, Usage
from pathoreason.runtime import visible_response
from test_p1_service import fixture, settled


def message(parts, parent='msg_user'):
    return {'info': {'role': 'assistant', 'parentID': parent}, 'parts': parts}


def test_tool_summary_only_exports_allowlisted_metadata():
    part={'id':'tool_1','type':'tool','tool':'skill','state':{
        'status':'completed','input':{'name':'pathology-data-api','secret':'PRIVATE_ARGUMENT'},
        'output':'PRIVATE_OUTPUT','title':'PRIVATE_TITLE','time':{'start':1000,'end':2234}}}
    result=visible_response([message([{'type':'reasoning','text':'PRIVATE_REASONING'},part])],'msg_user')
    assert result['tools'][0]['summary']=='加载「病理接口数据接入」Skill'
    assert result['tools'][0]['duration_ms']==1234
    assert 'PRIVATE_' not in json.dumps(result)
    ToolSummary.model_validate(result['tools'][0])
    Usage.model_validate(result['usage'])
    part['state']['input']['name']='PRIVATE_UNKNOWN_SKILL'
    assert tool_summary(part)['summary']=='加载 Skill'


@pytest.mark.parametrize('timing',[{}, {'start':1}, {'start':2,'end':1}, {'start':0,'end':float('nan')}, {'start':True,'end':5}])
def test_missing_or_invalid_timing_stays_unknown(timing):
    assert tool_summary({'id':'tool_1','tool':'bash','state':{'time':timing}})['duration_ms'] is None


@pytest.mark.parametrize('parts,phase',[
    ([{'type':'reasoning','text':'hidden'}],'thinking'),
    ([{'type':'text','text':'公开进度'},{'id':'t','type':'tool','tool':'read','state':{'status':'running'}}],'tool'),
    ([{'type':'text','text':'公开进度'},{'id':'t','type':'tool','tool':'read','state':{'status':'completed'}}],'waiting'),
    ([{'type':'text','text':'答复正文'}],'responding'),
    ([], 'waiting'),
])
def test_phase_uses_latest_message_without_exporting_reasoning(parts,phase):
    result=visible_response([message([{'type':'text','text':'早期公开进度'}]),message(parts),message([{'type':'text','text':'OTHER_TURN'}],'other')],'msg_user')
    assert result['usage']['activity_phase']==phase
    assert 'OTHER_TURN' not in result['text']
    assert 'hidden' not in json.dumps(result)


def test_old_tool_records_remain_valid_without_invented_summary():
    old=ToolSummary.model_validate({'id':'old','name':'skill','status':'completed'})
    assert old.summary is None and old.duration_ms is None
    assert Usage.model_validate({}).activity_phase is None


def test_activity_survives_reload_and_is_cleared_by_conversation_delete(fixture):
    s,c,request,runtime=fixture
    async def case():
        result=await s.submit(c['id'],request)
        tid=result['turn']['id']
        await settled(s,tid)
        await asyncio.gather(*list(s.tasks.values()))
        row=s.store.turn(tid)
        assert json.loads(row['tools'])[0]['summary']=='加载 Skill'
        assert s.view(row)['usage']['activity_phase']=='waiting'
        async def call(*args):return []
        async def delete(sid,directory):runtime.sessions.pop(sid,None)
        runtime.call=call;runtime.delete_session=delete
        assert (await s.conversations.delete(c['id'])).state=='deleted'
        with s.store.connect() as db:
            assert db.execute('SELECT tools FROM turns WHERE id=?',(tid,)).fetchone()[0]=='[]'
    asyncio.run(case())
