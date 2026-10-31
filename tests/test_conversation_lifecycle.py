import asyncio
import json
from pathlib import Path

import httpx
import pytest

from pathoreason.persistence import Conflict, Gone, Store, encoded
from pathoreason.runtime import OpenCode
from pathoreason.service import Service
from test_p1_service import fixture, settled


def install_delete(runtime):
    runtime.deleted = []
    async def call(*args):return []
    async def delete(sid, directory):
        runtime.deleted.append(sid)
        runtime.sessions.pop(sid, None)
    runtime.call = call
    runtime.delete_session = delete


async def finish(s, c, request):
    turn = await s.submit(c['id'], request)
    await settled(s, turn['turn']['id'])
    await asyncio.gather(*list(s.tasks.values()))
    return turn['turn']['id']


def test_archive_restore_retains_history_and_blocks_idempotent_submit(fixture):
    s, c, request, runtime = fixture
    install_delete(runtime)
    async def case():
        tid = await finish(s, c, request)
        before = s.store.turn(tid)
        assert (await s.conversations.archive(c['id'])).state == 'archived'
        assert s.conversations.list(c['project_id']) == []
        assert s.conversations.list(c['project_id'], True)[0].status == 'archived'
        assert s.store.turn(tid) == before
        with pytest.raises(Conflict, match='conversation_archived'):
            await s.submit(c['id'], request)
        with pytest.raises(Conflict, match='conversation_archived'):
            await s.context.compact(c['id'], 'compact_archived', request['model'])
        assert (await s.conversations.archive(c['id'], restore=True)).state == 'open'
        assert (await s.submit(c['id'], request))['turn']['id'] == tid
        assert len(runtime.calls) == 1 and runtime.deleted == []
    asyncio.run(case())


def test_delete_scrubs_content_preserves_assets_provenance_and_budget(fixture):
    s, c, request, runtime = fixture
    install_delete(runtime)
    async def case():
        tid = await finish(s, c, request)
        sibling = s.new_conversation(c['project_id'], 'Sibling')
        workspace = Path(s.store.conversation(c['id'])['directory'])
        shared = workspace / 'model-created-memory.md'
        shared.write_text('Project research evidence')
        artifacts = s.store.artifacts(c['project_id'])
        blobs = [s.artifact_bytes(a) for a in artifacts]
        with s.store.connect(True) as db:
            budget = [dict(r) for r in s.store.budget_rows(db)]
            db.execute('INSERT INTO context_operations VALUES(?,?,?,?,?,?)', ('op_test',c['id'],'compact_once','deepseek-v4-pro','completed',encoded({'id':'op_test','status':'completed','free_text':'CHAT_CONTEXT'})))
            db.execute('INSERT INTO handoffs VALUES(?,?)',(c['id'],encoded({'digest':'d'*64,'artifact_map':{'old':'art_test'},'source_environment':'local','source_runtime':'codex','source_project_id':'prj_origin','constraints':['CHAT_CONTEXT']})))
        result = await s.conversations.delete(c['id'])
        assert result.state == 'deleted' and result.native_deleted
        assert (await s.conversations.delete(c['id'])) == result
        assert len(runtime.deleted) == 1
        assert [x.id for x in s.conversations.list(c['project_id'],True)] == [sibling['id']]
        for read in [lambda:s.store.conversation(c['id']),lambda:s.store.turn(tid),lambda:s.store.events(c['id'],0),lambda:s.domain.context(tid),lambda:s.context.export(c['id'])]:
            with pytest.raises(Gone):read()
        with pytest.raises(Gone):await s.submit(c['id'], request)
        with s.store.connect() as db:
            assert [dict(r) for r in s.store.budget_rows(db)] == budget
            row = db.execute('SELECT * FROM turns WHERE id=?',(tid,)).fetchone()
            assert row['text'] == row['user_text'] == row['input_digest'] == ''
            assert row['tools'] == '[]'
            for table in ['events','bindings','context_snapshots','skill_invocations']:
                assert db.execute('SELECT count(*) FROM '+table).fetchone()[0] == 0
            receipt = json.loads(db.execute('SELECT document FROM handoffs').fetchone()[0])
            assert receipt['artifact_map'] == {'old':'art_test'} and 'constraints' not in receipt
            assert db.execute('SELECT count(*) FROM context_operations').fetchone()[0] == 1
            assert 'CHAT_CONTEXT' not in db.execute('SELECT document FROM context_operations').fetchone()[0]
        assert s.store.artifacts(c['project_id']) == artifacts
        assert [s.artifact_bytes(a) for a in artifacts] == blobs
        assert shared.read_text() == 'Project research evidence'
        assert s.store.conversation(sibling['id'])['directory'] == str(workspace)
        s.config['p1_test_limits']['max_turns'] = 1
        with pytest.raises(Conflict,match='acceptance_budget_exhausted'):
            await s.submit(sibling['id'],{**request,'request_key':'after_delete'})
    asyncio.run(case())


