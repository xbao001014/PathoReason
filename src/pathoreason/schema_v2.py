"""P4 contracts. Existing P0/P2 documents remain immutable source records."""
from __future__ import annotations
from typing import Annotated,Any,Literal
from pydantic import BaseModel,ConfigDict,Field,TypeAdapter,model_validator
from . import contracts as c
from .business import BusinessArtifact,BusinessView,WorkflowRef
from .formal_contracts import FormalArtifact,FormalReference

class Model(BaseModel):
    model_config=ConfigDict(extra='forbid',frozen=True,allow_inf_nan=False)

class LegacyReference(Model):
    kind:Literal['legacy']='legacy'
    reference:c.LegacyResourceRef
class BusinessReference(Model):
    kind:Literal['business']='business'
    role:Literal['workflow','decision','run']
    reference:WorkflowRef
class ArtifactReference(Model):
    kind:Literal['artifact']='artifact'
    project_id:c.Identifier
    artifact_id:c.Identifier
    sha256:c.Digest
ResourceReference=Annotated[LegacyReference|BusinessReference|ArtifactReference|FormalReference,Field(discriminator='kind')]

class ProvenanceHop(Model):
    environment:Literal['local','bxn-server','unknown']
    project_id:c.Identifier
    artifact_id:c.Identifier
    sha256:c.Digest
    handoff_digest:c.Digest|None=None
class ArtifactProvenance(Model):
    schema_version:Literal['pathoreason.provenance/1']='pathoreason.provenance/1'
    origin:ProvenanceHop
    transfers:list[ProvenanceHop]=Field(default_factory=list,max_length=32)
    basis:Literal['local_record','p3_handoff_record','handoff_manifest']
    verification:Literal['integrity_only_not_scientific_approval']='integrity_only_not_scientific_approval'
class ArtifactRecord(Model):
    schema_version:Literal['pathoreason.artifact/3']='pathoreason.artifact/3'
    artifact:c.ArtifactIndex|BusinessArtifact|FormalArtifact
    identity:ArtifactReference
    source:ResourceReference
    run:ResourceReference|None
    provenance:ArtifactProvenance

class ContextSnapshotV2(Model):
    schema_version:Literal['pathoreason.context/2','pathoreason.context/3']='pathoreason.context/2'
    id:c.Identifier
    project_id:c.Identifier
    project_revision:c.Positive
    goal:c.Text
    constraints:list[c.Text]
    source_refs:list[ResourceReference]
    decision_refs:list[ResourceReference]
    active_run_refs:list[ResourceReference]
    artifact_ids:list[c.Identifier]
    artifact_refs:list[ArtifactReference]
    pending_items:list[c.Text]
    created_at:c.AwareDatetime
    origin_version:str|None=None
    origin_digest:c.Digest|None=None
    digest:c.Digest
    @model_validator(mode='after')
    def coherent(self):
        if self.digest!=c.canonical_digest(self.model_dump(mode='json',exclude={'digest'})):raise ValueError('context_digest_mismatch')
        if self.artifact_ids!=[r.artifact_id for r in self.artifact_refs]:raise ValueError('context_artifact_identity_mismatch')
        if any(r.project_id!=self.project_id for r in self.artifact_refs):raise ValueError('context_cross_project_artifact')
        return self

class InvocationPolicy(Model):
    runtime:c.Runtime
    environment:Literal['local','bxn-server']
    execution_mode:Literal['discuss','synthetic']
    max_turns:int=Field(ge=1)
    max_wall_seconds:float=Field(gt=0)
    concurrency:Literal[1]=1
    automatic_retries:Literal[0]=0
    @model_validator(mode='after')
    def local_codex(self):
        if self.runtime=='codex' and self.environment!='local':raise ValueError('codex_inference_local_only')
        return self
from .reasoning import ReasoningEffort

class RuntimeConfiguration(Model):
    schema_version:Literal['pathoreason.runtime-config/1']='pathoreason.runtime-config/1'
    execution_mode:Literal['discuss','synthetic']
    business_context:BusinessView|None
    model:str
    agent:Literal['pathoreason']='pathoreason'
    skill:c.SkillDefinition|None
    opencode:dict[str,Any]|None
    runtime:c.Runtime
    environment:Literal['local','bxn-server']
    context_policy:Literal['native_compaction_with_authoritative_project_reload']
    model_descriptor:c.ModelDescriptor
    invocation_policy:InvocationPolicy
    codex:dict[str,Any]|None=None
    native_config_digest:c.Digest|None=None
    reasoning_effort:ReasoningEffort|None=None
    @model_validator(mode='after')
    def identities(self):
        if self.model!=self.model_descriptor.model or self.runtime!=self.model_descriptor.runtime:raise ValueError('runtime_model_mismatch')
        p=self.invocation_policy
        if (self.runtime,self.environment,self.execution_mode)!=(p.runtime,p.environment,p.execution_mode):raise ValueError('invocation_policy_mismatch')
        if self.execution_mode=='synthetic' and self.business_context is None:raise ValueError('business_context_required')
        return self

