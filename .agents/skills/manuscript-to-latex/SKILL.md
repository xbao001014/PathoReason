---
name: manuscript-to-latex
description: Convert a scientifically frozen, evidence-audited manuscript and bibliography into a compiled, journal-adapted LaTeX submission package with deterministic checks, provenance-tracked methodology figures, rendered-PDF QA, and versioned deliverables. Use after substantive manuscript drafting when the user wants LaTeX, a submission PDF/source bundle, Modern Pathology or Journal of Pathology Informatics formatting, method or study flowcharts, anonymous/title-page separation, figure packaging, or pre-submission technical validation. Do not use to invent missing science, rerun experiments, fabricate declarations, or treat an incomplete draft as submission-ready.
---

# Manuscript to LaTeX

Create a reproducible typesetting and submission package without changing the scientific claim boundary.

## PathoReason hosted manuscript review

When the host provides `MANUSCRIPT AUTHOR WORKFLOW`, use its five gates inside
research stage 5: blueprint → draft → review → scientific → delivery. This host
binding replaces legacy per-phase author-gate storage and duplicate confirmation
prompts, while retaining this skill's substantive evidence and quality checks.
Prepare routine work autonomously within the user's scope; register actual
artifacts and request the current gate through `checkpoint.manuscript_review`
with `outcome=needs_input`. Only the user's public review action advances a gate.
Never call review-decision endpoints, write author signatures/approval receipts,
or interpret tool auto-approval, ordinary “continue”, or a model-generated report
as author approval. Local `gate_status.json` files, if a helper requires them,
are work notes and confer no approval. Do not run the old experiment/workflow
store or modify its data. Use versioned pipeline subdirectories beneath
`<workspace>/manuscript/` (an allowed publication area).

The blueprint bundles inventory, test-use history, writing subject and claim
boundaries, including exploratory or negative results; no positive-result or
novel-method promotion is required to test the downstream writing path. Draft
review includes actual figures and a figure manifest, not image placeholders.
A blocked pre-review integrity check returns to the draft; a clean check can
proceed automatically to model-assisted review, explicitly labeled as such.
Review findings require the author's per-issue decisions and rationale. Freeze
requires a fresh integrity report tied to the exact revised manuscript; earlier
audit results are not reusable approval. Final delivery binds the approved
scientific packet plus PDF, source package, actual page QA and open-items list.
Publication/submission and independent scientific approval remain separate.

Carry original author statements forward, check them before asking again, and
make new versions for changes. Only missing facts necessary for the CURRENT
review go in `author_questions`; submission-only gaps remain explicit in the
checklist and permit an internal preview. Unresolved integrity blockers cannot
be waived. Approved material changes require reopening the affected node and
renewing downstream approval; preserve previous files, hashes and decisions.

## Required inputs

Before submission mode, locate or obtain:

- the frozen manuscript source (`.md` or `.tex`);
- the verified `.bib` bibliography;
- the current claim/integrity or test-use manifest, if the upstream project has one;
- the author-confirmed paper-subject or method-promotion contract, when the
  upstream project used automated candidate discovery;
- all cited figures, editable tables, captions, and supplements;
- target journal and article type;
- author, affiliation, corresponding-author, ethics, funding, competing-interest, contribution, data-availability, and AI-use declarations.

If author-owned metadata are missing, continue only in `preview` mode and record the gaps. Never infer declarations from silence.

## Ordered workflow boundary

For the ordered manuscript pipeline, method illustration generation belongs to
M4 drafting and its author gate. This skill supplies the raster-generation
capability there, without authorizing final formatting. After scientific freeze,
reuse the approved draft images; missing or changed scientific figures require
a draft revision, not new image generation during typesetting. The legacy
all-at-once route remains available only outside that ordered boundary.

## Workflow

1. Read [input-output-contract.md](references/input-output-contract.md).
2. Inspect upstream status and preserve its restrictions. A previously viewed test set remains exploratory everywhere, including the abstract, tables, captions, limitations, and conclusion.
3. Select the journal adapter:
   - read [modern-pathology.md](references/modern-pathology.md) for Modern Pathology;
   - read [journal-of-pathology-informatics.md](references/journal-of-pathology-informatics.md) for JPI;
   - otherwise use the generic profile and create a venue-requirements gap list.