@pytest.mark.parametrize('state',['queued','running','interrupt_requested','recovery_required'])
def test_active_or_unknown_turn_rejects_destructive_actions(fixture,state):
    s,c,request,runtime=fixture
    install_delete(runtime)
    async def case():
        tid=await finish(s,c,request)
        s.state(tid,state)
        for action in [s.conversations.archive,s.conversations.delete]:
            with pytest.raises(Conflict,match='conversation_busy'):await action(c['id'])
        assert runtime.deleted==[] and s.conversations.view(c['id']).state=='open'
    asyncio.run(case())


def test_failed_cleanup_survives_restart_and_resumes_without_redeleting_native(fixture,monkeypatch):
    s,c,request,runtime=fixture
    install_delete(runtime)
    async def case():
        await finish(s,c,request)
        def fail(*args):raise OSError('private filesystem details')
        monkeypatch.setattr(s.conversations,'_purge',fail)
        first=await s.conversations.delete(c['id'])
        assert first.state=='failed' and first.native_deleted
        assert first.error_code=='conversation_cleanup_incomplete'
        with pytest.raises(Conflict,match='deletion_pending'):s.store.conversation(c['id'])
        with pytest.raises(Conflict,match='deletion_pending'):await s.submit(c['id'],request)
        restored=Service(Store(s.store.path),runtime,s.config)
        assert restored.conversations.view(c['id']).state=='failed'
        assert (await restored.conversations.delete(c['id'])).state=='deleted'
        assert len(runtime.deleted)==1
    asyncio.run(case())


def test_shared_native_session_blocked(fixture):
    s,c,request,runtime=fixture
    install_delete(runtime)
    async def case():
        await finish(s,c,request)
        other=s.new_conversation(c['project_id'],'Shared native')
        with s.store.connect(True) as db:
            db.execute('UPDATE conversations SET native_session=? WHERE id=?',(s.store.conversation(c['id'])['native_session'],other['id']))
        with pytest.raises(Conflict,match='native_session_shared'):await s.conversations.delete(c['id'])
        assert runtime.deleted==[]
    asyncio.run(case())


@pytest.mark.parametrize('kind',['compaction','permission','native_busy','pending_permission'])
def test_unresolved_native_operations_block_cleanup(fixture,kind):
    s,c,request,runtime=fixture
    install_delete(runtime)
    async def case():
        await finish(s,c,request)
        if kind=='compaction':
            with s.store.connect(True) as db:db.execute('INSERT INTO context_operations VALUES(?,?,?,?,?,?)',('op_active',c['id'],'req_op','deepseek-v4-pro','recovery_required','{}'))
        elif kind=='permission':
            with s.store.connect(True) as db:db.execute('INSERT INTO formal_permissions VALUES(?,?,?,?)',('per_unknown',c['id'],'turn_x',encoded({'state':'dispatching'})))
        elif kind=='native_busy':runtime.hold=True
        else:
            async def pending(*args):return [{'sessionID':s.store.conversation(c['id'])['native_session']}]
            runtime.call=pending
        with pytest.raises(Conflict):await s.conversations.delete(c['id'])
        assert runtime.deleted==[]
    asyncio.run(case())


