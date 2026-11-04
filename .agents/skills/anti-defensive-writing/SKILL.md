---
name: anti-defensive-writing
description: Review and revise scientific manuscript prose for a coherent evidence-led contribution, direct reporting of negative results, proportionate limitations and authorial voice. Use during drafting, after author-adjudicated scientific revision and to verify the style record before delivery. Preserve adverse findings, uncertainty and claim boundaries; this is not scientific approval or permission to rewrite frozen content.
---

# Anti-defensive scientific writing

This is PathoReason's callable adaptation of the policy already maintained in
[authorial-voice.md](../method-results-to-manuscript/references/authorial-voice.md),
including its attributed anti-defensive-writing source. It does not install the
upstream publication-first instructions. Read that complete reference before
performing this work; it is the canonical policy and semantic-record contract.

## When to execute

- **Draft / M4:** load this skill before prose drafting. Lead with the research
  question, implemented comparison and measured finding. Before submitting the
  draft, read the whole manuscript and record the four semantic checks below.
  Temporary evidence markers allowed at M4 are documented as draft-only lint
  findings; they are not a clean-manuscript pass and cannot survive M6 freeze.
- **Scientific revision / M6:** after applying the author's scientific
  adjudication and before requesting content approval, execute a fresh whole-text
  pass. Preserve the prior version; make only authorized prose changes. Keep
  factual disagreements for author adjudication rather than resolving them as
  stylistic edits. Produce the exact-byte semantic and voice reports below.
- **Review / M5:** inspect the draft's records; missing or stale records are an
  explicit review finding, not proof that the manuscript is well written.
- **Delivery / M7:** verify the passing records against the approved scientific
  manuscript before conversion. If missing, inspect the frozen text read-only
  and report the gap. Do not edit an approved manuscript or fabricate a passing
  report. Necessary prose changes require reopening scientific review through
  the existing author workflow. A PDF build/QA pass is not a style pass.

## Execute and record

Read the complete manuscript, including abstract, conclusion, captions and
references, alongside the claim boundaries and author adjudication. Check:

1. `contribution_focus`: the question, comparisons and strongest supported
   finding form a coherent scientific account, including neutral/negative work.
2. `proportional_limitations`: necessary caveats qualify the relevant claims;
   repeated apologies and rebuttals to hypothetical reviewers do not dominate.
3. `direct_results`: adverse and null results remain quantitative and visible;
   neither conceal them nor use them to dismiss the entire study.
4. `disclosure_preservation`: scientific limitations and claim ceilings remain
   intact. Move internal file/verification commentary to linked audit artifacts,
   not the manuscript. Never remove substantive test exposure or bias disclosures
   to satisfy a word count, keyword rule or positive-result narrative.

Run the existing `method-results-to-manuscript/scripts/check_reader_facing_voice.py`
on the exact proposed manuscript. Its exit code and lexical `status` alone cannot
pass this skill. Apply the reference's policy-2 semantic procedure and create
versioned `reader_facing_style_review.json` and `reader_facing_voice_report.json`
under the current manuscript stage directory (M6: `05_review_revision/`). Pass
the semantic record via `--semantic-review` and the report path via `--output`.
Use exact excerpts, contextual reasons, the manuscript SHA-256 and the actual
reviewer role/model; assess every retained lint warning. Never label model
assessment human or independent scientific approval.

For the final clean revision, BOTH `status: passed` and `style_status: passed`
with the correct SHA-256 are required. Failed/unperformed checks remain explicit
and block a claimed style pass. Changed bytes require new records; do not reuse
an earlier version's pass. Register both reports with the review packet as
`style_review` and `voice_report`, include their artifact IDs in checkpoint
evidence, and record this actual skill load and execution in `skill_usage`.
Keep the existing author gates, project budgets and experiment scope unchanged.
