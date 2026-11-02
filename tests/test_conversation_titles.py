import asyncio
import json
import pytest
from pathoreason.conversation_titles import ConversationTitleUpdate, OPEN, CLOSE
from pathoreason.persistence import Conflict, Gone
from pathoreason.service import Service
from test_p1_service import fixture, settled
from test_conversation_lifecycle import install_delete


def request_title(title, revision=0):
    return ConversationTitleUpdate(title=title, expected_revision=revision)


def titled_runtime(runtime, title='基线方案与验证范围'):
    original = runtime.messages
    async def messages(*args):
        result = await original(*args)
        for m in result:
            if m['info'].get('role') == 'assistant' and m['info'].get('time', {}).get('completed'):
                m['parts'][0]['text'] += '\n' + OPEN + title + CLOSE
        return result
    runtime.messages = messages


def test_first_turn_names_once_without_extra_inference_or_metadata_in_report(fixture):
    s, c, request, runtime = fixture
    titled_runtime(runtime)
    async def case():
        result = await s.submit(c['id'], request);tid = result['turn']['id']
        await settled(s, tid)
        title = s.titles.view(c['id'])
        assert title.title == '基线方案与验证范围' and title.source == 'automatic' and title.revision == 1
        assert len(runtime.calls) == 1
        assert OPEN in runtime.calls[0][3]
        row = s.store.turn(tid)
        assert OPEN not in row['text']
        assert OPEN.encode() not in s.artifact_bytes(s.store.artifact(row['report_id'], c['project_id']))
        await s.submit(c['id'], {**request, 'request_key': 'second_turn'})
        await settled(s, s.store.turns(c['id'])[-1]['id'])
        assert s.titles.view(c['id']) == title
        assert 'Conversation naming metadata:' not in runtime.calls[-1][3]
        assert len(runtime.calls) == 2
        await s.close()
    asyncio.run(case())


def test_manual_rename_wins_over_first_turn_and_stale_editor(fixture):
    s, c, request, runtime = fixture
    titled_runtime(runtime);runtime.hold = True
    async def case():
        result = await s.submit(c['id'], request);tid = result['turn']['id']
        s.titles.consume(tid, OPEN+'自动建议'+CLOSE)
        title = await s.titles.rename(c['id'], request_title('我的研究笔记'))
        with pytest.raises(Conflict, match='conversation_title_changed'):
            await s.titles.rename(c['id'], request_title('过期编辑'))
        runtime.hold = False;await settled(s, tid)
        assert s.titles.view(c['id']) == title
        assert OPEN not in s.store.turn(tid)['text']
        assert len(runtime.calls) == 1
        await s.close()
    asyncio.run(case())


def test_manual_name_before_first_turn_disables_automatic_naming(fixture):
    s, c, request, runtime = fixture
    async def case():
        title = await s.titles.rename(c['id'], request_title(c['title']))
        result = await s.submit(c['id'], request);await settled(s, result['turn']['id'])
        assert s.titles.view(c['id']) == title
        assert 'Conversation naming metadata:' not in runtime.calls[0][3]
        await s.close()
    asyncio.run(case())


def test_streaming_metadata_never_leaks_and_restart_finishes_pending_title(fixture):
    s, c, request, runtime = fixture;runtime.hold = True
    async def case():
        result = await s.submit(c['id'], request);tid = result['turn']['id']
        for fragment in ['<','<pathoreason_',OPEN,OPEN+'流式名称']:
            assert s.titles.consume(tid, '正文\n'+fragment) == '正文'
        assert s.titles.consume(tid, '正文\n'+OPEN+'流式名称'+CLOSE) == '正文'
        assert s.titles.view(c['id']).title == c['title']
        await s.close()
        # Simulate a crash after persisting the terminal turn and before applying its title.
        row = s.store.turn(tid);doc = json.loads(row['document']);doc['status'] = 'completed'
        s.store.update(tid, status='completed', document=json.dumps(doc))
        restored = Service(s.store, runtime, s.config)
        restored.titles.recover();restored.titles.recover()
        assert restored.titles.view(c['id']).title == '流式名称'
        assert restored.titles.view(c['id']).revision == 1
        await restored.close()
    asyncio.run(case())


