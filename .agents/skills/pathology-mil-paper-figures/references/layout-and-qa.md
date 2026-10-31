# Layout and QA

## Final physical size

Record target venue, actual column width and figure height in mm before final layout. If the venue is unknown, use a declared preview width (for example 180 mm for a multi-panel figure), not a claim of journal compliance. Convert mm to inches with /25.4 and render at intended size. Do not assume a large notebook preview remains readable after reduction.

Use a consistent font, roughly 8–10 pt text and >=7 pt annotations at final size; adjust to verified venue requirements. Use >=0.5 pt lines, readable marker sizes, panel labels A/B/C in stable order and matched axes for comparable panels. A colorblind-safe palette (blue/orange/teal) needs redundant shapes, line styles or hatching; color alone cannot encode missingness or classes. Separate CI and SD visually and in the legend. Preserve negative values, outliers and failed/missing panels.

## Exports

Keep a code-native/vector master (SVG or PDF) for numeric plots and exact diagrams. Export a PNG at 300 dpi or the venue's specified raster resolution; record dpi and pixel dimensions. SVG requires explicit opt-in under the host's `svg_generation_enabled` policy. Do not rasterize text or silently regenerate a frozen image during typesetting. SVG text must remain editable where possible. PDFs and PNGs should match the same generation's limits, labels and data. Avoid timestamp metadata where deterministic hashes are feasible.

## Mechanical and pixel inspection

1. Render at final physical size and open the actual PNG, not only source code or a thumbnail.
2. Inspect each panel at 100% pixel scale and the entire figure at final placement width. Inspect long labels, panel edges, tick overlap, legends, units, denominators, titles/footers and clipping. For dense figures inspect crops of the original pixels without changing data.
3. Check contrast/grayscale, line/marker distinction, axis direction/limits, equal/shared normalization where intended, colorbar bounds and alignment. Tissue panels require original pixels and calibrated scale verification.
4. Check that caption panel letters match the displayed panel map and that alt text describes encodings and unavailable evidence without stronger conclusions.
5. Record image SHA-256, reviewer identity, actual viewing method, inspected dimensions, findings, and passed/blocked status. Automated dimensions or bounding-box checks support but do not replace pixel inspection. If pixel viewing is unavailable, leave visual review pending/blocked.

## Caption and alt contract

Caption: question/role → what each panel displays → cohort/split/denominator → estimator and exact uncertainty → abbreviations/units → statistical test or 'descriptive; no significance test' → material limitations. Do not imply an absent panel or clinical validation. Alt: concise panel order and visual encodings, direction of observations only when supported, and important missingness. Keep detailed numeric values in accessible source tables rather than stuffing them into alt text.

## Separate reviews

Visual QA evaluates legibility, rendering and visual correspondence. Scientific QA checks source/transformation, sampling unit, split integrity, uncertainty, causal/clinical wording and omitted negatives. Maintain separate status, reviewer and findings for each. A real visual inspection may pass while scientific and author reviews remain pending. Smoke tests cannot auto-confirm a manuscript gate or label candidates submission-ready. Corrections create a new version; the new image/caption hashes require renewed binding and review.
