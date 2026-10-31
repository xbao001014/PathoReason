import hashlib
from pathlib import Path
import pytest
from pathoreason.legacy import read_verified_file, index_evidence


def test_read_and_index_do_not_mutate_source(tmp_path):
    source=tmp_path/"result.json"
    source.write_bytes(b'{"goal_achieved_dev": false}')
    before=source.stat(); digest=hashlib.sha256(source.read_bytes()).hexdigest()
    item=index_evidence(project_id="prj_1",artifact_id="art_1",title="Result",root=tmp_path,
        relative_path="result.json",expected_sha256=digest,media_type="application/json",kind="report",evidence_role="development")
    assert item.source_ref.revision==digest and item.verification_scope=="bytes_verified"
    assert source.stat().st_mtime_ns==before.st_mtime_ns
    assert hashlib.sha256(source.read_bytes()).hexdigest()==digest


def test_changed_source_cannot_reuse_old_revision(tmp_path):
    path=tmp_path/"result"; path.write_bytes(b"before")
    digest=hashlib.sha256(path.read_bytes()).hexdigest();path.write_bytes(b"after")
    with pytest.raises(ValueError,match="changed"):
        read_verified_file(tmp_path,"result",digest)


@pytest.mark.parametrize("relative",["../outside","/etc/passwd","a/../outside","./result","a//b","a\\b"])
def test_traversal_rejected(tmp_path,relative):
    with pytest.raises(ValueError):read_verified_file(tmp_path,relative,"0"*64)


def test_symlink_rejected_even_with_matching_hash(tmp_path):
    original=tmp_path/"original";original.write_bytes(b"original")
    (tmp_path/"link").symlink_to(original)
    with pytest.raises(ValueError,match="symlink"):
        read_verified_file(tmp_path,"link",hashlib.sha256(b"original").hexdigest())


def test_experiment_projection_keeps_legacy_identity_and_manifest(tmp_path):
    import json
    from pathoreason.legacy import observe_experiment
    identity="a"*32;folder=tmp_path/identity;folder.mkdir()
    state={"id":identity,"stage":"completed","updated_at":"2026-10-30T05:00:00Z","workflow_template":None}
    for name,data in [("state.json",state),("config.json",{}),("blueprint.json",{}),("workflow_template.json",{})]:
        (folder/name).write_text(json.dumps(data))
    before={p.name:p.read_bytes() for p in folder.iterdir()}
    result=observe_experiment(tmp_path,identity)
    assert result["ref"]["resource_id"]==identity
    assert result["ref"]["revision_kind"]=="manifest_sha256"
    assert result["projection"]["stage"]=="completed"
    assert before=={p.name:p.read_bytes() for p in folder.iterdir()}
    (folder/"config.json").write_text('{"revision":2}')
    assert observe_experiment(tmp_path,identity)["ref"]["revision"]!=result["ref"]["revision"]


def test_unsafe_frozen_instance_path_rejected(tmp_path):
    import json
    from pathoreason.legacy import observe_experiment
    identity="a"*32;folder=tmp_path/identity;folder.mkdir()
    state={"id":identity,"stage":"completed","updated_at":"2026-10-30T05:00:00Z",
           "workflow_template":{"instance_path":"../outside"}}
    for name,data in [("state.json",state),("config.json",{}),("blueprint.json",{}),("workflow_template.json",{})]:
        (folder/name).write_text(json.dumps(data))
    with pytest.raises(ValueError,match="invalid evidence path"):
        observe_experiment(tmp_path,identity)
