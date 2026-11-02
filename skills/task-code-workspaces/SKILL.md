---
name: task-code-workspaces
description: Create independent MIL task code repositories, register Agent revisions, check and freeze source snapshots, or inspect public template updates in a PathoReason formal study.
---

# Task code workspaces

Resolve the current research task from the conversation and attached plan. A task can span conversations. For an existing task, inspect its registered revision before editing. A changed scientific target usually creates a child task; a repair or a training seed change normally stays in the task. Clarify only a material ambiguity. Preserve unchanged settings and prior evidence.

Call `/home/bxn/projects/PathoReason/.venv/bin/python /home/bxn/projects/PathoReason/scripts/task_code.py` with one JSON object on stdin. The CLI works from the current workspace; changing directories is unnecessary. Copy `turn_id` and `grant` from the **current** trusted dialogue capability; never print or save the grant. Responses are authoritative receipts. No project argument is accepted: the service binds the current project and conversation.

Fields: `operation`, `turn_id`, `grant`; mutations also require a unique stable `idempotency_key`. Existing-task mutations require `task_id` and `expected_revision` from the last receipt.

- `list`: find current task identities. `inspect` with `task_id`: inspect provenance, revisions, checks and snapshots.
- `create`: include `objective`, `template: "mil-classification/1.0.1"`, and optional `parent_task_id`. The returned `code_path` is a new independent Git repository. Do not copy/move an old research directory.
- Adapt files only in that task repository. Commit code and task instructions with a meaningful message, without credentials, data, results or checkpoints. `revise` registers the new clean commit; include `reason`. A conflict requires inspecting the latest revision and preserving the other change; do not reset history or force-register.
- `check`: syntax, exact dependency declarations and clean-byte checks. It does **not** execute model code or validate training. `freeze` takes the returned `check_id` and captures a source snapshot. Any change requires a new commit, revision and check.
- The latest template is `mil-classification/1.0.1`: it packages the same MIL sources independently and prevents bytecode cache writes before imports. Existing tasks and snapshots retain their original version.
- `inspect_update`: first read the published `catalog` in `list` or current trusted context, then include `task_id` and target `template`. Comparing the imported version with itself does not establish that no newer version exists. It returns source differences without editing the task. Review compatibility, apply useful changes yourself, then commit/register/check a new revision.
- `launch` is currently closed with a structured readiness gap: immutable Python environment, controlled inputs, matrix/budget and restricted executor integration are pending. Do not bypass the gap by executing the task runner directly. A source snapshot is not a runnable scientific experiment.

A repeated successful request with the same key returns the original result. A failed or pending receipt stays recorded; inspect it before a new request. Never erase a failure, old run, evaluated-test exposure, checkpoint or budget to retry. Report the achieved node and actual gap, without asking the user to supply Git/SHA details or repeating an already accepted task decision.


When the selected research goal includes preparation, create/adapt/register/check/freeze are internal execution steps: continue them without asking the user to approve each Git operation, synthetic check or source snapshot. For a material model/scope/resource trade-off use a continue-scoped clarification; resolve the choice and immediately resume the same goal. Keep native permission denials, existing bounds and the closed launch gate intact. A platform launch gap is not fixed by editing compute.json or repeatedly asking the user to confirm training. Finish independently available preparation and report the remaining platform blocker with its owner and concrete remedy.
