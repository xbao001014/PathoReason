# Artifact and versioning contract

## Default directory layout

```text
<project>/_manuscript_pipeline/
  README.md
  pipeline_index.json
  00_intake/                         # M0
    source_manifest.json
    upstream_handoff.json
    intake_snapshot.md
    truth_map.md
    conflict_register.md
    test_use_register.csv
    unresolved_inputs.md
    gate_status.json
  01_planning/                       # M1
    paper_blueprint.md
    claim_registry.csv
    missing_evidence.md
    figure_table_plan.md
    gate_status.json
  02_literature/                     # M2 + M3
    search_log.md
    raw_search/
    full_text/
    references_clean.bib
    literature_matrix.csv
    citation_validation.json
    thematic_synthesis.md
    argument_map.md
    gate_status.json
  03_manuscript/                     # M4
    drafts/
      manuscript_draft.md
    tables/
    figures/
    legends/
    change_log.md
    unresolved_author_inputs.md
    gate_status.json
  04_integrity/                      # M5 + fresh M7 integrity
    pre_review/
      integrity_report.md
      issue_register.csv
    final/
      final_integrity_report.md
    provenance/
    gate_status.json
  05_review_revision/                # M6
    review/
      review_report.md
    author_adjudication.md
    revision_matrix.csv
    revisions/
      manuscript_revised.md
    responses/
    reader_facing_voice_report.json
    change_log.md
    gate_status.json
  06_submission/                     # M7 freeze and delivery
    frozen/
      manuscript.md
      references.bib
      freeze_manifest.json
    figures/
      figure_manifest.json
      figure_review_report.md
      <figure-id>/
        asset_manifest.json
        # brief/reference/decomposition/source/QA/review/provenance
      _work/                        # transient; excluded from delivery
    latex/
      manuscript.tex
      references.bib
      figures/                      # accepted TeX-consumed copies only
      manuscript.pdf
      compile.log
      build_report.json
    qa/
      page-NNN.png
      pdf_qa_report.json
    checklist/
      submission_checklist.md
    bundle/
      pipeline_manifest.json
    provenance/
      stage_a_report.json
      stage_b_report.json
      stage_a_checkpoint.json
      stage_b_checkpoint.json
    gate_status.json
```

The project’s original files remain outside this generated tree unless the user explicitly requests otherwise.

For an integrated experiment-to-paper run, `upstream_handoff.json` must bind
the selected method provider, author-confirmed paper-subject contract, provider
evidence manifest, and source manifest by path and hash. This makes the
experiment stages discoverable from the ordered manuscript tree without
copying or re-authorizing their immutable source artifacts.

`README.md` is the human entry point and `pipeline_index.json` is the
machine-readable entry point. The index must list the directories in the
exact order above, map each directory to its M-stage(s), list required
artifacts, report artifact completeness, and expose the corresponding gate
path and status. Do not create competing flat `inputs/`, `draft/`, `review/`,
`frozen/`, `latex/`, `qa/`, or `provenance/` trees for new runs. Those names
are legacy layout only.

## Stage and gate ownership

| Directory | Workflow stage | Gate owner | Required decision |
|---|---|---|---|
| `00_intake` | M0 | Author | Confirm research object, label, test-use status, authority, conflicts, unresolved inputs |
| `01_planning` | M1 | Author | Approve research question, contribution boundary, claim ceilings, result framing, figure/table plan |
| `02_literature` | M2–M3 | Pipeline integrity; author if conflicts remain | Verify search provenance, references, exact support, synthesis, argument map |
| `03_manuscript` | M4 | Author | Approve scientific narrative and adjudicate unresolved factual or claim-strength choices |
| `04_integrity` | M5 and final M7 pass | Author for blockers | Disposition every blocking integrity issue; final pass must use revised bytes |
| `05_review_revision` | M6 | Author | Accept, modify, reject, or defer every material review recommendation; approve the clean reader-facing revision after the voice report passes |
| `06_submission` | M7 | Author | Confirm journal, article type, declarations, frozen content, and exact submission files |

Every stage directory must contain `gate_status.json` with at least:

```text
schema,gate_id,stage_id,gate_type,required_actor,blocking_for_submission,
status,guidance,decision,confirmed_by,confirmed_at_utc
```

Generated preview artifacts may continue while a user gate is pending, but a
pending gate must remain visible and must force `submission_ready=false`.
Automation must never mark an author gate confirmed or invent an author
adjudication. `author_adjudication.md` may be generated as a clearly labeled
pending template, not as a completed decision record.

The submission archive may live beside `_manuscript_pipeline/` to avoid
self-containing archives. Its content manifest belongs in
`06_submission/bundle/pipeline_manifest.json`, and any external archive and
checksum must point back to that manifest.

