---
name: pathology-mil-paper-figures
description: Plan, generate, audit, and package evidence-bound figures for pathology multiple-instance learning and whole-slide-image papers. Use for figure inventories, study and method schematics, quantitative result plots, spatial/attention panels, clinical outcome figures, multimodal evaluations, and manuscript-ready figure packages; do not use to invent tissue images or unsupported measurements.
---

# Pathology MIL paper figures

Build a figure set that carries the paper's scientific argument. Start from the study question, task contract, executed protocol, and available evidence; do not start from a preferred visual style.

## Evidence lanes

- Measurements, statistics, cohort counts, comparisons and clinical outcomes use deterministic plotting code.
- Study design, architecture and mechanisms use editable vector or code-native diagrams when topology and labels must be exact.
- Tissue panels require real WSI/ROI/patch pixels, slide identity, coordinates, pyramid level/downsample and source hash.
- Physical scale bars require calibrated X/Y MPP.
- Raster image generation is allowed only for explicitly non-data conceptual illustrations.
- Never reconstruct histology, heatmaps or spatial localization from bag features alone.
- Attention is an attribution signal, not a tumor annotation, causal explanation or calibrated probability.

## Required workflow

1. Classify the study as method-centric, application/biomarker, foundation-model, multimodal or clinical-validation.
2. Record task family, prediction unit, cohorts/centers, split strategy, endpoint and target venue.
3. Inventory patient/slide/patch counts, predictions, metrics, uncertainty, checkpoints, WSI pixels, coordinates, attributions, annotations and outcomes.
4. Mark unavailable inputs explicitly.
5. Give every panel one narrative role, one evidence source, one transformation and one allowed caption claim.
6. Generate exact-data panels reproducibly.
7. Refuse or downgrade panels whose required evidence is absent.
8. Inspect the rendered output at final size.
9. Package immutable, versioned candidates; never overwrite an approved figure.

## Minimum output contract

Every figure must contain:

- stable figure ID and narrative role;
- panel map;
- source identifiers and SHA-256;
- generation code or editable source;
- exact environment/model receipt;
- vector master when possible;
- review PNG;
- caption and alt text;
- abbreviations, units and denominators;
- estimator and uncertainty definition;
- statistical-test wording;
- visual and scientific QA record;
- known limitations;
- immutable generation receipt.

## Scientific invariants

- Preserve patient-level splits, class/target order, units, missingness and censoring.
- Never select or rank models using the test set.
- Distinguish raw observations, fold SD, confidence intervals and repeated-seed variation.
- Never label SD as CI.
- Never count repeated CV observations as unique patients.
- Classification figures retain prevalence and denominators.
- Imbalanced classification should show PR as well as ROC when case-level evidence exists.
- Confusion matrices state threshold or decision rule.
- Multilabel missing values are not negatives.
- Regression retains original target-specific units.
- Survival distinguishes censoring, risk scores, survival probabilities and time horizons.
- Do not pool uncalibrated fold risks into one Kaplan–Meier curve.
- Spatial comparisons use shared normalization and report the exact attribution method.
- Clinical claims require appropriate validation and uncertainty.
- Coordinates alone do not authorize a heatmap.
- Architecture diagrams require executed source/configuration binding; a manual brief is not a verified topology.

## Small-sample rendering rules

- n=1: show the observation only; no SD, CI or significance claim.
- n=2: paired observations may be displayed descriptively; do not present unstable significance as reliable evidence.
- Multiple valid folds: individual fold points and mean ± fold SD may be shown.
- CI and SD must use different labels and visual encodings.
- Missing and failed partitions remain visible.

## AutoResearch integration

- Reuse evidence hashes, immutable candidate rules and registered providers.
- Keep `prepare_assets`, `validate_assets` and `bind_assets` in the execution path.
- Do not add ad hoc scripts that bypass manuscript asset bindings.
- Existing providers include study design, outcome coverage, condition comparison, a source-bound MIL architecture, task diagnostics, and the opt-in spatial package (real tissue overview, declared ROI panels, top attributed patches, and spatial attribution overlays).
- Spatial, clinical and multimodal additions must be registered providers with typed evidence requirements and refusal behavior.
- Figure candidates remain unapproved until visual and author/scientific review are explicitly recorded.

## References and version

Project-local version: 1.1.0. The project manifest pins every file; a hash change requires a new manuscript candidate revision.

- For inventories and panel admission, read [figure-taxonomy.md](references/figure-taxonomy.md).
- For the task's minimum figure set and forbidden inferences, read [task-recipes.md](references/task-recipes.md).
- Before transforming evidence or writing receipts, read [evidence-and-provenance.md](references/evidence-and-provenance.md).
- Before rendering and visual review, read [layout-and-qa.md](references/layout-and-qa.md).
- Before invoking or adding a provider, read [auto-research-integration.md](references/auto-research-integration.md).
