import asyncio,json
from pathlib import Path
import pytest
from test_p1_service import fixture,settled
from test_goals import start,finish,accepted
from test_training_executor import environment,setup_plan,approve,wait
from pathoreason.goals import GoalCheckpoint,GoalRecoveryInput
from pathoreason.stages import StageHandoff,StageSwitch,StageAssign,STAGES
from pathoreason.persistence import Conflict

def deliver(s,cid,tid,workspace,run=None):
    w=s.stages.view(cid);file=Path(workspace)/'outputs'/f'{w.stage_id}.txt';file.write_text('Synthetic negative result; no scientific approval')
    body=GoalCheckpoint(turn_id=tid,grant=s.guidance.grant(tid),expected_revision=s.goals.view(cid).revision,
        outcome='completed',summary='Current stage delivered',evidence={'files':[str(file.relative_to(workspace))]},
        stage_handoff=StageHandoff(stage_id=w.stage_id,workflow_revision=w.revision,summary='Synthetic stage outcome',decisions=['Use current frozen inputs'],limitations=['Exploratory and non-blinded'],open_questions=['Author review pending'],next_action='Continue only the next authorized stage',training_run_ids=[run] if run and w.stage_id in ('baseline','innovation') else []))
    s.goals.checkpoint(body)
    return body

def test_five_stages_switch_explicitly_preserving_goal_budget_and_evidence(fixture,environment):
    s,r,v,cid,request,task,p,body,op=setup_plan(fixture,environment,units=1)
    approve(s,cid,p);done=wait(s,p.id,v.project_id);assert done.status=='completed'
    async def case():
        s.goals.start=lambda:None;r.hold=True
        async def call(*args,**kwargs):return []
        r.call=call
        from pathoreason.budget_settings import BudgetSettingsUpdate
        await s.budgets.update(cid,BudgetSettingsUpdate(request_key='fixture_allowance',project={'expected_revision':0,'max_turns':12,'max_wall_seconds':1000}))
        first=await s.submit(cid,{**request,'request_key':'stage_first','skill_id':None,'artifact_ids':[],'goal_mode':'continuous','text':'Complete the synthetic research workflow, including negative findings; no new training.'})
        current=cid;tid=first['turn']['id'];await accepted(s,tid);gid=s.goals.view(cid).id
        initial_limits=s.formal.view(v.project_id).budget.model_dump();counts=[]
        for index,(stage,label) in enumerate(STAGES):
            assert s.stages.view(current).stage_id==stage
            deliver(s,current,tid,v.workspace,done.run_id);await finish(s,r,tid)
            view=s.stages.view(current);goal=s.goals.view(current)
            assert not view.scientific_approval and not goal.scientific_approval
            assert view.handoff['agent_report']['limitations']==['Exploratory and non-blinded']
            assert len(s.store.conversations(v.project_id))==index+1
            if index==4:
                assert goal.state=='completed' and view.status=='completed';break
            assert goal.state=='waiting_input' and goal.reason=='stage_handoff_ready'
            await s.goals.tick();assert len(s.store.turns(current))==1  # No automatic stage crossing.
            r.hold=False;before=s.formal.view(v.project_id).used_turns
            next_view=await s.stages.switch(current,StageSwitch(expected_revision=view.revision))
            again=await s.stages.switch(current,StageSwitch(expected_revision=view.revision))
            assert again.conversation_id==next_view.conversation_id
            assert s.formal.view(v.project_id).used_turns==before
            assert s.goals.view(current).continued_in==next_view.conversation_id
            assert s.store.conversation(next_view.conversation_id)['native_session'] is None
            current=next_view.conversation_id
            assert s.goals.view(current).id==gid and s.goals.view(current).turns_used==index+1
            with s.store.connect() as db:
                moved=s.goals._latest(db,current)
            assert moved['user_instructions'][-1]['source']=='stage_switch'
            assert '不批准新训练' in moved['user_instructions'][-1]['text']
            assert s.formal.view(v.project_id).budget.model_dump()==initial_limits
            r.hold=True;await s.goals.tick();tid=s.store.turns(current)[-1]['id'];await accepted(s,tid)
            assert 'FIVE-STAGE WORKFLOW' in r.calls[-1][3] and 'Exploratory and non-blinded' in r.calls[-1][3]
            assert s.stages.view(current).incoming_handoff['source_stage']==stage
        assert len(r.calls)==5 and s.goals.view(current).turns_used==5
        await s.close()
    asyncio.run(case())

