---
name: pathology-figures
description: Plan, generate, audit and bind evidence-backed pathology MIL figures for classification, multilabel prediction, regression, multi-target regression and survival manuscripts. Routes numerical plots, conceptual diagrams and real tissue images separately; never reconstructs histology from features.
metadata:
  version: "1.0"
---

# Pathology research figures

Use the author-confirmed research subject and TaskSpec, not a default method-paper narrative. Before confirmation, produce figure candidates and missing-input inventories only. The host manuscript workflow owns approvals, versioning and phase order.

## Select the route from the evidence

For a requested conceptual pathology illustration during draft, explicitly load
the applicable figure skills and read manuscript-to-latex's
`references/methodology-figures.md` and `references/raster-generation.md`.
On PathoReason use the configured Seedream route via `scripts/study_io.py image`.
Do not substitute a code-generated experiment block chart for this request.
Record actual companion-file reads, generation receipt and image QA; native
file listings do not prove those reads. Generated tissue motifs are schematic,
not patient histology. Numeric plots and real specimen panels keep their routes.

- Complete paper figure planning, evidence inventory, cross-figure QA and delivery packaging: read `../pathology-mil-paper-figures/SKILL.md` and its task-specific references. Preserve this router's five-task and manuscript binding rules.

- Numeric results: read `../scientific-visualization/SKILL.md`. Use verified predictions and metric records with the declared patient split, target order, units, missing denominators and validation selection rule. Preserve negative and undefined results. No invented measurements or fold uncertainty for a single holdout.
- Conceptual study or method figures: read `../scientific-schematics/SKILL.md` for visual design and review guidance. The host's `method_figure_generation` settings control image execution; upstream OpenRouter examples do not change the configured provider, model or budget. Exact method topology requires executed source/configuration binding; a manual brief is not verified architecture. Code-based flow diagrams remain suitable for exact cohort counts. Do not send patient material to an image service.
- Real tissue overview, masks or patch panels: read `../histolab/SKILL.md` and its visualization/coordinate references. Require a real image source, source hash, slide/patch mapping and selection rule; record pyramid level and downsample. Physical scale bars require calibrated X/Y MPP. Keep the optional Histolab/OpenSlide environment isolated; installing this skill does not install that runtime or authorize feature extraction. Do not automatically install heavy Histolab/OpenSlide dependencies.
- Attention overlays additionally require aligned patch coordinates, checkpoint identity and actual attribution values. Attention is not a tumor annotation, causal explanation or calibrated probability. With features only, report missing image/coordinate inputs and produce no tissue heatmap.

## Five-task figure rules

| Task | Supported evidence-backed plots | Additional constraints |
| --- | --- | --- |
| Single-label classification | confusion matrix, binary or per-class ROC/PR | fixed class order, positive class and decision rule; preserve undefined curves |
| Multilabel classification | per-label ROC/PR, target coverage | labels may coexist; missing is not negative; macro/micro are distinct |
| Single regression | observed/predicted, residuals | original outcome units, equal axes where appropriate |
| Multi-target regression | per-target prediction/residual panels | preserve target-specific scales and missing denominators; no physical-unit macro error |
| Survival | event/censor summaries, within-partition risk diagnostics | risk is not survival probability; no pooled uncalibrated CV risk or invented KM/HR/calibration |

## Workflow integration

The registered figure providers and contracts live in `packages/core/experiment_agent/manuscript_assets.py` and `workflow_templates/extensions.py`. Use the provider receipt, reproduction script, caption, alt text, exact source hashes and versioned files. Never edit frozen inputs or an approved image in place.

During planning, build a figure inventory with required/optional role, evidence and unavailable inputs. During draft, insert actual relative image links and bind each image, caption and source version in `03_manuscript/figures/asset_bindings.json`. Inspect the rendered image at final size; record findings, not an invented quality score. Draft approval reviews the exact asset bytes. Integrity, freeze and delivery recheck bindings; changed source, image or caption requires a new reviewed revision. Formatting cannot manufacture a missing scientific figure.

For prediction/prognosis/comparison studies, the principal schematic explains the study design and evaluation. For exploratory method studies, it explains the implemented mechanism, training/inference distinction and component switches. A pipeline diagram cannot substitute for a method-principle figure.

## Provenance

External skill versions and file hashes are pinned in `config/pathology_figure_skills.json`. Their instructions are procedural references, not evidence of successful execution or scientific correctness. Verify any suggested scholarly citation through the literature stage before adding it to a manuscript.