class MetricView(Model):
    name:str
    split:str|None
    direction:str|None
    target_id:str|None=None
    unit:str|None=None
    aggregation:str|None=None
class TaskSemantics(Model):
    authority:Literal['task_spec','legacy_fields','synthetic_plan','task_project','unspecified']
    task_schema_version:int|None=None
    family:str|None=None
    targets:list[dict[str,Any]]=Field(default_factory=list)
    objective:dict[str,Any]|None=None
    selection:MetricView|None=None
    evaluation:list[MetricView]=Field(default_factory=list)
    bag_level:str|None=None
    target_level:str|None=None
    split_group:str|None=None
    source_task:dict[str,Any]|None=None
class ComputeSettings(Model):
    runtime:dict[str,Any]|None=None
    gpu_ids:str|None=None
    cpu_threads:int|None=None
    memory_gb:float|None=None
    feature_cache_mb:int|None=None
    protocol:dict[str,Any]=Field(default_factory=dict)
class BudgetQuantity(Model):
    name:str
    scope:Literal['research','unit','planner','candidate','repair','confirmation','reported_usage']
    unit:Literal['minutes','wall_seconds','gpu_seconds','worker_wall_seconds','calls','candidates','runs','attempts']
    value:float|None
    source_pointer:str
class SemanticIssue(Model):
    code:str
    field:str
    source_value:Any=None
    canonical_value:Any=None
class WorkflowNodeView(Model):
    id:str;title:str;kind:str;stages:list[str]
    gate_stage:str|None=None
    gate_hint:str|None=None
    current:bool
class WorkflowProjection(Model):
    schema_version:Literal['pathoreason.workflow-view/1']='pathoreason.workflow-view/1'
    source_version:str|int|None
    source_digest:c.Digest
    definition_digest:c.Digest
    definition:dict[str,Any]
    current_stage:str|None
    nodes:list[WorkflowNodeView]
    execution_authority:Literal[False]=False
class ResearchDefinition(Model):
    schema_version:Literal['pathoreason.research/1']='pathoreason.research/1'
    source_kind:Literal['legacy_experiment','synthetic_plan','task_project']
    source_id:str
    source_files:dict[str,c.Digest]
    source_payload:dict[str,Any]
    semantics:TaskSemantics
    compute:ComputeSettings
    invocation_settings:dict[str,Any]
    budgets:list[BudgetQuantity]
    workflow:WorkflowProjection|None=None
    compatibility:Literal['compatible','legacy_unresolved','conflict']
    issues:list[SemanticIssue]
    execution_authority:Literal[False]=False
    digest:c.Digest
    @model_validator(mode='after')
    def integrity(self):
        if self.digest!=c.canonical_digest(self.model_dump(mode='json',exclude={'digest'})):raise ValueError('research_definition_digest_mismatch')
        return self
class ProjectDomainView(Model):
    schema_version:Literal['pathoreason.project-view/1']='pathoreason.project-view/1'
    project_id:c.Identifier
    project_revision:int
    definitions:list[ResearchDefinition]
    artifact_records:list[ArtifactRecord]
    legacy_history_count:int=0
    authority:Literal['read_only_projection']='read_only_projection'

class LegacyHistoryEntry(Model):
    schema_version:Literal['pathoreason.legacy-history/1']='pathoreason.legacy-history/1'
    id:c.Identifier
    project_id:c.Identifier
    origin:Literal['legacy_import']='legacy_import'
    source_kind:Literal['review','repair']
    source_ref:c.LegacyResourceRef
    source_record_id:str
    source_record_digest:c.Digest
    occurred_at:str|None
    question:str
    answer:str|None=None
    status:str
    native_session_id:None=None
    executable:Literal[False]=False

class TransferArtifact(Model):
    metadata:c.ArtifactIndex|BusinessArtifact|FormalArtifact
    content_base64:str=Field(max_length=2700000)
    provenance:ArtifactProvenance
class TransferPayload(Model):
    version:Literal['pathoreason.handoff/2','pathoreason.handoff/3']='pathoreason.handoff/2'
    source_environment:Literal['local','bxn-server']
    source_runtime:c.Runtime
    project:c.ResearchProject
    constraints:list[str]=Field(max_length=20)
    artifacts:list[TransferArtifact]=Field(max_length=20)
    created_at:str=Field(max_length=40)
class TransferBundle(Model):
    payload:TransferPayload
    digest:c.Digest
