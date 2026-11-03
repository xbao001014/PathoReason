"""Experiment-owned compute contracts. Never share a conversation allowance."""
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field,model_validator
from .contracts import Identifier

class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True,allow_inf_nan=False,strict=True)

class TrainingBudget(Strict):
    max_wall_seconds:float=Field(gt=0,le=30*86400)
    max_gpu_seconds:float=Field(ge=0,le=30*86400)
    max_unit_seconds:float=Field(gt=0,le=7*86400)
    max_attempts_per_unit:int=Field(ge=1,le=10)
    @model_validator(mode='after')
    def bounds(self):
        if self.max_unit_seconds>self.max_wall_seconds:raise ValueError('unit_limit_exceeds_experiment_limit')
        return self

class TrainingInput(Strict):
    id:Identifier
    path:str=Field(min_length=1,max_length=4096)
    sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    role:Literal['development','sealed']
    subject_id:str=Field(min_length=1,max_length=160)
    prior_test_exposures:int|None=Field(default=None,ge=0)

class TrainingUnit(Strict):
    id:Identifier
    label:str=Field(min_length=1,max_length=160)
    phase:Literal['fit','evaluate']='fit'
    entrypoint:str=Field(min_length=1,max_length=300)
    args:list[str]=Field(default_factory=list,max_length=100)
    input_ids:list[Identifier]=Field(default_factory=list,max_length=100000)
    depends_on:list[Identifier]=Field(default_factory=list,max_length=1000)
    parameters:dict=Field(default_factory=dict)
    output_files:list[str]=Field(min_length=1,max_length=100)

class TrainingPlan(Strict):
    title:str=Field(min_length=1,max_length=160)
    task_id:Identifier
    snapshot_id:str=Field(pattern=r'^[a-f0-9]{64}$')
    environment_id:str=Field(pattern=r'^[a-f0-9]{64}$')
    protocol:str=Field(min_length=1,max_length=4000)
    evaluation:Literal['development_only','previously_exposed','independent_holdout']='development_only'
    inputs:list[TrainingInput]=Field(default_factory=list,max_length=100000)
    units:list[TrainingUnit]=Field(min_length=1,max_length=1000)
    memory_gib:int=Field(default=16,ge=1,le=512)
    gpu_uuid:str|None=Field(default=None,pattern=r'^GPU-[a-fA-F0-9-]{36}$')
    proposed_budget:TrainingBudget|None=None
    @model_validator(mode='after')
    def coherent(self):
        files={f.id:f for f in self.inputs}
        if len(files)!=len(self.inputs) or len({u.id for u in self.units})!=len(self.units):raise ValueError('duplicate_training_identity')
        if not any(u.phase=='fit' for u in self.units):raise ValueError('fit_matrix_required')
        for unit in self.units:
            if set(unit.input_ids)-files.keys():raise ValueError('unit_input_not_registered')
            if unit.phase=='fit' and any(files[i].role=='sealed' for i in unit.input_ids):raise ValueError('sealed_input_in_fit')
            if unit.phase=='evaluate' and self.evaluation=='development_only':raise ValueError('test_evaluation_not_in_scope')
        done=set()
        # A declared topological order is deterministic and keeps all fits before evaluation.
        for unit in sorted(self.units,key=lambda u:u.phase=='evaluate'):
            if set(unit.depends_on)-done:raise ValueError('training_dependency_must_precede_unit')
            done.add(unit.id)
        subjects={}
        for f in self.inputs:
            if f.subject_id in subjects and subjects[f.subject_id]!=f.role:raise ValueError('subject_in_development_and_test')
            subjects[f.subject_id]=f.role
            if f.role=='sealed' and self.evaluation=='independent_holdout' and f.prior_test_exposures!=0:raise ValueError('independent_holdout_requires_known_zero_exposure')
        return self

class TrainingToolInput(Strict):
    turn_id:Identifier
    grant:str=Field(min_length=1,max_length=128)
    operation:Literal['list','inspect','environment','prepare','launch','stop','retry']
    idempotency_key:Identifier|None=None
    experiment_id:Identifier|None=None
    expected_revision:int|None=Field(default=None,ge=1)
    python:str|None=None
    extra_paths:list[str]=Field(default_factory=list,max_length=10)
    plan:TrainingPlan|None=None
    plan_path:str|None=Field(default=None,max_length=4096)
    include_plan:bool=False
    reason:str|None=Field(default=None,max_length=2000)

class TrainingDecision(Strict):
    expected_revision:int=Field(ge=1)
    request_key:Identifier
    action:Literal['authorize','budget','stop','resume','cancel']
    budget:TrainingBudget|None=None
    acknowledge_unknown:bool=False

class TrainingView(Strict):
    id:str
    project_id:str
    conversation_id:str
    revision:int
    plan:TrainingPlan
    plan_digest:str
    scope_digest:str
    status:str
    authorized:bool
    budget:TrainingBudget|None=None
    used_wall_seconds:float
    used_gpu_seconds:float
    attempts:list[dict]
    events:list[dict]
    run_id:str|None=None
    error:str|None=None
    approval_ready:bool=True
    scientific_approval:Literal[False]=False