def test_public_api_confirmation_tombstone_and_deleted_read_paths(fixture):
    from fastapi.testclient import TestClient
    from pathoreason.api import app
    s,c,request,runtime=fixture
    app.state.service=s
    client=TestClient(app)
    url='/api/v1/conversations/'+c['id']
    assert client.post(url+'/archive').json()['state']=='archived'
    assert client.get('/api/v1/research-projects/'+c['project_id']+'/conversations').json()==[]
    assert len(client.get('/api/v1/research-projects/'+c['project_id']+'/conversations?include_archived=true').json())==1
    assert client.post(url+'/restore').json()['state']=='open'
    assert client.request('DELETE',url,json={'confirm':False}).status_code==422
    assert client.request('DELETE',url,json={'confirm':True},headers={'Origin':'https://untrusted.invalid'}).status_code==403
    assert client.request('DELETE',url,json={'confirm':True}).json()['state']=='deleted'
    for path in ['', '/context','/handoff','/events']:
        assert client.get(url+path).status_code==410
    assert client.post(url+'/turns',json=request).status_code==410
    assert client.post(url+'/restore').status_code==410
    assert client.get(url+'/lifecycle').json()['state']=='deleted'
    assert client.post(url+'/deletion/reconcile',json={'confirm':True}).json()['state']=='deleted'


def test_delete_retains_formal_budget_exactly(fixture):
    from pathoreason.formal import StudyCreate
    s,_,request,runtime=fixture
    s.config.update(execution_environment='bxn-server',formal_enabled=True)
    study=s.formal.create(StudyCreate(request_key='study_delete',title='Budget preservation',objective='Fixture',budget={'max_turns':3,'max_wall_seconds':600}))
    c=s.store.conversations(study.project_id)[0]
    runtime.create_formal=runtime.create
    runtime.prompt_formal=runtime.prompt
    async def configure(*args):pass
    runtime.configure_formal_permissions=configure
    install_delete(runtime)
    async def case():
        await finish(s,c,{**request,'skill_id':None,'artifact_ids':[],'execution_mode':'research'})
        before=s.formal.view(study.project_id)
        assert before.used_turns==1
        assert (await s.conversations.delete(c['id'])).state=='deleted'
        after=s.formal.view(study.project_id)
        assert after==before
    asyncio.run(case())


def test_cancelled_native_delete_is_reconcilable_after_restart(fixture):
    s,c,request,runtime=fixture
    install_delete(runtime)
    async def case():
        await finish(s,c,request)
        started=asyncio.Event()
        original=runtime.delete_session
        async def unknown(*args):
            await original(*args)
            started.set()
            await asyncio.Event().wait()
        runtime.delete_session=unknown
        task=asyncio.create_task(s.conversations.delete(c['id']))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):await task
        assert s.conversations.view(c['id']).state=='deleting'
        restored=Service(Store(s.store.path),runtime,s.config)
        async def reconcile(sid,directory):
            if sid in runtime.sessions:await original(sid,directory)
        runtime.delete_session=reconcile
        assert (await restored.conversations.delete(c['id'])).state=='deleted'
        assert len(runtime.deleted)==1
    asyncio.run(case())


@pytest.mark.parametrize('mode',['normal','lost_ack','children','wrong_directory','not_deleted'])
def test_native_delete_verifies_absence_and_does_not_repeat_unknown_delete(tmp_path,mode):
    runtime=OpenCode(tmp_path,8522)
    calls=[];exists=True
    async def call(method,path,directory):
        nonlocal exists
        calls.append((method,path))
        if path.endswith('/children'):return [{'id':'ses_child'}] if mode=='children' else []
        if method=='DELETE':
            exists=mode=='not_deleted'
            if mode=='lost_ack':raise TimeoutError('receipt lost')
            return True
        if not exists:
            response=httpx.Response(404,request=httpx.Request('GET','http://runtime'+path))
            response.raise_for_status()
        return {'id':'ses_test','directory':str(tmp_path/'wrong') if mode=='wrong_directory' else str(tmp_path)}
    runtime.call=call
    async def case():
        if mode=='lost_ack':
            with pytest.raises(TimeoutError):await runtime.delete_session('ses_test',str(tmp_path))
            await runtime.delete_session('ses_test',str(tmp_path))
        elif mode in ['children','wrong_directory','not_deleted']:
            with pytest.raises(Conflict):await runtime.delete_session('ses_test',str(tmp_path))
        else:await runtime.delete_session('ses_test',str(tmp_path))
        assert sum(method=='DELETE' for method,_ in calls)==(0 if mode in ['children','wrong_directory'] else 1)
    asyncio.run(case())
