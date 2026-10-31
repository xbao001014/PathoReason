# Evidence and provenance

## Authority by claim

1. Measured values/counts: immutable raw observations, explicit patient/slide mapping and executed output records; preserve failures and missingness.
2. Protocol and topology: frozen executed configuration, split manifest and execution-bound code snapshot. A plan proves intent, not completion. Current source cannot replace missing executed source.
3. Model identity: checkpoint bytes/hash plus training/inference receipt and the exact configuration/code binding. A checkpoint name alone proves nothing about predictions or attribution.
4. Derived summaries: versioned code, source hashes and declared aggregation. Cross-check against authoritative outputs; do not silently reconcile discrepancies.
5. Reference papers: conceptual context and verified citations only; never evidence for this experiment's measurements/topology. Manual briefs and author recollection remain declared assertions until bound to execution.

Compute SHA-256 of original file bytes before copying and after rendering. Record original absolute source, isolated relative destination, byte size and digest; copies must match. Do not open experiment databases for writing or regenerate historical audits. Hash a small explicit evidence allowlist; never load feature/checkpoint data just to create a figure if only their identities are needed.

## Identity and prediction schema

A case-level table needs `patient_id`, `slide_id` or explicit patient-bag membership, `prediction_unit`, `model_id`, `checkpoint_sha256`, `protocol_sha256`, `split`, `fold`, `seed`, `target_id`, `observed`, `truth`, prediction value/probabilities or risk, and source units. Classification probabilities retain the ordered class keys; survival additionally carries time, event/censor encoding, origin and horizon as appropriate. Multiple slides may map to one patient; aggregation must be declared. Composite keys must be unique for a prediction observation. A header-only CSV has zero cases and cannot authorize any case-level plot.

Keep fold membership hashes, repeat/seed identity and train/val/test semantics. Validate patient disjointness within each frozen partition from actual membership records; do not infer it from counts. Repeated CV observations are not unique patients. Record provenance gaps without filling default IDs or missing masks.

## Spatial binding

Bind one chain: patient → slide pixels SHA-256 → coordinate array SHA-256 and patch IDs → coordinate origin/units → level and downsample → preprocessing/encoder → model/checkpoint → exact attribution method and values SHA-256. Record patch width/height, valid-region mask and X/Y MPP independently. Check equal array lengths, unique patch IDs, finite/in-bounds coordinates, shared normalization and matching transforms. Coordinates alone do not authorize a heatmap. Unknown MPP forbids a physical scale bar. Attributions cannot be reverse-engineered from bag features or aggregate predictions.

## Immutable candidate and receipt

Create a new versioned directory with exclusive creation; never replace an approved or failed candidate. Use a stable figure ID and a separate generation ID. Each figure's brief contains panel map, role, estimator, uncertainty, units/abbreviations, denominator and allowed claim. Package PNG, vector master when supported, editable/generation source, sources JSON, caption, alt text, QA and receipt. Register all files in the normal manuscript `FigureResult` and validate before binding.

Receipt fields:

```json
{
  "schema": "pathology-mil-generation/1",
  "generation_id": "new-version-id",
  "figure_id": "stable-id",
  "provider": "registered-provider-id",
  "source_hashes": {"relative/source.json": "64-hex-sha256"},
  "specification_sha256": "64-hex-sha256",
  "renderer_sources": {"renderer.py": "64-hex-sha256"},
  "environment": {"python": "exact-version", "matplotlib": "exact-version", "numpy": "exact-version"},
  "model": "no generative model; checkpoint identity only if actually used",
  "transformation": "exact estimator and grouping",
  "artifacts": {"figure.png": "64-hex-sha256"},
  "visual_review": "pending",
  "scientific_review": "pending",
  "author_approved": false,
  "submission_ready": false
}
```

Use real values, never the illustrative digest placeholders. A receipt cannot hash itself; the outer manifest pins its bytes. Keep later visual reviews as separate hash-bound records, leaving generation receipts immutable. Re-run source verification before publishing a candidate manifest. Approval requires the existing explicit author/scientific workflow and never follows automatically from hash or software-test success.
