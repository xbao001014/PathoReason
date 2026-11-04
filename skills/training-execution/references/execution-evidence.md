# Diagnose from execution evidence

Use when explaining an unexpected result, sampling/preprocessing behavior, a
failed unit, or a discrepancy between a report and implementation. Inspect only
the relevant chain; this is Agent work, not another user approval checklist.

## Recover the run

Call the public training tool with `operation: audit`, `experiment_id`, current
turn/grant, and optional `run_id` (historical run), `unit_id` or `source_file`
(relative path inside the frozen task). Default is ten attempts; continue with
`audit_offset: next_offset`. The read-only operation neither launches work nor
changes quotas, exposure counts, checkpoints, files or scientific gates.

The receipt verifies the registered run/plan, frozen source/controller bytes,
environment binding and recorded input manifests. It does not rehash the entire
environment or read feature/label content. References identify the actual frozen
files, rather than today's mutable task code. Large values are explicitly omitted
with references; read those only when needed. A rejected digest means a provenance
problem to investigate, not permission to regenerate old evidence.

## Keep these evidence levels separate

| Level | What to check | What it establishes |
|---|---|---|
| Declared capability | Frozen source, optional flags and defaults | A code path exists; not that it ran. |
| Declared plan | Exact run, unit parameters, resolved input manifest | Intended configuration and registered inputs. |
| Platform launch specification | `launch_spec`, argv, fixed environment, inheritance policy | What the controller supplied before subprocess dispatch. Not proof of successful launch or settings after task imports. |
| Task runtime observation | Matching run/attempt logs or task-generated resolved configuration with provenance | What was observed at that point; label it task-reported rather than platform-attested. A later mutation remains possible. |
| Stored input | Authorized registered file digest, format metadata and shape | The current stored representation, not necessarily the original full bag. |
| Upstream production | Matching export/ingestion/preprocessing receipt and input/output hashes | Where and how a transformation occurred. Without this, its stage remains unknown. |

Older attempts may have no launch specification. Audit preserves that absence.
Read the returned frozen controller to trace environment construction if useful;
label the conclusion as source-derived, not a captured runtime observation. An
option missing from `request.json` does not establish its effective value. An
unset optional loader cap does not establish that upstream input was uncapped.

Inspect input metadata with available safe, authorized format readers; do not
execute task code or deserialize untrusted pickle merely to discover a shape.
An input audit is not authorization to read sealed test content or run another
evaluation. Report unavailable dependencies/producer records and the consequence
for the diagnosis instead of silently inventing provenance.

## Interpret and move forward

Align cohort, subject/slide unit, split, feature version, denominator and missing
files before joining aggregate statistics from different reports. Distinguish a
descriptive difference, a mechanistic hypothesis and evidence of causation.
Shared preprocessing helps comparability under that configuration; it does not
rule out method-by-preprocessing interactions or prove that an unrestricted
experiment would rank methods identically. Preserve uncertainty from selection
and repeated evaluation; lack of demonstrated improvement is not proof of no
possible benefit.

For a corrected explanation, the research Agent appends a versioned report with
evidence references and changed claims, retains the prior report, then registers
the new artifact. State the cheapest next action that resolves a consequential
unknown. Complete authorized read-only checks independently; ask the user only
when new data, scope, compute or a scientific tradeoff is required. Never launch
training as part of audit or silently extend either budget.
