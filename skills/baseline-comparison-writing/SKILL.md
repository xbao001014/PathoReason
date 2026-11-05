---
name: baseline-comparison-writing
description: Write and audit baseline comparisons in computational pathology and predictive-model manuscripts from existing results. Explain comparator selection, experimental comparability, uncertainty and positioning against prior research; distinguish algorithm comparisons from ablations and literature-only context. Use during manuscript planning, drafting and substantive scientific revision, not for running benchmarks or formatting-only edits.
---

# Baseline comparison writing

Turn an existing comparison into an answerable scientific argument: why these
comparators, under which conditions, what difference was observed, and what it
establishes. Apply to method, prediction, exploratory and negative-result papers;
do not require a novel winning model. This skill writes and checks evidence; it
does not authorize experiments, additional computation, author approval or a
change of research subject.

Read [references/paper-patterns.md](references/paper-patterns.md) before first
use. These primary-paper examples motivate writing choices, not a mandatory list
of models or citations for every disease. Reuse the guidance while it remains in
context; a directory listing is not a read. Read the manuscript, authoritative
results and latest synthesis/adjudication; preserve superseded findings as
history rather than importing their stronger interpretations into the revision.

## When and how to apply

- **Blueprint / synthesis:** identify the comparison question, comparator roles,
  evidence available and claim ceiling. Record the plan in the existing argument
  artifact. Missing optional benchmarks are scope limits, not new commitments.
- **Draft / scientific revision:** explicitly load this skill before writing the
  relevant sections. Build or update the comparison inventory, write the results
  and contextual discussion, then complete the exact-version review below.
- **Model-assisted review:** inspect the draft's comparison claims and record;
  locate omissions, unsupported rankings or stale evidence for adjudication.
- **Delivery / presentation-only edits:** preserve the approved scientific
  content. Do not require a new scientific review merely because this skill was
  introduced after approval. A clear request to change scientific content follows
  the host's revision route; ambiguous intent uses its clarification choices.

Use `paper-lookup` and `citation-management` for new literature discovery and
verification, and `statistical-analysis` for disputed statistical interpretation.
Existing verified literature may be reused with its version and access level.
Record actual loads, companion reads and outputs in the host's `skill_usage`.

## 1. Identify the comparison and its purpose

Create a compact comparison inventory in the existing `argument` or `literature`
artifact. For each comparator record its role, rationale, source/version,
implementation provenance, inputs, endpoint, evaluation population/protocol,
available results and intended manuscript location. Distinguish:

| Evidence | Question it answers | Reporting boundary |
| --- | --- | --- |
| Simple/reference model | Does complexity add value over a credible simple solution? | Explain why retained; never choose only weak comparators |
| Established/closest computational method | How does this approach compare with a relevant alternative? | Same-study implementation versus published score must be identifiable |
| Clinical/pathological standard, when applicable | Does the model add value over existing assessment? | Match clinical endpoint and input availability; do not invent an unavailable score |
| Component ablation or matched control | Which implemented change could explain an effect? | Name changed and held-fixed factors; distinguish information, capacity and optimization |
| Sensitivity/resampling/external validation | Is the finding stable under the examined conditions? | Not a substitute for component ablation or evidence of causal mechanism |
| Literature-only comparison | Where does this study sit in current research? | Context, not a same-protocol ranking |

Choose relevant roles, not a fixed number of methods or references. Identify
important missing comparators and explain the implication for the claim. Do not
pad the manuscript with unrun-experiment status tables. An unavailable clinical
baseline can be a concise scope limitation; it cannot become evidence of clinical
superiority. Read recent primary work for the actual task before claiming broad
coverage or state of the art; the example papers are not an evergreen SOTA list.

## 2. Establish what is comparable

For comparisons intended to isolate one factor, check the patient/case split,
unit of analysis, labels/endpoint, feature encoder and pretraining exposure,
patch selection/resolution/budget, model inputs, training and tuning protocol,
checkpoint/model/threshold selection, seeds/folds, and metric definition.
State which factors are held fixed and which differ by design. For multimodal
or full-system comparisons, explicitly describe the different information or
resources; do not pretend they isolate one architectural component.

Report actual implementation fidelity: official code/version, reimplementation,
adaptation or missing details. A method name does not prove faithful reproduction.
A shared optimizer alone does not establish fair comparison, and identical
hyperparameters are not universally fair to different architectures. Describe
actual tuning opportunity and deviations without retroactively changing results.

