#!/usr/bin/env python3
"""Create a non-destructive manuscript-pipeline scaffold and source inventory."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


STAGE_DIRS = (
    "00_intake",
    "01_planning",
    "02_literature",
    "03_manuscript",
    "04_integrity",
    "05_review_revision",
    "06_submission",
)

INVENTORY_EXTENSIONS = {
    ".md", ".txt", ".csv", ".tsv", ".json", ".bib", ".ris",
    ".docx", ".pdf", ".xlsx", ".xls", ".tex", ".yaml", ".yml",
    ".py", ".r", ".ipynb",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def classify(path: Path) -> str:
    name = path.name.lower()
    suffix = path.suffix.lower()
    if any(token in name for token in ("result", "comparison", "ablation", "metric", "evaluation", "prediction")):
        return "result_or_evaluation"
    if any(token in name for token in ("method", "methodology", "protocol", "config", "architecture")):
        return "methodology_or_protocol"
    if suffix in {".bib", ".ris"} or any(token in name for token in ("review", "literature", "reference", "citation")):
        return "literature_or_reference"
    if any(token in name for token in ("manuscript", "draft", "paper")):
        return "manuscript_or_plan"
    if any(token in name for token in ("template", "guideline", "checklist")):
        return "template_or_guidance"
    if suffix in {".py", ".r", ".ipynb", ".yaml", ".yml"}:
        return "code_or_configuration"
    return "other_source"


def safe_output(project: Path, output_name: str) -> Path:
    if not output_name or Path(output_name).is_absolute() or any(part == ".." for part in Path(output_name).parts):
        raise ValueError("output name must be a relative child path without '..'")
    output = (project / output_name).resolve()
    if output == project or project not in output.parents:
        raise ValueError("output directory must remain inside the project")
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", help="Existing project directory")
    parser.add_argument("--output-name", default="_manuscript_pipeline", help="Child directory for generated artifacts")
    parser.add_argument("--timestamp", help="Explicit UTC stamp YYYY-MM-DD_HHMMSSZ for reproducible tests")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project = Path(args.project).expanduser().resolve()
    if not project.is_dir():
        raise SystemExit(f"Project directory does not exist: {project}")

    output = safe_output(project, args.output_name)
    stamp = args.timestamp or datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%SZ")

    output.mkdir(exist_ok=True)
    for stage in STAGE_DIRS:
        (output / stage).mkdir(exist_ok=True)

    records = []
    for path in sorted(project.rglob("*")):
        if not path.is_file() or output in path.parents or ".git" in path.parts:
            continue
        if path.suffix.lower() not in INVENTORY_EXTENSIONS:
            continue
        stat = path.stat()
        records.append(
            {
                "relative_path": path.relative_to(project).as_posix(),
                "size_bytes": stat.st_size,
                "sha256": sha256(path),
                "modified_at_utc": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                "provisional_role": classify(path),
                "authority_status": "author_controlled_candidate",
            }
        )

    manifest = {
        "schema": "method-results-to-manuscript/source-manifest/1.0",
        "project_root": str(project),
        "generated_at_utc": stamp,
        "note": "Hashes identify bytes; roles and authority require author confirmation.",
        "sources": records,
    }
    manifest_path = output / "00_intake" / f"source_manifest_{stamp}.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    snapshot_lines = [
        "# Manuscript pipeline intake snapshot",
        "",
        f"- Project: `{project}`",
        f"- Generated at (UTC): `{stamp}`",
        f"- Inventoried files: `{len(records)}`",
        "- Authority status: provisional; author confirmation required",
        "- Test-use status: unclassified; inspect development history before drafting claims",
        "",
        "## Provisional source inventory",
        "",
        "| Path | Provisional role | Size (bytes) | SHA-256 |",
        "|---|---|---:|---|",
    ]
    for record in records:
        snapshot_lines.append(
            f"| `{record['relative_path']}` | {record['provisional_role']} | "
            f"{record['size_bytes']} | `{record['sha256']}` |"
        )
    snapshot_lines.extend(
        [
            "",
            "## Required author confirmations",
            "",
            "1. Which files are authoritative for methods and results?",
            "2. Has any test set or external set been inspected during development?",
            "3. What is the intended scientific claim and manuscript language?",
            "4. Which cohort, label, ethics, implementation, and journal facts remain outside the files?",
            "",
        ]
    )
    snapshot_path = output / "00_intake" / f"intake_snapshot_{stamp}.md"
    snapshot_path.write_text("\n".join(snapshot_lines), encoding="utf-8")

    state_path = output / "pipeline_state.json"
    if not state_path.exists():
        state = {
            "schema": "method-results-to-manuscript/pipeline-state/1.0",
            "project_root": str(project),
            "current_stage": "M0_intake",
            "status": "awaiting_author_confirmation",
            "source_manifest": str(manifest_path),
            "test_use_status": "unclassified",
            "completed_stages": [],
            "blocking_items": [
                "authoritative source roles not confirmed",
                "test-use history not classified",
            ],
        }
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(manifest_path)
    print(snapshot_path)
    print(state_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
