"""Evidence-bound presentation revisions preserve the approved scientific basis.

The comparison report is an Agent audit claim, never independent verification or
an author decision. Its exact input/output bindings and unchanged declarations
are enforced here; semantic and visual checks remain the research Agent's work.
"""
import json
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field
from .contracts import Identifier
from .persistence import Conflict

CHECKS=('data_values','statistics','labels_and_units','scientific_claims','captions','references')

class PresentationChange(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    original_artifact_id:Identifier
    revised_artifact_id:Identifier
    description:str=Field(min_length=1,max_length=600)


def validate_presentation(manuscripts,pid,w,req,materials):
    if req.gate!='delivery':
        if req.presentation_only or req.presentation_changes:raise ValueError('presentation_requires_delivery')
        return
    science=w['approved'][3]
    originals={m['artifact_id']:m for m in science['materials']}
    replacement_ids={c.revised_artifact_id for c in req.presentation_changes}
    visual_ids={m['artifact_id'] for m in materials if m['role'] in ('figure','table')}
    changed_visuals=visual_ids-originals.keys()
    required=(w.get('revision_context') or {}).get('kind')=='presentation' or bool(changed_visuals) or req.presentation_only or bool(replacement_ids)
    if not required:return
    if not req.presentation_only:raise ValueError('presentation_audit_required')
    if req.scientific_basis_digest!=science['digest']:raise Conflict('manuscript_scientific_basis_changed')
    # Scientific manuscript/source artifacts are immutable. Revised typesetting
    # belongs in the delivery source package, not a replacement scientific draft.
    if any(m['role']=='manuscript' and m['artifact_id'] not in originals for m in materials):raise Conflict('presentation_scientific_content_changed')
    if len(replacement_ids)!=len(req.presentation_changes) or len({c.original_artifact_id for c in req.presentation_changes})!=len(req.presentation_changes):raise ValueError('presentation_duplicate_replacement')
    if changed_visuals!=replacement_ids:raise ValueError('presentation_replacements_mismatch')
    current={m['artifact_id']:m for m in materials}
    for change in req.presentation_changes:
        original=originals.get(change.original_artifact_id);revised=current.get(change.revised_artifact_id)
        if not original or original['role'] not in ('figure','table') or not revised or revised['role']!=original['role']:raise ValueError('presentation_original_required')
        if original['artifact_id']==revised['artifact_id']:raise ValueError('presentation_new_version_required')
    reports=[m for m in materials if m['role']=='presentation_audit']
    if len(reports)!=1:raise ValueError('presentation_audit_required')
    try:report=json.loads(manuscripts.material_bytes(pid,reports[0])[1])
    except (ValueError,UnicodeError) as exc:raise ValueError('presentation_audit_invalid') from exc
    if not isinstance(report,dict) or report.get('schema_version')!='pathoreason.presentation-audit/1':raise ValueError('presentation_audit_invalid')
    if report.get('scientific_basis_digest')!=science['digest']:raise Conflict('presentation_audit_basis_changed')
    expected={m['artifact_id']:m['sha256'] for m in materials if m['role']!='presentation_audit'}
    if report.get('material_sha256')!=expected:raise Conflict('presentation_audit_version_mismatch')
    declared=[c.model_dump(mode='json') for c in req.presentation_changes]
    if report.get('changes')!=declared:raise Conflict('presentation_audit_changes_mismatch')
    checks=report.get('checks')
    passed=isinstance(checks,dict) and all(checks.get(k)=='unchanged' for k in CHECKS)
    if not passed or report.get('status')!='passed':
        if req.audit_status!='blocked' or not any(i.blocking and not i.resolved for i in req.issues):raise Conflict('presentation_scientific_review_required')


def instructions(script):
    return '''PRESENTATION AND POST-DELIVERY REVISIONS: Final author approval does not prohibit later authorized editing. A clear request to adjust figure/table appearance, typography, spacing, colors, layout, page breaks, journal formatting or export quality is sufficient authority to prepare a new version within the existing scope. Preserve approved originals and all budgets; no new experiments, analysis or approvals. Determine meaning from the actual request and context, not keyword triggers. Visual changes must preserve data values, statistics, labels/units meaning, scientific claims, captions meaning and references. Correcting a data point, significance mark, axis meaning, category meaning or factual label is content revision, even when called a small figure fix. When the scope is ambiguous, offer 2–3 clarification choices with scope=continue (presentation only / scientific content revision), preserving free text, and wait; do not reopen merely for discussion or conditional/quoted requests.
Use the authenticated helper '''+script+''' with the current dialogue turn_id/grant, expected_goal_revision, expected_revision, source=user_message (source_id=current user turn) or author_feedback (source_id=latest revise receipt at), exact instruction_excerpt and reason. Presentation: revision_kind=presentation,target_gate=delivery. Content: revision_kind=content,target_gate=scientific. It supports final approved packages and binds a new same-project conversation only after explicit interpretation of the current user's revision request; it never takes over an unfinished goal in another conversation. After routing, use the returned revision and continue the authorized work in this turn. No repeated reopen confirmation. If a presentation revision is already active, continue it without replaying a routing command.
For presentation-only delivery keep the approved scientific packet digest and existing scientific approval. Read manuscript-to-latex and its relevant figure guidance; inspect the requested originals and generate revised files in NEW paths. For pathology illustration generation/editing use the configured Seedream chain and actual visual review; no model diagram fallback. Do not redraw scientific data or substitute generated tissue for evidence. Only changed presentation needs renewed visual/content-invariance checks, PDF page QA and author delivery review; do not repeat blueprint/draft/peer review or unrelated literature/experiments. Submit pdf, source, pdf_qa, checklist plus role=presentation_audit, presentation_only=true. Add changed figure/table files as role=figure/table and presentation_changes=[{original_artifact_id: approved SCIENTIFIC figure/table ID,revised_artifact_id:new published ID,description:what visual detail changed}]. These replace presentation only, not the immutable scientific source. The JSON presentation_audit must contain schema_version=pathoreason.presentation-audit/1, scientific_basis_digest, material_sha256 mapping EVERY submitted material except the audit itself to its exact SHA, changes equal to presentation_changes, status=passed, checks={data_values:unchanged,statistics:unchanged,labels_and_units:unchanged,scientific_claims:unchanged,captions:unchanged,references:unchanged}. Perform real comparisons and image/page inspection before claiming unchanged; a checksum alone cannot prove semantic invariance. If content changed or cannot be verified, report audit_status=blocked with a blocking issue, explain the affected scope, and resolve via scientific revision instead of asking the author to waive it. Never approve or mark the revised delivery complete yourself.\n'''
