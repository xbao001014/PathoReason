import asyncio,hashlib,json
from pathlib import Path
import pytest
from pydantic import ValidationError
from test_p1_service import fixture
from test_p5_entry import study,formal_runtime
from test_goals import accepted as accepted_goal,finish as finish_goal
from pathoreason.study_io import publish_artifact
from pathoreason.goals import GoalCheckpoint,GoalControl
from pathoreason.stages import StageAssign,StageHandoff
from pathoreason.manuscript import ReviewRequest,ReviewDecision,GATES
from pathoreason.persistence import Conflict

async def accepted(s,tid):
    s.runtime.hold=True
    await accepted_goal(s,tid)

async def finish(s,r,tid):
    await finish_goal(s,r,tid)
    r.hold=False  # Completed native sessions are idle while waiting for author review.

async def setup(fixture,turns=12):
    s,_,request,r=fixture;formal_runtime(r);v=study(s,turns=turns);cid=s.store.conversations(v.project_id)[0]['id']
    with s.store.connect(True) as db:db.execute('DELETE FROM research_workflows WHERE project_id=?',(v.project_id,))
    await s.stages.assign(cid,StageAssign(stage_id='manuscript'))
    s.goals.start=lambda:None;r.hold=True
    r.native_busy=False
    original_status=r.status
    async def status(directory):return {sid:{'type':'busy'} for sid in r.sessions} if r.native_busy else await original_status(directory)
    async def call(method,path,directory):
        assert method=='GET' and path=='/permission'
        return []
    r.status=status;r.call=call
    body={**request,'request_key':'manuscript_first','text':'Prepare the reviewable manuscript within the original limits. No training or publication.','skill_id':None,'artifact_ids':[],'execution_mode':'research','goal_mode':'continuous'}
    result=await s.submit(cid,body);tid=result['turn']['id'];await accepted(s,tid)
    return s,r,v,cid,tid,body

def request_review(s,v,cid,tid,**overrides):
    w=s.manuscripts.view(cid);gate=w['gate'];materials=[]
    for role in w['required_roles']:
        rel=f'outputs/{gate}-{w["revision"]}-{role}'+('.pdf' if role=='pdf' else '.md')
        p=Path(v.workspace)/rel;p.write_bytes(b'%PDF-1.4\n%synthetic fixture only\n' if role=='pdf' else f'{gate} {role}; exploratory, not independently approved'.encode())
        if role=='figure_manifest':p.write_text(json.dumps({'artifact_ids':[],'no_figures_reason':'Synthetic text-only test; no real paper or figures.'}))
        a=publish_artifact(s,v.project_id,rel,role);materials.append({'role':role,'label':role,'artifact_id':a.id})
    raw=dict(gate=gate,expected_revision=w['revision'],summary='Synthetic materials ready for author review',materials=materials)
    if gate=='review':raw.update(audited_manuscript_sha256=next(m['sha256'] for m in w['approved'][1]['materials'] if m['role']=='manuscript'),issues=[{'id':'issue_one','finding':'Clarify the exploratory limitation','blocking':False}],audit_status='passed')
    if gate=='scientific':raw.update(audit_status='passed',audited_manuscript_sha256=s.store.artifact(next(m['artifact_id'] for m in materials if m['role']=='manuscript'),v.project_id)['sha256'])
    if gate=='delivery':raw.update(audit_status='passed',scientific_basis_digest=w['approved'][3]['digest'])
    raw.update(overrides)
    body=GoalCheckpoint(turn_id=tid,grant=s.guidance.grant(tid),expected_revision=s.goals.view(cid).revision,outcome='needs_input',summary='Author review required',evidence={'artifact_ids':[m['artifact_id'] for m in materials]},manuscript_review=raw)
    s.goals.checkpoint(body);return body

def decision(s,cid,action='approve',**kw):
    w=s.manuscripts.view(cid)
    value=dict(request_key=f'review_{w["revision"]}_{action}',expected_revision=w['revision'],action=action,comment='Author reviewed this exact version; no publication authorized.')
    if action=='approve' and w['gate']=='review':value['issues']=[dict(issue_id='issue_one',decision='modify',rationale='Preserve the limitation explicitly.')]
    value.update(kw);return ReviewDecision(**value)


