"""Execution evidence fixtures are synthetic and use independent CPU budgets."""
import asyncio
import json
import sqlite3
from pathlib import Path

import pytest

from test_training_executor import environment, setup_plan, approve, wait
from test_p1_service import fixture, settled
from test_p5_entry import study
from pathoreason.training_contracts import TrainingAuditQuery, TrainingToolInput
from pathoreason.training_files import file_digest
from pathoreason.persistence import Conflict


def ledger(s):
    with sqlite3.connect(s.store.path) as db:
        return list(db.iterdump())


def test_platform_launch_evidence_and_readonly_audit(fixture, environment, monkeypatch):
    monkeypatch.setenv('OPTIONAL_LOADER_CAP', '5')
    s, r, v, cid, request, task, p, body, op = setup_plan(fixture, environment)
    approve(s, cid, p)
    done = wait(s, p.id, v.project_id)
    assert done.status == 'completed', done.error
    before = ledger(s)
    result = s.training.audit(v.project_id, p.id, TrainingAuditQuery(audit_limit=1, source_file='runner.py'))
    assert ledger(s) == before and not r.calls
    assert result['source']['bytes_verified'] and result['controller']['bytes_verified']
    assert result['next_offset'] == 1 and result['attempt_count'] == 2
    a = result['attempts'][0]
    launch = a['launch_spec']['evidence']
    assert a['launch_spec']['status'] == 'recorded_before_dispatch'
    assert launch['inherits_parent_environment'] is False
    assert 'OPTIONAL_LOADER_CAP' not in launch['environment']
    assert launch['argv'][0] == result['source']['selected_file']['path']
    assert launch['input_manifest']['sha256'] == a['input_manifest']['reference']['sha256']
    assert a['effective_task_settings'] == 'not_observed'
    assert a['input_manifest']['stored_shapes'] == 'not_observed'
    assert a['input_manifest']['upstream_transform'] == 'unknown'
    assert a['input_manifest']['content_read'] is False
    assert not result['environment']['runtime_bytes_rechecked']
    page2 = s.training.audit(v.project_id, p.id, TrainingAuditQuery(audit_offset=1))
    assert page2['next_offset'] is None and page2['attempts'][0]['unit_id'] == 'unit_1'
    compact = s.training.receipt(done)
    assert all('launch_spec' not in a for a in compact['recent_attempts'])


def test_legacy_absence_failed_attempt_and_project_scope(fixture, environment):
    s, r, v, cid, request, task, p, body, op = setup_plan(fixture, environment, 'raise RuntimeError("fixture failure")', units=1)
    approve(s, cid, p)
    done = wait(s, p.id, v.project_id)
    assert done.status == 'failed'
    attempt = done.attempts[0]
    assert 'launch_spec' in attempt  # Failed launches/results preserve the specification.
    # Explicit legacy fixture, not a migration of live history.
    attempt.pop('launch_spec')
    with s.training.account.db() as db:
        db.execute('UPDATE training_attempts SET document=? WHERE id=?', (json.dumps(attempt), attempt['id']))
        db.execute("DELETE FROM training_events WHERE experiment_id=? AND json_extract(document,'$.kind')='launch_spec_recorded'", (p.id,))
    before = ledger(s)
    result = s.training.audit(v.project_id, p.id, TrainingAuditQuery())
    assert result['attempts'][0]['launch_spec']['evidence'] is None
    assert result['attempts'][0]['status'] == 'failed'
    assert ledger(s) == before
    other = study(s, key='other')
    with pytest.raises(ValueError, match='not_found'):
        s.training.audit(other.project_id, p.id, TrainingAuditQuery())
    with pytest.raises(ValueError, match='registered_run'):
        s.training.audit(v.project_id, p.id, TrainingAuditQuery(run_id='train_unregistered'))
    with pytest.raises(ValueError, match='relative_path'):
        s.training.audit(v.project_id, p.id, TrainingAuditQuery(source_file='../runner.py'))


def test_tampering_is_rejected_without_rewriting_evidence(fixture, environment):
    s, r, v, cid, request, task, p, body, op = setup_plan(fixture, environment, units=1)
    approve(s, cid, p)
    done = wait(s, p.id, v.project_id)
    root = s.training.root / 'runs' / done.run_id
    reqfile = root / 'request.json'
    original = reqfile.read_bytes()
    req = json.loads(original);req['plan']['units'][0]['parameters']['cap'] = 9
    reqfile.write_text(json.dumps(req))
    before = ledger(s)
    with pytest.raises(ValueError, match='run_binding_changed'):
        s.training.audit(v.project_id, p.id, TrainingAuditQuery())
    assert ledger(s) == before
    reqfile.write_bytes(original)
    manifest = root / 'unit_0/inputs/manifest.json'
    raw = json.loads(manifest.read_text());raw['parameters']['unexpected'] = 1
    manifest.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match='input_manifest_changed'):
        s.training.audit(v.project_id, p.id, TrainingAuditQuery())
    manifest.unlink();manifest.symlink_to(reqfile)
    with pytest.raises(ValueError, match='traverse_links'):
        s.training.audit(v.project_id, p.id, TrainingAuditQuery())
    import os
    manifest.unlink();os.mkfifo(manifest)
    with pytest.raises(ValueError, match='regular_unlinked_file'):
        s.training.audit(v.project_id, p.id, TrainingAuditQuery())


