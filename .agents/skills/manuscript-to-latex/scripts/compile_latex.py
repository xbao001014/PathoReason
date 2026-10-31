#!/usr/bin/env python3
"""Compile a prepared package in a fresh directory and reject stale or unresolved output."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path


UNDEFINED_RE = re.compile(r"undefined (?:citations?|references?)|Citation [`'].*undefined|Reference [`'].*undefined", re.IGNORECASE)
RERUN_RE = re.compile(r"Rerun to get cross-references right|Label\(s\) may have changed", re.IGNORECASE)
OVERFULL_RE = re.compile(r"Overfull \\hbox")
UNDERFULL_RE = re.compile(r"Underfull \\hbox")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def resolve_main(package: Path, requested: str | None = None) -> str:
    if requested is not None:
        return requested
    return "manuscript.tex" if (package / "manuscript.tex").is_file() else "main.tex"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-dir", required=True, type=Path)
    parser.add_argument("--main", help="Entry file; defaults to manuscript.tex, or main.tex for legacy packages")
    args = parser.parse_args()

    package = args.package_dir.resolve()
    args.main = resolve_main(package, args.main)
    main_tex = package / args.main
    manifest_path = package / "submission_manifest.json"
    if not main_tex.is_file() or not manifest_path.is_file():
        raise SystemExit("package must contain the requested main file and submission_manifest.json")
    latexmk = shutil.which("latexmk")
    if not latexmk:
        raise SystemExit("latexmk was not found on PATH")

    stamp = dt.datetime.now().strftime("%Y%m%dT%H%M%S_%f")
    build_dir = package / "build" / stamp
    build_dir.mkdir(parents=True, exist_ok=False)
    start = time.time()
    command = [latexmk, "-pdf", "-interaction=nonstopmode", "-halt-on-error", "-file-line-error",
               f"-outdir={build_dir}", args.main]
    completed = subprocess.run(command, cwd=package, text=True, capture_output=True)
    (build_dir / "latexmk.stdout.txt").write_text(completed.stdout, encoding="utf-8", errors="replace")
    (build_dir / "latexmk.stderr.txt").write_text(completed.stderr, encoding="utf-8", errors="replace")

    pdf = build_dir / (main_tex.stem + ".pdf")
    log = build_dir / (main_tex.stem + ".log")
    log_text = log.read_text(encoding="utf-8", errors="replace") if log.is_file() else ""
    errors: list[str] = []
    warnings: list[str] = []
    if completed.returncode != 0:
        errors.append(f"latexmk exited with code {completed.returncode}")
    if not pdf.is_file() or pdf.stat().st_size == 0:
        errors.append("new nonempty PDF was not produced")
    elif pdf.stat().st_mtime + 2 < start:
        errors.append("PDF timestamp predates this build and may be stale")
    if UNDEFINED_RE.search(log_text):
        errors.append("undefined citation or reference reported in LaTeX log")
    if RERUN_RE.search(log_text):
        errors.append("cross-references did not converge")
    overfull = len(OVERFULL_RE.findall(log_text))
    underfull = len(UNDERFULL_RE.findall(log_text))
    if overfull:
        warnings.append(f"{overfull} overfull hbox warnings require visual disposition")
    if underfull:
        warnings.append(f"{underfull} underfull hbox warnings require visual disposition")

    report = {
        "schema": "manuscript-to-latex-build/1.0",
        "built_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "command": command,
        "return_code": completed.returncode,
        "status": "compiled_pending_visual_qa" if not errors else "failed",
        "pdf": {"path": str(pdf), "sha256": sha256(pdf), "bytes": pdf.stat().st_size} if pdf.is_file() else None,
        "log": str(log) if log.is_file() else None,
        "errors": errors,
        "warnings": warnings,
    }
    report_path = build_dir / "build_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["latest_build"] = {
        "report": str(report_path.relative_to(package)),
        "status": report["status"],
        "pdf": str(pdf.relative_to(package)) if pdf.is_file() else None,
    }
    if manifest.get("mode") == "submission" and not errors and not manifest.get("errors"):
        manifest["status"] = "compiled_pending_visual_qa"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"Build directory: {build_dir}")
    print(f"Status: {report['status']}")
    for item in errors:
        print(f"ERROR: {item}")
    for item in warnings:
        print(f"WARNING: {item}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
