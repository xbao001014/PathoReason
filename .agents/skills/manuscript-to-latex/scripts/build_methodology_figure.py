#!/usr/bin/env python3
"""Build a provenance-tracked, editable methodology figure from reviewed JSON."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


SUPPORTED_SCHEMAS = {"methodology-figure/1.0", "methodology-figure/1.1"}
NODE_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
FIGURE_ID_RE = re.compile(r"^fig:[A-Za-z0-9_.:-]+$")
HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
ALLOWED_SHAPES = {"box", "ellipse", "diamond", "parallelogram", "hexagon"}
ALLOWED_STYLES = {"solid", "dashed", "dotted", "bold"}

ROLE_COLORS = {
    "input": ("#EAF2F8", "#3B6C8E"),
    "backbone": ("#E8F0F7", "#315F7D"),
    "spatial": ("#FFF3D6", "#9A6A00"),
    "ordinal": ("#EAF4EC", "#3C7448"),
    "objective": ("#F2ECF7", "#73528A"),
    "output": ("#F2F3F4", "#52565A"),
    "neutral": ("#F8F9FA", "#62666A"),
}

PROFILES = {
    "publication": {
        "font_family": "Arial",
        "body_font_pt": 8.0,
        "title_font_pt": 9.0,
        "note_font_pt": 7.0,
        "edge_font_pt": 7.0,
        "minimum_final_font_pt": 5.0,
        "target_width_mm": 183.0,
        "max_height_mm": 170.0,
        "node_penwidth": 0.9,
        "edge_penwidth": 0.85,
        "nodesep": 0.34,
        "ranksep": 0.56,
        "background": "#FFFFFF",
        "text_color": "#202124",
        "note_color": "#5F6368",
        "cluster_border": "#C9CDD1",
        "cluster_fill": "#FBFCFD",
    },
    "legacy": {
        "font_family": "Arial",
        "body_font_pt": 8.5,
        "title_font_pt": 8.5,
        "note_font_pt": 7.5,
        "edge_font_pt": 7.5,
        "minimum_final_font_pt": 5.0,
        "target_width_mm": 183.0,
        "max_height_mm": 247.0,
        "node_penwidth": 1.0,
        "edge_penwidth": 1.0,
        "nodesep": 0.24,
        "ranksep": 0.42,
        "background": "#FFFFFF",
        "text_color": "#202124",
        "note_color": "#5F6368",
        "cluster_border": "#B5B5B5",
        "cluster_fill": "#FFFFFF",
    },
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def dot_quote(value: object) -> str:
    text = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return '"' + text.replace("\n", "\\n") + '"'


def require_text(item: dict, key: str) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value.strip()


def normalized_sources(spec: dict) -> list[dict[str, str]]:
    raw = spec.get("source_files")
    if not isinstance(raw, list) or not raw:
        raise ValueError("source_files must contain at least one source path")
    sources: list[dict[str, str]] = []
    used: set[str] = set()
    for index, item in enumerate(raw, start=1):
        if isinstance(item, str):
            source_id, path = f"source_{index}", item
        elif isinstance(item, dict):
            source_id, path = require_text(item, "id"), require_text(item, "path")
        else:
            raise ValueError("source_files entries must be paths or {id, path} objects")
        if not NODE_ID_RE.fullmatch(source_id) or source_id in used:
            raise ValueError(f"invalid or duplicate source id: {source_id}")
        used.add(source_id)
        sources.append({"id": source_id, "path": path})
    return sources


def validate_evidence(item: dict, context: str, source_ids: set[str], required: bool) -> None:
    evidence = item.get("evidence", [])
    if required and (not isinstance(evidence, list) or not evidence):
        raise ValueError(f"{context} requires at least one evidence entry")
    if not isinstance(evidence, list):
        raise ValueError(f"{context}.evidence must be a list")
    for entry in evidence:
        if not isinstance(entry, dict):
            raise ValueError(f"{context}.evidence entries must be objects")
        source_id = require_text(entry, "source_id")
        require_text(entry, "locator")
        if source_id not in source_ids:
            raise ValueError(f"{context} references unknown evidence source: {source_id}")


def validate_visual(visual: dict) -> None:
    for key in (
        "target_width_mm", "max_height_mm", "body_font_pt", "edge_font_pt",
        "minimum_final_font_pt",
    ):
        if key in visual and (not isinstance(visual[key], (int, float)) or visual[key] <= 0):
            raise ValueError(f"visual.{key} must be a positive number")
    if "font_family" in visual and not isinstance(visual["font_family"], str):
        raise ValueError("visual.font_family must be text")
    colors = visual.get("role_colors", {})
    if not isinstance(colors, dict):
        raise ValueError("visual.role_colors must be an object")
    for role, pair in colors.items():
        if not isinstance(pair, list) or len(pair) != 2 or not all(isinstance(v, str) and HEX_COLOR_RE.fullmatch(v) for v in pair):
            raise ValueError(f"visual.role_colors.{role} must be [fill_hex, border_hex]")


def validate(spec: dict) -> None:
    schema = spec.get("schema")
    if schema not in SUPPORTED_SCHEMAS:
        raise ValueError(f"schema must be one of {sorted(SUPPORTED_SCHEMAS)}")
    figure_id = require_text(spec, "figure_id")
    if not FIGURE_ID_RE.fullmatch(figure_id):
        raise ValueError("figure_id must begin with fig: and contain no spaces")
    for key in ("filename_stem", "title", "caption", "alt_text", "callout"):
        require_text(spec, key)
    if f"\\ref{{{figure_id}}}" not in spec["callout"]:
        raise ValueError("callout must contain a LaTeX reference matching figure_id")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", spec["filename_stem"]):
        raise ValueError("filename_stem may contain only letters, digits, dot, underscore, and hyphen")
    sources = normalized_sources(spec)
    source_ids = {item["id"] for item in sources}
    insertion = spec.get("insertion")
    if not isinstance(insertion, dict) or not isinstance(insertion.get("before_heading"), str) or not insertion["before_heading"].strip():
        raise ValueError("insertion.before_heading is required")
    if spec.get("rankdir", "LR") not in {"LR", "TB"}:
        raise ValueError("rankdir must be LR or TB")
    if spec.get("orientation", "portrait") not in {"portrait", "landscape"}:
        raise ValueError("orientation must be portrait or landscape")
    visual = spec.get("visual", {})
    if schema == "methodology-figure/1.1" and not isinstance(visual, dict):
        raise ValueError("schema 1.1 requires a visual object")
    if not isinstance(visual, dict):
        raise ValueError("visual must be an object")
    validate_visual(visual)

    clusters = spec.get("clusters", [])
    if not isinstance(clusters, list):
        raise ValueError("clusters must be a list")
    cluster_ids: set[str] = set()
    for cluster in clusters:
        cid = require_text(cluster, "id")
        if not NODE_ID_RE.fullmatch(cid) or cid in cluster_ids:
            raise ValueError(f"invalid or duplicate cluster id: {cid}")
        cluster_ids.add(cid)
        require_text(cluster, "label")

    nodes = spec.get("nodes")
    if not isinstance(nodes, list) or len(nodes) < 2:
        raise ValueError("nodes must contain at least two entries")
    node_ids: set[str] = set()
    for node in nodes:
        nid = require_text(node, "id")
        if not NODE_ID_RE.fullmatch(nid) or nid in node_ids:
            raise ValueError(f"invalid or duplicate node id: {nid}")
        node_ids.add(nid)
        if schema == "methodology-figure/1.1":
            require_text(node, "title")
            details = node.get("details", [])
            if not isinstance(details, list) or not all(isinstance(v, str) and v.strip() for v in details):
                raise ValueError(f"node {nid}.details must be a list of non-empty strings")
            if "note" in node and (not isinstance(node["note"], str) or not node["note"].strip()):
                raise ValueError(f"node {nid}.note must be non-empty text")
        else:
            require_text(node, "label")
        if node.get("cluster") and node["cluster"] not in cluster_ids:
            raise ValueError(f"node {nid} references unknown cluster {node['cluster']}")
        if node.get("shape", "box") not in ALLOWED_SHAPES:
            raise ValueError(f"node {nid} has unsupported shape")
        validate_evidence(node, f"node {nid}", source_ids, schema.endswith("/1.1"))

    rank_groups = spec.get("rank_groups", [])
    if not isinstance(rank_groups, list):
        raise ValueError("rank_groups must be a list")
    for index, group in enumerate(rank_groups, start=1):
        if not isinstance(group, list) or len(group) < 2:
            raise ValueError(f"rank_groups[{index}] must contain at least two node ids")
        if len(set(group)) != len(group) or any(node_id not in node_ids for node_id in group):
            raise ValueError(f"rank_groups[{index}] contains duplicate or unknown node ids")

    edges = spec.get("edges")
    if not isinstance(edges, list) or not edges:
        raise ValueError("edges must contain at least one entry")
    for index, edge in enumerate(edges, start=1):
        if edge.get("from") not in node_ids or edge.get("to") not in node_ids:
            raise ValueError(f"edge references an unknown node: {edge}")
        if edge.get("style", "solid") not in ALLOWED_STYLES:
            raise ValueError(f"edge has unsupported style: {edge}")
        validate_evidence(edge, f"edge {index} ({edge.get('from')}->{edge.get('to')})", source_ids, schema.endswith("/1.1"))


def effective_config(spec: dict, profile_name: str) -> dict:
    config = dict(PROFILES[profile_name])
    visual = spec.get("visual", {})
    for key in config:
        if key in visual:
            config[key] = visual[key]
    colors = dict(ROLE_COLORS)
    for role, pair in visual.get("role_colors", {}).items():
        colors[role] = tuple(pair)
    config["role_colors"] = colors
    config["allow_raster_assets"] = bool(visual.get("allow_raster_assets", False))
    return config


def legacy_parts(node: dict) -> tuple[str, list[str], str | None]:
    parts = [part.strip() for part in str(node.get("label", "")).splitlines() if part.strip()]
    if not parts:
        return node["id"], [], None
    return parts[0], parts[1:], None


def html_label(node: dict, config: dict) -> str:
    if "title" in node:
        title = node["title"].strip()
        details = [str(v).strip() for v in node.get("details", [])]
        note = str(node.get("note", "")).strip() or None
    else:
        title, details, note = legacy_parts(node)
    font = html.escape(str(config["font_family"]), quote=True)
    title_html = html.escape(title).replace("\n", '<BR ALIGN="LEFT"/>')
    rows = [
        f'<TR><TD ALIGN="LEFT"><FONT FACE="{font}" POINT-SIZE="{config["title_font_pt"]:g}" COLOR="{config["text_color"]}"><B>{title_html}</B></FONT></TD></TR>'
    ]
    for detail in details:
        detail_html = html.escape(detail).replace("\n", '<BR ALIGN="LEFT"/>')
        rows.append(
            f'<TR><TD ALIGN="LEFT"><FONT FACE="{font}" POINT-SIZE="{config["body_font_pt"]:g}" COLOR="{config["text_color"]}">{detail_html}</FONT></TD></TR>'
        )
    if note:
        note_html = html.escape(note).replace("\n", '<BR ALIGN="LEFT"/>')
        rows.append(
            f'<TR><TD ALIGN="LEFT" CELLPADDING="2"><FONT FACE="{font}" POINT-SIZE="{config["note_font_pt"]:g}" COLOR="{config["note_color"]}"><I>{note_html}</I></FONT></TD></TR>'
        )
    return '<TABLE BORDER="0" CELLBORDER="0" CELLSPACING="0" CELLPADDING="1">' + "".join(rows) + "</TABLE>"


def build_dot(spec: dict, config: dict) -> str:
    rankdir = spec.get("rankdir", "LR")
    lines = [
        "digraph methodology {",
        (
            f'  graph [rankdir={rankdir}, bgcolor="{config["background"]}", pad=0.08, margin=0, '
            f'nodesep={config["nodesep"]}, ranksep={config["ranksep"]}, splines=polyline, '
            'outputorder=edgesfirst, compound=true, newrank=true];'
        ),
        (
            f'  node [shape=box, style="rounded,filled", fontname={dot_quote(config["font_family"])}, '
            f'fontsize={config["body_font_pt"]}, margin="0.12,0.09", penwidth={config["node_penwidth"]}, '
            'color="#62666A", fillcolor="#F8F9FA"];'
        ),
        (
            f'  edge [fontname={dot_quote(config["font_family"])}, fontsize={config["edge_font_pt"]}, '
            f'fontcolor="#42464A", color="#62666A", penwidth={config["edge_penwidth"]}, arrowsize=0.62];'
        ),
    ]
    clusters = {item["id"]: item for item in spec.get("clusters", [])}
    nodes_by_cluster: dict[str | None, list[dict]] = {None: []}
    for cid in clusters:
        nodes_by_cluster[cid] = []
    for node in spec["nodes"]:
        nodes_by_cluster.setdefault(node.get("cluster"), []).append(node)

    def node_line(node: dict, indent: str = "  ") -> str:
        fill, border = config["role_colors"].get(node.get("role", "neutral"), config["role_colors"]["neutral"])
        shape = node.get("shape", "box")
        return (
            f'{indent}{node["id"]} [label=<{html_label(node, config)}>, shape={dot_quote(shape)}, '
            f'fillcolor={dot_quote(fill)}, color={dot_quote(border)}];'
        )

    for node in nodes_by_cluster.get(None, []):
        lines.append(node_line(node))
    for cid, cluster in clusters.items():
        lines.extend([
            f"  subgraph cluster_{cid} {{",
            f"    label={dot_quote(cluster['label'])};",
            (
                f'    color="{config["cluster_border"]}"; fillcolor="{config["cluster_fill"]}"; '
                f'penwidth=0.8; style="rounded,filled"; fontname={dot_quote(config["font_family"])}; '
                f'fontcolor="#42464A"; fontsize={config["edge_font_pt"]}; margin=12;'
            ),
        ])
        for node in nodes_by_cluster.get(cid, []):
            lines.append(node_line(node, "    "))
        lines.append("  }")
    for group in spec.get("rank_groups", []):
        lines.append("  { rank=same; " + "; ".join(group) + "; }")
    for edge in spec["edges"]:
        attrs = {"style": edge.get("style", "solid")}
        if edge.get("label"):
            attrs["label"] = edge["label"]
        if edge.get("constraint") is False:
            attrs["constraint"] = "false"
        rendered = ", ".join(f"{key}={dot_quote(value)}" for key, value in attrs.items())
        lines.append(f"  {edge['from']} -> {edge['to']} [{rendered}];")
    lines.append("}")
    return "\n".join(lines) + "\n"


def node_text(node: dict) -> str:
    if "title" not in node:
        return str(node.get("label", node["id"]))
    parts = [node["title"], *node.get("details", [])]
    if node.get("note"):
        parts.append(node["note"])
    return "\n".join(parts)


def build_drawio(spec: dict, config: dict, layout: dict, created_at: str) -> str:
    root = ET.Element("mxfile", {
        "host": "app.diagrams.net", "modified": created_at, "agent": "manuscript-to-latex",
        "version": "24.7.17", "type": "device",
    })
    diagram = ET.SubElement(root, "diagram", {"id": spec["filename_stem"], "name": "Page-1"})
    model = ET.SubElement(diagram, "mxGraphModel", {
        "dx": "1200", "dy": "800", "grid": "1", "gridSize": "10", "guides": "1",
        "tooltips": "1", "connect": "1", "arrows": "1", "fold": "1", "page": "1",
        "pageScale": "1", "pageWidth": "1600", "pageHeight": "1000", "math": "0", "shadow": "0",
    })
    graph_root = ET.SubElement(model, "root")
    ET.SubElement(graph_root, "mxCell", {"id": "0"})
    ET.SubElement(graph_root, "mxCell", {"id": "1", "parent": "0"})
    bbox = layout.get("bb", "0,0,720,540").split(",")
    max_y = float(bbox[3]) if len(bbox) == 4 else 540.0
    scale = 96.0 / 72.0
    node_ids: dict[str, str] = {}
    objects = {obj.get("name"): obj for obj in layout.get("objects", []) if obj.get("name")}
    for index, node in enumerate(spec["nodes"], start=2):
        obj = objects.get(node["id"], {})
        pos = str(obj.get("pos", "0,0")).split(",")
        cx, cy = (float(pos[0]), float(pos[1])) if len(pos) >= 2 else (0.0, 0.0)
        width = max(float(obj.get("width", 1.8)) * 96.0, 150.0)
        height = max(float(obj.get("height", 0.8)) * 96.0, 64.0)
        x = cx * scale - width / 2 + 40
        y = (max_y - cy) * scale - height / 2 + 40
        fill, border = config["role_colors"].get(node.get("role", "neutral"), config["role_colors"]["neutral"])
        cell_id = f"n{index}"
        node_ids[node["id"]] = cell_id
        title = html.escape(node.get("title", legacy_parts(node)[0]))
        details = node_text(node).splitlines()[1:]
        value = f"<b>{title}</b>"
        if details:
            value += "<br>" + "<br>".join(html.escape(v) for v in details)
        style = (
            f"rounded=1;whiteSpace=wrap;html=1;fillColor={fill};strokeColor={border};"
            f"fontColor={config['text_color']};fontFamily={config['font_family']};fontSize=10;"
            "align=left;verticalAlign=middle;spacingLeft=8;spacingRight=8;spacingTop=6;"
            "spacingBottom=6;strokeWidth=1;shadow=0;glass=0;"
        )
        cell = ET.SubElement(graph_root, "mxCell", {
            "id": cell_id, "value": value, "style": style, "vertex": "1", "parent": "1",
        })
        ET.SubElement(cell, "mxGeometry", {
            "x": f"{x:.2f}", "y": f"{y:.2f}", "width": f"{width:.2f}",
            "height": f"{height:.2f}", "as": "geometry",
        })
    for index, edge in enumerate(spec["edges"], start=1):
        style = (
            "edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;"
            "endArrow=block;endFill=1;strokeColor=#62666A;strokeWidth=1;fontFamily=Arial;fontSize=9;"
        )
        if edge.get("style") == "dashed":
            style += "dashed=1;"
        cell = ET.SubElement(graph_root, "mxCell", {
            "id": f"e{index}", "value": html.escape(str(edge.get("label", ""))), "style": style,
            "edge": "1", "parent": "1", "source": node_ids[edge["from"]], "target": node_ids[edge["to"]],
        })
        ET.SubElement(cell, "mxGeometry", {"relative": "1", "as": "geometry"})
    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="unicode", xml_declaration=True) + "\n"


def parse_svg_dimension(value: str | None) -> float | None:
    if not value:
        return None
    match = re.match(r"^([0-9.]+)(?:pt|px)?$", value.strip())
    return float(match.group(1)) if match else None


def relative_luminance(color: str) -> float:
    values = [int(color[i:i + 2], 16) / 255.0 for i in (1, 3, 5)]
    linear = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in values]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast_ratio(a: str, b: str) -> float:
    high, low = sorted((relative_luminance(a), relative_luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def machine_qa(svg_path: Path, config: dict) -> dict:
    tree = ET.parse(svg_path)
    root = tree.getroot()
    width_pt = parse_svg_dimension(root.attrib.get("width"))
    height_pt = parse_svg_dimension(root.attrib.get("height"))
    text_nodes = [node for node in root.iter() if node.tag.endswith("text")]
    image_nodes = [node for node in root.iter() if node.tag.endswith("image")]
    font_sizes: list[float] = []
    font_families: set[str] = set()
    for node in text_nodes:
        value = node.attrib.get("font-size")
        if value:
            try:
                font_sizes.append(float(value.replace("px", "").replace("pt", "")))
            except ValueError:
                pass
        if node.attrib.get("font-family"):
            font_families.add(node.attrib["font-family"])
    target_width_mm = float(config["target_width_mm"])
    max_height_mm = float(config["max_height_mm"])
    min_final_required = float(config["minimum_final_font_pt"])
    target_width_pt = target_width_mm / 25.4 * 72.0
    scale = target_width_pt / width_pt if width_pt else None
    final_height_mm = (height_pt / width_pt * target_width_mm) if width_pt and height_pt else None
    min_source_font = min(font_sizes) if font_sizes else None
    min_final_font = min_source_font * scale if min_source_font is not None and scale is not None else None
    checks = {
        "has_vector_text": {"passed": bool(text_nodes), "value": len(text_nodes)},
        "essential_raster_images_absent": {
            "passed": not image_nodes or bool(config["allow_raster_assets"]), "value": len(image_nodes),
        },
        "minimum_final_font": {
            "passed": min_final_font is not None and min_final_font + 1e-6 >= min_final_required,
            "value_pt": round(min_final_font, 3) if min_final_font is not None else None,
            "required_pt": min_final_required,
        },
        "target_height": {
            "passed": final_height_mm is not None and final_height_mm <= max_height_mm + 1e-6,
            "value_mm": round(final_height_mm, 3) if final_height_mm is not None else None,
            "maximum_mm": max_height_mm,
        },
        "text_contrast": {
            "passed": all(contrast_ratio(config["text_color"], fill) >= 4.5 for fill, _ in config["role_colors"].values()),
            "minimum_ratio": round(min(contrast_ratio(config["text_color"], fill) for fill, _ in config["role_colors"].values()), 3),
            "screening_threshold": 4.5,
        },
    }
    blocking = [name for name, result in checks.items() if not result["passed"]]
    warnings: list[str] = []
    if len(text_nodes) > 60:
        warnings.append("High SVG text-element count; inspect density at final size.")
    if width_pt and height_pt and height_pt / width_pt > 1.25:
        warnings.append("Tall aspect ratio; inspect page use and consider a left-to-right layout.")
    return {
        "schema": "methodology-figure-machine-qa/1.0",
        "status": "passed_machine_checks" if not blocking else "failed_machine_checks",
        "target": {"width_mm": target_width_mm, "maximum_height_mm": max_height_mm},
        "observed": {
            "source_width_pt": width_pt, "source_height_pt": height_pt,
            "estimated_final_height_mm": round(final_height_mm, 3) if final_height_mm is not None else None,
            "svg_text_elements": len(text_nodes), "svg_image_elements": len(image_nodes),
            "font_families": sorted(font_families), "minimum_source_font_pt": min_source_font,
            "estimated_minimum_final_font_pt": round(min_final_font, 3) if min_final_font is not None else None,
        },
        "checks": checks,
        "blocking_failures": blocking,
        "warnings": warnings,
        "limitations": [
            "Target-size estimates assume proportional scaling to the declared width.",
            "This screening does not establish scientific correctness, accessibility, or journal compliance.",
            "Human inspection of the standalone figure and compiled manuscript remains required.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--profile", choices=sorted(PROFILES), default="publication")
    parser.add_argument(
        "--enable-svg-generation",
        action="store_true",
        help="Explicitly opt in to the currently disabled SVG generation route.",
    )
    args = parser.parse_args()
    if not args.enable_svg_generation:
        raise SystemExit(
            "SVG generation is disabled by default; pass --enable-svg-generation "
            "only after explicit user authorization"
        )
    spec_path = args.spec.resolve()
    output = args.output_dir.resolve()
    if not spec_path.is_file():
        raise SystemExit(f"missing figure specification: {spec_path}")
    if output.exists() and any(output.iterdir()):
        raise SystemExit(f"output directory must be new or empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    spec = json.loads(spec_path.read_text(encoding="utf-8-sig"))
    try:
        validate(spec)
    except ValueError as exc:
        raise SystemExit(f"invalid figure specification: {exc}") from exc
    config = effective_config(spec, args.profile)
    sources = []
    for item in normalized_sources(spec):
        path = Path(item["path"]).resolve()
        if not path.is_file():
            raise SystemExit(f"missing source file: {path}")
        sources.append({"id": item["id"], "path": str(path), "sha256": sha256(path)})
    dot_exe = shutil.which("dot")
    if not dot_exe:
        raise SystemExit("Graphviz dot was not found on PATH")

    created_at = dt.datetime.now(dt.timezone.utc).isoformat()
    normalized_spec = output / "figure_spec.json"
    normalized_spec.write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    stem = spec["filename_stem"]
    dot_path = output / f"{stem}.dot"
    dot_path.write_text(build_dot(spec, config), encoding="utf-8", newline="\n")

    exports: dict[str, dict] = {}
    commands: list[dict] = []
    for fmt, extra in (("pdf", []), ("svg", []), ("png", ["-Gdpi=600"])):
        destination = output / f"{stem}.{fmt}"
        command = [dot_exe, f"-T{fmt}:cairo" if fmt in {"pdf", "png"} else "-Tsvg", *extra, str(dot_path), "-o", str(destination)]
        completed = subprocess.run(command, text=True, encoding="utf-8", errors="replace", capture_output=True)
        commands.append({"command": command, "return_code": completed.returncode, "stderr": completed.stderr.strip()})
        if completed.returncode != 0 or not destination.is_file() or destination.stat().st_size == 0:
            raise SystemExit(f"Graphviz {fmt} export failed: {completed.stderr.strip()}")
        exports[fmt] = {"path": destination.name, "sha256": sha256(destination), "bytes": destination.stat().st_size}

    layout_command = [dot_exe, "-Tjson", str(dot_path)]
    layout_run = subprocess.run(layout_command, text=True, encoding="utf-8", errors="replace", capture_output=True)
    commands.append({"command": layout_command, "return_code": layout_run.returncode, "stderr": layout_run.stderr.strip()})
    if layout_run.returncode != 0:
        raise SystemExit(f"Graphviz JSON layout export failed: {layout_run.stderr.strip()}")
    layout = json.loads(layout_run.stdout)
    drawio_path = output / f"{stem}.drawio"
    drawio_path.write_text(build_drawio(spec, config, layout, created_at), encoding="utf-8", newline="\n")

    evidence_map = {
        "schema": "methodology-figure-evidence-map/1.0",
        "figure_id": spec["figure_id"],
        "sources": sources,
        "nodes": {node["id"]: node.get("evidence", []) for node in spec["nodes"]},
        "edges": [
            {"from": edge["from"], "to": edge["to"], "label": edge.get("label", ""), "evidence": edge.get("evidence", [])}
            for edge in spec["edges"]
        ],
    }
    evidence_path = output / "evidence_map.json"
    evidence_path.write_text(json.dumps(evidence_map, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")

    caption_path = output / "caption.md"
    caption_path.write_text(spec["caption"].strip() + "\n", encoding="utf-8", newline="\n")
    design_brief_path = output / "design_brief.md"
    design_brief_path.write_text(
        "# Methodology figure design brief\n\n"
        f"- Profile: `{args.profile}`\n"
        f"- Reading direction: `{spec.get('rankdir', 'LR')}`\n"
        f"- Declared final width: {config['target_width_mm']} mm\n"
        f"- Font: {config['font_family']}\n"
        "- Authoritative sources: reviewed JSON contract, DOT, and Draw.io XML\n"
        "- Reference-generated imagery: not used as evidence or final artwork\n"
        "- Visual language: opaque white background, semantic light fills, restrained borders, no gradients or shadows\n",
        encoding="utf-8", newline="\n",
    )

    qa = machine_qa(output / f"{stem}.svg", config)
    qa_path = output / "machine_qa.json"
    qa_path.write_text(json.dumps(qa, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    if qa["blocking_failures"]:
        raise SystemExit(f"methodology figure failed machine QA: {', '.join(qa['blocking_failures'])}")

    version = subprocess.run(
        [dot_exe, "-V"], text=True, encoding="utf-8", errors="replace", capture_output=True
    )
    editable_sources = []
    for kind, path in (("dot", dot_path), ("drawio", drawio_path)):
        editable_sources.append({"kind": kind, "path": path.name, "sha256": sha256(path), "bytes": path.stat().st_size})
    manifest = {
        "schema": spec["schema"],
        "created_at": created_at,
        "figure_id": spec["figure_id"],
        "filename_stem": stem,
        "title": spec["title"],
        "caption": spec["caption"],
        "alt_text": spec["alt_text"],
        "callout": spec["callout"],
        "insertion": spec["insertion"],
        "orientation": spec.get("orientation", "portrait"),
        "visual_contract": config,
        "specification": {"path": normalized_spec.name, "sha256": sha256(normalized_spec)},
        "source_files": sources,
        "generator": {"name": "Graphviz dot + native Draw.io XML", "version": (version.stderr or version.stdout).strip(), "commands": commands},
        "exports": exports,
        "editable_source": {"path": dot_path.name, "sha256": sha256(dot_path)},
        "editable_sources": editable_sources,
        "evidence_map": {"path": evidence_path.name, "sha256": sha256(evidence_path)},
        "caption_file": {"path": caption_path.name, "sha256": sha256(caption_path)},
        "design_brief": {"path": design_brief_path.name, "sha256": sha256(design_brief_path)},
        "machine_qa": {"path": qa_path.name, "sha256": sha256(qa_path), "status": qa["status"]},
        "human_visual_review": {"status": "pending", "path": None, "sha256": None},
        "evidence_boundary": "Methodology diagram only; nodes and edges are derived from recorded sources and are not independent experimental evidence.",
    }
    manifest_path = output / "asset_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"Created methodology figure: {output}")
    print(f"Manifest: {manifest_path}")
    print(f"Machine QA: {qa['status']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
