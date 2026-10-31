import copy
import json
from pathlib import Path
import pytest
from pydantic import ValidationError
from jsonschema import Draft202012Validator, FormatChecker
from pathoreason import contracts as c

ROOT = Path(__file__).resolve().parents[1]

@pytest.fixture
def example():
    return json.loads((ROOT / "contracts/examples/cesc-reading.json").read_text())


def test_example_roundtrip_and_structural_schema(example):
    result = c.AcceptanceBundle.model_validate(example)
    assert result.binding.native_session_id is None
    assert result.artifacts and not result.runtime_events
    schema = json.loads((ROOT / "contracts/v1/AcceptanceBundle.schema.json").read_text())
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(result.model_dump(mode="json"))
    assert c.AcceptanceBundle.model_validate_json(result.model_dump_json()) == result


def test_exported_contracts_are_current():
    for name, cls in vars(c).items():
        if isinstance(cls, type) and issubclass(cls, c.Contract) and cls is not c.Contract:
            exported = json.loads((ROOT / f"contracts/v1/{name}.schema.json").read_text())
            Draft202012Validator.check_schema(exported)
            exported.pop("$id")
            exported.pop("$schema")
            assert exported == cls.model_json_schema(), name


@pytest.mark.parametrize("path,value", [
    (("schema_version",), "pathoreason/999"),
    (("conversation", "project_id"), "prj_other"),
    (("conversation", "active_runtime_binding_id"), "bind_other"),
    (("binding", "conversation_id"), "conv_other"),
    (("binding", "state"), "bound"),
    (("binding", "runtime"), "opencode"),
    (("binding", "api_key"), "must-not-be-stored"),
    (("turns", 0, "model", "runtime"), "opencode"),
    (("turns", 0, "model", "context_limit_tokens"), 0),
    (("turns", 0, "status"), "completed"),
    (("turns", 0, "finished_at"), "2026-10-30T05:01:00Z"),
    (("messages", 0, "turn_id"), "turn_missing"),
    (("messages", 0, "kind"), "chain_of_thought"),
    (("invocations", 0, "skill_digest"), "0" * 64),
    (("invocations", 0, "input_artifact_ids"), ["art_other_project"]),
    (("artifacts", 0, "relative_path"), "../secret"),
    (("artifacts", 0, "relative_path"), "/etc/passwd"),
    (("artifacts", 0, "sha256"), "0" * 64),
    (("artifacts", 0, "size_bytes"), -1),
    (("context", "goal"), "silently changed objective"),
    (("skills", 0, "runtime_readiness"), "ready"),
    (("project", "created_at"), "2026-10-30T05:00:00"),
    (("project", "revision"), True),
])
def test_invalid_boundaries_rejected(example, path, value):
    node = example
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    with pytest.raises(ValidationError):
        c.AcceptanceBundle.model_validate(example)


def test_duplicate_submission_is_not_a_new_turn(example):
    duplicate = copy.deepcopy(example["turns"][0])
    duplicate["id"] = "turn_second"
    example["turns"].append(duplicate)
    with pytest.raises(ValidationError, match="duplicate request key"):
        c.AcceptanceBundle.model_validate(example)


def test_unknown_model_limits_are_not_zero(example):
    model = c.ModelDescriptor.model_validate(example["turns"][0]["model"])
    assert model.context_limit_tokens is None
    bad = model.model_dump()
    bad.update(context_limit_tokens=100, output_limit_tokens=101)
    with pytest.raises(ValidationError, match="exceeds"):
        c.ModelDescriptor.model_validate(bad)


def test_stale_snapshot_rejected_after_digest_recomputed(example):
    snapshot = example["context"]
    snapshot["project_revision"] = 2
    snapshot["digest"] = c.canonical_digest({k:v for k,v in snapshot.items() if k != "digest"})
    with pytest.raises(ValidationError, match="stale project"):
        c.AcceptanceBundle.model_validate(example)


def test_unbound_runtime_cannot_report_running(example):
    example["turns"][0]["status"] = "running"
    with pytest.raises(ValidationError, match="native binding"):
        c.AcceptanceBundle.model_validate(example)


def test_two_running_turns_rejected(example):
    example["binding"].update(state="bound", native_session_id="synthetic_native_id")
    example["turns"][0].update(status="running", native_turn_id="native_turn_a")
    turn=copy.deepcopy(example["turns"][0])
    turn.update(id="turn_second", request_key="req_second", native_turn_id="native_turn_b")
    example["turns"].append(turn)
    with pytest.raises(ValidationError, match="one active"):
        c.AcceptanceBundle.model_validate(example)


def test_domain_event_cannot_be_authored_by_runtime(example):
    domain=dict(id="evt_synthetic",project_id=example["project"]["id"],seq=1,occurred_at="2026-10-30T05:00:00Z",
        producer="runtime_adapter",kind="workflow_state_changed",authority_ref=example["project"]["resources"][0],
        source_event_key="synthetic_key",observed_status="completed",correlation_turn_id=None)
    with pytest.raises(ValidationError): c.DomainEvent.model_validate(domain)


def test_usage_must_state_measurement_scope():
    with pytest.raises(ValidationError): c.RuntimePayload(kind="usage", input_tokens=25)
    payload=c.RuntimePayload(kind="usage", input_tokens=25, usage_scope="cumulative", usage_source="runtime")
    assert payload.context_tokens is None


def test_execution_intent_binds_revision(example):
    with pytest.raises(ValidationError, match="revision"):
        c.ExecutionIntent(id="intent_1",project_id=example["project"]["id"],conversation_id=example["conversation"]["id"],
            turn_id=example["turns"][0]["id"],target_ref=example["project"]["resources"][0],expected_revision="0"*64,
            operation="read",idempotency_key="once",arguments_digest="1"*64,status="proposed",run_ref=None)


def test_unregistered_authority_rejected(example):
    example["project"]["resources"] = []
    with pytest.raises(ValidationError, match="not bound"):
        c.AcceptanceBundle.model_validate(example)
