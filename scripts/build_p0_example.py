"""Observe explicitly selected CESC evidence; write only new PathoReason fixtures."""
import hashlib
import json
from pathlib import Path
from pathoreason.contracts import *
from pathoreason.legacy import index_evidence, observe_experiment
from pathoreason.storage import data_root

repo = Path(__file__).resolve().parents[1]
output = data_root(repo / "config/pathoreason.local.json") / "acceptance/p0-20261030"
legacy = Path("/data/bxn/auto-research/acceptance")
project_id = "prj_cesc_reading"
items = [
    ("art_conclusions", "CESC development conclusions", "cesc_shared_context_replication_20261028_analysis/CONCLUSIONS.json", "report", "application/json", "development"),
    ("art_pipeline", "Manuscript review status", "cesc_manuscript_delivery_20261029/53a69e70219c4a1ca00a43e6fda8752a/_manuscript_pipeline/pipeline_index.json", "report", "application/json", "manuscript_review"),
    ("art_pdf", "CESC manuscript review copy", "cesc_manuscript_delivery_20261029/DELIVERABLES/CESC_manuscript.pdf", "document", "application/pdf", "manuscript_review"),
]
artifacts=[]
for artifact_id,title,path,kind,media,role in items:
    digest=hashlib.sha256((legacy/path).read_bytes()).hexdigest()
    artifacts.append(index_evidence(project_id=project_id, artifact_id=artifact_id,title=title,root=legacy,
        relative_path=path,expected_sha256=digest,media_type=media,kind=kind,evidence_role=role))
observation=observe_experiment(Path("/data/bxn/auto-research/experiments"), "11e2e1f03fe84ca38bf34b6315c8e3da")
(output/"legacy-experiment-observation.json").write_text(json.dumps(observation,ensure_ascii=False,indent=2)+"\n")
resources=[a.source_ref for a in artifacts]+[LegacyResourceRef.model_validate(observation["ref"])]
now="2026-10-30T05:00:00Z"  # fixed fixture time; never presented as an actual conversation
base={"schema_version":"pathoreason/1"}
common={**base,"project_id":project_id,"conversation_id":"conv_p0_fixture"}
project=ResearchProject(id=project_id,title="CESC 成果解读",objective="解释已有开发证据并定位论文审阅稿",revision=1,created_at=now,status="active",resources=resources)
skills=[]
for key,title,capability in [
    ("results_explanation","结果解读与研究汇报","research_reporting"),
    ("dataset_intake","数据接入与任务定义","dataset_intake"),
    ("mil_baseline","病理 MIL 基线研究","auto_mil"),
    ("mechanism_study","机制假设与消融研究","performance_loop"),
    ("manuscript","研究成果转论文","manuscript_pipeline"),
    ("figures_typesetting","图件与论文排版","manuscript_assets"),
    ("repair_recovery","实验排障与恢复","workbench"),
]:
    raw={**base,"id":key,"version":"0.1.0","title":title,"description":"既有能力的产品目录；PathoReason 运行时适配尚未接入。",
        "input_schema_ref":"urn:pathoreason:contracts:v1:ArtifactIndex","output_schema_ref":"urn:pathoreason:contracts:v1:MessagePart",
        "instruction_refs":[],"capability_refs":["auto_research:"+capability],"workflow_template_refs":[],
        "runtime_support":["codex","opencode"],"required_inputs":["project resource bindings"],"required_tools":["legacy evidence reader"],
        "implementation_status":"adapter_pending","evidence_scope":"contract_only","runtime_readiness":"unavailable",
        "unavailable_reason":"PathoReason runtime adapter pending; server Codex authentication missing"}
    skills.append(SkillDefinition(**raw,digest=canonical_digest(raw)))
binding=RuntimeBinding(**common,id="bind_p0_fixture",runtime="codex",runtime_version="0.164.0",native_session_id=None,state="unbound",storage_namespace=project_id,workspace_id=project_id,auth_ref="server_codex_login",created_at=now)
conversation=Conversation(**base,id=common["conversation_id"],project_id=project_id,title="P0 offline contract example",status="open",active_runtime_binding_id=binding.id,created_at=now)
model=ModelDescriptor(runtime="codex",provider="openai",model="gpt-6.1-sol",context_limit_tokens=None,input_limit_tokens=None,output_limit_tokens=None,tool_support="unknown",usage_source="unknown",metadata_source="p0 runtime model/list; inference not verified",availability="catalog_only")
turn=Turn(**common,id="turn_p0_fixture",runtime_binding_id=binding.id,request_key="req_p0_fixture",status="queued",model=model,config_digest=canonical_digest({"reasoning_effort":"low","tools":"evidence_read_only"}),created_at=now,finished_at=None,native_turn_id=None,error_code=None)
raw={**base,"id":"ctx_p0_fixture","project_id":project_id,"project_revision":1,"goal":project.objective,
    "constraints":["不新增训练或访问封存","开发准入、研究目标和作者审阅分别呈现"],"source_refs":[r.model_dump(mode="json") for r in resources],
    "decision_refs":[],"active_run_refs":[],"artifact_ids":[a.id for a in artifacts],"pending_items":["P1 认证与真实会话适配"],"created_at":now}
# Normalize timestamps before digesting, exactly as model JSON serialization does.
from pydantic import TypeAdapter, AwareDatetime
raw["created_at"]=TypeAdapter(AwareDatetime).dump_python(TypeAdapter(AwareDatetime).validate_python(now),mode="json")
context=ContextSnapshot(**raw,digest=canonical_digest(raw))
bundle=AcceptanceBundle(project=project,skills=skills,conversation=conversation,binding=binding,turns=[turn],
    invocations=[SkillInvocation(**common,id="inv_p0_fixture",turn_id=turn.id,skill_id=skills[0].id,skill_version=skills[0].version,skill_digest=skills[0].digest,input_artifact_ids=[a.id for a in artifacts])],
    messages=[MessagePart(**common,id="msg_p0_fixture",turn_id=turn.id,ordinal=0,role="user",kind="text",text="解释已有 CESC 结果，并定位论文审阅稿。",artifact_id=None)],
    context=context,artifacts=artifacts,runtime_events=[],domain_events=[],intents=[])
example=repo/"contracts/examples/cesc-reading.json";example.parent.mkdir(parents=True,exist_ok=True);example.write_text(bundle.model_dump_json(indent=2)+"\n")
(repo/"contracts/examples/skill-catalog.json").write_text(json.dumps([s.model_dump(mode="json") for s in skills],ensure_ascii=False,indent=2)+"\n")
(output/"source-artifacts.json").write_text(json.dumps([a.model_dump(mode="json") for a in artifacts],ensure_ascii=False,indent=2)+"\n")
print("Validated CESC contract fixture;",len(artifacts),"real artifacts indexed; no model turns dispatched")
