# Reader-facing authorial voice and audit separation

## Purpose

The manuscript should read as the authors' scientific account of their own
study. Internal evidence controls must remain available to reviewers of the
pipeline without leaking into the reader-facing prose as file commentary,
workflow labels, or an external auditor's voice.

This is a separation rule, not permission to conceal uncertainty, selective
reporting, post-hoc analysis, test reuse, conflicts, or other scientifically
material limitations.

## Two-layer output model

Keep two synchronized layers:

1. **Reader-facing manuscript** — scientific narrative, tables, captions,
   limitations, declarations, and citations written from the study authors'
   perspective.
2. **Internal traceability artifacts** — source hashes, claim/evidence IDs,
   exact locators, conflict records, test-use taxonomy, audit findings,
   unresolved-input requests, revision decisions, and change logs.

Moving an internal marker out of the manuscript never deletes its source
mapping. Preserve that mapping in the claim registry, integrity reports,
revision matrix, or other sidecar before removing the marker from prose.

## Placement in the pipeline

- **M4 drafting:** write in authorial voice from the start. Claim and evidence
  markers may remain temporarily while the draft is under active integrity
  review, but file-oriented commentary belongs in sidecars.
- **M5 integrity:** audit the evidence and numbers without polishing away
  uncomfortable findings. Corrections may add traceability markers to a
  working copy.
- **M6 revision:** after the author adjudicates scientific changes, perform the
  mandatory reader-facing narrative pass. This is the main transformation
  point: preserve the adjudicated science, remove internal markers and audit
  scaffolding from the revised manuscript, and record a machine-readable
  voice report before the author approves the revision.
- **M7 final integrity and freeze:** verify that the accepted clean manuscript
  still matches the internal records and contains no leaked audit scaffolding.
  Do not introduce substantive rewrites at formatting time.

M6 is the primary placement because it follows evidence correction and author
adjudication but precedes the fresh final-integrity pass and byte freeze.

## Authorial perspective

Unless the user identifies the work as a third-party reanalysis, review,
replication, or commentary, treat the method and experiments as the authors'
own study.

Prefer direct scientific subjects:

- `We developed ...`, `We evaluated ...`, `Our experiments showed ...`;
- `<Method> achieved ...`, `The comparison showed ...`;
- `We report an AUROC of ...` when active reporting language is natural.

Avoid writing as an outsider inspecting delivered files:

- `the supplied/provided/available results`;
- `the displayed baseline panel`;
- `the reported method/performance/best AUC` for the current study;
- `the source file did not document ...`;
- `the evidence package shows ...`.

`Smith et al. reported ...` remains appropriate for prior literature. A venue
that prefers passive voice does not require repeated `we`; the invariant is
research ownership, not pronoun frequency.

## Missing information and limitations

Do not expose a file gap as manuscript prose. Put the exact missing field,
source conflict, requested answer, and workflow impact in
`unresolved_author_inputs.md` or the relevant integrity report.

When the missing work creates a real scientific limitation, state the study
boundary in authorial language:

- `We did not perform external validation.`
- `Our evaluation did not include calibration analysis.`
- `The exact training-code revision was not retained, which limits complete
  computational reproduction.`

Material limitations must not disappear merely because their internal labels
sound procedural. For example, replace the literal taxonomy token
`test_previously_viewed` with clear scientific prose explaining that test
outcomes informed development and that independent confirmation is required.
Keep exploratory/post-hoc status visible wherever omission would make the
abstract, results, or conclusion misleading; also provide the full account in
the dedicated limitations passage.

## M6 narrative-pass procedure

1. Start from the author-adjudicated M6 revision, never from an earlier draft.
2. Lock the claim registry and numerical tables used by the revision.
3. Replace file-, pipeline-, and auditor-centered wording with direct
   scientific prose without changing numbers, direction, uncertainty,
   analysis status, or claim strength.
4. Move claim/evidence markers, workflow banners, locator notes, and exact
   missing-input requests to their existing sidecars; verify those sidecars
   retain a complete mapping.
5. Consolidate repeated qualifications, but retain each material disclosure
   at the locations needed for an honest interpretation.
6. Complete the policy-2 semantic review below, then run
   `scripts/check_reader_facing_voice.py --semantic-review <review.json>` on
   the revised manuscript and save the JSON result as
   `05_review_revision/reader_facing_voice_report.json`.
7. Rerun final integrity against the clean revised bytes. The author then
   approves this exact version before freeze.

