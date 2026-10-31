"""Pure, lossless read projections. No legacy producer is imported or saved."""
from __future__ import annotations
import json
from copy import deepcopy
from pathlib import Path
import jsonschema
from . import contracts as c
from .business import BusinessArtifact,BusinessView,WorkflowRef
from .schema_v2 import *
from .formal_contracts import FormalArtifact,FormalReference,FormalRef

TASK_SCHEMA=json.loads((Path(__file__).resolve().parents[2]/'contracts/legacy/TaskSpec.schema.json').read_text())

def parse_artifact(raw):
    version=raw.get('schema_version')
    if version=='pathoreason/1':return c.ArtifactIndex.model_validate(raw)
    if version=='pathoreason/3':return FormalArtifact.model_validate(raw)
    if version=='pathoreason/2':return BusinessArtifact.model_validate(raw)
    raise ValueError('artifact_version_unsupported')

def reference(raw,role='workflow'):
    if raw.get('schema_version')=='pathoreason.formal/1':return FormalReference(reference=FormalRef.model_validate(raw))
    if raw.get('schema_version')=='pathoreason.business/1':return BusinessReference(role=role,reference=WorkflowRef.model_validate(raw))
    return LegacyReference(reference=c.LegacyResourceRef.model_validate(raw))

def artifact_identity(raw):
    a=parse_artifact(raw)
    return ArtifactReference(project_id=a.project_id,artifact_id=a.id,sha256=a.sha256)

def snapshot(raw,artifacts,business_context=None):
    if raw.get('schema_version') in ('pathoreason.context/2','pathoreason.context/3'):return ContextSnapshotV2.model_validate(raw)
    old=c.ContextSnapshot.model_validate(raw);by_id={a['id']:a for a in artifacts}
    identities=[artifact_identity(by_id[aid]) for aid in old.artifact_ids]
    sources=[reference(r.model_dump(mode='json')) for r in old.source_refs]
    decisions=[reference(r.model_dump(mode='json')) for r in old.decision_refs]
    runs=[reference(r.model_dump(mode='json')) for r in old.active_run_refs]
    for aid in old.artifact_ids:
        a=by_id[aid];ref=reference(a['source_ref'])
        if ref not in sources:sources.append(ref)
        if a.get('run_ref'):
            ref=reference(a['run_ref'],'run')
            if ref not in runs:runs.append(ref)
    if business_context:
        view=BusinessView.model_validate(business_context)
        if view.project_id!=old.project_id:raise ValueError('business_context_project_mismatch')
        for action in view.actions:
            decisions.append(BusinessReference(role='decision',reference=WorkflowRef(project_id=old.project_id,resource_id=action.id,revision=c.canonical_digest(action.model_dump(mode='json')))))
        if view.run_id and not any(isinstance(r,BusinessReference) and r.reference.resource_id==view.run_id for r in runs):
            runs.append(BusinessReference(role='run',reference=WorkflowRef(project_id=old.project_id,resource_id=view.run_id,revision=view.revision)))
    value=old.model_dump(mode='json',exclude={'digest'})
    value.update(schema_version='pathoreason.context/2',source_refs=[r.model_dump(mode='json') for r in sources],decision_refs=[r.model_dump(mode='json') for r in decisions],active_run_refs=[r.model_dump(mode='json') for r in runs],artifact_refs=[r.model_dump(mode='json') for r in identities],origin_version=old.schema_version,origin_digest=old.digest)
    if any(r['kind']=='formal' for r in value['source_refs']+value['active_run_refs']):value['schema_version']='pathoreason.context/3'
    return ContextSnapshotV2(**value,digest=c.canonical_digest(value))

def new_snapshot(raw,artifacts,business_context=None):
    old=c.ContextSnapshot(**raw,digest=c.canonical_digest(raw))
    value=snapshot(old.model_dump(mode='json'),artifacts,business_context).model_dump(mode='json',exclude={'digest'})
    value.update(origin_version=None,origin_digest=None)
    return ContextSnapshotV2(**value,digest=c.canonical_digest(value))

def metric(raw):
    return MetricView(**{k:raw.get(k) for k in MetricView.model_fields})

def task_semantics(config,authority='task_spec'):
    issues=[];task=deepcopy(config.get('task_spec'))
    if task is None:
        return TaskSemantics(authority='legacy_fields',family=config.get('task_kind'),targets=[{'column':config.get('label_column'),'threshold':config.get('class_threshold')}],bag_level=config.get('bag_level')), [SemanticIssue(code='legacy_selection_unresolved',field='primary_metric',source_value=config.get('primary_metric'))]
    jsonschema.Draft202012Validator(TASK_SCHEMA).validate(task)
    selection=task['selection']['metric']
    if selection['split']!='val':issues.append(SemanticIssue(code='selection_must_use_validation',field='task_spec.selection.metric.split',source_value=selection['split'],canonical_value='val'))
    targets=task['targets'];derived={'task_kind':task['family'],'label_column':targets[0].get('column') or targets[0].get('time_column'),'bag_level':task['bag_level'],'primary_metric':'val_'+selection['name']}
    for key,value in derived.items():
        if config.get(key) is not None and config[key]!=value:issues.append(SemanticIssue(code='canonical_task_conflict',field=key,source_value=config[key],canonical_value=value))
    threshold=targets[0].get('threshold')
    if threshold and config.get('class_threshold') is not None and config['class_threshold']!=threshold['value']:
        issues.append(SemanticIssue(code='canonical_threshold_conflict',field='class_threshold',source_value=config['class_threshold'],canonical_value=threshold['value']))
    return TaskSemantics(authority=authority,task_schema_version=task.get('schema_version',1),family=task['family'],targets=targets,objective=task['objective'],selection=metric(selection),evaluation=[metric(m) for m in task['evaluation']],bag_level=task['bag_level'],target_level=task['target_level'],split_group=task['split_group'],source_task=task),issues

