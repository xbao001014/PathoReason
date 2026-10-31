import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('data_api_fetch', ROOT / 'skills/pathology-data-api/scripts/fetch_pages.py')
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)

QUERY = {'endpoint': '/diseases/patients', 'params': {'DiseaseId': 9}, 'page_size': 2, 'max_pages': 3}

def test_exact_bytes_multipage_and_resume(tmp_path):
    raw = [b'{"code":200, "data":[{"PatientId":"a"},{"PatientId":"b"}]}',
           b'{"code":200,"data":[]}']
    calls = []
    def request(endpoint, params, key):
        calls.append(params.copy())
        return raw[params['PageIndex'] - 1], 200
    group = tmp_path / 'q'
    result = helper.collect(group, QUERY, 'private', request)
    assert result == {'rows': 2, 'resumed': False}
    assert [p['PageIndex'] for p in calls] == [1, 2]
    assert (group / 'page-0001.response.json').read_bytes() == raw[0]
    receipt = json.loads((group / 'page-0001.receipt.json').read_text())
    assert receipt['sha256'] == helper.sha(raw[0])
    assert helper.collect(group, QUERY, 'private', request)['resumed']
    assert len(calls) == 2
    assert all('private' not in p.read_text() for p in group.iterdir())
    with pytest.raises(ValueError, match='query_changed'):
        helper.collect(group, {**QUERY, 'params': {'DiseaseId': 10}}, 'private', request)
    (group / 'rows.json').write_text('[]')
    with pytest.raises(ValueError, match='completed_bytes_changed'):
        helper.collect(group, QUERY, 'private', request)

def test_unknown_request_outcome_not_retried(tmp_path):
    calls = []
    def request(*args):
        calls.append(1)
        raise TimeoutError('private payload should not be logged')
    with pytest.raises(RuntimeError, match='request_failed'):
        helper.collect(tmp_path / 'q', QUERY, 'private', request)
    with pytest.raises(RuntimeError, match='reconciliation_required'):
        helper.collect(tmp_path / 'q', QUERY, 'private', request)
    assert calls == [1]
    assert not (tmp_path / 'q/complete.json').exists()
    assert 'private' not in (tmp_path / 'q/page-0001.failure.json').read_text()

def test_cap_is_incomplete_and_aggregate_is_unpaged(tmp_path):
    def full(endpoint, params, key):
        return b'{"code":200,"data":[{},{}]}', 200
    with pytest.raises(RuntimeError, match='page_cap_reached'):
        helper.collect(tmp_path / 'full', {**QUERY, 'max_pages': 1}, '', full)
    assert not (tmp_path / 'full/complete.json').exists()
    def aggregate(endpoint, params, key):
        assert 'PageIndex' not in params and 'PageSize' not in params
        return full(endpoint, params, key)
    result = helper.collect(tmp_path / 'aggregate', {**QUERY, 'endpoint': '/diseases/sample-count-by-hospital'}, '', aggregate)
    assert result['rows'] == 2

def test_api_rejection_retains_response_but_not_completion(tmp_path):
    raw = b'{"code":403,"data":[]}'
    with pytest.raises(RuntimeError, match='request_failed'):
        helper.collect(tmp_path / 'q', QUERY, '', lambda *a: (raw, 200))
    assert (tmp_path / 'q/page-0001.response.json').read_bytes() == raw
    assert not (tmp_path / 'q/complete.json').exists()

def test_http_error_body_is_preserved(monkeypatch, tmp_path):
    import io
    import urllib.error
    raw = b'{"code":401,"data":[]}'
    class Opener:
        def open(self, *args, **kwargs):
            raise urllib.error.HTTPError('http://example.invalid', 401, 'Unauthorized', {}, io.BytesIO(raw))
    monkeypatch.setattr(helper.urllib.request, 'build_opener', lambda *a: Opener())
    with pytest.raises(RuntimeError, match='request_failed'):
        helper.collect(tmp_path / 'q', QUERY, 'private')
    assert (tmp_path / 'q/page-0001.response.json').read_bytes() == raw
    receipt = json.loads((tmp_path / 'q/page-0001.receipt.json').read_text())
    assert receipt['http_status'] == 401 and receipt['api_code'] == 401

def test_query_scope_and_workspace_boundaries(tmp_path):
    with pytest.raises(ValueError, match='patient_scope'):
        helper.validate({'endpoint': '/molecular-results', 'params': {}})
    with pytest.raises(ValueError, match='unsupported'):
        helper.validate({'endpoint': '/patients/disease-subtypes', 'params': {'PatientId': 'a', 'DiseaseId': 9}})
    with pytest.raises(ValueError):
        helper.local_path(tmp_path, '../elsewhere', 'inputs')
    (tmp_path / 'inputs').symlink_to(tmp_path)
    with pytest.raises(ValueError, match='symlink'):
        helper.local_path(tmp_path, 'inputs/data', 'inputs')

def test_skill_catalog_binding_and_formal_only():
    from pathoreason.formal import project_skills
    from pathoreason.contracts import SkillDefinition
    skill = project_skills(True)[0]
    SkillDefinition.model_validate(skill)
    assert skill['id'] == 'pathology-data-api'
    assert skill['runtime_readiness'] == 'ready'
    assert skill['capability_refs'] == ['pathoreason:formal_study']
    assert len(skill['instruction_refs']) == 4
    assert project_skills(False)[0]['runtime_readiness'] == 'unavailable'
    navigation = json.loads((ROOT / 'config/skill-navigation.json').read_text())
    assert skill['id'] in navigation[0]['stages'][0]['skill_ids']
