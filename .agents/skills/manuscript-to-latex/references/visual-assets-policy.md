# Visual assets policy

## Current SVG switch

Automatic SVG generation and reconstruction are disabled by default. Do not
invoke Graphviz SVG export, AutoFigure-Edit reconstruction, local SVG builders,
or SVG packaging unless the user explicitly enables the capability. An
unchanged author-supplied SVG may be consumed as an existing input when its hash
and provenance are preserved. While the switch is off, export truthful
data-derived plots as PDF/PNG and preserve briefs, captions, source data, and
manual-art requirements for figures that still need design. Do not manufacture
scientific content. Conceptual raster generation has a separate capability
selection; see [raster-generation.md](raster-generation.md).

## Choose the source by meaning

- Data figure: generate only from verified row-level or aggregate data adequate for that exact plot. Use `scientific-visualization`, save the plotting code, input hash, and export settings.
- Method or study flowchart: freeze an evidence contract and manual-art handoff. Use an existing reviewed asset or an independently configured raster candidate that passes review; deterministic editable reconstruction requires explicit re-enablement.
- Model architecture: derive every connection and tensor label from the verified method specification. Do not add attractive but unsupported modules.
- Graphical abstract: may use deterministic vector design or, when the journal permits and the user requests it, `imagegen` for conceptual artwork. Record tool use and disclosure needs.
- Primary research image: preserve the original. Never synthesize, inpaint, or selectively enhance histology, microscopy, patient, blot, or scan evidence.

## Export rules

- Prefer PDF/EPS for newly exported line art while SVG generation is disabled. Existing reviewed SVG remains acceptable as an input; retain an editable source when available.
- For raster photographs use at least 300 dpi; for bitmap line art use at least 1000 dpi; for mixed line/halftone art use at least 500 dpi unless the current journal guide states otherwise.
- Use colorblind-safe palettes, adequate contrast, readable type at final print size, consistent panel labels, and units on axes.
- Provide an authoritative editable source, a final export, a caption, and an asset manifest with source-data hash. An SVG wrapper containing raster images does not by itself satisfy the vector/editability requirement.
- Do not reconstruct patient-level ROC/PR curves from mean AUROC/AUPRC values.

## Required QA

Check final-size legibility, font embedding, dimensions, resolution metadata, transparency, clipping, color space, caption agreement, and every in-text citation. For JPI graphical abstracts, also check the current minimum dimensions and separate-file requirement in the official guide.