The checker detects internal markers and common outsider/audit constructions.
It is a conservative lint, not proof of good style or scientific integrity;
all hits require contextual review.

## Acceptance criteria

- The reader-facing manuscript contains no claim/evidence markers, workflow
  banners, gate labels, internal taxonomy tokens, local paths, or requests to
  the author.
- Current-study methods and results are narrated as the authors' work, not as
  a supplied third-party package.
- Exact provenance, unresolved facts, and audit decisions remain intact in
  internal artifacts.
- No numerical value, uncertainty, comparator, negative result, post-hoc
  status, test-use limitation, or claim ceiling is weakened or omitted by the
  narrative pass.
- The clean manuscript is the input to the fresh M7 integrity report and the
  subsequent freeze manifest.

## Evidence-centered narrative and semantic style review (policy 2)

Reference: [Adkid-Zephyr/anti-defensive-writing-Skill](https://github.com/Adkid-Zephyr/anti-defensive-writing-Skill/blob/main/skills/anti-defensive-writing/SKILL.md), consulted 2026-10-08. This is a selective adaptation, not installation of its publication-first instructions. Use its focus on a coherent contribution and direct prose. Do not suppress unfavorable comparisons, change endpoints after seeing outcomes, invent a tradeoff, or present exploratory observations as validated advantages.

- **Planning:** identify the strongest supported finding, including a neutral or negative finding. Give each section and experiment a clear evidential purpose. Keep the originally specified endpoints and comparison scope in the record.
- **Draft:** lead with the question, method and measured finding. Report lower or null results precisely, without apology or global judgments about the work's worth. Do not turn every paragraph into a rebuttal to hypothetical reviewers.
- **Review:** distinguish a factual correction from a request for clearer prose. A reviewer caveat belongs at the claim it qualifies, not automatically in every section.
- **Revision:** perform a whole-manuscript semantic pass after scientific revisions. Consolidate repeated denials of novelty, superiority, validity or clinical utility. Keep concise exploratory status in standalone abstract/conclusion when needed, and the full methodological limitations in their appropriate section. No ban or quota on words such as exploratory, not, only or limitation.
- **Final integrity:** check that style edits retained all material disclosures, adverse results, numbers and claim boundaries. Do not reintroduce redundant disclaimers to demonstrate that the audit ran.

Examples (illustrative, never replacement scientific evidence):
- Prefer “The full model yielded AUROC X versus Y for the control” to apologizing for the comparison or asserting that it invalidates the entire method.
- Prefer “This two-fold analysis describes the observed differences; independent validation is needed” to repeatedly denying novelty, superiority and generalizability throughout the paper.
- Explain unavailable replication resources in reproducibility/data availability prose. Keep verification labels such as author-attested in the evidence record unless the distinction materially changes interpretation.

### Required semantic record

A new workflow uses `voice_policy_version: 2`. Regex lint alone cannot pass its style gate. First run the checker without `--semantic-review` to obtain advisory `style_warnings`; its lexical `status: passed` alone is not approval (`style_status` remains `needs_review`). Read the entire revision, make permitted prose edits and rescan. Before freezing, write `05_review_revision/reader_facing_style_review.json` against the exact final revision, then run:

```sh
python scripts/check_reader_facing_voice.py <revision.md> --semantic-review <reader_facing_style_review.json> --output <reader_facing_voice_report.json>
```

The semantic record has `manuscript_sha256`, `reviewer` (actual role/model; never claim human review), `status: passed`, and `checks`. Each check has `id`, `verdict: passed`, `evidence` (an exact nonempty excerpt from the revision), and `reason` explaining the contextual judgment. Required check IDs:

- `contribution_focus`: question, contribution and evidence form a coherent narrative.
- `proportional_limitations`: qualifications are necessary and placed appropriately across sections.
- `direct_results`: adverse/null findings remain quantitative and are not hidden or inflated into global self-dismissal.
- `disclosure_preservation`: all adjudicated material limitations and claim ceilings remain; reason identifies their locations and compares with the adjudication/claim record.

Inspect the complete manuscript, not just lint matches. For each remaining lint warning, add a `warning_dispositions` entry with its `code`, `line`, and a substantive `reason` for retaining it. Unresolved findings require revision and a fresh record/hash, not a passing label. Removed matches should disappear in a fresh scan. An explicit retained caveat is preferable to deleting a true limitation to satisfy style rules. The record is model-authored semantic assessment, not proof of scientific truth or human approval. Preserve existing author gates.
