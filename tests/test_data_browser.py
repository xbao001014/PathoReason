import asyncio
import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from pathoreason import data_browser as module
from pathoreason.data_browser import DataBrowser, DataBrowserError, PreviewQuery, SnapshotInput
from pathoreason.persistence import Conflict
from test_p1_service import fixture


def prepare(fixture, monkeypatch, rows=None):
    s, *_ = fixture
    s.config['execution_environment'] = 'bxn-server'
    browser = DataBrowser(s)
    s.data_browser = browser
    calls = []
    raw = json.dumps({'code': '200', 'data': rows if rows is not None else [{'PatientId': 'fixture-patient', 'SlideId': 7, 'FilePath': '', 'FeaturePath': ''}]}, ensure_ascii=False).encode()
    monkeypatch.setattr(module, 'credential_key', lambda: 'fixture-secret')
    def transport(endpoint, params, key):
        assert key == 'fixture-secret'
        calls.append((endpoint, params))
        return raw
    monkeypatch.setattr(module, 'transport', transport)
    return s, browser, calls, raw


def query(**kwargs):
    return PreviewQuery(endpoint='/diseases/slides', params={'DiseaseCode': 'FIXTURE'}, **kwargs)


@pytest.mark.parametrize('body', [
    {'endpoint': 'https://example.invalid'},
    {'endpoint': '/diseases/slides', 'params': {'DiseaseCode': 'X', 'Limit': 100}},
    {'endpoint': '/diseases/patients'},
    {'endpoint': '/patients/disease-attributes', 'params': {'DiseaseId': 1}},
    {'endpoint': '/molecular-results', 'params': {'BiomarkerName': 'X'}},
    {'endpoint': '/text-disease-matches'},
    {'endpoint': '/diseases', 'page_size': 101},
    {'endpoint': '/diseases', 'page': True},
    {'endpoint': '/diseases/sample-count-by-hospital', 'params': {'DiseaseCode': 'X'}, 'page': 2},
])
def test_rejects_unsupported_or_unbounded_query_before_dispatch(body):
    with pytest.raises(ValidationError):
        PreviewQuery(**body)


def test_preview_is_page_scoped_preserves_raw_hash_and_does_not_write(fixture, monkeypatch):
    s, browser, calls, raw = prepare(fixture, monkeypatch)
    before = list(s.data.rglob('response.json'))
    result = browser.query(query(page=3, page_size=1))
    assert calls == [('/diseases/slides', {'DiseaseCode': 'FIXTURE', 'DiagnosisStatus': '确诊', 'PageIndex': 3, 'PageSize': 1})]
    assert result.has_more and result.row_count == 1 and result.query.page == 3
    assert result.response_sha256 == hashlib.sha256(raw).hexdigest()
    assert result.nonempty['FilePath'] == 0
    assert all(f.state != 'ready' for f in result.figures)
    assert list(s.data.rglob('response.json')) == before
    assert 'fixture-secret' not in result.model_dump_json()


def test_aggregate_and_empty_diagnosis_keep_the_actual_scope(fixture, monkeypatch):
    _, browser, calls, _ = prepare(fixture, monkeypatch, [])
    result = browser.query(PreviewQuery(endpoint='/diseases/patient-count-by-province', params={'DiseaseId': 9, 'DiagnosisStatus': '', 'CurrentOnly': False}))
    assert calls[0][1] == {'DiseaseId': 9, 'DiagnosisStatus': '', 'CurrentOnly': 'false'}
    assert not result.has_more and result.rows == []
    assert result.query.params['DiagnosisStatus'] == ''


@pytest.mark.parametrize('raw', [b'{bad', b'{"code":403,"data":[]}', b'{"code":200,"data":{}}', b'{"code":200,"data":[1]}', b'[]'])
def test_api_failures_never_enter_recent_or_snapshot_cache(fixture, monkeypatch, raw):
    _, browser, _, _ = prepare(fixture, monkeypatch)
    monkeypatch.setattr(module, 'transport', lambda *args: raw)
    with pytest.raises(DataBrowserError) as error:
        browser.query(query())
    assert error.value.code == 'data_response_invalid'
    assert browser.recent() == []


def test_paths_alone_do_not_enable_spatial_or_prediction_figures(fixture, monkeypatch):
    _, browser, _, _ = prepare(fixture, monkeypatch, [{'FilePath': '/fixture.svs', 'FeaturePath': '/fixture.pt'}])
    result = browser.query(query())
    assert result.nonempty['FilePath'] == 1
    assert all(f.state != 'ready' for f in result.figures)


