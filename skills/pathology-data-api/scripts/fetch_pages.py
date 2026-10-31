"""Bounded API transport for research agents; no analysis or training actions."""
import argparse
import hashlib
import json
import os
import re
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = 'http://ai.gzfxyl.cn/api/v1/pathology'
DISEASE = {'DiseaseId', 'DiseaseCode', 'DiseaseName', 'DiagnosisStatus'}
FIELDS = {
    '/diseases': {'Keyword'},
    '/diseases/patient-count-by-province': DISEASE | {'CurrentOnly'},
    '/diseases/sample-count-by-hospital': DISEASE | {'CurrentOnly'},
    '/diseases/patients': DISEASE,
    '/diseases/specimens': DISEASE,
    '/diseases/slides': DISEASE | {'StainType'},
    '/patients/disease-subtypes': {'PatientId'},
    '/patients/disease-attributes': {'PatientId'},
    '/molecular-results': {'PatientId', 'BiomarkerName'},
    '/text-disease-matches': {'PatientId', 'DiseaseCode'},
}
AGGREGATES = {'/diseases/patient-count-by-province', '/diseases/sample-count-by-hospital'}

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def encode(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()

def write_new(path, raw):
    with path.open('xb') as f:
        f.write(raw)
        f.flush()
        os.fsync(f.fileno())

def validate(query):
    if set(query) - {'endpoint', 'params', 'page_size', 'max_pages'}:
        raise ValueError('unknown_query_fields')
    endpoint, params = query['endpoint'], query.get('params', {})
    if endpoint not in FIELDS or not isinstance(params, dict) or set(params) - FIELDS[endpoint]:
        raise ValueError('unsupported_endpoint_or_parameters')
    if any(not isinstance(v, (str, int, float, bool)) for v in params.values()):
        raise ValueError('scalar_query_values_required')
    if endpoint.startswith('/diseases/') and not any(params.get(k) for k in ['DiseaseId', 'DiseaseCode', 'DiseaseName']):
        raise ValueError('disease_scope_required')
    if endpoint in {'/patients/disease-subtypes', '/patients/disease-attributes', '/molecular-results'} and not params.get('PatientId'):
        raise ValueError('patient_scope_required')
    if endpoint == '/text-disease-matches' and not (params.get('PatientId') or params.get('DiseaseCode')):
        raise ValueError('text_scope_required')
    size, cap = query.get('page_size', 1000), query.get('max_pages', 200)
    if type(size) is not int or type(cap) is not int or not 1 <= size <= 1000 or not 1 <= cap <= 10000:
        raise ValueError('invalid_pagination_bounds')
    return endpoint, params, size, cap

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None

def fetch(endpoint, params, key):
    req = urllib.request.Request(BASE + endpoint + '?' + urllib.parse.urlencode(params),
                                 headers={'Accept': 'application/json', 'X-AiData-Key': key})
    try:
        response = urllib.request.build_opener(NoRedirect).open(req, timeout=90)
    except urllib.error.HTTPError as exc:
        response = exc
    with response as r:
        raw, status = r.read(64 * 1024 * 1024 + 1), r.status
    if len(raw) > 64 * 1024 * 1024:
        raise ValueError('response_too_large')
    return raw, status

def collect(group, query, key, request=fetch):
    endpoint, params, size, cap = validate(query)
    binding = sha(encode(query))
    complete = group / 'complete.json'
    if complete.is_file():
        record = json.loads(complete.read_text())
        if record['query_sha256'] != binding:
            raise ValueError('query_changed')
        for item in [*record['pages'], record['aggregate']]:
            if sha((group / item['file']).read_bytes()) != item['sha256']:
                raise ValueError('completed_bytes_changed')
        return {'rows': record['rows'], 'resumed': True}
    if group.exists():
        raise RuntimeError('reconciliation_required; no automatic replay')
    group.mkdir()
    rows, receipts = [], []
    for page in range(1, cap + 1):
        actual = dict(params)
        if endpoint not in AGGREGATES:
            actual.update(PageIndex=page, PageSize=size)
        stem = 'page-%04d' % page
        write_new(group / (stem + '.request.json'), encode({
            'endpoint': endpoint, 'query': actual, 'state': 'dispatching',
            'at': datetime.now(timezone.utc).isoformat()}))
        try:
            raw, status = request(endpoint, actual, key)
            name = stem + '.response.json'
            write_new(group / name, raw)
            try:
                body = json.loads(raw)
            except ValueError:
                body = None
            receipt = {'file': name, 'sha256': sha(raw), 'size_bytes': len(raw),
                       'http_status': status, 'api_code': body.get('code') if isinstance(body, dict) else None,
                       'page': page, 'at': datetime.now(timezone.utc).isoformat()}
            write_new(group / (stem + '.receipt.json'), encode(receipt))
            if status != 200 or not isinstance(body, dict) or str(body.get('code')) != '200' or not isinstance(body.get('data'), list):
                raise ValueError('api_rejected_or_invalid_structure')
            rows.extend(body['data'])
            receipts.append(receipt)
        except Exception as exc:
            write_new(group / (stem + '.failure.json'), encode({'error_type': type(exc).__name__}))
            raise RuntimeError('request_failed; reconcile saved files; no automatic retry') from None
        if endpoint in AGGREGATES or len(body['data']) < size:
            break
    else:
        write_new(group / 'incomplete.json', encode({'reason': 'page_cap_reached', 'pages': cap}))
        raise RuntimeError('page_cap_reached; incomplete')
    raw_rows = encode(rows)
    write_new(group / 'rows.json', raw_rows)
    write_new(complete, encode({'schema_version': 'pathoreason.api-query/1',
                               'query_sha256': binding, 'rows': len(rows), 'pages': receipts,
                               'aggregate': {'file': 'rows.json', 'sha256': sha(raw_rows)}}))
    return {'rows': len(rows), 'resumed': False}

def local_path(root, relative, prefix):
    p = Path(relative)
    if p.is_absolute() or '..' in p.parts or not p.parts or p.parts[0] != prefix:
        raise ValueError('invalid_project_relative_path')
    target = root / p
    if any(item.is_symlink() for item in [target, *target.parents]):
        raise ValueError('symlink_path')
    return target

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--project', required=True)
    ap.add_argument('--plan', required=True)
    ap.add_argument('--output', required=True)
    args = ap.parse_args()
    if not re.fullmatch(r'prj_[A-Za-z0-9_-]+', args.project):
        raise ValueError('invalid_project')
    data = Path('/data/bxn/PathoReason')
    with sqlite3.connect('file:' + str(data / 'state/pathoreason.sqlite3') + '?mode=ro', uri=True) as db:
        row = db.execute('SELECT document FROM formal_studies WHERE project_id=?', (args.project,)).fetchone()
    if not row:
        raise ValueError('formal_study_required')
    root = data / 'projects' / args.project
    if json.loads(row[0])['workspace'] != str(root):
        raise ValueError('workspace_mismatch')
    plan_path = local_path(root, args.plan, 'plans')
    out = local_path(root, args.output, 'inputs')
    if out == root / 'inputs':
        raise ValueError('versioned_output_directory_required')
    plan = json.loads(plan_path.read_text())
    if set(plan) != {'queries'} or not isinstance(plan['queries'], list) or not 1 <= len(plan['queries']) <= 50000:
        raise ValueError('invalid_plan')
    for query in plan['queries']:
        validate(query)
    key = os.environ.get('PATHOREASON_DATA_API_KEY')
    if not key:
        doc = Path('/home/bxn/projects/PathoReason/接口文档2.0.md')
        if doc.is_symlink() or doc.stat().st_mode & 0o077:
            raise ValueError('credential_document_permissions')
        match = re.search(r'X-AiData-Key:\s*([0-9a-fA-F-]{36})', doc.read_text())
        if not match:
            raise ValueError('credential_missing')
        key = match.group(1)
    if out.exists():
        if not (out / 'plan.json').is_file() or (out / 'plan.json').read_bytes() != encode(plan):
            raise ValueError('existing_output_has_different_or_unknown_plan')
    else:
        out.mkdir(parents=True)
        write_new(out / 'plan.json', encode(plan))
    # Prevent simultaneous invocations from racing the same query completion files.
    import fcntl
    with (out / '.fetch.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        results = [collect(out / ('q%05d' % i), q, key) for i, q in enumerate(plan['queries'])]
        summary = {'queries': len(results), 'rows': sum(r['rows'] for r in results),
                   'status': 'complete', 'scope': 'transport_only_not_training_validation'}
        if not (out / 'summary.json').exists():
            write_new(out / 'summary.json', encode(summary))
        print(json.dumps({**summary, 'summary': str(out / 'summary.json')}))

if __name__ == '__main__':
    main()