def test_five_author_gates_then_stage_delivery_preserve_budget_history_and_versions(fixture):
    async def case():
        s,r,v,cid,tid,body=await setup(fixture);gid=s.goals.view(cid).id;limits=s.formal.view(v.project_id).budget.model_dump()
        for index,(gate,_,_,_) in enumerate(GATES):
            assert s.manuscripts.view(cid)['gate']==gate
            request_review(s,v,cid,tid);await finish(s,r,tid)
            w=s.manuscripts.view(cid);assert w['status']=='awaiting_review'
            assert s.goals.view(cid).reason=='manuscript_review_pending'
            await s.goals.tick();assert len(r.calls)==index+1
            before=s.formal.view(v.project_id).used_turns;choice=decision(s,cid)
            after=await s.manuscripts.decide(cid,choice);again=await s.manuscripts.decide(cid,choice)
            assert after['revision']==again['revision'] and after['index']==index+1
            assert s.formal.view(v.project_id).used_turns==before
            assert s.goals.view(cid).id==gid and s.goals.view(cid).turns_used==index+1
            assert s.formal.view(v.project_id).budget.model_dump()==limits
            assert not after['submission_authorized'] and not after['independent_scientific_approval']
            await s.goals.tick();tid=s.store.turns(cid)[-1]['id'];await accepted(s,tid)
            assert 'MANUSCRIPT AUTHOR WORKFLOW' in r.calls[-1][3]
            assert 'Author reviewed this exact version' in r.calls[-1][3]
        final=s.manuscripts.view(cid);assert final['delivery_approved'] and final['author_content_approved']
        w=s.stages.view(cid)
        s.goals.checkpoint(GoalCheckpoint(turn_id=tid,grant=s.guidance.grant(tid),expected_revision=s.goals.view(cid).revision,outcome='completed',summary='Author-reviewed draft delivered',evidence={'artifact_ids':[m['artifact_id'] for m in final['approved'][-1]['materials']]},stage_handoff=StageHandoff(stage_id='manuscript',workflow_revision=w.revision,summary='Draft delivered',limitations=['No external approval or submission'],next_action='Await separate submission authorization')))
        await finish(s,r,tid);assert s.stages.view(cid).status=='completed' and s.goals.view(cid).turns_used==6
        # Rework preserves original approved bytes and revokes only affected effective approvals.
        old=final['approved'][1];a=old['materials'][0]['artifact_id'];raw=s.manuscripts.archived_material(cid,old['id'],a)[0]
        reopened=await s.manuscripts.decide(cid,decision(s,cid,'reopen',target_gate='draft',comment='Revise the draft interpretation.'))
        assert reopened['index']==1 and len(reopened['approved'])==1 and len(reopened['history'][-1]['invalidated'])==4
        assert s.manuscripts.archived_material(cid,old['id'],a)[0]==raw
        assert s.stages.view(cid).status=='active' and s.goals.view(cid).state=='completed'
        assert s.formal.view(v.project_id).used_turns==6
        await s.close()
    asyncio.run(case())


