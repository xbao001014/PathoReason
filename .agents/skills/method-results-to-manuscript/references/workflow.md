# Mid-entry methodology/results-to-manuscript workflow

Use this workflow when the project already contains a substantive method specification, implemented model, experiment record, result tables, or a partial manuscript. It is a focused adapter around the broader ARS pipeline; it does not replace domain judgment or author decisions.

## Stage M0 — Intake and truth map

**Goal:** establish what exists and what each artifact is allowed to support.

Actions:

1. Inventory source files and compute SHA-256 hashes.
2. Classify each file as author-controlled fact source, external evidence, generated analysis, manuscript draft, template, or administrative material.
3. Extract a factual inventory: cohort/data, label definition, unit of analysis, model components, training/evaluation protocol, baselines, ablations, metrics, and recorded limitations.
4. Classify test-set status using the taxonomy in `SKILL.md`. Prior viewing overrides later “fixed” labels.
5. Record contradictions and missing author inputs without resolving them by inference.

**Deliverables:** source manifest, intake snapshot, truth map, conflict register, unresolved inputs.

**Author checkpoint:** confirm the scientific object, label definition, test-use status, and which files are authoritative.

## Stage M1 — Paper blueprint and claim registry

**Goal:** convert the technical record into an answerable paper argument before prose drafting.

Actions:

1. Define the research question, target contribution, intended audience, and candidate journal family.
2. Build an outline with paragraph functions rather than generic section names alone.
3. Register core claims with fields: claim ID, proposed wording, evidence type, source artifact, strength ceiling, status, and required corroboration.
4. Separate claims supported by project data from claims requiring external literature.
5. Create a missing-evidence list prioritized as blocking, strengthening, or optional.

**Deliverables:** paper blueprint, claim registry, missing-evidence list, figure/table plan.

**Author checkpoint:** approve the research question, contribution boundary, primary result framing, and target language before full drafting.

## Stage M2 — Literature discovery and citation verification

**Goal:** build the minimum sufficient, reproducible evidence base for Background, Related Work, Discussion, and methods positioning.

Actions:

1. Audit any existing reviews or bibliographies before reuse.
2. Search by evidence role: disease/application context, target/measurement validity, closest methods, competing explanations, evaluation bias, and clinical/reproducibility guidance.
3. Preserve database, query, date, filters, identifier, and access route.
4. Resolve duplicates and versions; prefer the definitive peer-reviewed version while recording relevant preprints.
5. Verify metadata and, for high-impact claims, inspect full text with an exact locator.

**Skills:** `paper-lookup`, `citation-management`, and the relevant `academic-research-suite` research/literature mode.

**Deliverables:** search log, clean bibliography, source manifest, full-text evidence matrix, citation validation report.

**Gate:** no fabricated reference; no “first” claim based only on a zero-hit query.

## Stage M3 — Evidence synthesis and argument map

**Goal:** turn sources into a reasoned narrative rather than a paper-by-paper list.

Actions:

1. Group evidence by themes and the function it serves in the manuscript.
2. Record convergences, contradictions, boundary conditions, and search-bounded gaps.
3. Build claim–evidence–reasoning chains for each major section.
4. Position the method by the level at which it intervenes, the information it uses, and the problem it solves—not by adjective inflation.
5. Distinguish direct evidence, analogy, and author interpretation.

**Deliverables:** thematic synthesis, literature matrix, argument map, paragraph-level evidence plan.

## Stage M4 — Manuscript drafting

**Goal:** produce a complete, contribution-forward manuscript whose statements remain traceable.

Recommended order:

1. Materials and Methods from author-controlled facts.
2. Results from locked tables/predictions.
3. Introduction and Related Work from the evidence matrix.
4. Discussion, Limitations, and Future Directions.
5. Conclusion, then Abstract, title, highlights, and keywords.

Results paragraphs follow question → number → contrast → implication. Keep protocol/status language out of the Results unless the paper itself is a protocol. Unrun experiments belong in a planning artifact, not in a completed-results narrative.

Write from the study authors' perspective rather than as an auditor describing
files supplied to the pipeline. At this working stage, machine claim/evidence
markers may remain long enough to support M5 integrity review, but missing-file
commentary and workflow narration belong in sidecars. Follow
[authorial-voice.md](authorial-voice.md) through an explicit
`anti-defensive-writing` skill load. Save draft semantic/voice records; a temporary
M4 lint finding must be identified and resolved before the M6 clean revision.