## Figure artifact contract

`03_manuscript/figures/` holds the actual M4 method figure originals, visual brief,
labels/connection specification, source and generation receipts, captions and
visual review. These files are included in the draft author gate hash binding.
The Methods draft links the actual local image; a plan alone is insufficient. `06_submission/figures/` is the audited
production record created by `manuscript-to-latex` from the reviewed draft
originals (no new scientific image generation after freeze); it preserves how each
accepted visual was specified, generated or reconstructed, checked, and
approved. `06_submission/latex/figures/` contains only the final copies that
the TeX source consumes. These three locations have different responsibilities
and must not be collapsed into one another.

The aggregate `06_submission/figures/figure_manifest.json` uses schema
`manuscript-figure-artifacts/1.0`. With figures present, set `status` to
`reviewed` and list every figure with:

```text
figure_id,role,workflow,artifact_directory,asset_manifest,
accepted_source(path,sha256,editable),packaged_assets(path,sha256),
visual_review(status,path,sha256)
```

All paths are relative to `_manuscript_pipeline`, the review status must be
`passed`, and every recorded hash must match. With no figures, set `status` to
`no_figures`, use an empty list, and explain why in
`figure_review_report.md`. Put rejected or intermediate visual iterations only
under `06_submission/figures/_work/`; bundle construction excludes that
subtree while retaining every accepted per-figure package.

## Required source-manifest fields

- `project_root`
- `generated_at_utc`
- `relative_path`
- `size_bytes`
- `sha256`
- `modified_at_utc`
- `provisional_role`
- `authority_status`

Hashes establish file identity, not truth or authorship.

## Recommended artifact names

Use ISO dates and descriptive names:

- `source_manifest_YYYY-MM-DD_HHMMSSZ.json`
- `intake_snapshot_YYYY-MM-DD_HHMMSSZ.md`
- `paper_blueprint_YYYY-MM-DD.md`
- `claim_registry_YYYY-MM-DD.csv`
- `missing_evidence_YYYY-MM-DD.md`
- `literature_matrix_YYYY-MM-DD.csv`
- `references_clean_YYYY-MM-DD.bib`
- `manuscript_working_draft_<language>_YYYY-MM-DD.md`
- `manuscript_revision_<label>_<language>_YYYY-MM-DD.md`
- `integrity_report_<stage>_YYYY-MM-DD.md`
- `revision_matrix_round<N>_YYYY-MM-DD.csv`
- `unresolved_author_inputs_YYYY-MM-DD.md`
- `submission_checklist_<journal>_YYYY-MM-DD.md`

## Version rules

1. Never overwrite an author-controlled method/result source.
2. Never silently overwrite an author-approved manuscript. Create a new dated revision.
3. Every substantive manuscript revision has a change log and unresolved-input list.
4. Record the exact source artifact and hash used for each integrity report.
5. Preserve raw search outputs separately from cleaned bibliographies and narrative synthesis.
6. A copied snapshot is a convenience copy, not a new authority source.
7. Generated text is not automatically “verified”; its evidence status comes from a separate check.
8. Before M7 freeze, remove internal claim/evidence markers and workflow
   scaffolding only from the reader-facing manuscript. Preserve the complete
   mapping and audit findings in their sidecars, then bind the clean manuscript
   to `reader_facing_voice_report.json` and the fresh final-integrity report.

## Reader-facing voice report

`05_review_revision/reader_facing_voice_report.json` uses schema
`reader-facing-voice-report/1.0` and records the exact clean M6 manuscript that
was checked, status, issue count, line-scoped findings, and an authorial-signal
count. `status=passed` is required before the clean revision is copied into
`06_submission/frozen/manuscript.md`.

The report is a leakage/style lint, not an integrity certificate. It must not
be used to delete exploratory or post-hoc status, prior test exposure,
uncertainty, negative findings, or other material scientific limitations.

## Claim registry minimum columns

```text
claim_id,section,claim_text,claim_type,source_ids,exact_locator,evidence_status,strength_ceiling,author_decision,notes
```

Suggested `claim_type` values: project-result, project-method, background, related-work, interpretation, limitation, future-direction.

Suggested `evidence_status` values: verified-fulltext, verified-metadata, abstract-only, author-confirmed, generated-inference, unresolved, contradicted.

## Test-use register minimum columns

```text
result_id,dataset_or_split,selection_rule,first_view_date,development_use,status,allowed_language,source_path,notes
```

The `status` must use the taxonomy in `SKILL.md`. If test history is uncertain, set `unknown`; do not infer `fixed_checkpoint_test_unseen` from a filename containing “fixed”.
