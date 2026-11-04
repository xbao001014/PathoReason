# Stage execution and evidence

The host's current author gate remains authoritative. These are work dependencies,
not new author approvals. Execute inline using the configured research Agent.

## Required dependencies by work

| Work | Explicitly load | Read and execute | Observable output |
| --- | --- | --- | --- |
| Literature discovery or background strengthening | paper-lookup; citation-management; academic-research-suite | paper-lookup references for each queried database; ARS literature_strategist_agent.md | dated queries/endpoints, retrieved identifiers and access levels, deduplicated bibliography, claim-to-source locators |
| Synthesis and prose drafting/revision | scientific-writing; academic-research-suite | this skill's authorial-voice.md; scientific-writing references/evidence_workflow.md; ARS draft_writer_agent.md | paragraph evidence plan and public scientific argument, revised manuscript, semantic consistency review |
| Pathology conceptual illustration in draft | pathology-figures; pathology-mil-paper-figures; scientific-schematics; manuscript-to-latex (figure capability only) | manuscript-to-latex references/methodology-figures.md and references/raster-generation.md; relevant task reference selected by pathology-mil-paper-figures | evidence-bound visual brief, actual Seedream original, provider receipt, caption, image inspection and manuscript binding |
| Numerical plots changed | scientific-visualization | its relevant plotting/export reference | data-bound plots and source/units/uncertainty verification |
| Statistical interpretation reviewed | statistical-analysis | relevant reported-statistics reference | reported analysis/uncertainty review; no new experiment authority |
| Actual tissue/patch/attention panels | histolab via pathology-figures | coordinate/scale references | real image source and mapping; generated art is never specimen evidence |
| Model-assisted peer review after draft approval | peer-review | its applicable intake/evidence references | located review findings, subject to author adjudication |
| Frozen-content typesetting/delivery | manuscript-to-latex; documents/pdf if actually available and needed | packaging and page-QA references | source/PDF/page checks; do not run during draft |

Attempt each applicable native `skill` load. A current native failure may use a
permitted direct read of its actual SKILL.md, recorded as a fallback, not native
success. Read relevant companion files completely; discovery listings are not
file reads. Reuse still-present instructions within a turn; after context loss,
read them again. Do not treat an old failure as present unavailability.

Publish a versioned `skill_usage` report with work item, skill, load route,
actual tool-call identifier when available, companion paths and hashes, and
output paths/artifact IDs. Missing call IDs are unknown, never invented.
Distinguish discovered, loaded/read, executed and verified. This self-report
is audit evidence, not host attestation; compare it with the native trace.
Mark conditional skips with reasons. For a narrow correction, verified prior
literature can be reused with its source/version binding; background expansion
requires fresh targeted discovery and synthesis.
Budget exhaustion is an incomplete required dependency, not a conditional skip
or successful execution. Before checkpointing, include every review material's
artifact ID in checkpoint evidence, including reused artifacts. Rebind manifests
and audits to the new manuscript/image bytes; partial outputs do not constitute
a complete replacement packet.

## Introduction and research rationale

Read the current introduction and identify missing evidence roles before searching:
disease/task significance, existing clinical/pathology assessment and its limits,
computational pathology and representation/MIL approaches, closest work and
conflicting findings, the specific unresolved question, and why the present
comparison/intervention can answer it. Adapt paragraph count to the topic.

For each substantive paragraph record its purpose, supported claims, source
identifiers, evidence level and exact locators where available. Write a public,
evidence-backed rationale: established knowledge → specific limitation or
uncertainty → research question → justified design choices → bounded contribution.
Explain why each major comparison exists. This is a scientific argument, not
private model reasoning or an invented history of how the authors conceived it.
Do not invent preregistration, prior hypotheses or a novel mechanism retrospectively.

Use foundational and relevant recent primary sources for distinct claims. A
minimum reference count cannot certify depth: avoid citation padding and broad
claims supported only by abstracts. Seek full text for central claims; if it is
unavailable, narrow/remove the claim or state the evidence gap. Preserve negative
results, the actual prediction target and all test-use limitations. Publish
`literature` (search/evidence matrix) and `argument` (paragraph/rationale coverage)
with the draft packet; integrity review checks their agreement with the manuscript.

## Seedream during draft

On PathoReason, an authorized conceptual pathology/study illustration uses
`scripts/study_io.py image` with the configured Seedream adapter. Read the figure
references before writing the brief. Use a deidentified conceptual prompt and
local evidence paths in `sources`; only the prompt is sent, sources are hashed
locally. Depict pathology-to-patch-to-representation-to-aggregation/endpoint
relationships and scientifically relevant internal interactions. A grid of
experiment boxes does not satisfy a requested pathology illustration.

Generated tissue motifs must be clearly labeled schematic/AI-generated, never
presented as patient histology or measurements. Numeric results remain ordinary
data-derived plots. User-requested Seedream output cannot be replaced with a
matplotlib/SVG block diagram, another provider, or a textual promise.

Issue one candidate request within the authorized scope, preserve candidate.json
and original bytes in a new version directory, and inspect the image/caption.
No automatic paid retry. OCR supports label review but cannot certify morphology,
topology or visual quality; unavailable visual inspection remains an explicit
pending check. Do not assert renderer geometry for an API-generated raster.
Register the image, receipt and audit, link the actual image in the draft, and
keep it pending the existing author gate. A failed required figure is a declared
blocker, never a silently substituted box chart.
