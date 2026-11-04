"""Read-only, project-bound execution evidence. Never imports research code.

Launch specifications describe the platform's subprocess inputs, not the task's
effective loader settings or upstream feature-production history.
"""
import hashlib
import json
import os
import sqlite3
import stat
from pathlib import Path

from .training_files import canonical, digest, relative, verify_tree


def read_json(path):
    path = canonical(path)
    limit = 32 * 1024 * 1024
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), 'rb') as file:
        before = os.fstat(file.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise ValueError('training_audit_regular_unlinked_file_required')
        if before.st_size > limit:
            raise ValueError('training_audit_document_too_large')
        raw = file.read(limit + 1)
        after = os.fstat(file.fileno())
    if len(raw) > limit:
        raise ValueError('training_audit_document_too_large')
    if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
        raise ValueError('training_audit_document_changed')
    return json.loads(raw), {'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest()}


def compact(value, reference):
    if len(json.dumps(value, ensure_ascii=False).encode()) <= 8192:
        return value
    return {'omitted': True, 'reason': 'large_evidence_read_reference',
            'value_digest': digest(value), 'reference': reference}


def audit(training, pid, eid, query):
    # No reconcile(), usage updates, input decoding, task import or model call.
    with sqlite3.connect(Path(training.account.path).as_uri() + '?mode=ro', uri=True) as db:
        db.execute('BEGIN')
        db.row_factory = sqlite3.Row
        experiment = training.account.get(db, eid, pid)
        run_id = query.run_id or experiment.get('run_id')
        events = [json.loads(r[0]) for r in db.execute(
            'SELECT document FROM training_events WHERE experiment_id=?', (eid,))]
        queued = next((e for e in events if e['kind'] == 'run_queued' and e.get('run_id') == run_id), None)
        if not queued:
            raise ValueError('training_audit_registered_run_required')
        all_attempts = training.account.attempts(db, eid)
        attempts = [a for a in all_attempts if a['run_id'] == run_id]
        root = canonical(training.root / 'runs' / relative(run_id))
        request, request_ref = read_json(root / 'request.json')
        plan = request['plan']
        if (request['experiment_id'] != eid or request['run_id'] != run_id or
                digest(plan) != queued['plan_digest'] or request['controller_files'] != queued['controller']):
            raise ValueError('training_audit_run_binding_changed')
        env_row = db.execute('SELECT document FROM training_environments WHERE project_id=? AND id=?',
                             (pid, plan['environment_id'])).fetchone()
        if not env_row or json.loads(env_row[0]) != request['environment']:
            raise ValueError('training_audit_environment_binding_changed')
    environment = request['environment']
    if digest(environment['binding']) != plan['environment_id']:
        raise ValueError('training_audit_environment_digest_changed')
    task = training.s.task_code.workspaces.get(pid, plan['task_id'])
    snapshot = training.s.task_code.workspaces.verify_snapshot(task, plan['snapshot_id'])
    expected_source = {k: {q: v[q] for q in ('sha256', 'size')} for k, v in snapshot['code']['files'].items()}
    if snapshot != request['snapshot'] or expected_source != request['source_files']:
        raise ValueError('training_audit_source_binding_changed')
    code = canonical(Path(snapshot['path']) / 'code')
    controller = root / 'controller' / 'pathoreason'
    verify_tree(controller, queued['controller'])
    source_ref = None
    if query.source_file:
        name = relative(query.source_file)
        if name not in expected_source:
            raise ValueError('training_audit_source_not_registered')
        source_ref = {'path': str(code / name), **expected_source[name]}
    units = {u['id']: u for u in plan['units']}
    if query.unit_id and query.unit_id not in units:
        raise ValueError('training_audit_unit_not_found')
    selected = [a for a in attempts if not query.unit_id or a['unit_id'] == query.unit_id]
    page = []
    page_bytes = 0
    for attempt in selected[query.audit_offset:query.audit_offset + query.audit_limit]:
        unit = units[attempt['unit_id']]
        slot = root / relative(unit['id'])
        if attempt['plan_digest'] != queued['plan_digest'] or canonical(attempt['output']) != slot / 'output':
            raise ValueError('training_audit_attempt_binding_changed')
        manifest_ref = None
        manifest_state = 'not_recorded'
        manifest_path = slot / 'inputs' / 'manifest.json'
        input_ids = set(unit['input_ids'])
        inputs = [f for f in plan['inputs'] if f['id'] in input_ids]
        if manifest_path.exists():
            manifest, manifest_ref = read_json(manifest_path)
            prior = all_attempts[:next(i for i, a in enumerate(all_attempts) if a['id'] == attempt['id'])]
            dependencies = []
            for dependency in unit['depends_on']:
                previous = next((a for a in reversed(prior) if a['unit_id'] == dependency and
                                 a['status'] == 'completed' and a['scope_digest'] == attempt['scope_digest']), None)
                if not previous:
                    raise ValueError('training_audit_dependency_receipt_missing')
                for name, sha in previous['files'].items():
                    dependencies.append({'unit_id': dependency, 'name': name,
                                         'path': str(canonical(Path(previous['output']) / relative(name))), 'sha256': sha})
            if (manifest['files'] != inputs or manifest['parameters'] != unit['parameters'] or
                    manifest['phase'] != unit['phase'] or manifest['dependencies'] != dependencies):
                raise ValueError('training_audit_input_manifest_changed')
            manifest_state = 'matches_frozen_plan'
        launch = attempt.get('launch_spec')
        recorded = next((e for e in events if e['kind'] == 'launch_spec_recorded' and e.get('attempt_id') == attempt['id']), None)
        if recorded and not launch:
            raise ValueError('training_audit_launch_receipt_missing')
        if launch:
            # Ledger copy is written by the controller before dispatch, outside
            # the task sandbox. A task-written output JSON is not this receipt.
            expected_args = [arg.replace('{inputs}', str(manifest_path)).replace('{output}', str(slot / 'output'))
                             .replace('{device}', 'cuda:0' if plan['gpu_uuid'] else 'cpu') for arg in unit['args']]
            if (not recorded or recorded['digest'] != digest(launch) or not manifest_ref or
                    launch['input_manifest']['sha256'] != manifest_ref['sha256'] or
                    launch['environment_id'] != plan['environment_id'] or launch['cwd'] != str(code) or
                    launch['argv'] != [str(code / unit['entrypoint']), *expected_args] or
                    launch['entrypoint_sha256'] != expected_source[unit['entrypoint']]['sha256'] or
                    launch['controller_sha256'] != queued['controller']['training_sandbox.py']['sha256']):
                raise ValueError('training_audit_launch_binding_changed')
        item = {
            'attempt_id': attempt['id'], 'unit_id': unit['id'], 'status': attempt['status'],
            'phase': unit['phase'], 'charged_seconds': attempt.get('charged_seconds'),
            'declared_parameters': compact(unit['parameters'], request_ref),
            'declared_args': compact(unit['args'], request_ref),
            'entrypoint': {'path': str(code / unit['entrypoint']), **expected_source[unit['entrypoint']]},
            'input_manifest': {'status': manifest_state, 'reference': manifest_ref,
                               'registered_count': len(inputs), 'content_read': False,
                               'stored_shapes': 'not_observed', 'upstream_transform': 'unknown'},
            'launch_spec': {'status': 'recorded_before_dispatch' if launch else 'not_recorded_legacy_or_prelaunch_failure',
                            'evidence': compact(launch, {'attempt_id': attempt['id'], 'ledger_field': 'launch_spec'}) if launch else None},
            'effective_task_settings': 'not_observed',
            'output_directory': attempt['output'], 'error': attempt.get('error'),
        }
        size = len(json.dumps(item, ensure_ascii=False).encode())
        if page and page_bytes + size > 32768:
            break
        page.append(item)
        page_bytes += size
    next_offset = query.audit_offset + len(page)
    return {
        'schema': 'training-execution-audit/1', 'read_only': True, 'project_id': pid,
        'experiment_id': eid, 'run_id': run_id, 'request': request_ref,
        'plan_digest': queued['plan_digest'], 'evaluation': plan['evaluation'],
        'source': {'snapshot_id': plan['snapshot_id'], 'path': str(code), 'bytes_verified': True, 'selected_file': source_ref},
        'controller': {'path': str(controller), 'bytes_verified': True, 'files': queued['controller']},
        'environment': {'id': plan['environment_id'], 'path': environment['path'],
                        'binding_verified': True, 'runtime_bytes_rechecked': False},
        'attempt_count': len(selected), 'attempts': page,
        'next_offset': next_offset if next_offset < len(selected) else None,
        'limits': ['Declared options do not establish activated behavior.',
                   'A launch specification is not observation inside the task after imports or configuration changes.',
                   'Stored input shape does not establish original bag size or where a transformation occurred.',
                   'No input content, sealed data, task code or training was executed by this audit.'],
        'scientific_approval': False,
    }