**Deliverables:** dated Markdown draft, actual method figure originals and captions,
tables, change log, unresolved-author-input list. Generate the method-centered
conceptual illustration during M4 using the configured raster route (Codex image
tool or registered image API), not for the first time during final typesetting.
Store images, brief, exact labels/connections, source hashes, generation receipts
and visual review under `03_manuscript/figures/<figure-id>/`. Link the real local
image from the Methods section. If generation or verification is unavailable,
keep an explicit unresolved task at the draft author checkpoint; a statement
that a figure exists is not a deliverable. See manuscript-to-latex's
`references/raster-generation.md`; using that figure capability during M4 does
not authorize LaTeX conversion, future-stage outputs or submission approval.

**Author checkpoint:** review the scientific narrative AND actual method image (labels, arrows, caption and implementation fidelity); approval binds the original figure bytes alongside the manuscript. Explicitly adjudicate unresolved factual or claim-strength decisions.

## Stage M5 — Pre-review integrity gate

**Goal:** detect factual, citation, numerical, statistical, and provenance failures before simulated review.

Minimum checks:

- reference existence and version;
- claim–citation semantic support and exact-locator coverage;
- all manuscript numbers against authoritative source tables;
- Methods–Results and text–table–figure consistency, actual linked figure files and their approval-bound hashes; M5 audits but does not create images or rewrite approved M4 assets;
- cohort/sample/fold/seed accounting;
- test-selection, threshold-selection, and repeated-comparison leakage;
- uncertainty and significance language;
- fabricated or unsupported methodology, results, ethics, or clinical claims;
- missing disclosure, data/code, and author-input states.

Emit coverage denominators and unknown states. A partial audit is not a clean certificate.

**Deliverables:** integrity report, issue register, and a separately versioned corrected draft when the user authorizes correction.

**Mandatory checkpoint:** unresolved blocking issues require author disposition before review.

## Stage M6 — Review, author adjudication, and revision

**Goal:** pressure-test the manuscript and improve it without surrendering author control.

Use journal-fit, domain, methodology/statistics, reproducibility/ethics, and devil’s-advocate perspectives as applicable. Review findings must cite manuscript locations and evidence. Do not reduce review to a numeric score.

The author adjudicates every material recommendation as accept, modify, reject, or defer with rationale. Apply only authorized changes, preserve the prior manuscript, and produce a revision matrix plus change log.

After scientific changes are adjudicated, explicitly load `anti-defensive-writing`
and perform a distinct reader-facing
narrative pass before the M6 manuscript is approved. Remove internal banners,
claim/evidence markers, gate labels, file-oriented commentary, and outsider
phrasing from the manuscript while retaining their mappings in the audit
artifacts. Preserve every material limitation and evidence boundary in natural
scientific language. Write `reader_facing_style_review.json` using the policy-2
semantic contract in authorial-voice.md. Run
`scripts/check_reader_facing_voice.py --semantic-review <reader_facing_style_review.json>` and save the
result as `05_review_revision/reader_facing_voice_report.json`; a failed result
blocks freezing. Require both `status: passed` and `style_status: passed` bound
to the exact revised manuscript SHA-256; lexical status alone is insufficient.

**Deliverables:** review package, editorial synthesis, author-adjudication
record, revision matrix, clean reader-facing revised manuscript,
`reader_facing_style_review.json`, `reader_facing_voice_report.json`, change log, and response document when
needed.

## Stage M7 — Final integrity and submission preparation

**Goal:** rerun integrity checks from the revised bytes and then adapt the accepted content to the confirmed journal.

Actions:

1. Perform a fresh integrity pass; do not only recheck known issues.
2. Explicitly load `anti-defensive-writing` in verification mode. Confirm that
   the clean reader-facing manuscript has exact-byte passing M6 semantic and voice
   report and that every removed marker still maps to internal evidence. Do not
   rewrite scientific content merely to pass formatting.
3. Confirm journal, article type, anonymization, word/figure/table limits, reference style, and required reporting guidance against current authoritative instructions.
4. Finalize figures, captions, declarations, data/code statements, ethics, author contributions, funding, conflicts, acknowledgments, and AI-assistance disclosure.
5. Generate DOCX/PDF only after the scientific content is frozen; visually inspect rendered documents.

**Deliverables:** final integrity report, accepted manuscript, submissionless source package, submission formats, checklist, and optional process record.

**Mandatory checkpoint:** the author confirms final scientific content and the exact files intended for submission.
