import asyncio,json
import pytest
from test_p1_service import fixture
from test_goals import start,checkpoint,finish,accepted
from pathoreason.goals import GoalControl,GoalRecoveryInput
from pathoreason.persistence import Conflict,encoded
from pathoreason.runtime import compacted_context_estimate
from pathoreason.service import Service


def messages(tail=None):
    return [
      {'info':{'id':'old','role':'user'},'parts':[{'type':'text','text':'old history '*3000}]},
      {'info':{'id':'tail','role':'user'},'parts':[{'type':'text','text':'retained task'}]},
      {'info':{'id':'compact_user','role':'user'},'parts':[{'type':'compaction',**({'tail_start_id':tail} if tail else {})}]},
      {'info':{'id':'summary','role':'assistant','parentID':'compact_user','summary':True,'finish':'stop','time':{'completed':123},'tokens':{'input':1000000}},'parts':[{'type':'text','text':'Verified short summary'}]}]


def test_compaction_estimate_counts_retained_tail_and_rejects_unverified_summary():
    plain=compacted_context_estimate(messages(),{'summary'})
    tail=compacted_context_estimate(messages('tail'),{'summary'})
    assert 16384<plain['context_tokens']<20000 and tail['context_tokens']>plain['context_tokens']
    assert plain['retained_messages']==2 and tail['retained_messages']==3
    with pytest.raises(ValueError):compacted_context_estimate(messages('missing'),{'summary'})
    with pytest.raises(ValueError):compacted_context_estimate(messages(),{'old'})
    failed=messages();failed[-1]['info']['error']={'message':'failed'}
    with pytest.raises(ValueError):compacted_context_estimate(failed,{'summary'})


async def blocked(fixture):
    s,r,v,cid,tid,body=await start(fixture)
    checkpoint(s,cid,tid);await finish(s,r,tid)
    with s.store.connect() as db:g=s.goals._latest(db,cid)
    s.goals._set_state(g,'blocked','context_window_requires_compaction_or_handoff')
    async def call(*args,**kwargs):return []
    r.call=call;r.hold=False
    return s,r,v,cid,tid,body


def native_compactor(r,*,lost=False):
    marks=[];calls=[]
    async def marker(*args):return list(marks)
    async def compact(*args):
        calls.append(args);marks.append('summary')
        if lost:raise TimeoutError('ack lost')
        return {'observed':True,'source':'native_fixture'}
    async def estimate(session,directory,ids):return compacted_context_estimate(messages(),ids)
    r.compaction_marker=marker;r.compact=compact;r.compacted_context=estimate
    return calls


def test_verified_compaction_unblocks_without_rewriting_turn_usage(fixture):
    async def case():
        s,r,v,cid,tid,body=await blocked(fixture);calls=native_compactor(r)
        s.store.update(tid,usage=encoded({'context_tokens':1040000,'context_source':'estimate_from_runtime_usage'}))
        before=s.store.turn(tid);g=s.goals.view(cid)
        req=GoalRecoveryInput(goal_id=s.goals.view(cid).id,expected_revision=g.revision,action='compact')
        result=await s.goals.recover_context(cid,req)
        assert result.state=='active' and s.context.view(cid).source=='post_compaction_bytes_estimate'
        assert s.context.view(cid).context_tokens<20000 and s.context.view(cid).compaction_remaining==1
        assert s.store.turn(tid)==before
        await s.goals.recover_context(cid,req);assert len(calls)==1
        r.hold=True;await s.goals.tick();auto=s.store.turns(cid)[-1]['id'];await accepted(s,auto)
        assert len(s.store.turns(cid))==2 and s.goals.view(cid).turns_used==2
        assert s.context.view(cid).source!='post_compaction_bytes_estimate'
        await s.close()
    asyncio.run(case())


def test_unknown_compaction_reconciles_without_duplicate_model_call(fixture):
    async def case():
        s,r,v,cid,tid,body=await blocked(fixture);calls=native_compactor(r,lost=True)
        result=await s.goals.recover_context(cid,GoalRecoveryInput(goal_id=s.goals.view(cid).id,expected_revision=s.goals.view(cid).revision,action='compact'))
        assert result.state=='blocked' and result.reason=='context_operation_unresolved'
        result=await s.goals.recover_context(cid,GoalRecoveryInput(goal_id=s.goals.view(cid).id,expected_revision=result.revision,action='reconcile'))
        assert result.state=='active' and len(calls)==1 and len(s.store.turns(cid))==1
        await s.close()
    asyncio.run(case())


def test_missing_native_projection_does_not_resume(fixture):
    async def case():
        s,r,v,cid,tid,body=await blocked(fixture)
        async def compact(*args):return {'observed':True}
        r.compact=compact
        g=await s.goals.recover_context(cid,GoalRecoveryInput(goal_id=s.goals.view(cid).id,expected_revision=s.goals.view(cid).revision,action='compact'))
        assert g.state=='blocked' and g.reason=='context_usage_unverified'
        await s.goals.tick();assert len(s.store.turns(cid))==1
        await s.close()
    asyncio.run(case())


