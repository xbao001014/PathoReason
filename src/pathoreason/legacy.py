"""Read-only allowlisted evidence mapping; no legacy store imports or saves."""
from pathlib import Path
import hashlib

from .contracts import ArtifactIndex, LegacyResourceRef


def _checked_path(root: Path, relative_path: str) -> Path:
    parts = relative_path.split("/")
    if Path(relative_path).is_absolute() or any(p in {"..", ".", ""} for p in parts) or "\\" in relative_path:
        raise ValueError("invalid evidence path")
    path = root
    for component in (*root.parents, root):
        if component.is_symlink():
            raise ValueError("symlink in evidence root")
    for part in parts:
        path = path / part
        if path.is_symlink():
            raise ValueError("symlink in evidence path")
    if not path.is_file():
        raise ValueError("evidence file missing")
    return path


def read_verified_file(root: Path, relative_path: str, expected_sha256: str) -> bytes:
    import os, stat
    _checked_path(root, relative_path)
    # Open every directory relative to a verified descriptor; never follow a replaced symlink.
    directory = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in (*root.parts[1:], *relative_path.split("/")[:-1]):
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory); directory = child
        fd = os.open(relative_path.split("/")[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        with os.fdopen(fd, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError("evidence must be a regular file")
            data = stream.read()
    except OSError as exc:
        raise ValueError("evidence path changed or contains symlink") from exc
    finally:
        os.close(directory)
    if hashlib.sha256(data).hexdigest() != expected_sha256:
        raise ValueError("evidence changed; create a new reference revision")
    return data


def index_evidence(*, project_id: str, artifact_id: str, title: str, root: Path,
                   relative_path: str, expected_sha256: str, media_type: str,
                   kind: str, evidence_role: str) -> ArtifactIndex:
    data = read_verified_file(root, relative_path, expected_sha256)
    ref = LegacyResourceRef(adapter="auto_research.evidence_file", resource_id=relative_path,
                            revision=expected_sha256, revision_kind="file_sha256")
    return ArtifactIndex(id=artifact_id, project_id=project_id, title=title, kind=kind,
                         media_type=media_type, storage_root="legacy_evidence",
                         relative_path=relative_path, sha256=expected_sha256, size_bytes=len(data),
                         source_ref=ref, run_ref=None, stage_ref=None,
                         verification_scope="bytes_verified", evidence_role=evidence_role)


def observe_experiment(root: Path, experiment_id: str) -> dict:
    """Manifest revision covers observed files, distinct from the frozen workflow hash."""
    import json
    import re
    from .contracts import canonical_digest
    if not re.fullmatch(r"[0-9a-f]{32}", experiment_id):
        raise ValueError("invalid legacy experiment identity")
    folder = root / experiment_id
    names = ["state.json", "config.json", "blueprint.json", "workflow_template.json"]
    parsed, manifest = {}, {}
    for name in names:
        path = _checked_path(root, f"{experiment_id}/{name}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        raw = read_verified_file(root, f"{experiment_id}/{name}", digest)
        parsed[name], manifest[name] = json.loads(raw), digest
    state = parsed["state.json"]
    if state["id"] != experiment_id:
        raise ValueError("legacy state ID mismatch")
    frozen = state.get("workflow_template")
    if frozen and frozen.get("instance_path"):
        name = frozen["instance_path"]
        digest = hashlib.sha256(_checked_path(root, f"{experiment_id}/{name}").read_bytes()).hexdigest()
        read_verified_file(root, f"{experiment_id}/{name}", digest)
        manifest[name] = digest
    # Re-read the complete observation to detect a change during collection.
    for name, digest in manifest.items():
        read_verified_file(root, f"{experiment_id}/{name}", digest)
    ref = LegacyResourceRef(adapter="auto_research.experiment", resource_id=experiment_id,
                            revision=canonical_digest(manifest), revision_kind="manifest_sha256")
    return {"ref": ref.model_dump(mode="json"), "files": manifest,
            "projection": {"stage": state["stage"], "updated_at": state["updated_at"],
                           "workflow_template": frozen, "source_fields_preserved": True},
            "scope": "read-only observation; not approval or frozen-digest revalidation"}
