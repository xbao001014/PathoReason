import asyncio,json
from pathlib import Path
import pytest
from test_p1_service import fixture
from test_manuscript_review import setup,accepted,finish,request_review
from pathoreason.goals import GoalCheckpoint
from pathoreason.stages import StageSwitch
from pathoreason.persistence import Conflict

async def ready(fixture):
    s,r,v,cid,tid,request=await setup(fixture)
    p=Path(v.workspace)/'outputs/entry.txt';p.write_text('Synthetic exploratory negative results; not independent or blinded.')
    s.goals.checkpoint(GoalCheckpoint(turn_id=tid,grant=s.guidance.grant(tid),expected_revision=s.goals.view(cid).revision,outcome='completed',summary='Existing draft prepared; author decisions still pending preparation.',evidence={'files':['outputs/entry.txt']}))
    await finish(s,r,tid)
    return s,r,v,cid,request


def test_same_stage_entry_preserves_goal_budget_and_context_without_model_dispatch(fixture):
    async def case():
        s,r,v,cid,request=await ready(fixture);before=s.goals.view(cid).model_dump();budget=s.formal.view(v.project_id).model_dump();stage=s.stages.view(cid)
        old=s.store.conversation(cid);assert stage.can_open_conversation
        dest=await s.stages.open_conversation(cid,StageSwitch(expected_revision=stage.revision))
        repeat=await s.stages.open_conversation(cid,StageSwitch(expected_revision=stage.revision))
        assert dest.conversation_id==repeat.conversation_id and dest.conversation_id!=cid
        assert dest.stage_id=='manuscript' and dest.status=='active' and not dest.can_open_conversation
        assert s.goals.view(cid).model_dump()==before and s.goals.view(dest.conversation_id) is None
        assert s.formal.view(v.project_id).model_dump()==budget and len(r.calls)==1
        assert s.store.conversation(cid)==old
        assert s.store.conversation(dest.conversation_id)['native_session'] is None
        assert dest.incoming_handoff['verified_evidence'][0]['path']=='outputs/entry.txt'
        assert not dest.incoming_handoff['scientific_approval'] and not dest.manuscript_review['approved']
        # Only the user's subsequent task starts the fresh native window.
        result=await s.submit(dest.conversation_id,{**request,'request_key':'new_stage_task','text':'Prepare the first author review using the transferred draft.'})
        tid=result['turn']['id'];await accepted(s,tid)
        assert 'outputs/entry.txt' in r.calls[-1][3] and 'MANUSCRIPT AUTHOR WORKFLOW' in r.calls[-1][3]
        assert s.formal.view(v.project_id).used_turns==budget['used_turns']+1
        await s.close()
    asyncio.run(case())


def test_entry_rejects_unfinished_review_stale_or_foreign_state(fixture):
    async def case():
        s,r,v,cid,tid,_=await setup(fixture);w=s.stages.view(cid)
        assert not w.can_open_conversation
        with pytest.raises(Conflict,match='goal_not_finished'):await s.stages.open_conversation(cid,StageSwitch(expected_revision=w.revision))
        request_review(s,v,cid,tid);await finish(s,r,tid)
        with pytest.raises(Conflict,match='goal_not_finished'):await s.stages.open_conversation(cid,StageSwitch(expected_revision=w.revision))
        other=s.new_conversation(v.project_id,'Other')
        with pytest.raises(Conflict,match='stage_changed'):await s.stages.open_conversation(other['id'],StageSwitch(expected_revision=w.revision))
        with pytest.raises(Conflict,match='stage_changed'):await s.stages.open_conversation(cid,StageSwitch(expected_revision=w.revision+1))
        await s.close()
    asyncio.run(case())


def test_changed_evidence_does_not_create_destination(fixture):
    async def case():
        s,r,v,cid,_=await ready(fixture);w=s.stages.view(cid);count=len(s.store.conversations(v.project_id))
        (Path(v.workspace)/'outputs/entry.txt').write_text('Altered after completion')
        with pytest.raises(Conflict,match='evidence_changed'):await s.stages.open_conversation(cid,StageSwitch(expected_revision=w.revision))
        assert len(s.store.conversations(v.project_id))==count
        await s.close()
    asyncio.run(case())


def test_legacy_completed_stage_keeps_delivery_history_but_not_author_approval(fixture):
    from pathoreason.contracts import canonical_digest
    from pathoreason.persistence import encoded
    async def case():
        s,r,v,cid,_=await ready(fixture);goal=s.goals.view(cid)
        with s.store.connect(True) as db:
            w=s.stages.get(db,v.project_id)
            packet={'agent_report':{'summary':'Legacy draft delivered','limitations':['No independent evaluation']},'verified_evidence':[x for x in goal.evidence]}
            packet['digest']=canonical_digest(packet)
            w.update(status='completed',handoff=packet);s.stages.save(db,w,'synthetic_legacy_delivery')
        before=s.stages.view(cid);new=await s.stages.open_conversation(cid,StageSwitch(expected_revision=before.revision))
        assert new.history[-1]['kind']=='conversation_relocated' and new.incoming_handoff['prior_delivery_digest']==packet['digest']
        with s.store.connect() as db:assert s.stages.get(db,v.project_id)['history'][-1]['handoff']==packet
        assert new.manuscript_review['revision']==0 and not new.manuscript_review['delivery_approved']
        assert s.goals.view(cid).state=='completed' and len(r.calls)==1
        await s.close()
    asyncio.run(case())


def test_stage_entry_http_route_and_project_readonly(fixture,monkeypatch):
    from fastapi.testclient import TestClient
    import pathoreason.api as api
    from test_project_lifecycle import action
    s,r,v,cid,_=asyncio.run(ready(fixture));monkeypatch.setattr(api,'service',lambda:s)
    client=TestClient(api.app);base='/api/v2/conversations/'+cid+'/stage';rev=s.stages.view(cid).revision
    assert client.get(base).json()['can_open_conversation']
    assert client.post(base+'/new-conversation',json={'expected_revision':rev},headers={'Origin':'https://foreign.invalid'}).status_code==403
    asyncio.run(s.projects.archive(v.project_id,action(s,v.project_id)))
    assert client.post(base+'/new-conversation',json={'expected_revision':rev}).status_code==409
    asyncio.run(s.projects.archive(v.project_id,action(s,v.project_id),restore=True))
    r.native_busy=True
    assert client.post(base+'/new-conversation',json={'expected_revision':rev}).json()['detail']=='runtime_busy'
    r.native_busy=False
    result=client.post(base+'/new-conversation',json={'expected_revision':rev})
    assert result.status_code==200 and result.json()['conversation_id']!=cid
    assert client.post(base+'/new-conversation',json={'expected_revision':rev}).json()['conversation_id']==result.json()['conversation_id']
    assert len(r.calls)==1
    client.close();asyncio.run(s.close())
