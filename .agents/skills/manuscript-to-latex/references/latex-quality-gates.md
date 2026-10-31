# LaTeX quality gates

## Blocking gates

- The source manuscript and bibliography hashes are recorded.
- The journal guide was checked from its official site on a recorded date.
- No missing bibliography keys, undefined citations, undefined references, duplicate labels, or missing graphic files.
- The compiler exits with code 0 using a fresh output directory and produces a new nonempty PDF.
- No `TODO`, `TBD`, `AUTHOR INPUT REQUIRED`, internal draft banner, or claim/evidence audit marker remains in submission mode.
- Article-type limits pass or an explicit editor-approved exception is documented.
- All author and declaration fields are supplied by the authors.
- JPI anonymity checks pass for the anonymous manuscript and PDF metadata.
- Every table and figure is cited; captions explain abbreviations and symbols.
- Wide-table rows have consistent baselines: atomic values such as `mean ± SD` are not split across lines in only some cells, and any font reduction is applied uniformly to the table body.
- Methodology-figure manifests include authoritative editable sources, element-level provenance for schema `1.1`, target-size machine QA, and a recorded human visual disposition.
- The PDF has been visually inspected page by page.
- The manifest preserves upstream test-use and claim-boundary restrictions.

## Warnings requiring disposition

- overfull or underfull boxes;
- floats far from their first citation;
- equations or tables extending beyond margins;
- wide tables requiring body text below 6.5 pt or producing inconsistent row heights after adaptive scaling;
- non-embedded or substituted fonts;
- rasterized text in diagrams;
- SVG/PDF figures whose container is vector but whose essential labels or line art are embedded raster images;
- inconsistent English variant, abbreviations, units, decimal precision, or model naming;
- source bibliography records without DOI when a DOI exists;
- unused bibliography entries;
- portal-only or author-signature files still outstanding.

## Compile policy

Use a fresh build directory and run:

```text
latexmk -pdf -interaction=nonstopmode -halt-on-error -file-line-error
```

Check the process return code and the age/size of the generated PDF. Never accept a stale PDF left by an earlier build. Keep the `.log`, `.fls`, `.aux`, `.bbl`, and machine-readable build report for traceability.