@pytest.mark.parametrize('status', ['failed','interrupted'])
def test_failed_or_interrupted_turn_preserves_name(fixture, status):
    s,c,request,runtime = fixture;runtime.hold = True
    async def case():
        result = await s.submit(c['id'],request);tid = result['turn']['id']
        s.titles.consume(tid,OPEN+'未完成名称'+CLOSE)
        s.state(tid,status,'fixture_failure' if status == 'failed' else None)
        assert s.titles.view(c['id']).title == c['title']
        await s.close()
        restored = Service(s.store,runtime,s.config);restored.titles.recover()
        assert restored.titles.view(c['id']).title == c['title']
        await restored.close()
    asyncio.run(case())


def test_missing_metadata_falls_back_and_old_conversations_are_not_renamed(fixture):
    s,c,request,runtime = fixture
    async def case():
        result = await s.submit(c['id'],{**request,'text':'分析已有结果。不要启动训练。'});await settled(s,result['turn']['id'])
        assert s.titles.view(c['id']).title == '分析已有结果'
        assert s.titles.view(c['id']).source == 'fallback'
        with s.store.connect(True) as db:
            db.execute('DELETE FROM conversation_titles WHERE conversation_id=?',(c['id'],))
        original = json.loads(s.store.conversation(c['id'])['document'])['title']
        second = await s.submit(c['id'],{**request,'request_key':'legacy_followup'});await settled(s,second['turn']['id'])
        assert s.titles.view(c['id']).title == original
        assert 'Conversation naming metadata:' not in runtime.calls[-1][3]
        await s.close()
    asyncio.run(case())


def test_archive_rename_delete_scrubs_title_state_preserves_budget(fixture):
    s,c,request,runtime = fixture;install_delete(runtime)
    async def case():
        result = await s.submit(c['id'],request);tid = result['turn']['id'];await settled(s,tid)
        await asyncio.gather(*list(s.tasks.values()))
        before = s.store.turn(tid)
        await s.conversations.archive(c['id'])
        title = await s.titles.rename(c['id'],request_title('归档的证据核对',s.titles.view(c['id']).revision))
        assert s.conversations.list(c['project_id'],True)[0].title == title.title
        assert s.store.turn(tid) == before
        await s.conversations.delete(c['id'])
        with s.store.connect() as db:
            assert db.execute('SELECT count(*) FROM conversation_titles').fetchone()[0] == 0
            assert len(s.store.budget_rows(db)) == 1
        with pytest.raises(Gone):await s.titles.rename(c['id'],request_title('不能复活'))
        await s.close()
    asyncio.run(case())


def test_http_validation_conflict_and_no_model_calls(fixture,monkeypatch):
    from fastapi.testclient import TestClient
    import pathoreason.api as api
    s,c,request,runtime = fixture
    monkeypatch.setattr(api,'Service',lambda:s)
    original=api.settings();monkeypatch.setattr(api,'settings',lambda:{**original,'data_root':str(s.data)})
    url='/api/v1/conversations/'+c['id']+'/title'
    with TestClient(api.app) as client:
        assert client.get(url).json()['revision'] == 0
        for title in ['','   ','x'*121]:
            assert client.put(url,json={'title':title,'expected_revision':0}).status_code == 422
        response=client.put(url,json={'title':'  新名称  ','expected_revision':0})
        assert response.status_code == 200 and response.json()['title'] == '新名称'
        assert client.put(url,json={'title':'旧编辑器','expected_revision':0}).status_code == 409
        assert client.get('/api/v1/research-projects/'+c['project_id']+'/conversations').json()[0]['title'] == '新名称'
        assert not runtime.calls
