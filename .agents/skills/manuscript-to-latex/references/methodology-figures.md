# Methodology figure workflow

Use this stage for model architecture, study flow, preprocessing, or experiment-protocol diagrams that can be derived from verified project records. It does not authorize inventing missing implementation details. The intended result is a restrained, journal-scale information graphic, not a generic office flowchart.

Before composing the figure, identify the author-confirmed research object and
the figure's role in the manuscript. When the paper presents a promoted method,
the primary methodology figure must explain the method itself: its architecture,
information flow, component interactions, objectives, training versus inference
paths, and ablation switches where applicable. A diagram of baseline screening,
candidate discovery, experiment scheduling, or manuscript production is a
provenance/supplement figure and must not replace that primary method figure.
If no method has been author-confirmed, stop rather than infer the paper object
from whichever row has the highest observed metric.

## Active default: no automatic SVG generation

The project-level default is `svg_generation_enabled=false`. This controls vector
reconstruction only. For the independently configured conceptual raster route,
follow [raster-generation.md](raster-generation.md); retain original generated
images without converting to SVG. Under this setting:

1. Freeze the methodology text, module/visual-entity description, evidence
   locators, figure message, topology, exact short labels, caption, alt text,
   palette/accessibility requirements, and avoid list.
2. Do not generate or reconstruct SVG; do not call
   `package_illustrated_methodology_figure.py` or
   `build_methodology_figure.py`; and do not treat Graphviz as an automatic
   fallback.
3. An unchanged author-supplied SVG may be accepted only as an existing input
   with matching intake hash and complete review provenance. An author-approved
   raster, supplied or generated through the selected image route, may use the
   raster packaging route. Verified data
   plots should be exported as PDF/PNG while the switch is off.
4. If no acceptable existing figure is available, keep the brief and manual-art
   handoff, write `status: no_figures`, and identify the unresolved figure in
   `figure_review_report.md`. A configured conceptual raster candidate may be generated for review, but
   cannot be represented as author-approved merely to fill the slot.

## Explicit opt-in route: AutoFigure-Edit-style illustrated figure

The following route is dormant unless the user explicitly enables SVG
generation for the run. Both SVG helper scripts require the
`--enable-svg-generation` flag as a second safeguard.

1. **Two-file intake.** Read the methodology text and a separate module/visual-entity description. The methodology governs scientific truth; the module file states what must be visually depicted, emphasized, coupled, or caveated.
2. **Visual brief.** Compress the two inputs into a deidentified Stage-1 prompt containing the figure message, visible entities, topology, visual metaphors, palette, exact short labels, and an explicit avoid list. Prefer mechanism-specific entities such as WSI/patch mosaics, token streams, network layers, spatial grids, probability curves, timelines, or cohort funnels.
3. **Stage-1 draft.** Generate or import a polished raster composition. Treat it as a reference image only. Inspect topology and icon semantics; ignore or correct its text and numbers.
4. **Entity decomposition.** Inventory every icon, text block, connector, plot-like inset, and stage boundary. AutoFigure-Edit may use SAM placeholders; a local workflow may instead use an explicit entity table. Either route must preserve stable IDs for reconstruction.
5. **Editable SVG reconstruction.** After explicit enablement, recreate the accepted composition with native SVG groups, paths, shapes, text, and markers. Do not embed the Stage-1 image. Verify every scientific label and connection against the inputs.
6. **Critic/refine and fidelity gate.** Compare the SVG rendering with the Stage-1 reference and score position (icons, text, arrows, boundaries) separately from style (scale, hierarchy, line work, palette). Any text/shape overlap, panel-border collision, connector drift, clipping, or materially weaker hierarchy blocks SVG acceptance. Do not waive a visible defect merely because the file is editable.
7. **Choose the honest final format.** Use the accepted SVG when it passes. If reconstruction remains worse than the reference after bounded revisions, or the author explicitly prioritizes fidelity over editability, retain the reviewed high-resolution raster as the final figure. Record that choice; do not wrap the raster in SVG and describe it as editable.
8. **Packaging and QA.** Run `package_illustrated_methodology_figure.py --enable-svg-generation` for the explicitly enabled native-SVG route or `package_raster_methodology_figure.py` for an existing author-approved raster. Inspect its manifest and machine QA, then compile and review the manuscript page.

After explicit enablement, use `build_methodology_figure.py` only when the user requests a restrained conventional flowchart, when the method has no useful visual entities, or when a rapid text-first fallback is appropriate. Pass `--enable-svg-generation`; absence of that flag must stop the script.

## Two input files

The methodology file may be long-form Markdown or plain text. The companion module file should state:

- the figure's single message;
- module names and boundaries;
- visible scientific entities for each module;
- required arrows, branch/merge logic, feedback, or parameter coupling;
- short labels or equations that must appear exactly;
- caveats that must remain visible;
- intended reading direction, target width, palette, and avoid list.

The module file is not allowed to introduce scientific facts absent from the methodology. Resolve disagreements in favor of the methodology and report them.

## Structured fallback specification

Prefer schema `methodology-figure/1.1`; schema `1.0` is accepted only to rebuild legacy figures.

Top-level fields:

- `figure_id`: LaTeX/Pandoc identifier beginning with `fig:`;
- `filename_stem`, `title`, `caption`, and `alt_text`;
- `callout`: a short in-text sentence containing the matching `\\ref{fig:...}` reference;
- `source_files`: objects with unique `id` and absolute `path` values;
- `insertion.before_heading`: an exact cleaned Markdown heading before which the figure will be inserted;
- `rankdir`: `LR` for most pipelines or `TB` when the manuscript column/height makes it demonstrably clearer;
- `orientation`: `portrait` or `landscape` for manuscript insertion;
- `visual`: a publication contract containing `target_width_mm`, `max_height_mm`, `font_family`, `body_font_pt`, `edge_font_pt`, `minimum_final_font_pt`, and optional role-color overrides;
- `clusters`: optional labeled stages with unique IDs;
- `nodes`: unique IDs, `title`, optional `details` and `note`, cluster, semantic role, and `evidence` list;
- `edges`: existing source/target IDs, optional label/style, and `evidence` list.

Each evidence entry has `source_id` and a non-empty `locator`, such as a heading, equation, table, JSON key, or stable line range. Global source-file listing alone is insufficient under schema `1.1`.

Example element:

```json
{
  "id": "regional",
  "title": "Directed Regional Alignment",
  "details": ["8 x 8 and 16 x 16 grids", "Occupancy-weighted coverage"],
  "note": "Internal weak supervision; not cell-level truth",
  "cluster": "spatial",
  "role": "spatial",
  "evidence": [
    {"source_id": "method", "locator": "Sections 3.2-3.5; equations for C_n and delta_n"}
  ]
}
```

The generated manifest records the specification and source hashes, Graphviz version and commands, editable-source hashes, output hashes, element-level evidence map, target-size estimates, SVG raster/text inspection, and machine-QA status.

## Choose the figure's explanatory role

Distinguish a study/experiment flowchart (what happened in what order), a model
architecture overview (which components connect), and a method-principle figure
(how the proposed operations change or combine scientific representations).
Match the requested role before designing the layout; none substitutes for the
others merely because it contains all module names.

For a method-principle figure, state the mechanism the reader should understand
and depict the relevant entities, relationships, operation and resulting
representation. For example, graph neighborhoods, token interactions, soft
membership, feature fusion or message passing can be shown as mechanism insets.
Choose entities from the verified implementation, not from this list by default.
Use a small architecture context where helpful, but give the mechanism the main
visual space. Layer dimensions, training schedules, ablation tables and exhaustive
equations belong in the caption or a separate figure when they crowd out that
explanation. Do not impose a fixed number of boxes, panels or stages.

Abstract geometry or symbolic values must be labeled illustrative, not presented
as observed attention, segmentation, patient imagery or measured improvement.
Distinguish soft weights from hard partitions, sums from averages, learned from
fixed entities, and feature transformations from training-only supervision.
Do not imply an operation necessarily improves or sharpens a representation
unless the evidence supports that claim.

For a requested principle figure, visual review must answer: can the reader see
what interacts and how the representation is formed without reading the entire
caption? A chain of named boxes, paragraphs inside cards, or an experiment/ablation
schedule fails this explanatory check even if labels and hashes are correct.
A conventional flowchart remains appropriate when the user requests one or the
scientific subject is itself a procedure.

## Publication visual grammar

- Use a clear reading order appropriate to the figure's role. Split study flow, architecture and mechanism views when combining them becomes dense at final size.
- Separate short bold module titles from supporting details. Keep ordinary node text to about three concise lines; move qualifications that apply to the whole figure into the caption.
- Use recognizable scientific entities and small mechanism insets. Reserve cards for grouping; a module should not be only a paragraph inside a rounded rectangle when an honest visual metaphor exists.
- Use three to five semantic hues plus neutrals. Color must be redundant with titles, stage labels, line style, or position.
- Use a white or explicitly opaque background; avoid gradients, shadows, bevels, glass effects, decorative 3-D, and stock-office clip art.
- Keep arrows thin and direct. Label only relationships that would otherwise be ambiguous; avoid crossings and repeated labels.
- Design at the declared physical width. As a general journal-style starting point, use Arial/Helvetica, body text around 7-8 pt, edge labels around 6.5-7 pt, and ordinary strokes around 0.7-1.1 pt, then verify the exact target journal and phase.
- Prefer genuine WSI/patch/heatmap thumbnails when they are necessary to understand a computational-pathology pipeline. Do not generate or cosmetically alter patient-derived imagery.