def test_no_author_gate_can_be_skipped_by_checkpoint_resume_or_foreign_conversation(fixture):
    async def case():
        s,r,v,cid,tid,body=await setup(fixture)
        with pytest.raises(Conflict,match='manuscript_author_review_required'):
            s.goals.checkpoint(GoalCheckpoint(turn_id=tid,grant=s.guidance.grant(tid),expected_revision=s.goals.view(cid).revision,outcome='completed',summary='Skip author review',stage_handoff=StageHandoff(stage_id='manuscript',workflow_revision=s.stages.view(cid).revision,summary='Skip',limitations=['Unknown'],next_action='Done')))
        with pytest.raises(Conflict,match='review_changed'):request_review(s,v,cid,tid,gate='delivery')
        valid=request_review(s,v,cid,tid)
        assert s.manuscripts.view(cid)['pending'] is None  # Not surfaced before successful settlement.
        with pytest.raises(Conflict,match='active_turn'):await s.manuscripts.decide(cid,decision(s,cid))
        await finish(s,r,tid)
        r.native_busy=True
        with pytest.raises(Conflict,match='runtime_busy'):await s.manuscripts.decide(cid,decision(s,cid))
        r.native_busy=False
        with pytest.raises(Conflict,match='review_pending'):await s.goals.control(cid,GoalControl(expected_revision=s.goals.view(cid).revision,action='resume'))
        other=s.new_conversation(v.project_id,'Side')
        with pytest.raises(Conflict,match='stage_required'):await s.manuscripts.decide(other['id'],decision(s,cid))
        # A model's ordinary completed checkpoint cannot turn a pending review into approval.
        result=await s.submit(cid,{**body,'request_key':'status_query','text':'Explain the current review.'});next_id=result['turn']['id'];await accepted(s,next_id)
        s.goals.checkpoint(GoalCheckpoint(turn_id=next_id,grant=s.guidance.grant(next_id),expected_revision=s.goals.view(cid).revision,outcome='completed',summary='Answered',evidence=valid.evidence))
        await finish(s,r,next_id);assert s.goals.view(cid).reason=='manuscript_review_pending' and s.manuscripts.view(cid)['index']==0
        await s.close()
    asyncio.run(case())

@pytest.mark.parametrize('change',[{'issues':[{'id':'blocker','finding':'Fabricated citation','blocking':True}]},{'author_questions':['Which confirmed dataset was used?']}])
def test_blockers_and_required_author_facts_cannot_be_waived(fixture,change):
    async def case():
        s,r,v,cid,tid,body=await setup(fixture);request_review(s,v,cid,tid,**change);await finish(s,r,tid)
        with pytest.raises(Conflict,match='unresolved_blockers|author_facts_required'):await s.manuscripts.decide(cid,decision(s,cid))
        updated=await s.manuscripts.decide(cid,decision(s,cid,'clarify',comment='Keep earlier facts; make a new evidence-bound revision.'))
        assert updated['index']==0 and updated['status']=='preparing' and updated['history'][-1]['comment'].startswith('Keep earlier')
        assert 'Keep earlier facts' in s.manuscripts.prompt(cid)
        await s.close()
    asyncio.run(case())


def test_changed_material_rejects_approval_but_preserves_reviewed_snapshot_and_feedback(fixture):
    async def case():
        s,r,v,cid,tid,body=await setup(fixture);request_review(s,v,cid,tid);await finish(s,r,tid)
        w=s.manuscripts.view(cid);packet=w['pending'];m=packet['materials'][0]
        original=s.manuscripts.archived_material(cid,packet['id'],m['artifact_id'])[0]
        (Path(v.workspace)/'outputs/blueprint-0-facts.md').write_text('Changed after review requested')
        with pytest.raises(Conflict,match='evidence_changed'):await s.manuscripts.decide(cid,decision(s,cid))
        assert s.manuscripts.archived_material(cid,packet['id'],m['artifact_id'])[0]==original
        updated=await s.manuscripts.decide(cid,decision(s,cid,'revise',comment='Reconcile changed facts, retain the old version.'))
        assert updated['index']==0 and updated['history'][-1]['packet']['digest']==packet['digest']
        with pytest.raises(Conflict,match='review_changed'):await s.manuscripts.decide(cid,ReviewDecision(request_key='stale',expected_revision=w['revision'],action='approve'))
        await s.close()
    asyncio.run(case())


def test_review_adjudication_requires_every_issue_and_scientific_audit_exact_bytes(fixture):
    async def case():
        s,r,v,cid,tid,body=await setup(fixture)
        for i in range(2):
            request_review(s,v,cid,tid);await finish(s,r,tid);await s.manuscripts.decide(cid,decision(s,cid));await s.goals.tick();tid=s.store.turns(cid)[-1]['id'];await accepted(s,tid)
        request_review(s,v,cid,tid);await finish(s,r,tid)
        with pytest.raises(ValueError,match='each_issue'):await s.manuscripts.decide(cid,decision(s,cid,issues=[]))
        await s.manuscripts.decide(cid,decision(s,cid));await s.goals.tick();tid=s.store.turns(cid)[-1]['id'];await accepted(s,tid)
        with pytest.raises(Conflict,match='audit_version'):request_review(s,v,cid,tid,audited_manuscript_sha256='0'*64)
        request_review(s,v,cid,tid);await finish(s,r,tid)
        with pytest.raises(ValueError,match='written_confirmation'):await s.manuscripts.decide(cid,decision(s,cid,comment=''))
        assert s.manuscripts.view(cid)['index']==3
        await s.close()
    asyncio.run(case())


