"""Read-only cost evidence from the public training-progress projection."""
import json
import math
import statistics
import hashlib


def _measured(value):
    return (isinstance(value,(int,float)) and not isinstance(value,bool)
            and math.isfinite(value) and value >= 0)


def _stats(receipts):
    values = [r['elapsed_seconds'] for r in receipts if _measured(r.get('elapsed_seconds'))]
    return {'attempt_count': len(receipts), 'measured_count': len(values),
            'unknown_count': len(receipts)-len(values),
            'observed_sum_seconds': sum(values) if values else None,
            'mean_seconds': statistics.mean(values) if values else None,
            'median_seconds': statistics.median(values) if values else None,
            'min_seconds': min(values) if values else None,
            'max_seconds': max(values) if values else None}


def summarize(progress):
    if progress.get('schema_version') != 'pathoreason.training-progress/1':
        raise ValueError('training_progress_schema_required')
    experiments = []
    for experiment in progress['experiments']:
        units = {u['id']: u for u in experiment['units']}
        groups = {}; failures = []; excluded = []; seen = set()
        for attempt in experiment['attempts']:
            if attempt['id'] in seen:
                raise ValueError('duplicate_attempt_receipt')
            seen.add(attempt['id'])
            receipt = {k: attempt.get(k) for k in ('id','unit_id','status','elapsed_seconds',
                       'charged','current_scope','run_id','plan_digest','scope_digest')}
            if not _measured(receipt['elapsed_seconds']):
                receipt['elapsed_seconds'] = None
            if attempt['status'] == 'failed':
                failures.append(receipt)
            unit = units.get(attempt['unit_id'])
            if (attempt['status'] != 'completed' or not attempt.get('current_scope') or
                    not attempt.get('charged') or unit is None or attempt.get('phase') != unit.get('phase')):
                excluded.append(receipt)
                continue
            # Seeds are replicates. Keep every other parameter, including early
            # stopping, epochs and model; never pool experiments or environments.
            parameters = {k:v for k,v in unit.get('parameters',{}).items() if k != 'seed'}
            dependencies = []
            for dependency_id in unit.get('depends_on',[]):
                dependency = units.get(dependency_id)
                dependencies.append({'phase':dependency['phase'], 'parameters':{
                    k:v for k,v in dependency.get('parameters',{}).items() if k != 'seed'}}
                    if dependency else {'unresolved_unit_id':dependency_id})
            dependencies.sort(key=lambda d:json.dumps(d,sort_keys=True))
            key = json.dumps([unit['phase'],parameters,dependencies], sort_keys=True, ensure_ascii=False)
            group = groups.setdefault(key, {'phase':unit['phase'], 'parameters':parameters,
                                            'group_id':hashlib.sha256(key.encode()).hexdigest()[:16],
                                            'dependency_parameters':dependencies,
                                            'attempts':[]})
            group['attempts'].append(receipt)
        experiments.append({
            'experiment_id':experiment['id'], 'status':experiment['status'],
            'environment_id':experiment['plan'].get('environment_id'),
            'gpu_uuid':experiment['plan'].get('gpu_uuid'),
            'ledger_used_wall_seconds':experiment.get('used_wall_seconds'),
            'ledger_used_gpu_seconds':experiment.get('used_gpu_seconds'),
            'completed_groups':[{**g, 'statistics':_stats(g['attempts'])} for g in groups.values()],
            'failed_attempts':failures, 'failed_elapsed_statistics':_stats(failures),
            'excluded_from_completed_groups':excluded,
        })
    return {'schema_version':'pathoreason.training-cost-summary/1',
            'project_id':progress['project_id'], 'observed_at':progress.get('observed_at'),
            'metric':'attempt elapsed wall seconds; not per-attempt GPU billing',
            'scope':'descriptive evidence, not a budget authorization or future cost prediction',
            'experiments':experiments}


def render_table(summary):
    """Keep identities beside numbers so callers need not relabel array indices."""
    lines=['Elapsed wall seconds, not GPU billing. Read-only observations; no training authorization.']
    def cell(value):
        if value is None:return 'unknown'
        if isinstance(value,float):return f'{value:.3f}'
        return str(value).replace('|','\\|').replace('\n',' ')
    for experiment in summary['experiments']:
        lines.extend(['', '| experiment | group | phase | model | epochs | early_stop | wd | mechanism | n/measured | mean | median | min | max |',
                      '|---|---|---|---|---|---|---|---|---|---|---|---|---|'])
        for group in experiment['completed_groups']:
            params=group['parameters']
            parent=group['dependency_parameters']
            inherited=parent[0].get('parameters',{}) if len(parent)==1 else {}
            def parameter(key):return params.get(key,inherited.get(key))
            stats=group['statistics']
            values=[experiment['experiment_id'],group['group_id'],group['phase'],parameter('model'),
                    parameter('epochs'),parameter('early_stop_patience'),str(parameter('weight_decay')) if parameter('weight_decay') is not None else None,
                    parameter('mechanism'),str(stats['attempt_count'])+'/'+str(stats['measured_count']),
                    stats['mean_seconds'],stats['median_seconds'],stats['min_seconds'],stats['max_seconds']]
            lines.append('| '+' | '.join(cell(value) for value in values)+' |')
        failed=experiment['failed_elapsed_statistics']
        lines.append(f"\n{experiment['experiment_id']} failed attempts: {failed['attempt_count']}; "
                     f"measured elapsed sum: {cell(failed['observed_sum_seconds'])}; "
                     f"ledger wall/GPU: {cell(experiment['ledger_used_wall_seconds'])}/{cell(experiment['ledger_used_gpu_seconds'])}.\n")
    lines.append('Display labels omit some parameters. JSON preserves all grouping parameters, dependency parameters and attempt references. Do not rename groups by row position.')
    return '\n'.join(lines)
