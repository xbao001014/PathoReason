import asyncio,hashlib,json
from pathlib import Path
import pytest
from pathoreason.manuscript import RevisionRoute,ReviewRequest
from pathoreason.goals import GoalCheckpoint
from pathoreason.stages import StageHandoff
from pathoreason.persistence import Conflict
from pathoreason.presentation_revision import CHECKS,validate_presentation
from pathoreason.study_io import publish_artifact
from test_p1_service import fixture
from test_manuscript_review import setup,request_review,finish,accepted,decision


async def completed(fixture,with_figure=False):
    s,r,v,cid,tid,body=await setup(fixture,turns=24)
    for index in range(5):
        if with_figure and index==3:
            original_checkpoint=s.goals.checkpoint
            def add_figure(body):
                image=Path(v.workspace)/'figures/original.svg';image.parent.mkdir(exist_ok=True)
                image.write_text('<svg xmlns="http://www.w3.org/2000/svg"><text y="20">AUC 0.5</text></svg>')
                a=publish_artifact(s,v.project_id,'figures/original.svg','Original figure')
                manifest=next(m for m in body.manuscript_review.materials if m.role=='figure_manifest')
                value={'artifact_ids':[a.id],'figures':[{'artifact_id':a.id,'figure_number':1,'file':'figures/original.svg','caption':'Synthetic unchanged value'}]}
                file='manuscript/with-figure.json';(Path(v.workspace)/file).parent.mkdir(exist_ok=True);(Path(v.workspace)/file).write_text(json.dumps(value))
                ma=publish_artifact(s,v.project_id,file,'Manifest');manifest.artifact_id=ma.id
                audit='manuscript/figure-audit.md';(Path(v.workspace)/audit).write_text('Synthetic figure check')
                fa=publish_artifact(s,v.project_id,audit,'Figure audit')
                from pathoreason.manuscript import ReviewMaterial
                body.manuscript_review.materials.extend([ReviewMaterial(role='figure',label='Original',artifact_id=a.id),ReviewMaterial(role='figure_audit',label='Figure audit',artifact_id=fa.id)])
                body.evidence.artifact_ids=[m.artifact_id for m in body.manuscript_review.materials]
                return original_checkpoint(body)
            s.goals.checkpoint=add_figure
            try:request_review(s,v,cid,tid)
            finally:s.goals.checkpoint=original_checkpoint
        else:request_review(s,v,cid,tid)
        await finish(s,r,tid)
        await s.manuscripts.decide(cid,decision(s,cid));await s.goals.tick()
        tid=s.store.turns(cid)[-1]['id'];await accepted(s,tid)
    w=s.manuscripts.view(cid);stage=s.stages.view(cid)
    s.goals.checkpoint(GoalCheckpoint(turn_id=tid,grant=s.guidance.grant(tid),expected_revision=s.goals.view(cid).revision,outcome='completed',summary='Synthetic final delivery',evidence={'artifact_ids':[m['artifact_id'] for m in w['approved'][-1]['materials']]},stage_handoff=StageHandoff(stage_id='manuscript',workflow_revision=stage.revision,summary='Approved synthetic package',limitations=['Synthetic'],next_action='Await user request')))
    await finish(s,r,tid);assert s.goals.view(cid).state=='completed'
    return s,r,v,cid,body


def command(s,cid,tid,text,**kw):
    with s.store.connect() as db:w=s.manuscripts.get(db,s.store.conversation(cid)['project_id'])
    return RevisionRoute(turn_id=tid,grant=s.guidance.grant(tid),expected_goal_revision=s.goals.view(cid).revision,expected_revision=w['revision'],source='user_message',source_id=tid,instruction_excerpt=text,reason='Adjust presentation without changing scientific content',revision_kind=kw.pop('revision_kind','presentation'),target_gate=kw.pop('target_gate','delivery'),**kw)


def submit_adjusted_delivery(s,v,cid,tid,changes=(),extra=()):
    w=s.manuscripts.view(cid);materials=[]
    for role in ('pdf','source','pdf_qa','checklist'):
        name='manuscript/presentation-'+str(w['revision'])+'-'+role+('.pdf' if role=='pdf' else '.md')
        (Path(v.workspace)/name).parent.mkdir(exist_ok=True)
        (Path(v.workspace)/name).write_bytes(b'%PDF-1.4 synthetic adjusted page\n' if role=='pdf' else b'Synthetic presentation only')
        a=publish_artifact(s,v.project_id,name,role);materials.append({'role':role,'label':role,'artifact_id':a.id})
    materials.extend(extra)
    report={'schema_version':'pathoreason.presentation-audit/1','scientific_basis_digest':w['approved'][3]['digest'],
        'material_sha256':{m['artifact_id']:s.store.artifact(m['artifact_id'],v.project_id)['sha256'] for m in materials},
        'changes':list(changes),'status':'passed','checks':dict.fromkeys(CHECKS,'unchanged')}
    path='manuscript/presentation-audit-'+str(w['revision'])+'.json';(Path(v.workspace)/path).write_text(json.dumps(report))
    a=publish_artifact(s,v.project_id,path,'Presentation comparison');materials.append({'role':'presentation_audit','label':'Presentation comparison','artifact_id':a.id})
    req=ReviewRequest(gate='delivery',expected_revision=w['revision'],summary='Adjusted layout ready',materials=materials,
        audit_status='passed',scientific_basis_digest=w['approved'][3]['digest'],presentation_only=True,presentation_changes=list(changes),
        changes=['Layout updated'],key_findings=['Scientific content preserved'],key_limitations=['Synthetic visual audit'])
    s.goals.checkpoint(GoalCheckpoint(turn_id=tid,grant=s.guidance.grant(tid),expected_revision=s.goals.view(cid).revision,outcome='needs_input',summary='Author delivery review',evidence={'artifact_ids':[m['artifact_id'] for m in materials]},manuscript_review=req))
    return req


