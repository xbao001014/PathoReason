#!/usr/bin/env python3
"""Package and audit an AutoFigure-Edit-style native SVG methodology figure."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path


SVG_NS = "http://www.w3.org/2000/svg"
EDGE_CANDIDATES = (
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def browser_path() -> Path:
    for candidate in EDGE_CANDIDATES:
        if candidate.is_file():
            return candidate
    for name in (
        "msedge",
        "chrome",
        "google-chrome",
        "google-chrome-stable",
        "chromium",
        "chromium-browser",
    ):
        found = shutil.which(name)
        if found:
            return Path(found)
    raise SystemExit("A supported Chromium-family browser is required for SVG rendering")


def parse_viewbox(root: ET.Element) -> tuple[float, float]:
    raw = root.get("viewBox", "")
    parts = raw.replace(",", " ").split()
    if len(parts) != 4:
        raise SystemExit("SVG root requires a four-number viewBox")
    try:
        width, height = float(parts[2]), float(parts[3])
    except ValueError as exc:
        raise SystemExit("SVG viewBox must be numeric") from exc
    if width <= 0 or height <= 0:
        raise SystemExit("SVG viewBox dimensions must be positive")
    return width, height


def inspect_svg(svg: Path, target_width_mm: float, min_font_pt: float) -> dict:
    try:
        root = ET.parse(svg).getroot()
    except ET.ParseError as exc:
        raise SystemExit(f"invalid SVG XML: {exc}") from exc
    if root.tag.split("}")[-1] != "svg":
        raise SystemExit("editable source root is not SVG")
    width, height = parse_viewbox(root)
    counts: dict[str, int] = {}
    font_sizes: list[float] = []
    forbidden: list[str] = []
    ids: set[str] = set()
    duplicate_ids: set[str] = set()
    for element in root.iter():
        tag = element.tag.split("}")[-1]
        counts[tag] = counts.get(tag, 0) + 1
        if tag in {"image", "foreignObject", "script"}:
            forbidden.append(tag)
        element_id = element.get("id")
        if element_id:
            if element_id in ids:
                duplicate_ids.add(element_id)
            ids.add(element_id)
        raw_size = element.get("font-size", "")
        style = element.get("style", "")
        match = re.search(r"font-size\s*:\s*([0-9.]+)", style)
        if not raw_size and match:
            raw_size = match.group(1)
        size_match = re.match(r"([0-9.]+)", raw_size)
        if size_match:
            font_sizes.append(float(size_match.group(1)))
    scale_mm = target_width_mm / width
    smallest_user = min(font_sizes) if font_sizes else 0.0
    smallest_final_pt = smallest_user * scale_mm * 72.0 / 25.4
    final_height_mm = height * scale_mm
    blocking: list[str] = []
    if forbidden:
        blocking.append("embedded_or_executable_content")
    if counts.get("text", 0) < 8:
        blocking.append("insufficient_editable_text")
    if counts.get("g", 0) < 5:
        blocking.append("insufficient_editable_groups")
    if duplicate_ids:
        blocking.append("duplicate_svg_ids")
    if smallest_final_pt < min_font_pt:
        blocking.append("minimum_final_font")
    return {
        "schema": "illustrated-methodology-machine-qa/1.0",
        "status": "passed_machine_checks" if not blocking else "failed_machine_checks",
        "target_width_mm": target_width_mm,
        "observed": {
            "viewbox_width": width,
            "viewbox_height": height,
            "estimated_final_height_mm": round(final_height_mm, 3),
            "minimum_svg_font_user_units": smallest_user,
            "estimated_minimum_final_font_pt": round(smallest_final_pt, 3),
            "element_counts": counts,
            "stable_id_count": len(ids),
            "duplicate_ids": sorted(duplicate_ids),
            "forbidden_elements": sorted(set(forbidden)),
        },
        "required_minimum_final_font_pt": min_font_pt,
        "blocking_failures": blocking,
        "limitations": [
            "SVG structure checks do not establish scientific correctness.",
            "Final topology and visual fidelity require human comparison with both input files and the Stage-1 reference.",
        ],
    }


def render(svg_text: str, output: Path, stem: str) -> tuple[Path, Path, list[str]]:
    browser = browser_path()
    png = output / f"{stem}.png"
    pdf = output / f"{stem}.pdf"
    commands: list[str] = []
    with tempfile.TemporaryDirectory(prefix="illustrated-figure-") as tmp:
        tmp_path = Path(tmp)
        html_path = tmp_path / "render.html"
        profile = tmp_path / "browser-profile"
        html_path.write_text(
            "<!doctype html><html><head><meta charset='utf-8'><style>"
            "@page{size:18.75in 9.375in;margin:0}"
            "html,body{width:100%;height:100%;margin:0;overflow:hidden;background:white}"
            "svg{display:block;width:100vw!important;height:100vh!important}"
            "</style></head><body>" + svg_text + "</body></html>",
            encoding="utf-8",
        )
        uri = html_path.resolve().as_uri()
        screenshot = [
            str(browser), "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
            "--window-size=3600,1800", "--force-device-scale-factor=1",
            f"--user-data-dir={profile}", f"--screenshot={png}", uri,
        ]
        commands.append(subprocess.list2cmdline(screenshot))
        shot = subprocess.run(screenshot, text=True, encoding="utf-8", errors="replace", capture_output=True)
        if shot.returncode != 0 or not png.is_file() or png.stat().st_size == 0:
            raise SystemExit(f"browser PNG rendering failed: {shot.stderr.strip()}")
        print_cmd = [
            str(browser), "--headless=new", "--no-sandbox", "--disable-gpu", "--no-pdf-header-footer",
            f"--user-data-dir={profile}", f"--print-to-pdf={pdf}", uri,
        ]
        commands.append(subprocess.list2cmdline(print_cmd))
        printed = subprocess.run(print_cmd, text=True, encoding="utf-8", errors="replace", capture_output=True)
        if printed.returncode != 0 or not pdf.is_file() or pdf.stat().st_size == 0:
            raise SystemExit(f"browser PDF rendering failed: {printed.stderr.strip()}")
    return png, pdf, commands


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--methodology", required=True, type=Path)
    parser.add_argument("--modules", required=True, type=Path)
    parser.add_argument("--svg", required=True, type=Path)
    parser.add_argument("--stage1-image", required=True, type=Path)
    parser.add_argument("--caption", required=True, type=Path)
    parser.add_argument("--alt-text", required=True, type=Path)
    parser.add_argument("--figure-id", required=True)
    parser.add_argument("--filename-stem", required=True)
    parser.add_argument("--callout", required=True)
    parser.add_argument("--insertion-before", required=True)
    parser.add_argument("--orientation", choices=("portrait", "landscape"), default="portrait")
    parser.add_argument("--target-width-mm", type=float, default=160.0)
    parser.add_argument("--minimum-final-font-pt", type=float, default=5.2)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--enable-svg-generation",
        action="store_true",
        help="Explicitly opt in to packaging a newly reconstructed SVG.",
    )
    args = parser.parse_args()
    if not args.enable_svg_generation:
        raise SystemExit(
            "SVG generation is disabled by default; pass --enable-svg-generation "
            "only after explicit user authorization"
        )
    inputs = [args.methodology, args.modules, args.svg, args.stage1_image, args.caption, args.alt_text]
    for path in inputs:
        if not path.resolve().is_file():
            raise SystemExit(f"missing input: {path}")
    if not args.figure_id.startswith("fig:"):
        raise SystemExit("figure-id must begin with fig:")
    if f"\\ref{{{args.figure_id}}}" not in args.callout:
        raise SystemExit("callout must contain a matching LaTeX figure reference")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", args.filename_stem):
        raise SystemExit("filename-stem contains unsupported characters")
    output = args.output_dir.resolve()
    if output.exists() and any(output.iterdir()):
        raise SystemExit(f"output directory must be new or empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    editable_svg = output / f"{args.filename_stem}.svg"
    shutil.copy2(args.svg.resolve(), editable_svg)
    stage1 = output / "stage1_visual_reference.png"
    shutil.copy2(args.stage1_image.resolve(), stage1)
    methodology_copy = output / "methodology_input.md"
    modules_copy = output / "module_description_input.md"
    caption_copy = output / "caption.md"
    alt_copy = output / "alt_text.md"
    shutil.copy2(args.methodology.resolve(), methodology_copy)
    shutil.copy2(args.modules.resolve(), modules_copy)
    shutil.copy2(args.caption.resolve(), caption_copy)
    shutil.copy2(args.alt_text.resolve(), alt_copy)
    qa = inspect_svg(editable_svg, args.target_width_mm, args.minimum_final_font_pt)
    qa_path = output / "machine_qa.json"
    qa_path.write_text(json.dumps(qa, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if qa["blocking_failures"]:
        raise SystemExit("SVG failed machine QA: " + ", ".join(qa["blocking_failures"]))
    png, pdf, commands = render(editable_svg.read_text(encoding="utf-8"), output, args.filename_stem)
    created_at = dt.datetime.now(dt.timezone.utc).isoformat()
    manifest = {
        "schema": "illustrated-methodology-figure/2.0",
        "created_at": created_at,
        "figure_id": args.figure_id,
        "filename_stem": args.filename_stem,
        "title": args.filename_stem.replace("_", " "),
        "caption": caption_copy.read_text(encoding="utf-8").strip(),
        "alt_text": alt_copy.read_text(encoding="utf-8").strip(),
        "callout": args.callout,
        "insertion": {"before_heading": args.insertion_before},
        "orientation": args.orientation,
        "source_files": [
            {"id": "methodology", "path": str(args.methodology.resolve()), "sha256": sha256(args.methodology.resolve())},
            {"id": "modules", "path": str(args.modules.resolve()), "sha256": sha256(args.modules.resolve())},
        ],
        "input_snapshots": [
            {"kind": "methodology", "path": methodology_copy.name, "sha256": sha256(methodology_copy)},
            {"kind": "module_description", "path": modules_copy.name, "sha256": sha256(modules_copy)},
        ],
        "autofigure_style_workflow": {
            "stages": ["two-file intake", "Stage-1 raster composition", "entity decomposition", "native SVG reconstruction", "critic/refine", "render and QA"],
            "stage1_reference": {"path": stage1.name, "sha256": sha256(stage1), "authoritative": False},
            "final_svg_embeds_stage1": False,
        },
        "exports": {
            "pdf": {"path": pdf.name, "sha256": sha256(pdf), "bytes": pdf.stat().st_size},
            "svg": {"path": editable_svg.name, "sha256": sha256(editable_svg), "bytes": editable_svg.stat().st_size},
            "png": {"path": png.name, "sha256": sha256(png), "bytes": png.stat().st_size},
        },
        "editable_source": {"path": editable_svg.name, "sha256": sha256(editable_svg)},
        "editable_sources": [{"kind": "native_svg", "path": editable_svg.name, "sha256": sha256(editable_svg), "bytes": editable_svg.stat().st_size}],
        "design_brief": {"path": modules_copy.name, "sha256": sha256(modules_copy)},
        "caption_file": {"path": caption_copy.name, "sha256": sha256(caption_copy)},
        "machine_qa": {"path": qa_path.name, "sha256": sha256(qa_path), "status": qa["status"]},
        "human_visual_review": {"status": "pending", "path": None, "sha256": None},
        "generator": {"name": "AutoFigure-Edit-style local SVG reconstruction", "render_commands": commands},
        "evidence_boundary": "The Stage-1 raster is a composition reference only. Scientific content is governed by the copied methodology and module-description inputs.",
    }
    manifest_path = output / "asset_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Created illustrated methodology figure: {output}")
    print(f"Manifest: {manifest_path}")
    print(f"Machine QA: {qa['status']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
