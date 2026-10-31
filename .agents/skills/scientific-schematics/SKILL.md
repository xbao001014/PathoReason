---
name: scientific-schematics
description: Design and review scientific concept and mechanism diagrams using the configured Seedream route in PathoReason. Use for method, architecture or mechanism illustrations; use deterministic plotting for measurements and real pixels for tissue imagery.
---

# Scientific schematics in PathoReason

Use the configured Seedream model via `scripts/study_io.py image` in the PathoReason checkout. Do not switch to OpenRouter, Gemini, Nano Banana, or Codex image tools. The model and credential are configured by the operator; never copy a key into a prompt or command argument.

Before generation, bind the visual brief to actual method/source files. Distinguish mechanism from a simple process flow; show the relevant entities and interactions accurately. Preserve topology, units, mathematical meanings and the distinction between observed results and conceptual illustration. Never generate fake tissue, attention maps or quantitative evidence. Read the figure-planning references in `../pathology-mil-paper-figures/` as relevant.

One request produces one versioned candidate without automatic retry. Inspect the actual image, checking labels, links and scientific meaning. DeepSeek text-only narration is not visual inspection; if a visual reviewer is unavailable, preserve `pending_review` for the operator. Retain each attempt and its receipt. Author approval remains a separate workflow gate.

The historical provider-specific entry is archived in `references/upstream-entry.md` for provenance only. Its paid-model examples do not override this route. The original supporting design references and scripts remain available, but their OpenRouter helpers are not the active execution path.