Separate **checkpoint selection**, **host/final-model selection**, and **threshold
selection**. Record what data informed each. Validation-selected checkpoints do
not erase test-informed model choice or prior test inspection. Resolve conflicting
records from authoritative provenance/adjudication, not a blanket sentence that
all selection used validation. Unresolved conflicts remain visible in the audit.

Never directly rank risk-grade AUC against survival C-index, different label
definitions, populations or internal versus external validation. Keep literature
scores in a separately labeled context table when numerical comparison would
otherwise imply equivalent conditions.

## 3. Write the comparison across sections

- **Introduction / related work:** synthesize the relevant approaches, their
  different information/assumptions, and the specific comparison question. Explain
  why the chosen reference and closest alternatives answer it. Avoid a list of
  paper titles or unsupported claims that an entire field neglected the question.
- **Methods:** define the reference/final model, comparator identities, intended
  contrast and actual evaluation protocol. Separate the original selection rule
  from retrospective explanation. Define components and ablation switches where
  relevant; do not invent preregistered hypotheses after observing results.
- **Results:** use a comparison table or equivalent explicit presentation, then
  describe the primary contrast, its magnitude/uncertainty, consistency and
  bounded implication. Keep unfavorable, null and contradictory comparisons.
  Do not merely list the winner or narrate execution order.
- **Discussion:** explain what the findings establish relative to the research
  question and prior work, which differences could account for disagreement, and
  which explanations remain hypotheses. A negative comparison can support a
  useful cohort-specific reference; it does not prove universal equivalence or
  that a mechanism is impossible.

Suggested same-study table fields (adapt to task): method/version; input/features;
cohort and evaluation partition; primary metric with available uncertainty;
repetition unit/count; relevant secondary metric; test-use status. Put shared
protocol in the caption/Methods, not repeated in every cell. Preserve validation
and test results when both are needed to explain selection; do not rank on test
alone. Show measured cost only when it supports a stated efficiency claim and
hardware/workload are comparable; missing cost is not zero.

Suggested literature context fields: source/year; task/endpoint; inputs; cohort
and evaluation unit; internal/external validation; key finding; concrete reason
it is or is not directly comparable. Use this only when helpful; it may be a
supplement or concise synthesis rather than another mandatory main-text table.

Use the uncertainty actually available. Label seed/fold SD separately from
patient-level confidence intervals; identify the resampling unit. Never invent
intervals or P values from rounded means. Report paired differences only from
matched records, label absolute versus relative change, and reserve significance,
equivalence and noninferiority language for the corresponding valid analysis.
Missing uncertainty may require narrower wording, not an automatic new run.

For mechanism claims, map **hypothesis → controlled change → predicted observation
→ observed effect/uncertainty → interpretation** in the existing argument. Do not
call a cross-validation exercise an ablation or infer biological causation from
attention heatmaps. A retained baseline needs a selection rationale; it need not
be repackaged as a novel mechanism.

## 4. Review and record the actual version

Before submitting a new draft or substantive scientific revision, create
`baseline_comparison_review.json` under the current versioned manuscript stage.
It is a model-authored assessment, not platform attestation or author approval.
Include:

- `manuscript_sha256`, actual `reviewer`, `status` (`passed`, `needs_revision`, or
  `not_applicable`), and source artifact IDs/paths with hashes where available;
- `checks`, each with `id`, `verdict` (`passed`, `needs_revision`, or
  `not_applicable`), manuscript/table and source locators, and a substantive
  `reason` supporting the judgment;
- `gaps`: each missing/conflicting item, affected claim, disposition
  (`corrected`, `claim_narrowed`, `scope_limit`, or `unresolved`) and location.

Required check IDs: `comparator_rationale`, `protocol_comparability`,
`selection_provenance`, `quantitative_reporting`, `literature_positioning`,
`ablation_distinction`, `claim_calibration`. Assess applicability by manuscript
content, not by whether the author has used the word baseline. A method claim
without comparison evidence is a gap, not a not-applicable pass.

Verify agreement across abstract, Methods, tables/captions, Results and Discussion.
Only mark passed after unsupported asserted comparisons are corrected or narrowed
and unresolved factual contradictions are absent. A bounded missing experiment
is not itself a blocker; an unsupported superiority claim is. Repeated generic
reasons or a read receipt are not an executed review. Changed scientific content
requires reassessment and a new hash; never just relabel an old pass.

On PathoReason register the report as `baseline_review`, include it in checkpoint
evidence and `skill_usage`, and reference it from the existing integrity report.
Put unresolved claim-affecting problems in the current review issues, not a
generic future checklist. Preserve the existing five author gates and budgets.