@pytest.mark.parametrize('new_chat',[False,True])
def test_post_final_presentation_preserves_science_and_budget_and_only_reviews_delivery(fixture,new_chat):
    async def case():
        s,r,v,oldcid,body=await completed(fixture)
        original=s.manuscripts.view(oldcid);old_goal=s.goals.view(oldcid).model_dump();limits=s.formal.view(v.project_id).budget.model_dump()
        cid=s.new_conversation(v.project_id,'Adjust figure appearance')['id'] if new_chat else oldcid
        text='请把图表字体放大并调整页面留白，保留数据和内容。'
        before=s.stages.view(oldcid)
        result=await s.submit(cid,{**body,'request_key':'adjust_final','text':text});tid=result['turn']['id'];await accepted(s,tid)
        if new_chat:
            assert s.stages.view(oldcid).conversation_id==oldcid
            assert 'PROJECT MANUSCRIPT REVISION ENTRY' in r.calls[-1][3]
            assert str(original['revision']) in r.calls[-1][3]
        goal=s.goals.view(cid).model_dump();cmd=command(s,cid,tid,text);after=s.manuscripts.route_revision(cmd)
        assert after['index']==4 and after['author_content_approved'] and not after['delivery_approved']
        assert after['approved']==original['approved'][:4]
        assert after['history'][-1]['invalidated']==[original['approved'][4]]
        assert after['revision_context']['kind']=='presentation'
        assert s.stages.view(cid).conversation_id==cid and s.stages.view(cid).status=='active'
        assert s.goals.view(cid).model_dump()==goal and s.formal.view(v.project_id).budget.model_dump()==limits
        if new_chat:assert s.goals.view(oldcid).model_dump()==old_goal
        assert s.manuscripts.route_revision(cmd)['revision']==after['revision']
        with pytest.raises(Conflict,match='replay_changed'):s.manuscripts.route_revision(cmd.model_copy(update={'reason':'different'}))
        # A generic delivery report is insufficient for a routed presentation revision.
        with pytest.raises(ValueError,match='presentation_audit_required'):request_review(s,v,cid,tid)
        submit_adjusted_delivery(s,v,cid,tid);await finish(s,r,tid)
        pending=s.manuscripts.view(cid);assert pending['index']==4 and pending['status']=='awaiting_review'
        assert pending['author_content_approved'] and not pending['delivery_approved']
        for p in original['approved']:
            for m in p['materials']:
                assert hashlib.sha256((s.manuscripts.root/v.project_id/p['id']/m['artifact_id']).read_bytes()).hexdigest()==m['sha256']
        # Explicit author delivery decision, never automatically granted by route/audit.
        final=await s.manuscripts.decide(cid,decision(s,cid));assert final['delivery_approved']
        assert final['approved'][:4]==original['approved'][:4]
        assert s.formal.view(v.project_id).budget.model_dump()==limits
        await s.close()
    asyncio.run(case())


def test_discussion_in_new_chat_only_discovers_and_does_not_reopen(fixture):
    async def case():
        s,r,v,cid,body=await completed(fixture);new=s.new_conversation(v.project_id,'Discussion')['id']
        original=s.manuscripts.view(cid);stage=s.stages.view(cid)
        prompt=s.stages.prompt(new);assert 'not ownership or permission' in prompt
        assert s.manuscripts.view(cid)==original and s.stages.view(cid)==stage
        result=await s.submit(new,{**body,'request_key':'question','text':'如果以后想改图，可以吗？'});await accepted(s,result['turn']['id'])
        assert s.manuscripts.view(cid)==original and s.stages.view(cid)==stage
        await s.close()
    asyncio.run(case())


