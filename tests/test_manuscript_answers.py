"""Explicit plan answer + approval, without weakening content/integrity gates."""
import asyncio,json
import pytest
from test_p1_service import fixture
from test_manuscript_review import setup,request_review,finish,decision,accepted
from pathoreason.persistence import Conflict
from pathoreason.contracts import canonical_digest


def test_answer_and_plan_approval_once_preserves_packet_budget_and_prompt(fixture):
    async def case():
        s,r,v,cid,tid,body=await setup(fixture)
        questions=['Choose the paper scope.','Should a possible follow-up remain optional?']
        request_review(s,v,cid,tid,author_questions=questions);await finish(s,r,tid)
        original=s.manuscripts.view(cid)['pending'];budget=s.formal.view(v.project_id);goal=s.goals.view(cid)
        answer='Use the existing exploratory results. Mention the follow-up only as optional; no new experiment.'
        choice=decision(s,cid,comment=answer,confirm_answers=True)
        after=await s.manuscripts.decide(cid,choice);again=await s.manuscripts.decide(cid,choice)
        assert after['revision']==again['revision'] and after['index']==1
        assert after['approved'][0]==original and after['approved'][0]['request']['author_questions']==questions
        receipt=after['history'][-1]
        assert receipt['question_response']=={'questions':questions,'answer':answer,'confirmed_with_plan':True}
        assert receipt['comment']==answer and not after['author_content_approved'] and not after['submission_authorized']
        assert s.formal.view(v.project_id).budget==budget.budget and s.formal.view(v.project_id).used_turns==budget.used_turns
        assert s.goals.view(cid).id==goal.id and s.goals.view(cid).turns_used==goal.turns_used
        assert answer in s.manuscripts.prompt(cid) and 'question_response' in s.manuscripts.prompt(cid)
        await s.goals.tick();next_id=s.store.turns(cid)[-1]['id'];await accepted(s,next_id)
        assert answer in r.calls[-1][3] and 'do not request the same confirmation again' in r.calls[-1][3]
        await s.close()
    asyncio.run(case())

@pytest.mark.parametrize('options',[{'comment':'A generic comment'}, {'comment':'   ','confirm_answers':True}])
def test_pending_questions_require_explicit_nonempty_plan_response(fixture,options):
    async def case():
        s,r,v,cid,tid,body=await setup(fixture);request_review(s,v,cid,tid,author_questions=['Which scope?']);await finish(s,r,tid)
        before=s.manuscripts.view(cid)
        with pytest.raises(Conflict,match='author_facts_required'):await s.manuscripts.decide(cid,decision(s,cid,**options))
        assert s.manuscripts.view(cid)==before
        await s.close()
    asyncio.run(case())

@pytest.mark.parametrize('change',[{'issues':[{'id':'bad','finding':'Unverified result','blocking':True}]},{'audit_status':'blocked'}])
def test_plan_answer_does_not_waive_integrity(fixture,change):
    async def case():
        s,r,v,cid,tid,body=await setup(fixture);request_review(s,v,cid,tid,author_questions=['Which scope?'],**change);await finish(s,r,tid)
        with pytest.raises(Conflict,match='unresolved_blockers'):await s.manuscripts.decide(cid,decision(s,cid,comment='Keep exploratory scope.',confirm_answers=True))
        await s.close()
    asyncio.run(case())


def test_answer_confirmation_cannot_approve_missing_facts_in_later_content(fixture):
    async def case():
        s,r,v,cid,tid,body=await setup(fixture);request_review(s,v,cid,tid);await finish(s,r,tid)
        with pytest.raises(ValueError,match='answer_confirmation_wrong_gate'):await s.manuscripts.decide(cid,decision(s,cid,confirm_answers=True))
        await s.manuscripts.decide(cid,decision(s,cid));await s.goals.tick();tid=s.store.turns(cid)[-1]['id'];await accepted(s,tid)
        request_review(s,v,cid,tid,author_questions=['Missing source must be incorporated into the draft.']);await finish(s,r,tid)
        with pytest.raises(ValueError,match='answer_confirmation_wrong_gate'):await s.manuscripts.decide(cid,decision(s,cid,confirm_answers=True))
        assert s.manuscripts.view(cid)['index']==1
        reply=await s.manuscripts.decide(cid,decision(s,cid,'revise',comment='Incorporate the source into a new draft.'))
        assert reply['index']==1 and reply['status']=='preparing'
        await s.close()
    asyncio.run(case())


def test_legacy_command_digest_remains_retryable(fixture):
    async def case():
        s,r,v,cid,tid,body=await setup(fixture);request_review(s,v,cid,tid);await finish(s,r,tid)
        choice=decision(s,cid);after=await s.manuscripts.decide(cid,choice)
        old=choice.model_dump(mode='json');old.pop('confirm_answers')
        with s.store.connect() as db:
            saved=db.execute('SELECT digest FROM manuscript_review_commands WHERE project_id=? AND request_key=?',(v.project_id,choice.request_key)).fetchone()[0]
        assert saved==canonical_digest(old)
        assert (await s.manuscripts.decide(cid,choice))['revision']==after['revision']
        await s.close()
    asyncio.run(case())


def test_answer_confirmation_http_and_reopen_preserve_original_response(fixture,monkeypatch):
    from fastapi.testclient import TestClient
    import pathoreason.api as api
    async def prepare():
        s,r,v,cid,tid,body=await setup(fixture);request_review(s,v,cid,tid,author_questions=['Choose the scope.']);await finish(s,r,tid);return s,cid
    s,cid=asyncio.run(prepare());monkeypatch.setattr(api,'service',lambda:s)
    client=TestClient(api.app)
    route='/api/v2/conversations/'+cid+'/manuscript-review';choice=decision(s,cid,comment='Existing results only.',confirm_answers=True).model_dump()
    assert client.post(route,json=choice,headers={'Origin':'https://foreign.invalid'}).status_code==403
    response=client.post(route,json=choice);assert response.status_code==200 and response.json()['index']==1
    again=client.post(route,json=choice);assert again.status_code==200 and again.json()['revision']==response.json()['revision']
    reopened=client.post(route,json=decision(s,cid,'reopen',target_gate='blueprint',comment='Change the writing direction.').model_dump())
    assert reopened.status_code==200 and reopened.json()['index']==0
    assert reopened.json()['history'][0]['question_response']['answer']=='Existing results only.'
    client.close()
    asyncio.run(s.close())