def workflow(blueprint,state):
    raw=deepcopy(blueprint);version=raw.get('schema_version')
    if version==1:
        definition={k:v for k,v in raw.items() if k!='workspace'}
        nodes=[WorkflowNodeView(id=n['id'],title=n['title'],kind=n['kind'],stages=n['stages'],gate_stage=n.get('gateStage'),gate_hint=n.get('gateHint'),current=state.get('stage') in n['stages']) for n in raw.get('workspace',{}).get('nodes',[])]
    elif version==2:
        definition={k:v for k,v in raw.items() if k!='workspace'}
        nodes=[WorkflowNodeView(id=n['id'],title=n['title'],kind=n['kind'],stages=[n['id']],gate_stage=n['id'] if n['kind']=='gate' else None,current=state.get('stage')==n['id']) for n in raw['steps']]
    else:raise ValueError('workflow_version_unsupported')
    return WorkflowProjection(source_version=version,source_digest=c.canonical_digest(raw),definition_digest=c.canonical_digest(definition),definition=definition,current_stage=state.get('stage'),nodes=nodes)

def _definition(**kwargs):
    # Defaults and JSON date/union normalization form the versioned projection identity.
    raw=ResearchDefinition.model_construct(**kwargs,digest='0'*64).model_dump(mode='json',exclude={'digest'})
    return ResearchDefinition(**raw,digest=c.canonical_digest(raw))

def experiment_definition(source_id,documents,files):
    config=documents['config.json'];budget=config.get('budget',{})
    semantics,issues=task_semantics(config)
    quantities=[]
    for name,scope,unit in [('max_minutes','research','minutes'),('per_run_timeout_minutes','unit','minutes'),('max_model_variants','candidate','candidates'),('max_runs','research','runs')]:
        if name in budget:quantities.append(BudgetQuantity(name=name,scope=scope,unit=unit,value=budget[name],source_pointer='/budget/'+name))
    compute=ComputeSettings(runtime=config.get('runtime'),**{k:budget.get(k) for k in ['gpu_ids','cpu_threads','memory_gb','feature_cache_mb']},protocol={k:deepcopy(config[k]) for k in ['training_protocol','split_strategy','split_seed','holdout','cv_val_fraction_of_train'] if k in config}|{'stage_training':{k:budget[k] for k in ['n_splits','baseline_epochs','innovation_epochs','ablation_epochs'] if k in budget}})
    return _definition(source_kind='legacy_experiment',source_id=source_id,source_files=files,source_payload=deepcopy(documents),semantics=semantics,compute=compute,invocation_settings={'legacy_codex_timeout_minutes':budget.get('codex_timeout_minutes'),'authority':'legacy_call_policy_not_training_budget'},budgets=quantities,workflow=workflow(documents['blueprint.json'],documents['state.json']),compatibility='conflict' if any(i.code!='legacy_selection_unresolved' for i in issues) else 'legacy_unresolved' if issues else 'compatible',issues=issues)

def synthetic_definition(source_id,plan,state,files):
    semantics,issues=task_semantics({'task_spec':plan['task']},'synthetic_plan')
    contract=plan['contract'];budget=contract['budget'];quantities=[]
    for name,scope,unit in [('max_gpu_seconds','research','gpu_seconds'),('max_wall_seconds','research','wall_seconds'),('max_model_calls','planner','calls'),('max_candidates','candidate','candidates'),('max_repairs_per_hypothesis','repair','attempts'),('reserved_confirmation_gpu_seconds','confirmation','gpu_seconds')]:
        if name in budget:quantities.append(BudgetQuantity(name=name,scope=scope,unit=unit,value=budget[name],source_pointer='/contract/budget/'+name))
    usage=state.get('result',{}).get('budget',{})
    for name,unit in [('used_worker_seconds','worker_wall_seconds'),('reserved_worker_seconds','worker_wall_seconds'),('gpu_seconds','gpu_seconds'),('model_calls','calls')]:
        if name in usage:quantities.append(BudgetQuantity(name=name,scope='reported_usage',unit=unit,value=usage[name],source_pointer='/state/result/budget/'+name))
    return _definition(source_kind='synthetic_plan',source_id=source_id,source_files=files,source_payload={'plan':deepcopy(plan),'state':deepcopy(state)},semantics=semantics,compute=ComputeSettings(runtime={'kind':'independent_cpu_synthetic'},protocol={'evaluation':contract['protocol'],'unit_timeout_seconds':plan['unit_timeout_seconds']}),invocation_settings={'planner_model_calls':budget['max_model_calls'],'authority':'research_planner_not_chat_turn_budget'},budgets=quantities,compatibility='conflict' if issues else 'compatible',issues=issues)

def task_project_definition(source_id,blueprint,state,files):
    view=workflow(blueprint,state)
    return _definition(source_kind='task_project',source_id=source_id,source_files=files,source_payload={'blueprint':deepcopy(blueprint),'state':deepcopy(state)},semantics=TaskSemantics(authority='task_project',family=blueprint['task']),compute=ComputeSettings(protocol={'execution':blueprint['execution']}),invocation_settings={},budgets=[],workflow=view,compatibility='compatible',issues=[])
