# MIL classification task

This repository is task-local and can be adapted by the research Agent. Preserve the imported Git history. Commit all execution files, then register a new revision with expected_revision before checking/freezing. Do not put patient manifests, credentials, features, checkpoints or results in Git. Keep them in controlled input/output storage with references and digests.

The template uses the explicit public MIL builder, copied with its upstream dependencies and license. Supported adapters are MEAN_MIL, MAX_MIL, AB_MIL; other requested models remain explicit adaptation gaps, never silently remove them from a benchmark. Use numeric dropout and an explicit task configuration. The example is a schema example, not a scientific protocol or execution authorization.

A source-structure check does not prove trainability. The task-local runner uses the same builder for CPU preflight and training. Real execution needs immutable environment and input bindings, external isolation, matrix/compute authorization and a hard budget. The current platform source snapshot alone does not supply these.

Outputs, failed attempts, evaluation versions, test exposure and costs are append-only research evidence. A changed scientific objective generally creates a child task; implementation repair retains this task and creates a new commit/revision. Public updates are reviewed and applied by the Agent to a new revision, never hot-patched into a run.