def test_failed_model_turn_does_not_request_author_approval(fixture):
    async def case():
        s,r,v,cid,tid,body=await setup(fixture);request_review(s,v,cid,tid)
        await s.interrupt(tid);await finish(s,r,tid)
        assert s.manuscripts.view(cid)['pending'] is None and s.manuscripts.view(cid)['index']==0
        await s.close()
    asyncio.run(case())


def test_integrity_blocker_returns_to_draft_and_retains_invalidated_approval(fixture):
    async def case():
        s,r,v,cid,tid,body=await setup(fixture)
        for i in range(2):
            request_review(s,v,cid,tid);await finish(s,r,tid);await s.manuscripts.decide(cid,decision(s,cid));await s.goals.tick();tid=s.store.turns(cid)[-1]['id'];await accepted(s,tid)
        request_review(s,v,cid,tid,audit_status='blocked',issues=[dict(id='bad_citation',finding='The cited work does not support the claim.',blocking=True)])
        await finish(s,r,tid)
        with pytest.raises(Conflict,match='unresolved_blockers'):await s.manuscripts.decide(cid,decision(s,cid))
        after=await s.manuscripts.decide(cid,decision(s,cid,'revise',comment='Correct the unsupported claim before reviewing.'))
        assert after['gate']=='draft' and len(after['approved'])==1
        assert after['history'][-1]['invalidated'][0]['request']['gate']=='draft'
        assert s.goals.view(cid).state=='active'
        await s.close()
    asyncio.run(case())


def test_snapshot_corruption_is_not_approved_and_pause_is_preserved(fixture):
    async def case():
        s,r,v,cid,tid,body=await setup(fixture);request_review(s,v,cid,tid);await finish(s,r,tid)
        p=s.manuscripts.view(cid)['pending'];m=p['materials'][0]
        dest=s.manuscripts.root/v.project_id/p['id']/m['artifact_id'];old=dest.read_bytes();dest.write_text('corrupted')
        with pytest.raises(Conflict,match='snapshot_changed'):await s.manuscripts.decide(cid,decision(s,cid))
        dest.write_bytes(old)
        await s.goals.control(cid,GoalControl(expected_revision=s.goals.view(cid).revision,action='pause'))
        result=await s.manuscripts.decide(cid,decision(s,cid))
        assert result['goal_state']=='paused' and result['index']==1
        await s.goals.tick();assert len(r.calls)==1
        await s.close()
    asyncio.run(case())


def test_material_mutation_after_checkpoint_does_not_surface_review(fixture):
    async def case():
        s,r,v,cid,tid,body=await setup(fixture);request_review(s,v,cid,tid)
        (Path(v.workspace)/'outputs/blueprint-0-facts.md').write_text('Changed during final model response')
        await finish(s,r,tid)
        assert s.manuscripts.view(cid)['pending'] is None
        assert s.goals.view(cid).state=='blocked' and s.goals.view(cid).reason=='manuscript_evidence_changed'
        await s.close()
    asyncio.run(case())


def test_delivery_source_types_publish_immutable_artifacts(fixture):
    s,_,_,_=fixture;v=study(s);root=Path(v.workspace)
    for name,data,kind in [('source.zip',b'PK\x03\x04fixture','application/zip'),('paper.tex',b'\\documentclass{article}','text/plain'),('refs.bib',b'@article{fixture}','text/plain')]:
        (root/'outputs'/name).write_bytes(data)
        a=publish_artifact(s,v.project_id,'outputs/'+name,name)
        assert a.media_type==kind and s.artifact_bytes(a.model_dump())==data