## Visual-fidelity gate

Inspect the full figure and targeted crops at final manuscript scale. A candidate fails if any of the following is present:

- text intersects a panel edge, icon, gauge, plot, or another label;
- a gauge, heatmap, or thumbnail intrudes into a neighboring visual entity without an intentional overlap specified in the brief;
- an arrowhead is clipped, touches the wrong boundary, terminates ambiguously, or obscures text;
- reconstruction changes module spacing or hierarchy enough to make the Stage-1 reference easier to read;
- downscaling makes ordinary labels unreadable even though the source-size render looks acceptable.

Use editability as a preference, not a reason to accept a visually inferior figure. Raster fallback requires explicit author acceptance, an effective resolution appropriate for the intended width, a preserved original, and a manifest that labels the asset non-editable.

## Evidence boundary

- Derive every scientific label and connection from the listed sources.
- Use words such as `internal`, `weakly supervised`, `exploratory`, or `not cell-level ground truth` wherever omission would materially overstate evidence.
- Do not display patient-level labels as pixel/cell annotations.
- Do not call a viewed test set independent, external, prospective, or confirmatory.
- Do not add performance plots or uncertainty intervals when only aggregate summaries are available.
- Keep the figure conceptual when tensor shapes or implementation details are not verified.
- Do not reproduce the distinctive composition of one published figure. Derive a general style brief from several legitimate references and retain source/permission notes for any reused asset.

## Review sequence

1. Review the methodology and module-description files together; list any conflict or unsupported visual request.
2. Review the Stage-1 raster for composition and visual entities, not textual accuracy.
3. If SVG generation was explicitly enabled, inspect the reconstructed SVG source and render side by side. Confirm it contains native editable groups and no embedded Stage-1 raster. Apply the visual-fidelity gate before choosing it. Otherwise use the independent raster route if configured, or retain the manual-art handoff.
4. Only with explicit enablement, run `scripts/package_illustrated_methodology_figure.py --enable-svg-generation` into a new empty directory. Use `scripts/package_raster_methodology_figure.py --author-approved-raster` only for an existing, reviewed raster the author accepts; it is not a bypass for generating substitute artwork.
5. Inspect `machine_qa.json`, then visually inspect the standalone PDF/SVG at final manuscript width and review the caption. Resolve warnings or record their disposition; do not relabel an automated pass as human approval.
6. Pass the generated `asset_manifest.json` to `scripts/prepare_package.py --figure-manifest`.
7. Compile and inspect the entire manuscript page by page, including float placement and the first in-text callout. A caption alone does not satisfy the figure-citation gate.

Prefer a single readable overview over an overloaded diagram. Split study flow and model architecture only when one figure is illegible at full-page width.

## Canonical artifact placement

In an ordered manuscript pipeline, package every accepted figure under
`06_submission/figures/<figure-id>/`. Keep the complete reviewable chain there:

- methodology and module-description snapshots or equivalent source locators;
- the visual brief and exact short-label inventory;
- the Stage-1 composition reference when that route was used;
- entity-decomposition records with stable IDs;
- native editable source, or the original author-approved raster when the
  fidelity fallback was chosen;
- `asset_manifest.json`, machine QA, human visual review, captions, alt text,
  hashes, generator details, and the explicit Graphviz/fallback reason if any.

Use `06_submission/figures/_work/` only for rejected or intermediate
iterations; it is excluded from the normalized delivery bundle. Never promote
an iteration merely by copying it into `latex/figures/`.

After acceptance, copy only the assets actually consumed by TeX into
`06_submission/latex/figures/`. At `06_submission/figures/figure_manifest.json`,
write aggregate schema `manuscript-figure-artifacts/1.0` with `status` equal to
`reviewed` and one record per figure containing:

```text
figure_id, role, workflow, artifact_directory, asset_manifest,
accepted_source(path,sha256,editable), packaged_assets(path,sha256),
visual_review(status,path,sha256)
```

The visual-review status must be `passed`; hashes must match the preserved
files. Summarize cross-figure checks and any accepted limitations in
`06_submission/figures/figure_review_report.md`. This aggregate contract makes
the distinction explicit: `figures/` explains and audits how a visual became
acceptable, while `latex/figures/` contains the final typesetting copies.
