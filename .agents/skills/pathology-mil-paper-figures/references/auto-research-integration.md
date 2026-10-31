# AutoResearch integration (project-local 1.1.0)

## Resolve the real checkout

Read ancestor/current AGENTS.md, PathoReason docs/p5/OPERATOR.md, runtime configuration and `orchestrator.resolve_remote_project_root`. An explicit `remote_manuscript_cwd` wins; a bundled engine maps to its containing checkout. `sync_code` copies engine code only, not the manuscript repository or the entire skills directory. In the bxn-server deployment, the active Skill checkout is `/home/bxn/projects/PathoReason`; reusable engine code remains read-only at `/home/bxn/projects/auto-research`; current experiment runtimes are `local_conda` and have no `remote_manuscript_cwd`. Old `/baoxinan` remote settings do not prove that deployment is reachable. Never change a historical runtime to make a smoke test work.

Before invoking a provider, read the actual versions of:

- `packages/core/experiment_agent/manuscript_assets.py`: skill hashes, prepare/validate/bind and typeset checks.
- `packages/core/experiment_agent/pathology_figures.py`: native schematic/comparison providers.
- `packages/core/experiment_agent/research_figures.py`: task diagnostics and protocol checks.
- `packages/core/experiment_agent/development_figure_assets.py`: explicitly selected development-summary adapter.
- `packages/core/experiment_agent/workflow_templates/extensions.py`: FigureSpec, FigureResult, EvidenceReference and ManuscriptAssetBinding.
- `packages/core/experiment_agent/manuscript_workflow.py`: phase-specific skill routing, input/skill fingerprint, preparation and bindings.

## Registered providers and scope

| Provider | Source and behavior |
| --- | --- |
| `study_design` | Declared executed task/protocol schematic; no WSI or clinical claim |
| `outcome_coverage` | Observed/missing target counts by fold/split; repeated bag observations are not unique patients |
| `condition_comparison` | All condition summary values in recorded order; available fold SD labelled separately from CI |
| `mil_moment_architecture` | Only `mil-moment-residual/1` with executed `research_model.py` hash matching the known adapter; otherwise raises |
| `task_diagnostics` | `research_figures.export_diagnostics`: classification ROC/PR/fixed-rule confusion, regression residual/prediction, survival within-fold risk; complete nonempty partitions and frozen task required |
| `development_single_metric` | Explicit `prepare_assets(..., provider='development_summary')`; existing comparison renderer with receipt-verified single-regression validation RMSE grouped by seed |
| `development_cohort_metrics` | Same adapter; typed cohort/split audit and receipt values for RMSE/MAE/R2/Spearman; declared units preserved, undefined values visible |
| `development_ablation` | Same adapter; executed full/removal mapping and matched fold/seed RMSE differences; no causal or significance claim |

The development adapter is opt-in for candidate engineering. It does not promote a development experiment into a paper or bypass independent-confirmation requirements. It reads only copied plan, bundles and hash-bound outcome JSON; it never invokes a controller, checkpoint loader or trainer. Complete replication cells are required; missing/failed matrices are refused with an explicit reason, never silently shortened. SVG export requires `svg_generation_enabled=True`. Default manuscript figure output remains PNG/PDF.

## Registered spatial package

Use prepare_assets(root, output, provider='spatial') with the typed artifacts/spatial_figure_request.json.
SpatialFigureRequest, SpatialMapping and AttributionBinding are exposed by extension_contracts().
Providers: tissue_overview, roi_panel, top_patches, attention_overlay.
Pixels must be real decoded PNG/JPEG/TIFF with patient/slide identity, pixel hash, level-0 extent,
origin, X/Y downsample and pyramid level. Derived WSI pixels require the hash-bound export receipt.
pathology_slide_assets.export_wsi_region supports bounded OpenSlide reads; SDPC uses optional
opensdpc. MRXS requires an explicit complete companion-file closure. Proprietary zyp/ibl/tron
are unsupported unless a decoder recognizes the actual bytes; do not claim support by extension.
Optional WSI libraries can live in a figure-only PYTHONPATH without altering a training environment.

Coordinates are CSV with unique patch_id,x,y,width,height in level-0 pixels, plus optional
valid (0/1). Attribution CSV is patch_id,score. A typed inference receipt binds exact pixels,
coordinates, scores, checkpoint, executed source, preprocessing and feature-manifest hashes.
Partial sampling is permitted only with declared matching patch IDs; unknown patches, nonfinite
values, out-of-range coordinates and normalization clipping are refused. Overlaps use mean raw
attribution, unsampled pixels remain transparent, and all overlays use declared shared bounds.
Top patches have deterministic score ordering with patch-ID tie break. ROI selection must be
declared. Physical scale bars require independent hash-bound X/Y MPP calibration evidence.
Candidate creation is exclusive; refusals are recorded. Standard validate/bind and visual/author
review gates remain in force. No real heatmap may be synthesized from feature tensors alone.

## Not registered

Clinical calibration/KM/HR/decision curves, multimodal fusion/evaluation and arbitrary architecture topology are not registered. A skill reference describes evidence needs but does not implement these capabilities. `figure_capabilities()` advertises the registered raster providers and their input requirements; native WSI decoding is optional and proprietary formats are not presumed supported. Header-only CSVs, coordinates without pixels/attributions and manual architecture briefs must produce refusal records, not plausible-looking figures.

## Required integration path

1. `validate_skills(PROJECT_ROOT)` verifies the manifest, all registered skill files and every reference SHA-256. `skill_files` includes those files in manuscript fingerprints; missing files/hash mismatches fail closed.
2. The manuscript prompt supplies the project-local `pathology-mil-paper-figures/SKILL.md` path for intake/planning/draft/audits/review/revision/freeze and typesetting. Read only the relevant reference sections for that phase.
3. Call `prepare_assets(experiment_root, output)` for ordinary research evidence. For a new isolated development evidence copy, explicitly select `provider='development_summary'`. The experiment root must retain a valid experiment ID and all output must be owned by that root.
4. Call `validate_assets(root, manifest)` to verify input, specification, all images, renderer snapshots, caption, QA and receipt-bound companion bytes.
5. Open every PNG and write a separate actual `visual_review.json` tied to exact image hashes, real reviewer identity and findings. Leave author/scientific approval pending.
6. Insert actual relative image links, bound captions and alt text into the isolated draft. `bind_assets` creates the normal `asset_bindings.json`; it refuses missing visual review, captions or required images. Do not handwrite bindings.
7. Preserve the existing author gates before freeze/typeset. Binding and software tests never approve a manuscript.

## Adding a provider

A new provider requires a typed specification and versioned ID; evidence requirements and byte/identity/schema gates; deterministic renderer or exactly configured conceptual-image route; caption/alt; QA records; immutable reproduction/environment/source receipt; registration in capabilities and preparation routing; meaningful refusal tests; and validation/binding compatibility. Do not create an ad hoc plotting script outside these contracts. Do not relax other providers when this one lacks evidence. New spatial/clinical/multimodal providers remain unavailable until all these pieces exist.

## Safe smoke test

Use an already completed experiment. Copy an explicit allowlist of small evidence files into a fresh versioned smoke directory, preserving relative layout and original hashes. Avoid SQLite, feature bags, image pixels and checkpoints unless explicitly required/authorized. Record pre/post source hashes. Render through the registered preparation path, inspect pixels, validate and bind in the isolated draft. Test missing/header-only prediction evidence and absent spatial/topology bindings using separate negative fixtures, never by editing historical sources. Retain all failed attempts and pending scientific/author reviews. Do not start/resume/rerun experiments, install heavy WSI dependencies or auto-confirm gates.