def test_figure_manifest_requires_actual_version_bound_artifacts(fixture):
    async def case():
        s,r,v,cid,tid,body=await setup(fixture)
        request_review(s,v,cid,tid);await finish(s,r,tid);await s.manuscripts.decide(cid,decision(s,cid));await s.goals.tick();tid=s.store.turns(cid)[-1]['id'];await accepted(s,tid)
        # Prepare a valid request without persisting it so the malformed variant is tested first.
        original=s.goals.checkpoint;s.goals.checkpoint=lambda b:None
        body=request_review(s,v,cid,tid);s.goals.checkpoint=original
        manifest=next(m for m in body.manuscript_review.materials if m.role=='figure_manifest')
        p=Path(v.workspace)/'outputs/figure-manifest-bad.json';p.write_text(json.dumps({'artifact_ids':['art_missing']}))
        manifest.artifact_id=publish_artifact(s,v.project_id,'outputs/figure-manifest-bad.json','Broken figure list').id
        body.evidence.artifact_ids=[m.artifact_id for m in body.manuscript_review.materials]
        with pytest.raises(ValueError,match='figure_materials_mismatch'):s.goals.checkpoint(body)
        await s.close()
    asyncio.run(case())


def test_review_http_routes_are_user_only_and_serve_safe_snapshots(fixture,monkeypatch):
    from fastapi.testclient import TestClient
    import pathoreason.api as api
    async def prepare():
        s,r,v,cid,tid,body=await setup(fixture);check=request_review(s,v,cid,tid);await finish(s,r,tid)
        return s,cid,check
    s,cid,check=asyncio.run(prepare());monkeypatch.setattr(api,'service',lambda:s)
    client=TestClient(api.app)
    base='/api/v2/conversations/'+cid+'/manuscript-review'
    w=client.get(base).json();p=w['pending'];m=p['materials'][0]
    snapshot=client.get(base+'/'+p['id']+'/materials/'+m['artifact_id'])
    assert snapshot.status_code==200 and snapshot.headers['x-content-type-options']=='nosniff'
    assert client.post('/internal/goal-checkpoint',json=check.model_dump()).status_code==403
    invalid=client.post(base,json={**decision(s,cid).model_dump(),'author_approval':True})
    assert invalid.status_code==422
    assert client.post(base,json=decision(s,cid).model_dump(),headers={'Origin':'https://foreign.invalid'}).status_code==403
    good=client.post(base,json=decision(s,cid).model_dump())
    assert good.status_code==200 and good.json()['index']==1
    assert client.post(base,json={'request_key':'stale_http','expected_revision':w['revision'],'action':'approve'}).status_code==409
    client.close();asyncio.run(s.close())


def test_author_approval_does_not_extend_exhausted_project_budget(fixture):
    async def case():
        s,r,v,cid,tid,body=await setup(fixture,turns=1);request_review(s,v,cid,tid);await finish(s,r,tid)
        before=s.formal.view(v.project_id)
        await s.manuscripts.decide(cid,decision(s,cid));await s.goals.tick()
        after=s.formal.view(v.project_id)
        assert len(r.calls)==1 and after.used_turns==before.used_turns==1
        assert after.budget==before.budget
        assert s.goals.view(cid).state=='budget_exhausted'
        assert s.manuscripts.view(cid)['index']==1  # Decision saved; execution waits for user-controlled budget.
        await s.close()
    asyncio.run(case())


def test_restart_retains_review_and_original_author_statements(fixture):
    from pathoreason.service import Service
    async def case():
        s,r,v,cid,tid,body=await setup(fixture);request_review(s,v,cid,tid);await finish(s,r,tid)
        await s.manuscripts.decide(cid,decision(s,cid,'clarify',comment='Author fact: existing evaluation is not independent or blinded.'))
        await s.goals.tick();tid=s.store.turns(cid)[-1]['id'];await accepted(s,tid);request_review(s,v,cid,tid);await finish(s,r,tid)
        before=s.manuscripts.view(cid);await s.close()
        restored=Service(s.store,r,s.config);restored.goals.start=lambda:None
        assert restored.manuscripts.view(cid)==before
        assert 'existing evaluation is not independent or blinded' in restored.manuscripts.prompt(cid)
        await restored.goals.tick();assert len(r.calls)==2
        await restored.manuscripts.decide(cid,decision(restored,cid));assert restored.manuscripts.view(cid)['index']==1
        await restored.close()
    asyncio.run(case())