def test_changed_evidence_and_cross_conversation_cannot_switch(fixture):
    async def case():
        s,r,v,cid,tid,request=await start(fixture)
        deliver(s,cid,tid,v.workspace);await finish(s,r,tid);w=s.stages.view(cid);r.hold=False
        async def call(*args,**kwargs):return []
        r.call=call
        other=s.new_conversation(v.project_id,'Side conversation')
        with pytest.raises(Conflict,match='stage_changed'):await s.stages.switch(other['id'],StageSwitch(expected_revision=w.revision))
        (Path(v.workspace)/'outputs/data.txt').write_text('changed after handoff')
        with pytest.raises(Conflict,match='stage_evidence_changed'):await s.stages.switch(cid,StageSwitch(expected_revision=w.revision))
        assert len(s.store.conversations(v.project_id))==2 and s.stages.view(cid).status=='ready'
        await s.close()
    asyncio.run(case())

def test_stage_checkpoint_requires_correct_stage_revision_and_deliverable(fixture):
    async def case():
        s,r,v,cid,tid,request=await start(fixture)
        w=s.stages.view(cid)
        base=dict(turn_id=tid,grant=s.guidance.grant(tid),expected_revision=s.goals.view(cid).revision,outcome='completed',summary='Not enough')
        h=dict(stage_id='data',workflow_revision=w.revision,summary='Summary',limitations=['Unknown'],next_action='Next')
        with pytest.raises(ValueError,match='deliverable'):s.goals.checkpoint(GoalCheckpoint(**base,stage_handoff=h))
        h['stage_id']='innovation'
        with pytest.raises(Conflict,match='stage_changed'):s.goals.checkpoint(GoalCheckpoint(**base,stage_handoff=h))
        assert s.stages.view(cid).status=='active'
        await s.close()
    asyncio.run(case())

def test_user_revision_invalidates_old_switch_without_erasing_handoff(fixture):
    async def case():
        s,r,v,cid,tid,request=await start(fixture);deliver(s,cid,tid,v.workspace);await finish(s,r,tid)
        w=s.stages.view(cid)
        result=await s.submit(cid,{**request,'request_key':'revision','text':'Correct the data limitation before switching.'});await accepted(s,result['turn']['id'])
        new=s.stages.view(cid);assert new.status=='active' and new.history[-1]['kind']=='revision_requested'
        with pytest.raises(Conflict,match='stage_changed'):await s.stages.switch(cid,StageSwitch(expected_revision=w.revision))
        await s.close()
    asyncio.run(case())

def test_legacy_assignment_does_not_invent_history_or_change_running_training(fixture):
    async def case():
        from test_p5_entry import study,formal_runtime
        s,_,_,r=fixture;formal_runtime(r);v=study(s);cid=s.store.conversations(v.project_id)[0]['id']
        with s.store.connect(True) as db:db.execute('DELETE FROM research_workflows WHERE project_id=?',(v.project_id,))
        assert s.stages.view(cid) is None
        result=await s.stages.assign(cid,StageAssign(stage_id='innovation'))
        assert result.stage_id=='innovation' and result.history==[] and result.handoff is None
        with pytest.raises(Conflict,match='already_registered'):await s.stages.assign(cid,StageAssign())
        await s.close()
    asyncio.run(case())


def test_context_recovery_rebinds_same_stage_without_advancing(fixture):
    from test_context_recovery import blocked
    async def case():
        s,r,v,cid,tid,request=await blocked(fixture)
        stage=s.stages.view(cid);g=s.goals.view(cid)
        result=await s.goals.recover_context(cid,GoalRecoveryInput(goal_id=g.id,expected_revision=g.revision,action='new_conversation'))
        moved=s.stages.view(result.conversation_id)
        assert moved.stage_id==stage.stage_id and moved.conversation_id!=cid
        assert moved.history==[] and moved.status=='active' and moved.handoff is None
        assert result.turns_used==g.turns_used and result.max_turns==g.max_turns
        await s.close()
    asyncio.run(case())


def test_stage_cannot_finish_during_running_or_unknown_training(fixture):
    async def case():
        s,r,v,cid,tid,request=await start(fixture)
        with s.store.connect(True) as db:
            db.execute('INSERT INTO training_experiments VALUES(?,?,?)',('exp_active',v.project_id,json.dumps({'status':'running'})))
        with pytest.raises(Conflict,match='training_not_terminal'):deliver(s,cid,tid,v.workspace)
        with s.store.connect(True) as db:
            db.execute('UPDATE training_experiments SET document=? WHERE id=?',(json.dumps({'status':'needs_reconciliation'}),'exp_active'))
        with pytest.raises(Conflict,match='training_not_terminal'):deliver(s,cid,tid,v.workspace)
        assert s.stages.view(cid).status=='active'
        await s.close()
    asyncio.run(case())
