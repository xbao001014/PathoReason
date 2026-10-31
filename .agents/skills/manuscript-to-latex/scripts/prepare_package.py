#!/usr/bin/env python3
"""Create a provenance-tracked LaTeX package from a frozen Markdown manuscript."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
PROFILE_DIR = SKILL_DIR / "assets" / "journal_profiles"
TEMPLATE = SKILL_DIR / "assets" / "templates" / "manuscript.tex.tpl"
MARKER_RE = re.compile(r"\s*\[(?:claim|evidence):[^\]\r\n]+\]", re.IGNORECASE)
PLACEHOLDER_RE = re.compile(r"\b(?:TODO|TBD|AUTHOR INPUT REQUIRED)\b|\[INSERT[^\]]*\]", re.IGNORECASE)
CITATION_RE = re.compile(r"(?<!\w)@([A-Za-z0-9_:.+\-/]+)")
BIB_KEY_RE = re.compile(r"@\w+\s*\{\s*([^,\s]+)\s*,", re.IGNORECASE)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def latex_escape(value: str) -> str:
    scientific = {
        "δₙ": r"\ensuremath{\delta_n}",
        "Cₙ": r"\ensuremath{C_n}",
        "p̂ₙ": r"\ensuremath{\hat{p}_n}",
        "×": r"\ensuremath{\times}",
        "≤": r"\ensuremath{\leq}",
        "≥": r"\ensuremath{\geq}",
    }
    protected: dict[str, str] = {}
    for index, (source, replacement) in enumerate(scientific.items()):
        token = f"\ue000{index}\ue001"
        value = value.replace(source, token)
        protected[token] = replacement
    table = {
        "\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$",
        "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}",
        "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
    }
    escaped = "".join(table.get(ch, ch) for ch in value)
    for token, replacement in protected.items():
        escaped = escaped.replace(token, replacement)
    return escaped


def normalize_latex_unicode(value: str) -> tuple[str, list[str]]:
    """Replace Unicode symbols that pdfLaTeX does not handle reliably."""
    replacements = {
        "−": r"\ensuremath{-}",
        "±": r"\ensuremath{\pm}",
        "Δ": r"\ensuremath{\Delta}",
        "λ": r"\ensuremath{\lambda}",
        "τ": r"\ensuremath{\tau}",
    }
    transformations: list[str] = []
    for source, replacement in replacements.items():
        count = value.count(source)
        if count:
            value = value.replace(source, replacement)
            transformations.append(
                f"normalized_{count}_unicode_u{ord(source):04x}_characters_for_pdflatex"
            )
    return value, transformations


def word_count(text: str) -> int:
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    text = re.sub(r"\$.*?\$|\\\[.*?\\\]", " ", text, flags=re.DOTALL)
    text = re.sub(r"\[[^\]]+\]\([^\)]+\)", " ", text)
    return len(re.findall(r"\b[\w][\w'’-]*\b", text, flags=re.UNICODE))


def section(text: str, heading: str) -> tuple[str, str]:
    match = re.search(rf"^##\s+{re.escape(heading)}(?:\s+\{{[^}}]+\}})?\s*$", text, flags=re.IGNORECASE | re.MULTILINE)
    if not match:
        return "", text
    next_heading = re.search(r"^##\s+", text[match.end():], flags=re.MULTILINE)
    end = match.end() + (next_heading.start() if next_heading else len(text[match.end():]))
    return text[match.end():end].strip(), text[:match.start()] + text[end:]


def clean_source(raw: str) -> tuple[str, list[str], str]:
    transformations: list[str] = []
    lines = raw.splitlines()
    title = "Untitled manuscript"
    title_index = next(
        (index for index, line in enumerate(lines) if re.match(r"^#\s+", line)),
        None,
    )
    if title_index is not None:
        title = re.sub(r"^#\s+", "", lines.pop(title_index)).strip()
        transformations.append("moved_level_1_title_to_latex_title")
    kept: list[str] = []
    skip_banner = False
    for line in lines:
        if "INTERNAL SCIENTIFIC DRAFT" in line or "Pandoc-style citation keys and claim/evidence" in line:
            skip_banner = True
            transformations.append("removed_internal_draft_banner")
            continue
        if skip_banner and line.strip() == ">":
            continue
        skip_banner = False
        kept.append(line)
    cleaned = "\n".join(kept).strip() + "\n"
    marker_count = len(MARKER_RE.findall(cleaned))
    if marker_count:
        cleaned = MARKER_RE.sub("", cleaned)
        transformations.append(f"removed_{marker_count}_claim_evidence_markers")
    display_math_count = len(re.findall(r"\\\[.*?\\\]", cleaned, flags=re.DOTALL))
    inline_math_count = len(re.findall(r"\\\(.*?\\\)", cleaned, flags=re.DOTALL))
    if display_math_count:
        cleaned = re.sub(r"\\\[(.*?)\\\]", lambda match: "\n$$\n" + match.group(1).strip() + "\n$$\n", cleaned, flags=re.DOTALL)
        transformations.append(f"normalized_{display_math_count}_display_math_delimiters")
    if inline_math_count:
        cleaned = re.sub(r"\\\((.*?)\\\)", lambda match: "$" + match.group(1).strip() + "$", cleaned, flags=re.DOTALL)
        transformations.append(f"normalized_{inline_math_count}_inline_math_delimiters")
    numbered_headings = len(re.findall(r"^#{2,6}\s+\d+(?:\.\d+)*\.?\s+", cleaned, flags=re.MULTILINE))
    if numbered_headings:
        cleaned = re.sub(r"^(#{2,6}\s+)\d+(?:\.\d+)*\.?\s+", r"\1", cleaned, flags=re.MULTILINE)
        transformations.append(f"removed_manual_numbering_from_{numbered_headings}_headings")
    cleaned, horizontal_rule_count = re.subn(
        r"^[ \t]{0,3}(?:(?:-[ \t]*){3,}|(?:\*[ \t]*){3,}|(?:_[ \t]*){3,})[ \t]*\n"
        r"(?=(?:[ \t]*\n)*#{2,6}[ \t]+)",
        "",
        cleaned,
        flags=re.MULTILINE,
    )
    if horizontal_rule_count:
        transformations.append(
            f"removed_{horizontal_rule_count}_decorative_horizontal_rules_before_headings"
        )
    cleaned, abstract_heading_count = re.subn(
        r"^##\s+Abstract\s*$", "## Abstract {.unnumbered}", cleaned,
        count=1, flags=re.IGNORECASE | re.MULTILINE,
    )
    if abstract_heading_count:
        transformations.append("marked_abstract_heading_unnumbered")
    abstract_subheading_count = 0

    def mark_abstract_subheadings(match: re.Match[str]) -> str:
        nonlocal abstract_subheading_count

        def mark_heading(heading_match: re.Match[str]) -> str:
            nonlocal abstract_subheading_count
            heading = heading_match.group(1).rstrip()
            attributes = (heading_match.group(2) or "").strip()
            if ".unnumbered" not in attributes.split():
                attributes = f"{attributes} .unnumbered".strip()
                abstract_subheading_count += 1
            return f"{heading} {{{attributes}}}"

        abstract_body = re.sub(
            r"^(#{3,6}\s+.*?)(?:\s+\{([^}\n]*)\})?\s*$",
            mark_heading,
            match.group(2),
            flags=re.MULTILINE,
        )
        return match.group(1) + abstract_body

    cleaned = re.sub(
        r"(^##\s+Abstract(?:\s+\{[^}\n]+\})?\s*$\n?)(.*?)(?=^##\s+|\Z)",
        mark_abstract_subheadings,
        cleaned,
        count=1,
        flags=re.IGNORECASE | re.MULTILINE | re.DOTALL,
    )
    if abstract_subheading_count:
        transformations.append(
            f"marked_{abstract_subheading_count}_abstract_subheadings_unnumbered"
        )
    return cleaned, list(dict.fromkeys(transformations)), title


def flatten_abstract_for_unstructured_profile(text: str) -> tuple[str, int]:
    """Merge a structured Markdown abstract into one paragraph, preserving keywords."""
    abstract_pattern = re.compile(
        r"(^##\s+Abstract(?:\s+\{[^}\n]+\})?\s*$\n?)(.*?)(?=^##\s+|\Z)",
        flags=re.IGNORECASE | re.MULTILINE | re.DOTALL,
    )
    match = abstract_pattern.search(text)
    if not match:
        return text, 0

    body_lines = match.group(2).splitlines()
    content_lines: list[str] = []
    keyword_lines: list[str] = []
    removed_subheadings = 0
    for line in body_lines:
        stripped = line.strip()
        if re.match(r"^#{3,6}\s+", stripped):
            removed_subheadings += 1
            continue
        if re.match(r"^\*\*Keywords:\*\*", stripped, flags=re.IGNORECASE):
            keyword_lines.append(stripped)
            continue
        if stripped:
            content_lines.append(stripped)

    if not removed_subheadings:
        return text, 0

    merged_body = " ".join(content_lines)
    replacement_parts = [match.group(1).rstrip(), "", merged_body]
    if keyword_lines:
        replacement_parts.extend(["", " ".join(keyword_lines)])
    replacement = "\n".join(replacement_parts).rstrip() + "\n\n"
    flattened = text[:match.start()] + replacement + text[match.end():]
    return flattened, removed_subheadings


def format_longtables(tex: str) -> tuple[str, list[str]]:
    transformations: list[str] = []
    pattern = re.compile(
        r"(?P<title>(?:\\hypertarget\{[^\n]*\}\{%\n\\subsection\{.*?\}\\label\{[^\n]*\}\}\s*|"
        r"\\textbf\{Table[^\n]*\}\s*[^\n]*\n*))?"
        r"(?P<table>\\begin\{longtable\}.*?\\end\{longtable\})"
        r"(?P<note>\s*\\emph\{Note\.\}[^\n]*)?",
        re.DOTALL,
    )

    def replace(match: re.Match[str]) -> str:
        title = match.group("title") or ""
        block = match.group("table")
        note = (match.group("note") or "").strip()
        # Pandoc emits wrapped header cells terminated by ``\tabularnewline``;
        # count separators through ``\midrule`` rather than looking for a
        # literal ``\\`` row terminator.
        header = re.search(r"\\toprule\s*(.*?)\\midrule", block, flags=re.DOTALL)
        columns = header.group(1).count("&") + 1 if header else 1
        if columns >= 7:
            block = re.sub(
                r"(?<![\d.])(\d+\.\d+)\s*±\s*(\d+\.\d+)(?![\d.])",
                r"\1~±~\2",
                block,
            )
            # Long model identifiers commonly contain escaped underscores.  A
            # normal ``\_`` is unbreakable in narrow table cells, so expose a
            # legal line-break point without changing the rendered identifier.
            block = block.replace(r"\_", r"\_\allowbreak{}")
            transformations.append(f"breakable_identifiers_{columns}_column_longtable")
        if columns >= 9:
            block = block.replace(r"\real{0.09}", r"\real{0.12}", 1)
            transformations.append(f"adaptive_scaled_{columns}_column_longtable")
            transformations.append(f"nonbreaking_estimates_{columns}_column_longtable")
            return ("\\clearpage\n\\begin{landscape}\n\\begingroup\n\\footnotesize\n" +
                    title +
                    "\\fontsize{7pt}{8pt}\\selectfont\n"
                    "\\setlength{\\columnwidth}{\\linewidth}\n"
                    "\\setlength{\\tabcolsep}{2pt}\n"
                    "\\renewcommand{\\arraystretch}{1.12}\n" +
                    block +
                    ("\n\\footnotesize\n" + note if note else "") +
                    "\n\\endgroup\n\\end{landscape}\n\\clearpage")
        if columns >= 7:
            transformations.append(f"landscape_wrapped_{columns}_column_longtable")
            return ("\\clearpage\n\\begin{landscape}\n\\begingroup\n\\footnotesize\n"
                    "\\setlength{\\columnwidth}{\\linewidth}\n\\setlength{\\tabcolsep}{4pt}\n" +
                    title + block + ("\n" + note if note else "") +
                    "\n\\endgroup\n\\end{landscape}\n\\clearpage")
        size = "\\footnotesize" if columns >= 5 else "\\small"
        transformations.append(f"compact_wrapped_{columns}_column_longtable")
        return (title + "\\begingroup\n" + size + "\n\\setlength{\\tabcolsep}{4pt}\n" +
                block + "\n\\endgroup" + ("\n" + note if note else ""))

    return pattern.sub(replace, tex), transformations


def remove_resolved_production_stubs(
    text: str, *, figures_integrated: bool
) -> tuple[str, list[str]]:
    """Remove internal-only stub sections superseded by production artifacts."""
    transformations: list[str] = []
    if figures_integrated:
        text, count = re.subn(
            r"^##\s+Figure legends\s*$\n\s*"
            r"See the versioned `figure_legends\.md`.*?production-stage visual review\.\s*"
            r"(?=^##\s+|\Z)",
            "",
            text,
            count=1,
            flags=re.IGNORECASE | re.MULTILINE | re.DOTALL,
        )
        if count:
            transformations.append("removed_resolved_internal_figure_legend_stub")
    text, count = re.subn(
        r"^##\s+References\s*$\n\s*"
        r"Citation metadata are maintained in .*?final frozen bibliography\.\s*"
        r"(?=^##\s+|\Z)",
        "",
        text,
        count=1,
        flags=re.IGNORECASE | re.MULTILINE | re.DOTALL,
    )
    if count:
        transformations.append("removed_internal_reference_provenance_stub")
    return text, transformations


def load_json(path: Path | None) -> dict:
    if path is None:
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def integrate_figure_manifests(
    cleaned: str,
    manifest_paths: list[Path],
    output: Path,
    transformations: list[str],
    errors: list[str],
) -> tuple[str, list[dict]]:
    records: list[dict] = []
    seen_ids: set[str] = set()
    seen_stems: set[str] = set()
    for manifest_arg in manifest_paths:
        manifest_path = manifest_arg.resolve()
        if not manifest_path.is_file():
            errors.append(f"figure manifest not found: {manifest_path}")
            continue
        try:
            manifest = load_json(manifest_path)
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"figure manifest could not be read: {manifest_path}: {exc}")
            continue
        if manifest.get("schema") not in {
            "methodology-figure/1.0",
            "methodology-figure/1.1",
            "illustrated-methodology-figure/2.0",
            "raster-methodology-figure/1.0",
        }:
            errors.append(f"unsupported figure manifest schema: {manifest_path}")
            continue
        figure_id = str(manifest.get("figure_id", ""))
        stem = str(manifest.get("filename_stem", ""))
        caption = str(manifest.get("caption", "")).strip()
        callout = str(manifest.get("callout", "")).strip()
        orientation = str(manifest.get("orientation", "portrait"))
        before_heading = str(manifest.get("insertion", {}).get("before_heading", "")).strip()
        if (not figure_id.startswith("fig:") or not stem or not caption or not callout
                or f"\\ref{{{figure_id}}}" not in callout or not before_heading
                or orientation not in {"portrait", "landscape"}):
            errors.append(f"figure manifest lacks required insertion fields: {manifest_path}")
            continue
        if figure_id in seen_ids or stem in seen_stems:
            errors.append(f"duplicate figure id or filename stem: {figure_id} / {stem}")
            continue
        seen_ids.add(figure_id)
        seen_stems.add(stem)
        manifest_dir = manifest_path.parent
        asset_dir = output / "figures" / stem
        source_dir = output / "figure_sources" / stem
        asset_dir.mkdir(parents=True, exist_ok=True)
        source_dir.mkdir(parents=True, exist_ok=True)
        copied: dict[str, dict] = {}

        def verified_source(item: dict, label: str) -> Path | None:
            relative = item.get("path") if isinstance(item, dict) else None
            expected = item.get("sha256") if isinstance(item, dict) else None
            if not isinstance(relative, str) or not isinstance(expected, str):
                errors.append(f"figure manifest {label} entry is incomplete: {manifest_path}")
                return None
            candidate = (manifest_dir / relative).resolve()
            try:
                candidate.relative_to(manifest_dir)
            except ValueError:
                errors.append(f"figure manifest {label} escapes its asset directory: {candidate}")
                return None
            if not candidate.is_file():
                errors.append(f"figure manifest {label} asset not found: {candidate}")
                return None
            actual = sha256(candidate)
            if actual.lower() != expected.lower():
                errors.append(f"figure manifest {label} hash mismatch: {candidate}")
                return None
            return candidate

        pdf_item = manifest.get("exports", {}).get("pdf", {})
        pdf_source = verified_source(pdf_item, "PDF")
        if pdf_source is None:
            continue
        for fmt, item in manifest.get("exports", {}).items():
            source = verified_source(item, str(fmt).upper())
            if source is not None:
                destination = asset_dir / source.name
                shutil.copy2(source, destination)
                copied[f"figures/{stem}/{destination.name}"] = {"sha256": sha256(destination), "bytes": destination.stat().st_size}
        source_items: list[tuple[str, dict]] = []
        editable_sources = manifest.get("editable_sources")
        if isinstance(editable_sources, list) and editable_sources:
            for item in editable_sources:
                if isinstance(item, dict):
                    source_items.append((f"editable {item.get('kind', 'source')}", item))
        else:
            source_items.append(("DOT", manifest.get("editable_source", {})))
        for item in manifest.get("input_snapshots", []):
            if isinstance(item, dict):
                source_items.append((f"input snapshot {item.get('kind', '')}", item))
        stage1_reference = manifest.get("autofigure_style_workflow", {}).get("stage1_reference", {})
        if isinstance(stage1_reference, dict) and stage1_reference:
            source_items.append(("Stage-1 visual reference", stage1_reference))
        stage1_record = manifest.get("autofigure_style_workflow", {}).get(
            "stage1_generation_record", {}
        )
        if isinstance(stage1_record, dict) and stage1_record:
            source_items.append(("Stage-1 generation record", stage1_record))
        entity_decomposition = manifest.get("autofigure_style_workflow", {}).get(
            "entity_decomposition", {}
        )
        if isinstance(entity_decomposition, dict) and entity_decomposition:
            source_items.append(("entity decomposition", entity_decomposition))
        source_items.extend([
            ("specification", manifest.get("specification", {})),
            ("generation prompt", manifest.get("generation_prompt", {})),
            ("author approval", manifest.get("author_approval", {})),
            ("caption", manifest.get("caption_file", {})),
            ("alt text", manifest.get("alt_text_file", {})),
            ("evidence map", manifest.get("evidence_map", {})),
            ("design brief", manifest.get("design_brief", {})),
            ("machine QA", manifest.get("machine_qa", {})),
            ("human visual review", manifest.get("human_visual_review", {})),
        ])
        copied_source_names: set[str] = set()
        for label, item in source_items:
            if not item:
                continue
            source = verified_source(item, label)
            if source is not None:
                if source.name in copied_source_names:
                    continue
                copied_source_names.add(source.name)
                destination = source_dir / source.name
                shutil.copy2(source, destination)
                copied[f"figure_sources/{stem}/{destination.name}"] = {"sha256": sha256(destination), "bytes": destination.stat().st_size}
        copied_manifest = source_dir / "asset_manifest.json"
        shutil.copy2(manifest_path, copied_manifest)
        copied[f"figure_sources/{stem}/asset_manifest.json"] = {"sha256": sha256(copied_manifest), "bytes": copied_manifest.stat().st_size}
        normalized_heading = (
            before_heading
            if re.match(r"^#{2,6}\s+", before_heading)
            else f"## {before_heading}"
        )
        heading_pattern = re.compile(
            rf"^(?P<heading>{re.escape(normalized_heading)}(?:\s+\{{[^}}]+\}})?\s*)$",
            flags=re.IGNORECASE | re.MULTILINE,
        )
        heading_match = heading_pattern.search(cleaned)
        if not heading_match:
            errors.append(f"figure insertion heading not found after source cleaning: {before_heading}")
            continue
        caption_md = caption.replace("\n", " ").replace("]", "\\]")
        relative_pdf = f"figures/{stem}/{pdf_source.name}"
        if orientation == "landscape":
            figure_block = (
                f"{callout}\n\n\\clearpage\n\\begin{{landscape}}\n\\begin{{figure}}[p]\n\\centering\n"
                f"\\includegraphics[width=0.96\\linewidth,height=0.72\\textheight,keepaspectratio]{{{relative_pdf}}}\n"
                f"\\caption{{{latex_escape(caption)}}}\n\\label{{{figure_id}}}\n"
                "\\end{figure}\n\\end{landscape}\n\\clearpage\n\n"
            )
        else:
            figure_block = (
                f"{callout}\n\n\\begin{{figure}}[p]\n\\centering\n"
                f"\\includegraphics[width=0.90\\linewidth,height=0.74\\textheight,keepaspectratio]{{{relative_pdf}}}\n"
                f"\\caption{{{latex_escape(caption)}}}\n\\label{{{figure_id}}}\n"
                "\\end{figure}\n\n"
            )
        cleaned = cleaned[:heading_match.start()] + figure_block + cleaned[heading_match.start():]
        transformations.append(f"inserted_provenance_tracked_methodology_figure_{figure_id}")
        records.append({
            "manifest": {"path": str(manifest_path), "sha256": sha256(manifest_path)},
            "figure_id": figure_id,
            "filename_stem": stem,
            "orientation": orientation,
            "schema": manifest.get("schema"),
            "source_files": manifest.get("source_files", []),
            "machine_qa": manifest.get("machine_qa", {}),
            "human_visual_review": manifest.get("human_visual_review", {}),
            "copied_assets": copied,
        })
    return cleaned, records


def nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip()) and not PLACEHOLDER_RE.search(value)


def metadata_errors(metadata: dict, profile: dict) -> list[str]:
    errors: list[str] = []
    authors = metadata.get("authors")
    affiliations = metadata.get("affiliations")
    corr = metadata.get("corresponding_author", {})
    declarations = metadata.get("declarations", {})
    verification = metadata.get("journal_verification", {})
    if not isinstance(authors, list) or not authors or any(not isinstance(a, dict) or not nonempty(a.get("name")) for a in authors):
        errors.append("metadata.authors must contain author-confirmed full names")
    if not isinstance(affiliations, list) or not affiliations:
        errors.append("metadata.affiliations is required")
    for key in ("name", "email", "postal_address"):
        if not nonempty(corr.get(key)):
            errors.append(f"metadata.corresponding_author.{key} is required")
    for key in ("ethics", "consent", "competing_interests", "funding", "author_contributions", "data_availability", "ai_use"):
        if not nonempty(declarations.get(key)):
            errors.append(f"metadata.declarations.{key} is required")
    checked_on = str(verification.get("checked_on", ""))
    if not nonempty(verification.get("url")) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", checked_on):
        errors.append("metadata.journal_verification requires an official URL and YYYY-MM-DD checked_on date")
    else:
        if profile.get("guide_url") and verification.get("url") != profile.get("guide_url"):
            errors.append("metadata.journal_verification.url does not match the selected journal's official guide")
        age = (dt.date.today() - dt.date.fromisoformat(checked_on)).days
        if age < 0 or age > 30:
            errors.append("official journal guide verification must be dated within the last 30 days")
    return errors


def title_page_tex(title: str, metadata: dict) -> str:
    authors = metadata.get("authors", [])
    affiliations = metadata.get("affiliations", [])
    corr = metadata.get("corresponding_author", {})
    decl = metadata.get("declarations", {})
    author_lines = []
    for author in authors:
        aff = ",".join(author.get("affiliations", []))
        suffix = rf"\textsuperscript{{{latex_escape(aff)}}}" if aff else ""
        author_lines.append(latex_escape(author.get("name", "")) + suffix)
    affiliation_lines = [
        rf"\textsuperscript{{{latex_escape(str(item.get('id', '')))}}}{latex_escape(str(item.get('text', '')))}"
        for item in affiliations
    ]
    blocks = [
        r"\documentclass[11pt]{article}", r"\usepackage[T1]{fontenc}",
        r"\usepackage[utf8]{inputenc}", r"\usepackage[margin=1in]{geometry}",
        r"\begin{document}", rf"\section*{{{latex_escape(title)}}}",
        r"\textbf{Authors}\\" + "\\\n".join(author_lines),
        r"\subsection*{Affiliations}" + "\n\n".join(affiliation_lines),
        r"\subsection*{Corresponding author}",
        latex_escape(str(corr.get("name", ""))) + r"\\" + latex_escape(str(corr.get("postal_address", ""))) + r"\\" + latex_escape(str(corr.get("email", ""))),
    ]
    for label, key in (("Funding", "funding"), ("Competing interests", "competing_interests"), ("Author contributions", "author_contributions"), ("Acknowledgements", "acknowledgements")):
        if nonempty(decl.get(key)):
            blocks.extend([rf"\subsection*{{{label}}}", latex_escape(decl[key])])
    blocks.append(r"\end{document}")
    return "\n\n".join(blocks) + "\n"


def declarations_tex(metadata: dict, anonymous: bool) -> str:
    declarations = metadata.get("declarations", {})
    keys = [("Ethics approval", "ethics"), ("Consent", "consent"),
            ("Data availability", "data_availability"),
            ("Declaration of generative AI use", "ai_use")]
    if not anonymous:
        keys.extend([("Funding", "funding"), ("Competing interests", "competing_interests"),
                     ("Author contributions", "author_contributions")])
    blocks = []
    for label, key in keys:
        if nonempty(declarations.get(key)):
            blocks.extend([rf"\section*{{{label}}}", latex_escape(declarations[key])])
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def reader_facing_wrapper_values(
    *, mode: str, anonymous: bool, authors: list[dict]
) -> tuple[str, str, list[str]]:
    """Keep workflow state out of the reader-facing manuscript wrapper.

    Preview/submission readiness and missing-author metadata belong in the
    requirements report and manifest.  They must not be rendered as an
    audit banner or a fabricated author value in the paper itself.
    """
    if anonymous:
        return "Anonymous manuscript", "", []
    author_text = "; ".join(
        str(author.get("name", "")).strip()
        for author in authors
        if isinstance(author, dict) and str(author.get("name", "")).strip()
    )
    transformations: list[str] = []
    if mode == "preview":
        transformations.append("kept_preview_status_in_sidecars_not_reader_facing_pdf")
    if not author_text:
        transformations.append("omitted_unconfirmed_author_metadata_from_reader_facing_pdf")
    return author_text, "", transformations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manuscript", required=True, type=Path)
    parser.add_argument("--bibliography", required=True, type=Path)
    parser.add_argument("--journal", choices=("generic", "modern-pathology", "journal-of-pathology-informatics"), default="generic")
    parser.add_argument("--mode", choices=("preview", "submission"), default="preview")
    parser.add_argument("--metadata", type=Path)
    parser.add_argument("--upstream-manifest", type=Path)
    parser.add_argument("--figures-dir", type=Path)
    parser.add_argument("--figure-manifest", action="append", default=[], type=Path,
                        help="Provenance-tracked methodology figure manifest; may be repeated")
    parser.add_argument("--cover-letter", type=Path)
    parser.add_argument("--declaration-form", type=Path)
    parser.add_argument("--line-numbers", choices=("auto", "on", "off"), default="auto",
                        help="Override line numbering; auto preserves the adapter default")
    parser.add_argument("--section-numbering", choices=("auto", "on", "off"), default="auto",
                        help="Override section/subsection numbering; auto preserves the adapter default")
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    manuscript = args.manuscript.resolve()
    bibliography = args.bibliography.resolve()
    output = args.output_dir.resolve()
    if manuscript.suffix.lower() not in {".md", ".markdown"}:
        raise SystemExit("prepare_package.py currently accepts Markdown input; audit native LaTeX separately")
    for path in (manuscript, bibliography):
        if not path.is_file():
            raise SystemExit(f"missing input file: {path}")
    if output.exists() and any(output.iterdir()):
        raise SystemExit(f"output directory must be new or empty: {output}")
    output.mkdir(parents=True, exist_ok=True)

    profile = load_json(PROFILE_DIR / f"{args.journal}.json")
    line_numbers_enabled = True if args.line_numbers == "auto" else args.line_numbers == "on"
    section_numbering_enabled = (
        bool(profile.get("number_sections"))
        if args.section_numbering == "auto"
        else args.section_numbering == "on"
    )
    metadata = load_json(args.metadata.resolve() if args.metadata else None)
    warnings: list[str] = []
    errors: list[str] = []
    raw = manuscript.read_text(encoding="utf-8-sig")
    cleaned, transformations, inferred_title = clean_source(raw)
    if profile.get("abstract_style") == "unstructured":
        cleaned, merged_abstract_parts = flatten_abstract_for_unstructured_profile(cleaned)
        if merged_abstract_parts:
            transformations.append(
                f"merged_{merged_abstract_parts}_structured_abstract_parts_into_one_paragraph"
            )
    if args.line_numbers != "auto":
        transformations.append(f"line_numbers_{args.line_numbers}_by_author_request")
    if args.section_numbering != "auto":
        transformations.append(f"section_numbering_{args.section_numbering}_by_author_request")
    cleaned, figure_manifest_records = integrate_figure_manifests(
        cleaned, args.figure_manifest, output, transformations, errors
    )
    cleaned, production_stub_transformations = remove_resolved_production_stubs(
        cleaned, figures_integrated=bool(figure_manifest_records)
    )
    transformations.extend(production_stub_transformations)
    title = str(metadata.get("title") or inferred_title)
    abstract, body_without_abstract = section(cleaned, "Abstract")
    abstract_plain = re.sub(r"^#{3,6}\s+.*$", "", abstract, flags=re.MULTILINE)
    abstract_plain = re.sub(r"^\*\*Keywords:\*\*.*$", "", abstract_plain, flags=re.IGNORECASE | re.MULTILINE)
    abstract_words = word_count(abstract_plain)
    body_count_source = re.sub(
        r"\\begin\{figure\}.*?\\end\{figure\}", " ", body_without_abstract,
        flags=re.DOTALL,
    )
    body_words = word_count(body_count_source)
    abstract_subheadings = re.findall(r"^#{3,6}\s+(.+)$", abstract, flags=re.MULTILINE)
    keywords_match = re.search(r"^\*\*Keywords:\*\*\s*(.+)$", cleaned, flags=re.IGNORECASE | re.MULTILINE)
    keywords = [item.strip() for item in re.split(r"[;,]", keywords_match.group(1)) if item.strip()] if keywords_match else []
    table_count = len(re.findall(r"^\|(?:\s*:?-+:?\s*\|)+\s*$", cleaned, flags=re.MULTILINE))
    figure_count = len(re.findall(r"!\[[^\]]*\]\([^\)]+\)|\\includegraphics", cleaned))
    bib_keys = set(BIB_KEY_RE.findall(bibliography.read_text(encoding="utf-8-sig")))
    cited_keys = set(CITATION_RE.findall(cleaned))

    if not abstract:
        errors.append("abstract section not found")
    if profile.get("abstract_max_words") and abstract_words > profile["abstract_max_words"]:
        errors.append(f"abstract has {abstract_words} words; maximum is {profile['abstract_max_words']}")
    if profile.get("abstract_style") == "unstructured" and abstract_subheadings:
        errors.append("abstract is structured but the journal requires an unstructured abstract")
    if profile.get("body_max_words") and body_words > profile["body_max_words"]:
        errors.append(f"estimated main-body count is {body_words}; maximum is {profile['body_max_words']}")
    if profile.get("title_max_characters") and len(title) > profile["title_max_characters"]:
        errors.append(f"title has {len(title)} characters; maximum is {profile['title_max_characters']}")
    if profile.get("keywords_min") is not None and len(keywords) < profile["keywords_min"]:
        errors.append(f"found {len(keywords)} keywords; minimum is {profile['keywords_min']}")
    if profile.get("keywords_max") is not None and len(keywords) > profile["keywords_max"]:
        errors.append(f"found {len(keywords)} keywords; maximum is {profile['keywords_max']}")
    if profile.get("figures_tables_max") and figure_count + table_count > profile["figures_tables_max"]:
        errors.append(f"found {figure_count + table_count} figures/tables; maximum is {profile['figures_tables_max']}")
    if profile.get("references_max") and len(cited_keys) > profile["references_max"]:
        errors.append(f"manuscript cites {len(cited_keys)} references; maximum is {profile['references_max']}")
    missing_keys = sorted(cited_keys - bib_keys)
    if missing_keys:
        errors.append("missing bibliography keys: " + ", ".join(missing_keys))
    unused_keys = sorted(bib_keys - cited_keys)
    if unused_keys:
        warnings.append(f"{len(unused_keys)} bibliography entries are not cited")
    placeholders = sorted(set(match.group(0) for match in PLACEHOLDER_RE.finditer(cleaned)))
    if placeholders:
        errors.append("unresolved placeholders: " + ", ".join(placeholders))
    if args.journal == "generic":
        warnings.append("generic profile is submission-neutral; current journal requirements are unresolved")
    if args.journal == "journal-of-pathology-informatics":
        warnings.append("highlights and graphical abstract are encouraged but are not generated automatically")
        warnings.append("manual anonymity review is required for text, filenames, supplements, self-citations, and PDF metadata")
    if args.journal == "modern-pathology":
        warnings.append("a journal-specific cover letter is required before submission")
    if not args.upstream_manifest:
        warnings.append("no upstream claim/integrity manifest was supplied; test-use and claim restrictions require manual verification")
    if args.mode == "submission":
        if args.journal == "generic":
            errors.append("generic profile cannot be labeled submission-ready")
        errors.extend(metadata_errors(metadata, profile))
        if args.journal == "modern-pathology" and not args.cover_letter:
            errors.append("Modern Pathology submission mode requires --cover-letter")
        if args.journal == "journal-of-pathology-informatics" and not args.declaration_form:
            errors.append("JPI submission mode requires the Elsevier declaration form via --declaration-form")

    for label, path in (("upstream manifest", args.upstream_manifest), ("cover letter", args.cover_letter),
                        ("declaration form", args.declaration_form)):
        if path and not path.resolve().is_file():
            errors.append(f"{label} file not found: {path.resolve()}")

    (output / "source_clean.md").write_text(cleaned, encoding="utf-8", newline="\n")
    bib_source = bibliography.read_text(encoding="utf-8-sig")
    bib_output = html.unescape(bib_source)
    bib_output = re.sub(r"(?<!\\)&", r"\\&", bib_output)
    if bib_output != bib_source:
        transformations.append("normalized_bibtex_html_entities_and_ampersands")
    (output / "references.bib").write_text(bib_output, encoding="utf-8", newline="\n")
    if args.figures_dir:
        figure_dir = args.figures_dir.resolve()
        if not figure_dir.is_dir():
            errors.append(f"figures directory not found: {figure_dir}")
        else:
            shutil.copytree(figure_dir, output / "figures", dirs_exist_ok=True)
    auxiliary = output / "auxiliary"
    for path in (args.cover_letter, args.declaration_form):
        if path and path.resolve().is_file():
            auxiliary.mkdir(exist_ok=True)
            shutil.copy2(path.resolve(), auxiliary / path.name)

    pandoc = shutil.which("pandoc")
    if not pandoc:
        raise SystemExit("pandoc was not found on PATH")
    pandoc_help = subprocess.run(
        [pandoc, "--help"], text=True, capture_output=True
    ).stdout
    supports_heading_shift = "--shift-heading-level-by" in pandoc_help
    pandoc_source = output / "source_clean.md"
    heading_args: list[str] = []
    if supports_heading_shift:
        heading_args.append("--shift-heading-level-by=-1")
    else:
        pandoc_source = output / ".pandoc_legacy_heading_input.md"
        legacy_source = re.sub(
            r"^(#{2,6})(\s+)",
            lambda match: match.group(1)[1:] + match.group(2),
            cleaned,
            flags=re.MULTILINE,
        )
        pandoc_source.write_text(legacy_source, encoding="utf-8", newline="\n")
        transformations.append("compat_shifted_heading_levels_for_legacy_pandoc")
    pandoc_cmd = [pandoc, str(pandoc_source),
                  "--from=markdown+citations+tex_math_dollars+tex_math_single_backslash+raw_tex", "--to=latex",
                  "--natbib", "--wrap=none", *heading_args,
                  "--output", str(output / "manuscript_body.tex")]
    resource_paths = [str(manuscript.parent)]
    if args.figures_dir:
        resource_paths.append(str(args.figures_dir.resolve()))
    pandoc_cmd.extend(["--resource-path=" + os.pathsep.join(resource_paths), "--extract-media=figures"])
    if section_numbering_enabled:
        pandoc_cmd.append("--number-sections")
    conversion = subprocess.run(pandoc_cmd, cwd=output, text=True, capture_output=True)
    if pandoc_source.name == ".pandoc_legacy_heading_input.md":
        pandoc_source.unlink(missing_ok=True)
    if conversion.returncode != 0:
        errors.append("pandoc conversion failed: " + conversion.stderr.strip())
    else:
        body_path = output / "manuscript_body.tex"
        formatted_body, unicode_transformations = normalize_latex_unicode(
            body_path.read_text(encoding="utf-8")
        )
        formatted_body, table_transformations = format_longtables(formatted_body)
        body_path.write_text(formatted_body, encoding="utf-8", newline="\n")
        transformations.extend(unicode_transformations)
        transformations.extend(table_transformations)

    anonymous = args.journal == "journal-of-pathology-informatics"
    author_text, draft_banner, wrapper_transformations = reader_facing_wrapper_values(
        mode=args.mode,
        anonymous=anonymous,
        authors=metadata.get("authors", []),
    )
    transformations.extend(wrapper_transformations)
    template = TEMPLATE.read_text(encoding="utf-8")
    declarations_input = ""
    if metadata.get("declarations"):
        declaration_text = declarations_tex(metadata, anonymous)
        if declaration_text:
            (output / "declarations.tex").write_text(declaration_text, encoding="utf-8", newline="\n")
            declarations_input = r"\input{declarations.tex}"
            transformations.append("generated_declarations_from_author_metadata")
    main_tex = (template.replace("@@TITLE@@", latex_escape(title))
                .replace("@@AUTHOR@@", latex_escape(author_text))
                .replace("@@DRAFT_BANNER@@", draft_banner)
                .replace("@@LINE_NUMBER_PACKAGE@@", r"\IfFileExists{lineno.sty}{\usepackage{lineno}}{}" if line_numbers_enabled else "")
                .replace("@@LINE_NUMBERS@@", r"\IfFileExists{lineno.sty}{\linenumbers}{}" if line_numbers_enabled else "")
                .replace("@@SECTION_NUMBERING@@", r"\setcounter{secnumdepth}{3}" if section_numbering_enabled else r"\setcounter{secnumdepth}{-1}")
                .replace("@@DECLARATIONS_INPUT@@", declarations_input))
    (output / "manuscript.tex").write_text(main_tex, encoding="utf-8", newline="\n")
    # Keep older invocations working without maintaining two divergent sources.
    (output / "main.tex").write_text("\\input{manuscript.tex}\n", encoding="utf-8", newline="\n")
    if metadata.get("authors"):
        (output / "title_page.tex").write_text(title_page_tex(title, metadata), encoding="utf-8", newline="\n")

    readiness = "preview_only" if args.mode == "preview" else ("submission_ready_pending_pdf_qa" if not errors else "not_ready")
    report_lines = [f"# Requirements report — {profile['journal_name']}", "",
                    f"- Mode: `{args.mode}`", f"- Status: `{readiness}`",
                    f"- Line numbers: `{'on' if line_numbers_enabled else 'off'}`",
                    f"- Section numbering: `{'on' if section_numbering_enabled else 'off'}`",
                    f"- Official guide: {profile.get('guide_url') or 'unresolved'}",
                    f"- Local profile checked: {profile.get('profile_checked_on') or 'not applicable'}",
                    f"- Abstract words: {abstract_words}", f"- Estimated main-body words: {body_words}",
                    f"- Figures: {figure_count}; tables: {table_count}; bibliography entries: {len(bib_keys)}",
                    f"- Keywords: {len(keywords)}", "", "## Blocking items", ""]
    report_lines.extend(f"- {item}" for item in errors)
    if not errors:
        report_lines.append("- None at preparation stage; compilation and visual PDF QA remain.")
    report_lines.extend(["", "## Warnings and manual checks", ""])
    report_lines.extend(f"- {item}" for item in warnings)
    if not warnings:
        report_lines.append("- None recorded.")
    (output / "requirements_report.md").write_text("\n".join(report_lines) + "\n", encoding="utf-8", newline="\n")

    manifest = {
        "schema": "manuscript-to-latex/1.0", "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "mode": args.mode, "status": readiness, "journal_profile": profile,
        "layout": {
            "line_numbers": line_numbers_enabled,
            "section_numbering": section_numbering_enabled,
            "line_numbers_option": args.line_numbers,
            "section_numbering_option": args.section_numbering,
        },
        "inputs": {
            "manuscript": {"path": str(manuscript), "sha256": sha256(manuscript)},
            "bibliography": {"path": str(bibliography), "sha256": sha256(bibliography)},
            "metadata": {"path": str(args.metadata.resolve()), "sha256": sha256(args.metadata.resolve())} if args.metadata else None,
            "upstream_manifest": {"path": str(args.upstream_manifest.resolve()), "sha256": sha256(args.upstream_manifest.resolve())} if args.upstream_manifest and args.upstream_manifest.resolve().is_file() else None,
            "cover_letter": {"path": str(args.cover_letter.resolve()), "sha256": sha256(args.cover_letter.resolve())} if args.cover_letter and args.cover_letter.resolve().is_file() else None,
            "declaration_form": {"path": str(args.declaration_form.resolve()), "sha256": sha256(args.declaration_form.resolve())} if args.declaration_form and args.declaration_form.resolve().is_file() else None,
            "figure_manifests": figure_manifest_records,
        },
        "counts": {"abstract_words": abstract_words, "estimated_main_body_words": body_words,
                   "figures": figure_count, "tables": table_count, "bibliography_entries": len(bib_keys),
                   "cited_keys": len(cited_keys), "keywords": len(keywords)},
        "transformations": transformations, "errors": errors, "warnings": warnings, "outputs": {},
    }
    for filename in ("source_clean.md", "manuscript_body.tex", "manuscript.tex", "main.tex", "references.bib", "requirements_report.md", "title_page.tex", "declarations.tex"):
        path = output / filename
        if path.is_file():
            manifest["outputs"][filename] = sha256(path)
    if figure_manifest_records:
        manifest["outputs"]["figure_assets"] = {
            key: value
            for record in figure_manifest_records
            for key, value in record["copied_assets"].items()
        }
    (output / "submission_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")

    print(f"Created package: {output}")
    print(f"Status: {readiness}")
    if errors:
        print("Blocking items:")
        for item in errors:
            print(f"- {item}")
    return 2 if args.mode == "submission" and errors else 0


if __name__ == "__main__":
    sys.exit(main())
