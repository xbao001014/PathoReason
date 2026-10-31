#!/usr/bin/env python3
"""Lint a reader-facing manuscript for leaked audit scaffolding and outsider voice."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path


RULES: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    (
        "internal_claim_marker",
        "Remove machine claim/evidence markers only after preserving their mapping in sidecars.",
        re.compile(r"\[(?:claim|evidence):[^\]]+\]", re.IGNORECASE),
    ),
    (
        "internal_workflow_banner",
        "Keep draft status, author requests, and workflow banners outside the reader-facing manuscript.",
        re.compile(
            r"internal evidence-grounded|not submission-ready|author verification is required|author input required",
            re.IGNORECASE,
        ),
    ),
    (
        "internal_pipeline_term",
        "Replace internal stage, registry, and audit-control terminology with scientific prose.",
        re.compile(
            r"\bM[0-7](?:\b|[-_])|claim registry|truth map|source manifest|"
            r"integrity audit|audit sidecar|hash-recorded|execution-time source snapshot",
            re.IGNORECASE,
        ),
    ),
    (
        "internal_test_taxonomy",
        "Rewrite the taxonomy token as a plain-language scientific disclosure; do not remove the limitation.",
        re.compile(r"\btest_(?:previously_viewed|selected)\b", re.IGNORECASE),
    ),
    (
        "file_centered_current_study",
        "Describe the study directly and keep file/package provenance in internal artifacts.",
        re.compile(
            r"\b(?:supplied|provided|displayed)\s+(?:data|results?|methods?|comparators?|baselines?|panel)\b|"
            r"\bavailable\s+(?:results?|baselines?|comparators?)\b|"
            r"\b(?:source|input)\s+files?\b|\bevidence package\b",
            re.IGNORECASE,
        ),
    ),
    (
        "outsider_reported_current_study",
        "Use an authorial construction such as 'we report' or name the current method/result directly.",
        re.compile(
            r"\b(?:the\s+)?reported\s+(?:method|performance|comparison|results?|best(?:\s+result)?|"
            r"AUC|AUROC|pattern)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "audit_narration",
        "State the scientific fact or limitation rather than narrating the internal audit process.",
        re.compile(
            r"\b(?:aggregate\s+)?dataset audit recorded\b|\bretained for (?:the )?audit\b|"
            r"\bfor audit purposes\b",
            re.IGNORECASE,
        ),
    ),
)

AUTHORIAL_SIGNAL = re.compile(
    r"\bwe\s+(?:characterized|conducted|developed|designed|evaluated|generated|implemented|"
    r"represented|trained|transformed|used|subtracted|compared|observed|found|report|show|could|did)|"
    r"\bour\s+(?:method|model|study|analysis|experiment|results?)\b",
    re.IGNORECASE,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manuscript", type=Path, help="Reader-facing Markdown manuscript")
    parser.add_argument("--output", type=Path, help="Write the JSON report to this path")
    parser.add_argument("--semantic-review", type=Path, help="Hash-bound whole-manuscript style assessment")
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def portable_path(path: Path) -> str:
    for parent in path.parents:
        if parent.name == "_manuscript_pipeline":
            return path.relative_to(parent).as_posix()
    return str(path)


def lint(text: str, manuscript: Path) -> dict[str, object]:
    issues: list[dict[str, object]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        for code, message, pattern in RULES:
            for match in pattern.finditer(line):
                issues.append(
                    {
                        "code": code,
                        "severity": "error",
                        "line": line_number,
                        "matched_text": match.group(0),
                        "message": message,
                    }
                )
    authorial_signals = len(AUTHORIAL_SIGNAL.findall(text))
    warnings = []
    patterns = {
        "blanket_disclaimer": r"(?:without claiming|refrain from claiming|no claim of|no superiority claim|不主张|不声称)[^.!?。\n]{0,120}",
        "global_self_dismissal": r"(?:no evidential weight|essentially no evidential|毫无价值|没有任何意义)",
        "audit_attestation": r"author-attested|作者自证",
    }
    for line_number, line in enumerate(text.splitlines(), 1):
        for code, pattern in patterns.items():
            for match in re.finditer(pattern, line, re.I):
                warnings.append({"code": code, "line": line_number, "matched_text": match.group(0),
                                 "severity": "review", "message": "Review in context; preserve any material scientific disclosure."})
    return {
        "schema": "reader-facing-voice-report/1.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "manuscript": {
            "path": portable_path(manuscript),
            "sha256": sha256(manuscript),
            "bytes": manuscript.stat().st_size,
        },
        "status": "passed" if not issues else "failed",
        "issue_count": len(issues),
        "authorial_signal_count": authorial_signals,
        "issues": issues,
        "style_policy_version": 2,
        "style_status": "needs_review",
        "style_warnings": warnings,
        "notes": [
            "This lint detects internal scaffolding and common outsider constructions; it does not prove scientific integrity or stylistic quality.",
            "Exploratory, post-hoc, test-exposure, uncertainty, and other material limitations must remain visible in clear scientific language.",
        ],
    }


def validate_semantic_review(review: object, report: dict, text: str) -> bool:
    """Validate assessment coverage and binding, not literary judgment."""
    if not isinstance(review, dict):
        return False
    required = {"contribution_focus", "proportional_limitations", "direct_results", "disclosure_preservation"}
    checks = review.get("checks")
    reviewer = review.get("reviewer")
    if (review.get("manuscript_sha256") != report["manuscript"]["sha256"]
            or review.get("status") != "passed"
            or not isinstance(reviewer, str) or not reviewer.strip()
            or not isinstance(checks, list) or len(checks) != len(required)):
        return False
    seen = set()
    for check in checks:
        if not isinstance(check, dict):
            return False
        identifier, evidence, reason = check.get("id"), check.get("evidence"), check.get("reason")
        if (not isinstance(identifier, str) or identifier not in required or identifier in seen
                or check.get("verdict") != "passed"
                or not isinstance(evidence, str) or not evidence.strip() or evidence not in text
                or not isinstance(reason, str) or not reason.strip()):
            return False
        seen.add(identifier)
    dispositions = review.get("warning_dispositions", [])
    return isinstance(dispositions, list) and all(
        any(isinstance(d, dict) and d.get("code") == w["code"] and d.get("line") == w["line"]
            and isinstance(d.get("reason"), str) and d["reason"].strip() for d in dispositions)
        for w in report["style_warnings"])


def main() -> int:
    args = parse_args()
    manuscript = args.manuscript.expanduser().resolve()
    if not manuscript.is_file():
        raise SystemExit(f"Manuscript does not exist: {manuscript}")
    report = lint(manuscript.read_text(encoding="utf-8"), manuscript)
    if args.semantic_review:
        review = json.loads(args.semantic_review.read_text(encoding="utf-8"))
        valid = validate_semantic_review(review, report, manuscript.read_text(encoding="utf-8"))
        report["semantic_review"] = review
        report["style_status"] = "passed" if valid else "needs_review"
        if not valid:
            report["status"] = "failed"
    encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        output = args.output.expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
