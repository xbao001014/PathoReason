#!/usr/bin/env python3
"""Package an author-approved high-fidelity raster methodology figure."""

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
from pathlib import Path

from PIL import Image


BROWSER_CANDIDATES = (
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
    for candidate in BROWSER_CANDIDATES:
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
    raise SystemExit("A supported Chromium-family browser is required for PDF rendering")


def inspect_image(image_path: Path, target_width_mm: float, minimum_dpi: float) -> dict:
    with Image.open(image_path) as image:
        image.load()
        width_px, height_px = image.size
        mode = image.mode
        image_format = image.format
    effective_dpi = width_px / (target_width_mm / 25.4)
    target_height_mm = target_width_mm * height_px / width_px
    blocking: list[str] = []
    if width_px <= 0 or height_px <= 0:
        blocking.append("invalid_dimensions")
    if effective_dpi < minimum_dpi:
        blocking.append("insufficient_effective_resolution")
    if mode not in {"RGB", "RGBA"}:
        blocking.append("unsupported_color_mode")
    return {
        "schema": "raster-methodology-machine-qa/1.0",
        "status": "passed_machine_checks" if not blocking else "failed_machine_checks",
        "target_width_mm": target_width_mm,
        "observed": {
            "width_px": width_px,
            "height_px": height_px,
            "aspect_ratio": round(width_px / height_px, 6),
            "target_height_mm": round(target_height_mm, 3),
            "effective_dpi_at_target_width": round(effective_dpi, 3),
            "mode": mode,
            "format": image_format,
        },
        "required_minimum_effective_dpi": minimum_dpi,
        "blocking_failures": blocking,
        "limitations": [
            "Resolution and metadata checks do not detect overlaps or scientific errors.",
            "Human visual review of the full figure and final manuscript page remains required.",
        ],
    }


def render_pdf(png: Path, pdf: Path, width_mm: float, height_mm: float) -> list[str]:
    browser = browser_path()
    with tempfile.TemporaryDirectory(prefix="raster-methodology-") as temp:
        temp_path = Path(temp)
        html = temp_path / "render.html"
        profile = temp_path / "browser-profile"
        html.write_text(
            "<!doctype html><html><head><meta charset='utf-8'><style>"
            f"@page{{size:{width_mm:.6f}mm {height_mm:.6f}mm;margin:0}}"
            "html,body{width:100%;height:100%;margin:0;overflow:hidden;background:white}"
            "img{display:block;width:100%;height:100%;object-fit:contain}"
            "</style></head><body>"
            f"<img src='{png.resolve().as_uri()}' alt='Methodology figure'>"
            "</body></html>",
            encoding="utf-8",
        )
        command = [
            str(browser), "--headless=new", "--no-sandbox", "--disable-gpu", "--no-pdf-header-footer",
            f"--user-data-dir={profile}", f"--print-to-pdf={pdf}", html.resolve().as_uri(),
        ]
        result = subprocess.run(command, text=True, encoding="utf-8", errors="replace", capture_output=True)
        if result.returncode != 0 or not pdf.is_file() or pdf.stat().st_size == 0:
            raise SystemExit(f"browser PDF rendering failed: {result.stderr.strip()}")
    return [subprocess.list2cmdline(command)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--methodology", required=True, type=Path)
    parser.add_argument("--modules", required=True, type=Path)
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--author-approved-raster", action="store_true")
    parser.add_argument("--caption", required=True, type=Path)
    parser.add_argument("--alt-text", required=True, type=Path)
    parser.add_argument("--figure-id", required=True)
    parser.add_argument("--filename-stem", required=True)
    parser.add_argument("--callout", required=True)
    parser.add_argument("--insertion-before", required=True)
    parser.add_argument("--orientation", choices=("portrait", "landscape"), default="portrait")
    parser.add_argument("--target-width-mm", type=float, default=160.0)
    parser.add_argument("--minimum-effective-dpi", type=float, default=250.0)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    if not args.author_approved_raster:
        raise SystemExit("raster fallback requires explicit --author-approved-raster")
    inputs = [args.methodology, args.modules, args.image, args.caption, args.alt_text]
    for path in inputs:
        if not path.resolve().is_file():
            raise SystemExit(f"missing input: {path}")
    if not args.figure_id.startswith("fig:"):
        raise SystemExit("figure-id must begin with fig:")
    if f"\\ref{{{args.figure_id}}}" not in args.callout:
        raise SystemExit("callout must contain a matching LaTeX figure reference")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", args.filename_stem):
        raise SystemExit("filename-stem contains unsupported characters")
    if args.target_width_mm <= 0 or args.minimum_effective_dpi <= 0:
        raise SystemExit("target width and minimum effective DPI must be positive")

    output = args.output_dir.resolve()
    if output.exists() and any(output.iterdir()):
        raise SystemExit(f"output directory must be new or empty: {output}")
    output.mkdir(parents=True, exist_ok=True)

    final_png = output / f"{args.filename_stem}.png"
    with Image.open(args.image.resolve()) as source_image:
        source_image.load()
        if source_image.format == "PNG" and source_image.mode in {"RGB", "RGBA"}:
            shutil.copy2(args.image.resolve(), final_png)
        else:
            source_image.convert("RGB").save(final_png, format="PNG", optimize=True)

    methodology_copy = output / "methodology_input.md"
    modules_copy = output / "module_description_input.md"
    caption_copy = output / "caption.md"
    alt_copy = output / "alt_text.md"
    shutil.copy2(args.methodology.resolve(), methodology_copy)
    shutil.copy2(args.modules.resolve(), modules_copy)
    shutil.copy2(args.caption.resolve(), caption_copy)
    shutil.copy2(args.alt_text.resolve(), alt_copy)

    qa = inspect_image(final_png, args.target_width_mm, args.minimum_effective_dpi)
    qa_path = output / "machine_qa.json"
    qa_path.write_text(json.dumps(qa, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if qa["blocking_failures"]:
        raise SystemExit("raster failed machine QA: " + ", ".join(qa["blocking_failures"]))

    height_mm = qa["observed"]["target_height_mm"]
    final_pdf = output / f"{args.filename_stem}.pdf"
    commands = render_pdf(final_png, final_pdf, args.target_width_mm, height_mm)
    manifest = {
        "schema": "raster-methodology-figure/1.0",
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
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
            "stages": ["two-file intake", "Stage-1 raster composition", "visual-fidelity review", "author-approved raster fallback", "render and QA"],
            "stage1_reference": {"path": final_png.name, "sha256": sha256(final_png), "authoritative": True},
            "raster_fidelity_fallback": True,
            "editable": False,
        },
        "exports": {
            "pdf": {"path": final_pdf.name, "sha256": sha256(final_pdf), "bytes": final_pdf.stat().st_size},
            "png": {"path": final_png.name, "sha256": sha256(final_png), "bytes": final_png.stat().st_size},
        },
        "final_raster": {"path": final_png.name, "sha256": sha256(final_png), "editable": False},
        "editable_sources": [],
        "design_brief": {"path": modules_copy.name, "sha256": sha256(modules_copy)},
        "caption_file": {"path": caption_copy.name, "sha256": sha256(caption_copy)},
        "alt_text_file": {"path": alt_copy.name, "sha256": sha256(alt_copy)},
        "machine_qa": {"path": qa_path.name, "sha256": sha256(qa_path), "status": qa["status"]},
        "human_visual_review": {"status": "pending", "path": None, "sha256": None},
        "generator": {"name": "Author-approved raster fidelity fallback", "render_commands": commands},
        "evidence_boundary": "The final raster is an author-approved conceptual methodology illustration governed by the copied methodology and module-description inputs; it is not primary research evidence.",
    }
    manifest_path = output / "asset_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Created raster methodology figure: {output}")
    print(f"Manifest: {manifest_path}")
    print(f"Machine QA: {qa['status']}")
    print(f"Effective DPI at {args.target_width_mm:g} mm: {qa['observed']['effective_dpi_at_target_width']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