def test_final_scientific_revision_revokes_only_scientific_and_delivery(fixture):
    async def case():
        s,r,v,cid,body=await completed(fixture);original=s.manuscripts.view(cid)
        new=s.new_conversation(v.project_id,'Correct scientific label')['id'];text='请更正图中的类别含义并返回科学审核。'
        result=await s.submit(new,{**body,'request_key':'content','text':text});tid=result['turn']['id'];await accepted(s,tid)
        result=s.manuscripts.route_revision(command(s,new,tid,text,revision_kind='content',target_gate='scientific'))
        assert result['approved']==original['approved'][:3] and not result['author_content_approved']
        assert result['history'][-1]['invalidated']==original['approved'][3:]
        await s.close()
    asyncio.run(case())


@pytest.mark.parametrize('bad',['hash','meaning','mapping','foreign_original','false_flag'])
def test_presentation_audit_rejects_unbound_or_content_changes(bad):
    from types import SimpleNamespace
    science={'digest':'a'*64,'materials':[{'artifact_id':'original','role':'figure','sha256':'b'*64}]}
    changes=[{'original_artifact_id':'original','revised_artifact_id':'new','description':'Increase font size'}]
    req=ReviewRequest(gate='delivery',expected_revision=1,summary='Adjusted',materials=[{'artifact_id':'new','role':'figure','label':'figure'}],presentation_only=True,presentation_changes=changes,scientific_basis_digest=science['digest'],audit_status='passed')
    materials=[{'artifact_id':'new','role':'figure','sha256':'c'*64},{'artifact_id':'audit','role':'presentation_audit','sha256':'d'*64}]
    report={'schema_version':'pathoreason.presentation-audit/1','scientific_basis_digest':science['digest'],'material_sha256':{'new':'c'*64},'changes':changes,'status':'passed','checks':dict.fromkeys(CHECKS,'unchanged')}
    w={'approved':[{}, {}, {},science],'revision_context':{'kind':'presentation'}}
    service=SimpleNamespace(material_bytes=lambda *_:(None,json.dumps(report).encode()))
    validate_presentation(service,'p',w,req,materials)
    if bad=='hash':report['material_sha256']['new']='e'*64
    if bad=='meaning':report['checks']['labels_and_units']='changed'
    if bad=='mapping':report['changes']=[]
    if bad=='foreign_original':req.presentation_changes[0].original_artifact_id='foreign'
    if bad=='false_flag':req.presentation_only=False
    with pytest.raises((ValueError,Conflict)):validate_presentation(service,'p',w,req,materials)


def test_new_figure_delivery_is_pending_until_author_accepts_and_updates_workbench(fixture):
    from pathoreason.research_workbench import project_snapshot
    async def case():
        s,r,v,oldcid,body=await completed(fixture,with_figure=True)
        science=s.manuscripts.view(oldcid)['approved'][3];old=next(m for m in science['materials'] if m['role']=='figure')
        cid=s.new_conversation(v.project_id,'Enlarge figure labels')['id'];text='只把图中文字加大，数字与含义保持不变。'
        result=await s.submit(cid,{**body,'request_key':'figure_adjust','text':text});tid=result['turn']['id'];await accepted(s,tid)
        s.manuscripts.route_revision(command(s,cid,tid,text))
        file='figures/large-labels.svg';(Path(v.workspace)/file).write_text('<svg xmlns="http://www.w3.org/2000/svg"><text y="20" font-size="20">AUC 0.5</text></svg>')
        new=publish_artifact(s,v.project_id,file,'Larger labels')
        changes=[dict(original_artifact_id=old['artifact_id'],revised_artifact_id=new.id,description='Font size only')]
        submit_adjusted_delivery(s,v,cid,tid,changes,extra=[dict(role='figure',label='Larger labels',artifact_id=new.id)])
        await finish(s,r,tid)
        projected=project_snapshot(s,v.project_id)['outcomes']
        assert projected['content']['status']=='approved'
        assert projected['figures'][0]['id']==new.id and projected['figures'][0]['status']=='awaiting_review'
        assert projected['delivery']['presentation_only']
        await s.manuscripts.decide(cid,decision(s,cid))
        projected=project_snapshot(s,v.project_id)['outcomes']
        assert projected['figures'][0]['status']=='approved'
        assert s.manuscripts.view(cid)['approved'][3]==science
        await s.close()
    asyncio.run(case())


def test_new_chat_cannot_take_over_unfinished_owner_goal(fixture):
    async def case():
        s,r,v,cid,body=await completed(fixture)
        with s.store.connect(True) as db:
            g=s.goals._latest(db,cid);g.update(state='paused');s.goals._save(db,g,'synthetic_paused_owner')
        other=s.new_conversation(v.project_id,'Other chat')['id'];text='调整图表格式。'
        result=await s.submit(other,{**body,'request_key':'busy_owner','text':text});tid=result['turn']['id'];await accepted(s,tid)
        original=s.manuscripts.view(cid);stage=s.stages.view(cid)
        with pytest.raises(Conflict,match='owner_busy'):s.manuscripts.route_revision(command(s,other,tid,text))
        assert s.manuscripts.view(cid)==original and s.stages.view(cid)==stage
        await s.close()
    asyncio.run(case())
