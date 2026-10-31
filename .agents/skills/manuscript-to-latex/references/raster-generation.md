# Original-raster method illustration route

In the ordered manuscript workflow, generate the method figure during M4,
store its original, receipt, specification, caption and visual review under
`03_manuscript/figures/<figure-id>/`, and link it from the Methods draft.
The draft author gate binds these files; M5 checks them. Stage 11 copies and
packages approved originals, never silently generates a missing method figure.
The all-at-once legacy formatter may still use the original generation route.

The method figure depicts verified architecture and information flow, not measured
results or primary research imagery. SVG reconstruction is optional and independent
of image generation. Preserve the generated PNG/JPEG bytes without upscaling or
claiming editability.

Before writing the visual brief, apply the **Choose the figure's explanatory role**
section in [methodology-figures.md](methodology-figures.md). A requested model
principle figure must visualize its mechanisms, not only list modules or training
steps. Review that explanatory quality as well as exact labels and connections.

The orchestrator supplies `method_figure_generation` settings:

- `auto`: use the existing image tool for the manuscript **Codex harness**; other
  harnesses use the configured API model, or retain a manual task if unset.
- `codex`: available only with the Codex harness; never silently switch providers.
  Check real tool availability. The original image2/imagegen route is retained,
  but a Codex CLI installation does not necessarily expose that tool.
- `api`: use the registered adapter; initially Seedream on mainland Ark.
- `manual`: consume reviewed existing assets and prepare a manual handoff.

Freeze methodology, module specification, exact labels and connectors, caption,
alt text and a deidentified conceptual visual brief. Only the brief is transmitted;
source files are hashed locally. Do not transmit an unpublished manuscript or
patient material outside the user's authorized scope.

For API generation write request JSON with `config` (provider, model, api_key_env,
size), `prompt` and `sources` (file paths). Run:

For a targeted correction after inspecting an existing candidate, optionally add
`reference_images` (up to four local PNG/JPEG paths). The adapter sends those
images, records their source hashes and writes a new candidate; it never
overwrites the source. Use an edit only within the authorized image scope.

```sh
python3 scripts/generate_method_figure.py --request request.json --output-dir 03_manuscript/figures/method/new-candidate
```

The script requires a new directory, issues one request, and saves original bytes
and `candidate.json`. Credentials are read from the execution host's environment;
never place their values in files or prompts. It does not retry after network
failure; verify provider billing/task status before considering a new attempt.

Generated images are `pending_review`, never automatically author approved.
Review exact labels, topology, module semantics, caption agreement and readability
at final print size. Keep unresolved issues explicit. A candidate can appear in a
clearly labeled review preview, with pending acceptance at the existing draft author
gate. Do not invoke `--author-approved-raster` on the agent's own authority.
After actual author acceptance, use the existing raster packaging script and
preserve the candidate receipt alongside the final asset manifest. That script's
hash/format/size checks remain required. No new automatic scientific approval is
introduced by routing or a successful HTTP response.

If the tool, model or credential is unavailable, preserve the manual-art task.
Do not pretend the image exists or use a different provider without configuration.
