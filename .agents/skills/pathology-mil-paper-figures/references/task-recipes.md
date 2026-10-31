# Task recipes

Choose a study type first, then a task recipe. Record target venue as unselected until specified. Minimum sets below are evidence-conditional, not permission to fill missing panels. Emit a refusal row for every omitted mandatory panel. Use deterministic numeric providers and keep negative results.

## Single-label classification

Minimum: cohort/class prevalence and missingness; protocol-bound all-model metric comparison; ROC plus PR for binary/one-vs-rest probabilities; confusion matrix under the frozen 0.5/argmax or explicitly validated threshold. Give each class its denominator and use the same order everywhere. Calibration requires case-level probabilities and a declared binning/evaluation protocol. Do not derive curves from AUC, simulate cases from summary statistics, choose thresholds on test data, or hide undefined one-class partitions.

## Multilabel classification

Minimum: per-label observed/positive/negative/missing coverage; per-target ROC/PR where defined; macro and micro summaries with explicit weighting and denominators. Fix label order and thresholds. Evaluate only observed labels, retaining missing masks. Do not interpret labels as exclusive, impute missing labels as negative, or average physically different target metrics without definitions.

## Single-target regression

Minimum: target coverage and distribution where actual outcomes exist; all-condition original-unit MAE/RMSE and unitless R2/rank correlation; observed-versus-predicted and residual panels when case predictions exist. Record inverse transforms and prediction unit. Draw the identity line with equal limits when appropriate; retain outliers. No classification thresholds, case scatters or residual distributions inferred from aggregate errors.

## Multi-target regression

Minimum: target-wise coverage; target-wise metrics in source units; separate prediction/residual panels for each target with adequate case evidence. State observed n per target. Apply each target's actual inverse transform. Do not pool errors across physical units or silently drop sparse targets. A normalized summary requires its predefined normalization and weights.

## Survival

Minimum: event/censor and follow-up coverage; declared discrimination at supported horizons; within-partition risk diagnostics. KM needs actual times/events and a predeclared stratification rule with numbers at risk; time-dependent discrimination and calibration require their estimator, censoring handling and supported horizon. Never convert Cox risk into survival probability without a bound baseline hazard, pool uncalibrated fold risks into one KM curve, or invent HR/p-values. State censored counts and independent validation limitations.

## Method-centric MIL

Minimum: study/evaluation schematic; executed-source-bound model figure including training/inference and enabled/removed branches; all-model comparison; full-versus-removal ablation under matched protocol; limitations or failure cases supported by real observations. A manual brief remains an unverified design handoff. Frozen/fine-tuned encoders, pretraining overlap, parameters and compute need receipts. Development ablation can support descriptive differences, not causal biological explanation or independent clinical benefit. Real tissue/attention panels are optional and require their own complete spatial evidence lane.

## Application, foundation-model, multimodal and clinical overlays

Application studies foreground endpoint/cohort coverage and independent evaluation, not an invented novel mechanism. Foundation-model studies add overlap and downstream adaptation evidence. Multimodal studies add availability/join and unimodal controls. Clinical validation adds time/site/setting independence, uncertainty and locked decisions. When any overlay lacks evidence, retain a missing-input inventory instead of expanding claims.

## Repeated runs and small samples

Keep folds and seeds as separate axes or facets. For each seed, multiple valid fold estimates can be shown as individual fold points and mean ± sample fold SD (ddof=1); these bars are not CIs. One fold has no SD/CI; two observations remain descriptive. Missing/failed cells stay present. Do not turn fold×seed rows into a patient count or perform unsupported significance testing.
