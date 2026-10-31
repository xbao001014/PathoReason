"""Repeatable read-only compatibility and evidence verification for P0."""
import hashlib
import importlib.metadata
import json
import socket
import subprocess
import urllib.request
from pathlib import Path
from pathoreason.contracts import AcceptanceBundle
from pathoreason.legacy import read_verified_file, observe_experiment
from pathoreason.storage import data_root

repo=Path(__file__).resolve().parents[1]
out=data_root(repo/"config/pathoreason.local.json")/"acceptance/p0-20261030"
old=Path("/home/bxn/projects/auto-research")
base=json.loads((out/"baseline.json").read_text())
checks={}
checks["legacy_head_unchanged"]=subprocess.check_output(["git","-C",str(old),"rev-parse","HEAD"],text=True).strip()==base["old_head"]
checks["legacy_worktree_status_unchanged"]=subprocess.check_output(["git","-C",str(old),"status","--porcelain"],text=True)==base["old_status"]
checks["legacy_baseline_source_bytes_unchanged"]=all(hashlib.sha256((old/name).read_bytes()).hexdigest()==digest for name,digest in base["files"].items())
inventory=json.loads((out/"source-inventory.json").read_text())
checks["legacy_inventory_source_bytes_unchanged"]=all(hashlib.sha256((old/i["path"]).read_bytes()).hexdigest()==i["sha256"] for i in inventory)
bundle=AcceptanceBundle.model_validate_json((repo/"contracts/examples/cesc-reading.json").read_text())
for artifact in bundle.artifacts:
    raw=read_verified_file(Path("/data/bxn/auto-research/acceptance"),artifact.relative_path,artifact.sha256)
    checks[artifact.id+"_bytes_unchanged"]=len(raw)==artifact.size_bytes
observed=json.loads((out/"legacy-experiment-observation.json").read_text())
checks["legacy_experiment_manifest_unchanged"]=observe_experiment(Path("/data/bxn/auto-research/experiments"),observed["ref"]["resource_id"])==observed
ready=json.load(urllib.request.urlopen("http://127.0.0.1:8002/ready",timeout=5))
before=json.loads((out/"ready-before.json").read_text())
checks["old_service_same_instance_ready"]=ready["status"]=="ready" and ready["instance"]==before["instance"] and ready["pid"]==before["pid"]
checks["old_service_no_active_experiments_or_jobs"]=not ready["active_experiments"] and not ready["background_jobs"]
(out/"ready-after.json").write_text(json.dumps(ready,indent=2)+"\n")
for port in [8520,8521,8522]:
    try:
        with socket.socket() as sock:sock.bind(("127.0.0.1",port))
        checks[f"port_{port}_available"]=True
    except OSError:checks[f"port_{port}_available"]=False
references=json.loads((repo/"docs/references/provenance.json").read_text())["references"]
checks["reference_snapshots_unchanged"]=all(hashlib.sha256((repo/r["snapshot_path"]).read_bytes()).hexdigest()==r["sha256"] for r in references)
deps=[]
for dist in importlib.metadata.distributions():
    metadata=dist.metadata
    deps.append({"name":metadata["Name"],"version":dist.version,"license_expression":metadata.get("License-Expression"),
        "license":metadata.get("License"),"license_classifiers":[v for v in metadata.get_all("Classifier",[]) if v.startswith("License ::")]})
(out/"dependencies.json").write_text(json.dumps(deps,indent=2)+"\n")
report={"checks":checks,"all_passed":all(checks.values()),"contract_schemas":len(list((repo/"contracts/v1").glob("*.schema.json"))),
    "artifact_count":len(bundle.artifacts),"inference_calls":0,"training_jobs_started":0,"legacy_mutations_requested":0,
    "auth_readiness":"missing_server_codex_login","p1_started":False}
(out/"verification.json").write_text(json.dumps(report,indent=2)+"\n")
print(json.dumps(report,indent=2))
if not report["all_passed"]:raise SystemExit(1)