def test_launch_ledger_change_is_not_accepted_as_proof(fixture, environment):
    s, r, v, cid, request, task, p, body, op = setup_plan(fixture, environment, units=1)
    approve(s, cid, p);done = wait(s, p.id, v.project_id)
    attempt = done.attempts[0]
    attempt['launch_spec']['environment']['OPTIONAL_LOADER_CAP'] = '999'
    with s.training.account.db() as db:
        db.execute('UPDATE training_attempts SET document=? WHERE id=?', (json.dumps(attempt), attempt['id']))
    with pytest.raises(ValueError, match='launch_binding_changed'):
        s.training.audit(v.project_id, p.id, TrainingAuditQuery())


def test_unconsumed_sealed_input_not_opened_and_no_exposure_created(fixture, environment, monkeypatch):
    s, r, v, cid, request, task, p, body, op = setup_plan(fixture, environment, units=1)
    secret = s.data/'projects'/v.project_id/'sealed.bin'
    secret.write_bytes(b'unread synthetic input')
    from pathoreason.training_contracts import TrainingPlan
    raw = body.plan.model_dump()
    raw['inputs'] = [{'id': 'sealed', 'path': str(secret), 'sha256': file_digest(secret),
                      'role': 'sealed', 'subject_id': 'subject', 'prior_test_exposures': 0}]
    p = s.training.prepare(v.project_id, cid, body.model_copy(update={'plan': TrainingPlan.model_validate(raw),
        'experiment_id': p.id, 'expected_revision': p.revision}), {'kind':'engineering_fixture'})
    approve(s, cid, p);done = wait(s, p.id, v.project_id)
    assert done.status == 'completed'
    secret.unlink()  # Audit needs the frozen manifest, not input content.
    before = ledger(s)
    result = s.training.audit(v.project_id, p.id, TrainingAuditQuery())
    assert result['attempts'][0]['input_manifest']['registered_count'] == 0
    assert ledger(s) == before


def test_audit_http_readonly_and_active_tool_authority(fixture, environment, monkeypatch):
    import pathoreason.api as api
    from fastapi.testclient import TestClient
    from test_goals import accepted
    s, r, v, cid, request, task, p, body, op = setup_plan(fixture, environment, units=1)
    approve(s, cid, p);done = wait(s, p.id, v.project_id)
    monkeypatch.setattr(api, 'service', lambda:s)
    client = TestClient(api.app)
    url = f'/api/v2/conversations/{cid}/training/{p.id}/audit'
    before = ledger(s)
    response = client.get(url)
    assert response.status_code == 200, response.text
    assert response.headers['cache-control'] == 'no-store'
    assert ledger(s) == before
    assert client.get(url+'?audit_limit=26').status_code == 422
    assert client.post(url, json={}).status_code == 405
    async def case():
        r.hold = True
        first = await s.submit(cid, {**request,'request_key':'audit_scope','skill_id':None,'artifact_ids':[]})
        tid = first['turn']['id'];await accepted(s, tid)
        tool = TrainingToolInput(turn_id=tid, grant=s.guidance.grant(tid), operation='audit', experiment_id=p.id)
        with s.store.connect(True) as db:
            db.execute('INSERT INTO turn_guidance_context VALUES(?,?)', (tid, json.dumps({'selected_option_id':'read','proposal':{'options':[{'id':'read','scope':'inspect'}]}})))
        assert s.training.call(tool)['run_id'] == done.run_id
        with pytest.raises(Conflict, match='authority'):
            s.training.call(tool.model_copy(update={'grant':'wrong'}))
        with pytest.raises(Conflict, match='outside_turn_scope'):
            s.training.call(tool.model_copy(update={'operation':'retry','idempotency_key':'blocked'}))
        r.hold = False;await settled(s, tid)
        with pytest.raises(Conflict, match='authority'):
            s.training.call(tool)
        await s.close()
    asyncio.run(case())


def test_audit_mcp_schema_and_bridge(monkeypatch, tmp_path):
    from test_guidance_mcp import run_bridge, request
    results, calls = run_bridge(monkeypatch, tmp_path, [
        {'jsonrpc':'2.0','id':1,'method':'tools/list'},
        request({'turn_id':'turn_fixture','grant':'PRIVATE_GRANT_VALUE','operation':'audit','experiment_id':'exp_fixture'}, ident=2, name='training')],
        responder={'read_only':True, 'attempts':[]})
    tool = next(t for t in results[0]['result']['tools'] if t['name']=='training')
    assert 'audit' in tool['inputSchema']['properties']['operation']['enum']
    assert tool['inputSchema']['properties']['audit_limit']['maximum'] == 25
    assert not results[1]['result']['isError'] and len(calls) == 1