def test_cache_is_bounded_and_expired_items_cannot_be_saved(fixture, monkeypatch):
    _, browser, _, _ = prepare(fixture, monkeypatch)
    first = browser.query(query())
    for _ in range(16):
        browser.query(query())
    assert len(browser.recent()) == 16
    with pytest.raises(DataBrowserError) as error:
        browser.get(first.query_id)
    assert error.value.status == 410
    monkeypatch.setattr(module.time, 'monotonic', lambda: 10**12)
    assert browser.recent() == []


def test_saved_snapshot_is_exact_idempotent_recoverable_and_tamper_checked(fixture, monkeypatch):
    s, browser, _, raw = prepare(fixture, monkeypatch)
    p = s.store.create_project('Snapshot', 'Fixture')
    result = browser.query(query())
    body = SnapshotInput(project_id=p['id'], query_id=result.query_id)
    saved = browser.save(body)
    path = s.data / 'projects' / p['id'] / saved.relative_path
    assert (path / 'response.json').read_bytes() == raw
    before = {p.name: p.read_bytes() for p in path.iterdir()}
    assert browser.save(body) == saved
    assert before == {p.name: p.read_bytes() for p in path.iterdir()}
    receipt = json.loads((path / 'receipt.json').read_text())
    assert receipt['complete_dataset'] is False
    assert 'fixture-secret' not in (path / 'receipt.json').read_text()
    assert 'fixture-patient' not in saved.draft
    reloaded = DataBrowser(s)
    assert reloaded.snapshots(p['id'])[0].query_id == result.query_id
    assert reloaded.load_snapshot(p['id'], result.query_id) == result
    (path / 'response.json').write_text('tampered')
    with pytest.raises(DataBrowserError) as error:
        browser.save(body)
    assert error.value.code == 'data_snapshot_changed'
    with pytest.raises(DataBrowserError):
        reloaded.load_snapshot(p['id'], result.query_id)


def test_archived_and_symlink_project_paths_reject_snapshot(fixture, monkeypatch, tmp_path):
    s, browser, _, _ = prepare(fixture, monkeypatch)
    result = browser.query(query())
    p = s.store.create_project('Archived', 'Fixture')
    with s.store.connect(True) as db:
        p['status'] = 'archived'
        db.execute('UPDATE projects SET document=? WHERE id=?', (json.dumps(p), p['id']))
    with pytest.raises(Conflict, match='project_archived'):
        browser.save(SnapshotInput(project_id=p['id'], query_id=result.query_id))
    p2 = s.store.create_project('Symlink', 'Fixture')
    parent = s.data / 'projects' / p2['id']
    parent.parent.mkdir(exist_ok=True)
    parent.symlink_to(tmp_path)
    with pytest.raises(DataBrowserError):
        browser.save(SnapshotInput(project_id=p2['id'], query_id=result.query_id))
    assert not (tmp_path / 'inputs').exists()


def test_http_errors_origin_and_no_store(fixture, monkeypatch):
    from pathoreason.api import app
    s, browser, calls, _ = prepare(fixture, monkeypatch)
    app.state.service = s
    client = TestClient(app)
    catalog = client.get('/api/v2/data-browser/catalog')
    assert len(catalog.json()['endpoints']) == 10
    assert catalog.headers['cache-control'] == 'no-store'
    assert 'fixture-secret' not in catalog.text
    url = '/api/v2/data-browser/query'
    assert client.post(url, json=query().model_dump(), headers={'Origin': 'https://elsewhere.invalid'}).status_code == 403
    assert client.post(url, json={'endpoint': '/molecular-results'}).status_code == 422
    assert calls == []
    result = client.post(url, json=query().model_dump())
    assert result.status_code == 200
    assert client.get('/api/v2/data-browser/queries/' + result.json()['query_id']).json() == result.json()
    monkeypatch.setattr(module, 'credential_key', lambda: None)
    assert client.post(url, json=query().model_dump()).json()['detail'] == 'data_credential_missing'


def test_transport_has_no_redirect_and_hides_error_body(monkeypatch):
    import urllib.error
    def opener(handler):
        assert handler.redirect_request(None, None, None, None, None, None) is None
        class Opener:
            def open(self, req, timeout):
                assert req.full_url.startswith(module.BASE + '/diseases?')
                assert timeout == 12
                raise urllib.error.URLError('fixture-secret must not leak')
        return Opener()
    monkeypatch.setattr(module.urllib.request, 'build_opener', opener)
    with pytest.raises(DataBrowserError) as error:
        module.transport('/diseases', {}, 'fixture-secret')
    assert error.value.code == 'data_upstream_unavailable'
    assert 'fixture-secret' not in str(error.value)