def test_same_project_window_transfer_keeps_goal_scope_and_counters(fixture):
    async def case():
        s,r,v,cid,tid,body=await blocked(fixture);g=s.goals.view(cid)
        from pathoreason.permission_settings import PermissionSettingsUpdate
        await s.formal.permissions.update(cid,PermissionSettingsUpdate(expected_revision=0,settings={'mode':'custom','bash':'deny','edit':'deny','webfetch':'deny','external_directory':'deny'}))
        with s.store.connect(True) as db:
            row=s.store.turn(tid);digest=json.loads(row['document'])['config_digest']
            frozen=json.loads(db.execute('SELECT document FROM runtime_configs WHERE digest=?',(digest,)).fetchone()[0]);frozen['execution_scope']='inspection'
            db.execute('UPDATE runtime_configs SET document=? WHERE digest=?',(encoded(frozen),digest))
        req=GoalRecoveryInput(goal_id=s.goals.view(cid).id,expected_revision=g.revision,action='new_conversation')
        new=await s.goals.recover_context(cid,req)
        assert new.id==g.id and new.conversation_id!=cid and new.turns_used==g.turns_used and new.max_turns==g.max_turns
        assert new.completion_criteria==g.completion_criteria
        assert s.goals.view(cid).continued_in==new.conversation_id
        assert s.store.conversation(new.conversation_id)['project_id']==v.project_id
        assert s.formal.permissions.view(new.conversation_id).settings.bash=='deny'
        again=await s.goals.recover_context(cid,req);assert again.conversation_id==new.conversation_id
        assert len(s.store.conversations(v.project_id))==2
        r.hold=True;await s.goals.tick();auto=s.store.turns(new.conversation_id)[-1]['id'];await accepted(s,auto)
        assert s.formal.view(v.project_id).used_turns==2 and s.goals.view(new.conversation_id).turns_used==2
        with s.store.connect() as db:
            digest=json.loads(s.store.turn(auto)['document'])['config_digest']
            assert json.loads(db.execute('SELECT document FROM runtime_configs WHERE digest=?',(digest,)).fetchone()[0])['execution_scope']=='inspection'
        assert len(s.store.turns(cid))==1
        await s.close()
    asyncio.run(case())


def test_window_transfer_transaction_rolls_back_on_failure(fixture,monkeypatch):
    async def case():
        s,r,v,cid,tid,body=await blocked(fixture)
        def fail(*args):raise RuntimeError('transaction failure')
        monkeypatch.setattr(s.goals,'_save',fail)
        with pytest.raises(RuntimeError):await s.goals.recover_context(cid,GoalRecoveryInput(goal_id=s.goals.view(cid).id,expected_revision=s.goals.view(cid).revision,action='new_conversation'))
        assert len(s.store.conversations(v.project_id))==1 and s.goals.view(cid).conversation_id==cid
        await s.close()
    asyncio.run(case())


def test_plain_resume_does_not_reenter_context_failure(fixture):
    async def case():
        s,r,v,cid,tid,body=await blocked(fixture)
        with pytest.raises(Conflict,match='context_recovery_required'):await s.goals.control(cid,GoalControl(expected_revision=s.goals.view(cid).revision,action='resume'))
        assert len(s.store.turns(cid))==1
        await s.close()
    asyncio.run(case())


def test_user_pause_wins_over_recovery_completion(fixture,monkeypatch):
    async def case():
        s,r,v,cid,tid,body=await blocked(fixture)
        async def compact(*args):
            await s.goals.control(cid,GoalControl(expected_revision=s.goals.view(cid).revision,action='pause'))
            return {'status':'completed'}
        monkeypatch.setattr(s.context,'compact',compact)
        g=await s.goals.recover_context(cid,GoalRecoveryInput(goal_id=s.goals.view(cid).id,expected_revision=s.goals.view(cid).revision,action='compact'))
        assert g.state=='paused' and g.reason=='user_paused'
        await s.goals.tick();assert len(s.store.turns(cid))==1
        await s.close()
    asyncio.run(case())


def test_recovery_restart_stops_unknown_intent(fixture):
    async def case():
        s,r,v,cid,tid,body=await blocked(fixture)
        with s.store.connect(True) as db:
            g=s.goals._latest(db,cid);g.update(state='paused',reason='context_recovery_running');s.goals._save(db,g,'test_interrupted_recovery')
        await s.close();restored=Service(s.store,r,s.config);restored.goals.start=lambda:None
        await restored.recover()
        assert restored.goals.view(cid).state=='blocked' and restored.goals.view(cid).reason=='context_operation_unresolved'
        await restored.goals.tick();assert len(restored.store.turns(cid))==1
        await restored.close()
    asyncio.run(case())


