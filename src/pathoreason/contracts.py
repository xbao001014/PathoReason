"""Versioned P0 contracts. No imports or mutations of legacy domain models."""
from __future__ import annotations

import hashlib
import json
from pathlib import PurePosixPath
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

Identifier = Annotated[str, Field(min_length=1, max_length=160, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Text = Annotated[str, Field(min_length=1)]
Nonnegative = Annotated[int, Field(ge=0, strict=True)]
Positive = Annotated[int, Field(gt=0, strict=True)]
Runtime = Literal["codex", "opencode"]


def canonical_digest(value: object) -> str:
    """SHA256 of UTF-8 sorted compact JSON; excludes digest only at caller boundary."""
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_default=True, frozen=True)
    schema_version: Literal["pathoreason/1"] = "pathoreason/1"


class LegacyResourceRef(Contract):
    adapter: Literal["auto_research.experiment", "auto_research.task_project", "auto_research.evidence_file"]
    resource_id: Text
    revision: Digest
    revision_kind: Literal["file_sha256", "manifest_sha256"]
    access: Literal["read_only"] = "read_only"


class ResearchProject(Contract):
    id: Identifier
    title: Text
    objective: Text
    revision: Positive
    created_at: AwareDatetime
    status: Literal["active", "archived"]
    resources: list[LegacyResourceRef]


class SkillDefinition(Contract):
    id: Identifier
    version: Text
    title: Text
    description: Text
    input_schema_ref: Text
    output_schema_ref: Text
    instruction_refs: list[Text]
    capability_refs: list[Text]
    workflow_template_refs: list[Text]
    runtime_support: list[Runtime] = Field(min_length=1)
    required_inputs: list[Text]
    required_tools: list[Text]
    implementation_status: Literal["planned", "adapter_pending", "implemented"]
    evidence_scope: Literal["none", "contract_only", "synthetic", "real_scenario"]
    runtime_readiness: Literal["unchecked", "unavailable", "ready"]
    unavailable_reason: Text | None
    digest: Digest

    @model_validator(mode="after")
    def validate_definition(self) -> Self:
        if self.runtime_readiness != "ready" and not self.unavailable_reason:
            raise ValueError("unready skill requires an explanation")
        if self.runtime_readiness == "ready" and (self.unavailable_reason is not None or self.implementation_status != "implemented"):
            raise ValueError("ready requires an implemented adapter and no unavailable reason")
        if self.digest != canonical_digest(self.model_dump(mode="json", exclude={"digest"})):
            raise ValueError("skill digest mismatch")
        return self


class SkillInvocation(Contract):
    id: Identifier
    project_id: Identifier
    conversation_id: Identifier
    turn_id: Identifier
    skill_id: Identifier
    skill_version: Text
    skill_digest: Digest
    input_artifact_ids: list[Identifier]


class ModelDescriptor(Contract):
    runtime: Runtime
    provider: Text
    model: Text
    context_limit_tokens: Positive | None
    input_limit_tokens: Positive | None
    output_limit_tokens: Positive | None
    tool_support: Literal["supported", "unsupported", "unknown"]
    usage_source: Literal["runtime", "provider", "estimated", "unknown"]
    metadata_source: Text
    availability: Literal["catalog_only", "authenticated", "inference_verified", "unavailable"]

    @model_validator(mode="after")
    def limits(self) -> Self:
        if self.context_limit_tokens is not None:
            for value in (self.input_limit_tokens, self.output_limit_tokens):
                if value is not None and value > self.context_limit_tokens:
                    raise ValueError("input/output limit exceeds context limit")
        return self


class RuntimeBinding(Contract):
    id: Identifier
    project_id: Identifier
    conversation_id: Identifier
    runtime: Runtime
    runtime_version: Text
    native_session_id: Text | None
    state: Literal["unbound", "bound", "closed"]
    storage_namespace: Identifier
    workspace_id: Identifier
    auth_ref: Literal["server_codex_login", "server_provider_credential"]
    created_at: AwareDatetime

    @model_validator(mode="after")
    def native_identity(self) -> Self:
        if (self.state == "unbound") != (self.native_session_id is None):
            raise ValueError("unbound has no native session; bound/closed must retain its native ID")
        if self.runtime == "opencode" and self.auth_ref == "server_codex_login":
            raise ValueError("Codex login cannot authenticate an OpenCode binding")
        return self


class Conversation(Contract):
    id: Identifier
    project_id: Identifier
    title: Text
    status: Literal["open", "archived"]
    active_runtime_binding_id: Identifier
    created_at: AwareDatetime


class Turn(Contract):
    id: Identifier
    project_id: Identifier
    conversation_id: Identifier
    runtime_binding_id: Identifier
    request_key: Identifier
    status: Literal["queued", "running", "interrupt_requested", "completed", "interrupted", "failed", "recovery_required"]
    model: ModelDescriptor
    config_digest: Digest
    created_at: AwareDatetime
    finished_at: AwareDatetime | None
    native_turn_id: Text | None
    error_code: Text | None

    @model_validator(mode="after")
    def lifecycle(self) -> Self:
        terminal = self.status in {"completed", "interrupted", "failed"}
        if terminal != (self.finished_at is not None):
            raise ValueError("only terminal turns have finished_at")
        if self.finished_at is not None and self.finished_at < self.created_at:
            raise ValueError("turn finishes before it starts")
        if self.status == "failed" and not self.error_code:
            raise ValueError("failed turn requires error_code")
        return self


class MessagePart(Contract):
    id: Identifier
    project_id: Identifier
    conversation_id: Identifier
    turn_id: Identifier
    ordinal: Nonnegative
    role: Literal["user", "assistant", "tool", "system"]
    kind: Literal["text", "artifact_reference", "tool_summary"]
    text: Text | None
    artifact_id: Identifier | None

    @model_validator(mode="after")
    def content(self) -> Self:
        if self.kind == "artifact_reference":
            if not self.artifact_id or self.text is not None:
                raise ValueError("artifact reference requires only artifact_id")
        elif not self.text or self.artifact_id is not None:
            raise ValueError("text/tool summary requires only text")
        return self


class ContextSnapshot(Contract):
    id: Identifier
    project_id: Identifier
    project_revision: Positive
    goal: Text
    constraints: list[Text]
    source_refs: list[LegacyResourceRef]
    decision_refs: list[LegacyResourceRef]
    active_run_refs: list[LegacyResourceRef]
    artifact_ids: list[Identifier]
    pending_items: list[Text]
    created_at: AwareDatetime
    digest: Digest

    @model_validator(mode="after")
    def digest_matches(self) -> Self:
        if self.digest != canonical_digest(self.model_dump(mode="json", exclude={"digest"})):
            raise ValueError("context digest mismatch")
        return self


class ArtifactIndex(Contract):
    id: Identifier
    project_id: Identifier
    title: Text
    kind: Literal["document", "figure", "table", "report", "source_bundle"]
    media_type: Text
    storage_root: Literal["legacy_evidence", "pathoreason_artifacts"]
    relative_path: Text
    sha256: Digest
    size_bytes: Nonnegative
    source_ref: LegacyResourceRef
    run_ref: LegacyResourceRef | None
    stage_ref: Text | None
    verification_scope: Literal["indexed", "bytes_verified", "scientifically_reviewed"]
    evidence_role: Literal["development", "synthetic", "manuscript_review", "independent_test", "not_assessed"]

    @field_validator("relative_path")
    @classmethod
    def safe_path(cls, value: str) -> str:
        path = PurePosixPath(value)
        if path.is_absolute() or any(p in {"..", ".", ""} for p in value.split("/")) or "\\" in value:
            raise ValueError("artifact path must be normalized and relative")
        return value

    @model_validator(mode="after")
    def legacy_bytes(self) -> Self:
        if self.storage_root == "legacy_evidence":
            if (self.source_ref.adapter != "auto_research.evidence_file"
                or self.source_ref.revision_kind != "file_sha256"
                or self.source_ref.revision != self.sha256
                or self.source_ref.resource_id != self.relative_path):
                raise ValueError("legacy artifact source identity differs from indexed bytes")
        return self


class RuntimePayload(Contract):
    kind: Literal["turn_status", "text_delta", "tool_summary", "usage", "compaction", "error"]
    text: Text | None = None
    part_id: Identifier | None = None
    turn_status: Literal["queued", "running", "interrupt_requested", "completed", "interrupted", "failed", "recovery_required"] | None = None
    input_tokens: Nonnegative | None = None
    output_tokens: Nonnegative | None = None
    context_tokens: Nonnegative | None = None
    usage_source: Literal["runtime", "provider", "estimated", "unknown"] | None = None
    usage_scope: Literal["turn", "cumulative", "context_window"] | None = None

    @model_validator(mode="after")
    def shape(self) -> Self:
        if self.kind == "text_delta" and (self.text is None or self.part_id is None):
            raise ValueError("text delta needs text and a stable part ID")
        if self.kind == "turn_status" and self.turn_status is None:
            raise ValueError("status event needs turn_status")
        if self.kind == "usage" and (self.usage_source is None or self.usage_scope is None):
            raise ValueError("usage needs provenance and scope")
        if self.kind in {"tool_summary", "compaction", "error"} and self.text is None:
            raise ValueError("public summary required")
        return self


class RuntimeEvent(Contract):
    id: Identifier
    project_id: Identifier
    conversation_id: Identifier
    turn_id: Identifier
    runtime_binding_id: Identifier
    seq: Positive
    occurred_at: AwareDatetime
    source_event_key: Text
    scope: Literal["runtime"] = "runtime"
    producer: Literal["runtime_adapter"] = "runtime_adapter"
    payload: RuntimePayload


class DomainEvent(Contract):
    id: Identifier
    project_id: Identifier
    seq: Positive
    occurred_at: AwareDatetime
    scope: Literal["domain"] = "domain"
    producer: Literal["legacy_adapter", "domain_service"]
    kind: Literal["resource_observed", "artifact_indexed", "workflow_state_changed"]
    authority_ref: LegacyResourceRef
    source_event_key: Text
    observed_status: Text
    correlation_turn_id: Identifier | None


class ExecutionIntent(Contract):
    id: Identifier
    project_id: Identifier
    conversation_id: Identifier
    turn_id: Identifier
    target_ref: LegacyResourceRef
    expected_revision: Digest
    operation: Text
    idempotency_key: Identifier
    arguments_digest: Digest
    status: Literal["proposed", "validated", "dispatched", "rejected", "reconciled"]
    run_ref: LegacyResourceRef | None

    @model_validator(mode="after")
    def revision_matches(self) -> Self:
        if self.expected_revision != self.target_ref.revision:
            raise ValueError("intent revision differs from bound target")
        return self


class AcceptanceBundle(Contract):
    """Offline contract fixture; not a database or a runtime launch request."""
    fixture_kind: Literal["contract_only"] = "contract_only"
    project: ResearchProject
    skills: list[SkillDefinition]
    conversation: Conversation
    binding: RuntimeBinding
    turns: list[Turn]
    invocations: list[SkillInvocation]
    messages: list[MessagePart]
    context: ContextSnapshot
    artifacts: list[ArtifactIndex]
    runtime_events: list[RuntimeEvent]
    domain_events: list[DomainEvent]
    intents: list[ExecutionIntent]

    @model_validator(mode="after")
    def relationships(self) -> Self:
        project, conversation, binding = self.project, self.conversation, self.binding
        if conversation.active_runtime_binding_id != binding.id or binding.conversation_id != conversation.id:
            raise ValueError("active runtime binding does not belong to conversation")
        owned = [conversation, binding, self.context, *self.turns, *self.invocations, *self.messages,
                 *self.artifacts, *self.runtime_events, *self.domain_events, *self.intents]
        if any(o.project_id != project.id for o in owned):
            raise ValueError("cross-project reference")
        if self.context.project_revision != project.revision:
            raise ValueError("stale project snapshot")
        if any(o.conversation_id != conversation.id for o in [*self.turns, *self.invocations, *self.messages, *self.runtime_events, *self.intents]):
            raise ValueError("cross-conversation reference")
        for collection in [self.skills, self.turns, self.invocations, self.messages, self.artifacts, self.runtime_events, self.domain_events, self.intents]:
            if len({o.id for o in collection}) != len(collection):
                raise ValueError("duplicate entity ID")
        turns = {o.id: o for o in self.turns}
        artifacts = {o.id for o in self.artifacts}
        if len({o.request_key for o in self.turns}) != len(self.turns):
            raise ValueError("duplicate request key")
        if len([t for t in self.turns if t.status in {"running", "interrupt_requested", "recovery_required"}]) > 1:
            raise ValueError("only one active or unresolved turn per conversation")
        for turn in self.turns:
            if turn.status != "queued" and binding.state == "unbound":
                raise ValueError("dispatched turn requires a native binding")
            if turn.runtime_binding_id != binding.id or turn.model.runtime != binding.runtime:
                raise ValueError("turn runtime mismatch")
        for obj in [*self.invocations, *self.messages, *self.runtime_events, *self.intents]:
            if obj.turn_id not in turns:
                raise ValueError("missing turn")
        message_keys = [(m.turn_id, m.ordinal) for m in self.messages]
        if len(set(message_keys)) != len(message_keys):
            raise ValueError("duplicate message ordinal")
        for event in self.runtime_events:
            if event.runtime_binding_id != binding.id:
                raise ValueError("event runtime mismatch")
        for events in [self.runtime_events, self.domain_events]:
            if len({e.seq for e in events}) != len(events) or len({e.source_event_key for e in events}) != len(events):
                raise ValueError("duplicate event sequence or source key")
        for event in self.domain_events:
            if event.correlation_turn_id is not None and event.correlation_turn_id not in turns:
                raise ValueError("unknown domain correlation")
        refs = self.context.artifact_ids + [m.artifact_id for m in self.messages if m.artifact_id]
        refs += [a for i in self.invocations for a in i.input_artifact_ids]
        if not set(refs) <= artifacts:
            raise ValueError("missing artifact")
        skills = {s.id: s for s in self.skills}
        for invocation in self.invocations:
            skill = skills.get(invocation.skill_id)
            if skill is None or (invocation.skill_version, invocation.skill_digest) != (skill.version, skill.digest):
                raise ValueError("skill version or digest mismatch")
        resources = {r.model_dump_json() for r in project.resources}
        source_refs = [*self.context.source_refs, *self.context.decision_refs, *self.context.active_run_refs]
        source_refs += [a.source_ref for a in self.artifacts] + [a.run_ref for a in self.artifacts if a.run_ref]
        source_refs += [e.authority_ref for e in self.domain_events] + [i.target_ref for i in self.intents]
        if any(ref.model_dump_json() not in resources for ref in source_refs):
            raise ValueError("source is not bound to project")
        return self
