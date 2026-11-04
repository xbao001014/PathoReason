import asyncio,json
import pytest
from pydantic import ValidationError
from test_p1_service import fixture
from test_manuscript_review import setup,request_review,finish,accepted,decision
from pathoreason.manuscript import RevisionRoute
from pathoreason.persistence import Conflict
from pathoreason.guidance import OfferInput

async def delivery(fixture,feedback='Please rewrite the manuscript using the writing skill.'):
    s,r,v,cid,tid,body=await setup(fixture,turns=20)
    for _ in range(4):
        request_review(s,v,cid,tid);await finish(s,r,tid)
        await s.manuscripts.decide(cid,decision(s,cid))
        await s.goals.tick();tid=s.store.turns(cid)[-1]['id'];await accepted(s,tid)
    request_review(s,v,cid,tid);await finish(s,r,tid)
    if feedback is not None:
        await s.manuscripts.decide(cid,decision(s,cid,'revise',comment=feedback))
        await s.goals.tick();tid=s.store.turns(cid)[-1]['id'];await accepted(s,tid)
    return s,r,v,cid,tid,body

def route(s,cid,tid,**overrides):
    w=s.manuscripts.view(cid);author=next(h for h in reversed(w['history']) if h['event']=='author_decision')
    args=dict(turn_id=tid,grant=s.guidance.grant(tid),expected_goal_revision=s.goals.view(cid).revision,
        expected_revision=w['revision'],source='author_feedback',source_id=author['at'],
        instruction_excerpt=author['comment'],reason='Author requests prose revision; preserve approved original and review the new version.')
    args.update(overrides);return RevisionRoute(**args)

def test_routes_existing_feedback_in_same_turn_without_approval_budget_reset_or_overwrite(fixture):
    async def case():
        s,r,v,cid,tid,_=await delivery(fixture)
        before=s.manuscripts.view(cid);old=before['approved'][3];m=next(m for m in old['materials'] if m['role']=='manuscript')
        raw=s.manuscripts.archived_material(cid,old['id'],m['artifact_id'])[0]
        goal=s.goals.view(cid).model_dump();budget=s.formal.view(v.project_id).model_dump()
        cmd=route(s,cid,tid);after=s.manuscripts.route_revision(cmd)
        assert after['gate']=='scientific' and after['status']=='preparing' and not after['author_content_approved']
        assert len(after['approved'])==3 and after['history'][-1]['source']=='agent_interpretation'
        assert after['history'][-1]['invalidated']==[old]
        usage=s.formal.view(v.project_id).model_dump()
        assert s.goals.view(cid).model_dump()==goal and usage['budget']==budget['budget'] and usage['used_turns']==budget['used_turns']
        assert usage['used_budget_seconds']>=budget['used_budget_seconds']  # Active-turn time continues accruing.
        assert s.manuscripts.archived_material(cid,old['id'],m['artifact_id'])[0]==raw
        assert s.manuscripts.route_revision(cmd)['revision']==after['revision']
        with pytest.raises(Conflict,match='replay_changed'):s.manuscripts.route_revision(cmd.model_copy(update={'reason':'different'}))
        request_review(s,v,cid,tid);await finish(s,r,tid)
        assert s.manuscripts.view(cid)['gate']=='scientific' and s.manuscripts.view(cid)['status']=='awaiting_review'
        assert not s.manuscripts.view(cid)['author_content_approved']
        with pytest.raises(Conflict,match='turn_inactive'):s.manuscripts.route_revision(cmd)
        await s.close()
    asyncio.run(case())

@pytest.mark.parametrize('change,error',[
    ({'grant':'fake'},'grant_invalid'),
    ({'expected_revision':999},'review_changed'),
    ({'expected_goal_revision':999},'goal_changed'),
    ({'source_id':'not-a-user-receipt'},'instruction_required'),
    ({'instruction_excerpt':'Invented permission to rewrite'},'excerpt_mismatch'),
    ({'source':'user_message'},'instruction_required'),
])
def test_rejects_unbound_stale_or_fabricated_authority_without_state_change(fixture,change,error):
    async def case():
        s,r,v,cid,tid,_=await delivery(fixture);before=s.manuscripts.view(cid)
        with pytest.raises(Conflict,match=error):s.manuscripts.route_revision(route(s,cid,tid,**change))
        assert s.manuscripts.view(cid)==before
        await s.close()
    asyncio.run(case())

def test_direct_user_request_can_route_but_old_approval_is_not_revision_authority(fixture):
    async def case():
        s,r,v,cid,tid,body=await delivery(fixture,feedback=None)
        text='请保留原稿，润色摘要和讨论并提交新版本。'
        result=await s.submit(cid,{**body,'request_key':'direct_rewrite','text':text})
        tid=result['turn']['id'];await accepted(s,tid)
        with pytest.raises(Conflict,match='instruction_required'):s.manuscripts.route_revision(route(s,cid,tid))
        after=s.manuscripts.route_revision(route(s,cid,tid,source='user_message',source_id=tid,instruction_excerpt=text))
        assert after['gate']=='scientific'
        await s.close()
    asyncio.run(case())

@pytest.mark.parametrize('selected',['content','layout','vague'])
def test_ambiguous_feedback_waits_for_choice_and_selection_continues_same_goal(fixture,selected):
    async def case():
        s,r,v,cid,tid,body=await delivery(fixture,feedback='再改一下')
        goalid=s.goals.view(cid).id
        offer=OfferInput(turn_id=tid,grant=s.guidance.grant(tid),kind='clarification',question='要修改正文还是仅调整排版？',options=[
            {'id':'content','label':'修改正文并返回科学审核','scope':'continue'},
            {'id':'layout','label':'仅调整排版','scope':'continue'}])
        receipt=s.guidance.publish(offer);await finish(s,r,tid)
        assert s.manuscripts.view(cid)['gate']=='delivery' and s.goals.view(cid).reason=='goal_user_choice'
        assert s.guidance.view(tid).status=='available'
        choice=offer.options[0 if selected=='content' else 1]
        text=choice.text() if selected!='vague' else '好'
        req={**body,'request_key':'choose_'+selected,'text':text}
        if selected!='vague':req['guidance_selection']={'guidance_id':receipt['guidance_id'],'option_id':choice.id}
        result=await s.submit(cid,req);tid=result['turn']['id'];await accepted(s,tid)
        assert s.goals.view(cid).id==goalid
        cmd=route(s,cid,tid,source='user_message',source_id=tid,instruction_excerpt=text)
        if selected=='content':assert s.manuscripts.route_revision(cmd)['gate']=='scientific'
        elif selected=='vague':
            with pytest.raises(Conflict):s.manuscripts.route_revision(cmd)
            assert s.manuscripts.view(cid)['gate']=='delivery'
        else:
            # A model must keep layout-only work in delivery; no routing call.
            assert s.manuscripts.view(cid)['gate']=='delivery'
            request_review(s,v,cid,tid);await finish(s,r,tid)
            assert s.manuscripts.view(cid)['gate']=='delivery'
        await s.close()
    asyncio.run(case())

def test_route_contract_cannot_approve_or_jump_forward():
    with pytest.raises(ValidationError):RevisionRoute(turn_id='turn_test',grant='x',expected_goal_revision=1,
        expected_revision=1,source='user_message',source_id='turn_test',instruction_excerpt='Rewrite',reason='Revise',target_gate='delivery')
