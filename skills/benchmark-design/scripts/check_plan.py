"""Check plan structure, local evidence references and matrix arithmetic, not scientific truth."""
import argparse
from datetime import date
import json
from pathlib import Path
from urllib.parse import urlparse


def local_file(workspace, value):
    root = Path(workspace).resolve()
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        raise ValueError('expected workspace-relative file')
    path = (root / value).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError('missing file or outside workspace')
    return path


def check(plan, workspace):
    errors, warnings = [], []
    def need(condition, message):
        if not condition:
            errors.append(message)
    def nonempty(value):
        return isinstance(value, str) and bool(value.strip())
    def url(value):
        return isinstance(value, str) and urlparse(value).scheme in ('http', 'https') and bool(urlparse(value).netloc)
    if not isinstance(plan, dict):
        return {'structure_valid': False, 'errors': ['plan must be an object'], 'warnings': []}
    need(plan.get('schema_version') == 'pathoreason.benchmark-plan/1', 'schema_version')
    need(nonempty(plan.get('objective')), 'objective')
    try:
        cutoff = date.fromisoformat(plan.get('as_of', ''))
        need(cutoff <= date.today(), 'as_of is in the future')
    except (ValueError, TypeError):
        cutoff = date.today()
        errors.append('as_of must be an ISO date')
    recent = plan.get('recent_from_year')
    need(type(recent) is int and 1900 <= recent <= cutoff.year, 'recent_from_year')
    for key in ('inventory_ref', 'search_log_ref'):
        try:
            local_file(workspace, plan.get(key))
        except ValueError as exc:
            errors.append(key + ': ' + str(exc))
    searches = plan.get('searches', [])
    if not isinstance(searches, list):
        searches = []
    need(len(searches) >= 2, 'at least two recorded searches required')
    for item in searches:
        if not isinstance(item, dict):
            errors.append('search must be an object')
            continue
        need(all(nonempty(item.get(k)) for k in ('query', 'accessed_at', 'source')), 'search provenance')
        need(isinstance(item.get('urls'), list) and bool(item['urls']) and all(url(u) for u in item['urls']), 'search URLs')
    candidates = plan.get('candidates', [])
    if not isinstance(candidates, list):
        candidates = []
    ids, selected, roles = set(), set(), set()
    selected_papers_read = True
    for item in candidates:
        if not isinstance(item, dict):
            errors.append('candidate must be an object')
            continue
        identifier = item.get('id')
        if not nonempty(identifier):
            errors.append('candidate id')
            continue
        need(identifier not in ids, 'duplicate candidate: ' + identifier)
        ids.add(identifier)
        for key in ('name', 'reason', 'task_fit', 'input_requirements', 'comparison_track', 'implementation_gap', 'evidence_notes'):
            need(nonempty(item.get(key)), identifier + ': ' + key)
        for key, allowed in {'decision': ('select', 'defer', 'exclude'),
                             'role': ('classic', 'recent', 'simple', 'alternative'),
                             'local_status': ('absent', 'partial', 'structural_complete', 'validated'),
                             'executor_status': ('unknown', 'needs_adaptation', 'validated'),
                             'source_checked': ('metadata_only', 'abstract_only', 'paper', 'paper_and_code'),
                             'paper_access': ('metadata_only', 'abstract_only', 'full_text'),
                             'code_access': ('not_checked', 'repository_page', 'source_files')}.items():
            need(item.get(key) in allowed, identifier + ': ' + key)
        if item.get('source_checked') in ('paper', 'paper_and_code'):
            need(item.get('paper_access') == 'full_text', identifier + ': paper claim requires full text')
        if item.get('source_checked') == 'paper_and_code':
            need(item.get('code_access') == 'source_files', identifier + ': code claim requires source files')
        if item.get('code_access') != 'not_checked':
            need(url(item.get('code_url')), identifier + ': checked code needs URL')
        year = item.get('year')
        need(type(year) is int and 1900 <= year <= cutoff.year, identifier + ': year')
        need(url(item.get('paper_url')), identifier + ': paper_url')
        need(item.get('code_url') is None or url(item['code_url']), identifier + ': code_url')
        if item.get('decision') == 'select':
            selected.add(identifier)
            roles.add(item.get('role'))
            if item.get('role') == 'recent' and type(year) is int and type(recent) is int:
                need(year >= recent, identifier + ': outside recent window')
            if item.get('paper_access') != 'full_text':
                selected_papers_read = False
                warnings.append(identifier + ': original paper not yet checked')
            if item.get('executor_status') != 'validated':
                warnings.append(identifier + ': executor not validated')
        if item.get('executor_status') == 'validated':
            need(item.get('local_status') == 'validated', identifier + ': executor/local status conflict')
    need(bool(selected), 'no selected methods')
    exceptions = plan.get('coverage_exceptions', {})
    for role in ('classic', 'recent'):
        need(role in roles or (isinstance(exceptions, dict) and nonempty(exceptions.get(role))), 'missing ' + role + ' coverage or substantive exception')
    fairness = plan.get('fairness', {})
    for key in ('patient_split', 'feature_policy', 'tuning_policy', 'sampling_policy', 'held_out_policy'):
        need(isinstance(fairness, dict) and nonempty(fairness.get(key)), 'fairness: ' + key)
    matrix = plan.get('matrix', {})
    if not isinstance(matrix, dict):
        matrix = {}
    models, seeds = matrix.get('model_ids'), matrix.get('seeds')
    valid_models = isinstance(models, list) and all(nonempty(x) for x in models)
    need(valid_models and len(models) == len(set(models)) and set(models) == selected, 'matrix models must equal selected candidates without duplicates')
    valid_seeds = isinstance(seeds, list) and bool(seeds) and all(type(x) is int for x in seeds)
    need(valid_seeds and len(seeds) == len(set(seeds)), 'matrix seeds')
    for key in ('folds', 'settings_per_model', 'cv_runs', 'final_fit_runs', 'total_fit_runs'):
        value = matrix.get(key)
        need(type(value) is int and value >= (1 if key in ('folds', 'settings_per_model') else 0), 'matrix: ' + key)
    if valid_models and valid_seeds and all(type(matrix.get(k)) is int for k in ('folds', 'settings_per_model', 'cv_runs', 'final_fit_runs', 'total_fit_runs')):
        need(matrix['cv_runs'] == len(models) * matrix['folds'] * len(seeds) * matrix['settings_per_model'], 'cv_runs arithmetic mismatch')
        need(matrix['total_fit_runs'] == matrix['cv_runs'] + matrix['final_fit_runs'], 'total_fit_runs arithmetic mismatch')
    counts = plan.get('split_counts', {})
    valid_counts = isinstance(counts, dict) and all(type(counts.get(k)) is int and counts[k] > 0 for k in ('cohort', 'development', 'locked_test'))
    need(valid_counts, 'split_counts: positive cohort/development/locked_test required')
    if valid_counts:
        need(counts['cohort'] == counts['development'] + counts['locked_test'], 'split_counts: cohort arithmetic mismatch')
        sizes = counts.get('cv_oof')
        valid_sizes = isinstance(sizes, list) and all(type(n) is int and n > 0 for n in sizes)
        need(valid_sizes and len(sizes) == matrix.get('folds') and sum(sizes) == counts['development'], 'split_counts: OOF fold sizes must cover development cohort')
    need(plan.get('training_authorized') is False, 'planning cannot authorize training')
    return {'structure_valid': not errors, 'source_review_complete': bool(selected) and selected_papers_read and not errors,
            'errors': errors, 'warnings': warnings,
            'scope': 'Structure, local references and arithmetic only; does not verify sources, fairness or execution readiness.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', required=True)
    parser.add_argument('--plan', required=True)
    args = parser.parse_args()
    try:
        result = check(json.loads(local_file(args.workspace, args.plan).read_text()), args.workspace)
    except (ValueError, OSError) as exc:
        result = {'structure_valid': False, 'errors': [str(exc)], 'warnings': []}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result['structure_valid'] else 1)