4. Recheck the current official Guide for Authors when preparing a real submission. Timestamp the source URL and verification date. If the official page is inaccessible or contradicts the local profile, stop submission labeling, retain a compilable preview, and report the discrepancy.
5. When a method, study, or experiment figure is requested or missing, read [methodology-figures.md](references/methodology-figures.md). First bind the figure subject to the manuscript's author-confirmed research object. For a promoted method paper, the primary methodology figure must explain that method's architecture, information flow, component interactions, objectives, training/inference paths, and ablation switches as applicable. Baseline screening, candidate discovery, or experiment orchestration may appear only as provenance or supplementary material and cannot substitute for the primary method figure. **Automatic SVG generation and reconstruction are currently disabled by default.** Produce the author-reviewable methodology text, companion module/visual-entity description, visual brief, exact-label inventory, caption, alt text, and manual-art requirements, but do not create an SVG or call the SVG scripts unless the user explicitly enables SVG generation. Raster generation is independently routed by `method_figure_generation`: Codex retains its available image tool; other runtimes may use the configured image API. Follow [raster-generation.md](references/raster-generation.md). SVG being disabled does not prohibit an explicitly configured conceptual raster route. An unchanged author-supplied SVG remains an input asset and must retain its intake hash. An author-approved raster (supplied or generated through the selected route) or a truthful data-derived PDF/PNG may be packaged when appropriate. Unapproved generated candidates remain in review previews; if no acceptable figure is available, record `status: no_figures` and the unresolved figure task. Do not invent scientific content or use raster generation to evade evidence checks. Generated candidates require visual review and author acceptance before final packaging. The AutoFigure-Edit and Graphviz routes remain documented only as explicit opt-in/legacy routes.
6. Before LaTeX conversion, preserve each accepted figure package in the
   standalone figure artifact tree described under **Output location**. This is
   the auditable source-of-truth for the brief, composition reference, entity
   decomposition, editable or author-approved raster source, manifest, QA,
   review, and provenance. Then run `scripts/prepare_package.py` to create a new
   versioned output directory. Pass each reviewed figure manifest with
   `--figure-manifest`; the script copies only accepted rendered/editable assets
   into the derived package's `figures/` directory. For wide tables, prefer
   uniform table-body scaling and nonbreaking atomic numeric estimates over
   cell-specific wrapping; inspect the result at final page size. Do not edit
   or overwrite the source manuscript.
   When the selected journal profile requires an unstructured abstract, the derived package merges supplied structured abstract parts into one paragraph, preserves the separate keywords line, and records the transformation without overwriting the frozen source.
   Remove standalone Markdown thematic breaks immediately before ATX section headings from the derived package; numbered journal headings already provide the section boundary, and Pandoc would otherwise render the marker as an unintended horizontal rule. Record the removal in the manifest.
7. Prepare other figures under [visual-assets-policy.md](references/visual-assets-policy.md).
8. Run `scripts/compile_latex.py` in a fresh build directory. A PDF counts as successful only when the process exits successfully, the PDF is newly generated and nonempty, and unresolved citations/references are absent.
9. Visually inspect every rendered PDF page using the `pdf` skill. Check equations, tables, figures, float placement, line breaks, captions, page numbering, anonymity, and glyphs.
10. Apply [latex-quality-gates.md](references/latex-quality-gates.md). Package only when all blocking gates pass.

## Commands

Preview conversion:

```powershell
python scripts/prepare_package.py --manuscript <draft.md> --bibliography <references.bib> --journal modern-pathology --mode preview --output-dir <new-output-dir>
python scripts/compile_latex.py --package-dir <new-output-dir>
```

Use `--line-numbers off` or `on` and `--section-numbering off` or `on` only when the author explicitly requests a layout override; the default `auto` preserves the journal adapter. The package manifest records both resolved settings and their source options.

Explicitly enabled legacy SVG methodology route and preview conversion:

```powershell
python scripts/package_illustrated_methodology_figure.py --methodology <methodology.md> --modules <module-description.md> --svg <editable.svg> --stage1-image <composition-draft.png> --caption <caption.md> --alt-text <alt-text.md> --figure-id <fig:id> --filename-stem <stem> --output-dir <new-figure-dir> --enable-svg-generation
python scripts/prepare_package.py --manuscript <draft.md> --bibliography <references.bib> --journal modern-pathology --mode preview --figure-manifest <new-figure-dir>/asset_manifest.json --output-dir <new-output-dir>
python scripts/compile_latex.py --package-dir <new-output-dir>
```

Author-approved raster-fidelity fallback:

```powershell
python scripts/package_raster_methodology_figure.py --methodology <methodology.md> --modules <module-description.md> --image <approved-figure.png> --author-approved-raster --caption <caption.md> --alt-text <alt-text.md> --figure-id <fig:id> --filename-stem <stem> --output-dir <new-figure-dir>
python scripts/prepare_package.py --manuscript <draft.md> --bibliography <references.bib> --journal modern-pathology --mode preview --figure-manifest <new-figure-dir>/asset_manifest.json --output-dir <new-output-dir>
python scripts/compile_latex.py --package-dir <new-output-dir>
```

Submission conversion with author-owned metadata:

```powershell
python scripts/prepare_package.py --manuscript <frozen.md> --bibliography <references.bib> --journal journal-of-pathology-informatics --mode submission --metadata <metadata.json> --upstream-manifest <integrity.json> --declaration-form <elsevier-declaration.docx> --output-dir <new-output-dir>
python scripts/compile_latex.py --package-dir <new-output-dir>
```

For Modern Pathology submission mode, pass `--cover-letter <file>` instead of the JPI declaration-form argument. The scripts copy journal-specific auxiliary files into the package but never author them from unstated facts.

Use absolute paths when working across project roots. On SSH/Linux, use `python3` if `python` is unavailable.

## Scientific invariants

- Preserve all reported values, cohort counts, labels, comparator membership, test-selection history, limitations, and citation keys unless the user separately authorizes substantive revision.
- Remove only explicit internal traceability markers such as `[claim:...]` and `[evidence:...]`; log the transformation.
- Do not generate ROC/PR curves, uncertainty bands, saliency maps, or patient-level plots from aggregate means.
- Do not create or alter primary research images with generative tools.
- A methodology figure is a traceable representation of supplied methods, not new scientific evidence. Its labels, connectors, icons, and mechanisms must be traceable to the methodology and module-description inputs. Structured schema `methodology-figure/1.1` remains available for strict node/edge inventories and legacy regeneration.
- Do not turn a method-discovery workflow into the primary figure of a method
  paper. Baselines are comparators; the promoted method is the figure subject.
- Treat declarations and author identities as supplied data, not boilerplate.
- Do not upload an unpublished manuscript or patient-derived material to an external service without explicit authorization.
- A successful compile is not equivalent to submission readiness.

## Visual tool routing

- Before generating a method figure, distinguish principle, architecture and
  procedure views using [methodology-figures.md](references/methodology-figures.md).
  Review the requested explanatory role, not just the presence of module labels.
- Use `scientific-visualization` for plots derived directly from verified data and for accessibility/export audits.
- While `svg_generation_enabled=false`, do not run AutoFigure-Edit reconstruction, Graphviz SVG export, local SVG reconstruction, or either SVG helper script. Preserve a method-centered brief; use the independent raster route when configured, otherwise retain the manual handoff. Export verified data plots as PDF/PNG rather than SVG.
- Only after the user explicitly enables SVG generation may the AutoFigure-Edit-style reconstruction route be used. Never wrap a raster in an SVG container and call it editable. Graphviz remains an opt-in legacy fallback, not the default figure style.
- Do not upload unpublished text or patient-derived material to an external provider without explicit authorization. Abstract or deidentify Stage-1 prompts when needed.
- Use the selected image tool only for a clearly labeled conceptual method illustration or graphical abstract when journal policy permits it; never use it for quantitative results, histology, patient imagery, or evidence diagrams.
- Use `pdf` for rendered-page QA before delivery.

## Output location

For projects using `_manuscript_pipeline`, use these distinct locations:

```text
<project>/_manuscript_pipeline/06_submission/
  figures/
    figure_manifest.json
    figure_review_report.md
    <figure-id>/
      asset_manifest.json
      ...brief, reference, decomposition, accepted source, QA, review, provenance...
    _work/                         # transient iterations; excluded from delivery
  latex/
    figures/                       # accepted copies consumed by TeX only
    manuscript.tex
    manuscript.pdf
```

`figures/` and `latex/figures/` are not aliases. The former preserves the
figure evidence chain; the latter is the minimal final typesetting payload.
Write aggregate schema `manuscript-figure-artifacts/1.0` to
`figures/figure_manifest.json`, binding each accepted source, passing visual
review, and packaged copy by relative path and SHA-256. If the manuscript has
no figures, still write the manifest with `status: no_figures`, an empty
`figures` list, and explain the decision in `figure_review_report.md`.

For non-orchestrated use, create a new user-approved versioned output directory
and apply the same separation when practical. Keep the original manuscript
intact and report all generated paths.