def test_project_budget_still_blocks_new_window(fixture):
    async def case():
        s,r,v,cid,tid,body=await blocked(fixture)
        from types import SimpleNamespace
        s.formal.view=lambda _:SimpleNamespace(used_turns=1,used_budget_seconds=1,budget=SimpleNamespace(max_turns=1,max_wall_seconds=60))
        with pytest.raises(Conflict,match='acceptance_budget_exhausted'):await s.goals.recover_context(cid,GoalRecoveryInput(goal_id=s.goals.view(cid).id,expected_revision=s.goals.view(cid).revision,action='new_conversation'))
        assert len(s.store.conversations(v.project_id))==1
        await s.close()
    asyncio.run(case())


def test_compaction_quota_follows_project_across_conversations(fixture):
    async def case():
        s,r,v,cid,tid,body=await blocked(fixture);native_compactor(r)
        for key in ['quota_one','quota_two']:
            assert (await s.context.compact(cid,key,body['model']))['status']=='completed'
        other=s.new_conversation(v.project_id,'same project')
        assert s.context.view(other['id']).compaction_remaining==0
        assert s.context.view(cid).compaction_remaining==0
        from test_p5_entry import study
        new=study(s,key='other_project')
        newcid=s.store.conversations(new.project_id)[0]['id']
        assert s.context.view(newcid).compaction_remaining==2
        with pytest.raises(Conflict,match='context_budget_exhausted'):await s.context.compact(cid,'third',body['model'])
        await s.close()
    asyncio.run(case())


def test_recovery_http_route_is_idempotent(fixture,monkeypatch):
    from fastapi.testclient import TestClient
    import pathoreason.api as api
    async def prepare():return await blocked(fixture)
    s,r,v,cid,tid,body=asyncio.run(prepare())
    from contextlib import asynccontextmanager
    @asynccontextmanager
    async def lifespan(app):
        app.state.service=s
        yield
        await s.close()
    monkeypatch.setattr(api.app.router,'lifespan_context',lifespan)
    with TestClient(api.app) as client:
        request={'goal_id':s.goals.view(cid).id,'expected_revision':s.goals.view(cid).revision,'action':'new_conversation'}
        first=client.post('/api/v2/conversations/'+cid+'/goal/context-recovery',json=request)
        second=client.post('/api/v2/conversations/'+cid+'/goal/context-recovery',json=request)
        assert first.status_code==second.status_code==200
        assert first.json()['conversation_id']==second.json()['conversation_id']
        assert client.get('/api/v2/conversations/'+cid+'/goal').json()['continued_in']==first.json()['conversation_id']


def test_two_goals_with_equal_revisions_do_not_share_recovery_receipts(fixture):
    async def case():
        s,r,v,cid,tid,body=await blocked(fixture);native_compactor(r)
        first=s.goals.view(cid)
        await s.goals.recover_context(cid,GoalRecoveryInput(goal_id=first.id,expected_revision=first.revision,action='compact'))
        with s.store.connect() as db:g=s.goals._latest(db,cid)
        s.goals._set_state(g,'completed','fixture_first_goal_finished')
        r.hold=True
        result=await s.submit(cid,{**body,'request_key':'second_goal_context','text':'第二个合成目标'})
        tid2=result['turn']['id'];await accepted(s,tid2)
        checkpoint(s,cid,tid2);await finish(s,r,tid2);r.hold=False
        with s.store.connect() as db:g=s.goals._latest(db,cid)
        s.goals._set_state(g,'blocked','context_window_requires_compaction_or_handoff')
        second=s.goals.view(cid)
        assert first.revision==second.revision and first.id!=second.id
        moved=await s.goals.recover_context(cid,GoalRecoveryInput(goal_id=second.id,expected_revision=second.revision,action='new_conversation'))
        assert moved.id==second.id and moved.conversation_id!=cid
        assert s.goals.view(cid).id==second.id and s.goals.view(cid).continued_in==moved.conversation_id
        await s.close()
    asyncio.run(case())


def test_first_release_receipts_migrate_without_repeating_compaction(fixture):
    async def case():
        s,r,v,cid,tid,body=await blocked(fixture);calls=native_compactor(r)
        g=s.goals.view(cid);request=GoalRecoveryInput(goal_id=g.id,expected_revision=g.revision,action='compact')
        await s.goals.recover_context(cid,request)
        with s.store.connect(True) as db:
            rows=db.execute('SELECT source_conversation,revision,action,document FROM goal_context_recoveries').fetchall()
            db.execute('DROP TABLE goal_context_recoveries')
            db.execute('CREATE TABLE goal_context_recoveries(source_conversation TEXT,revision INTEGER,action TEXT,document TEXT,PRIMARY KEY(source_conversation,revision))')
            for row in rows:db.execute('INSERT INTO goal_context_recoveries VALUES(?,?,?,?)',tuple(row))
        from pathoreason.goals import Goals
        s.goals=Goals(s);s.goals.start=lambda:None
        result=await s.goals.recover_context(cid,request)
        assert result.id==g.id and len(calls)==1
        with s.store.connect() as db:
            assert db.execute('SELECT count(*) FROM goal_context_recoveries_legacy').fetchone()[0]==1
            assert db.execute('SELECT goal_id FROM goal_context_recoveries').fetchone()[0]==g.id
        await s.close()
    asyncio.run(case())
