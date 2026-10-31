# Input and output contract

## Modes

`preview` creates a compilable internal reading package. Missing author metadata and unresolved journal requirements are allowed but must be listed. The manifest status is never `submission_ready`.

`submission` applies blocking checks. It requires current journal-rule verification and author-owned metadata. If any blocking item fails, preserve the generated diagnostic package but mark it `not_ready` and do not call it submission-ready.

## Accepted manuscript inputs

- Markdown with Pandoc citation syntax such as `[@key]`.
- LaTeX may be audited and compiled directly, but the supplied preparation script currently converts Markdown. For native LaTeX, copy sources into a new package and run the compiler plus the same gates.
- A BibTeX file whose keys agree with manuscript citations.

## Metadata JSON

Submission mode expects this shape. Values must come from the authors.

```json
{
  "authors": [{"name": "Full Name", "affiliations": ["a"], "orcid": "optional"}],
  "affiliations": [{"id": "a", "text": "Department, Institution, City, Country"}],
  "corresponding_author": {
    "name": "Full Name",
    "email": "name@example.org",
    "postal_address": "Full postal address"
  },
  "declarations": {
    "ethics": "Author-confirmed statement or not applicable with reason",
    "consent": "Author-confirmed statement or not applicable with reason",
    "competing_interests": "Author-confirmed statement",
    "funding": "Author-confirmed statement",
    "author_contributions": "Author-confirmed statement",
    "data_availability": "Author-confirmed statement",
    "ai_use": "Author-confirmed statement or none"
  },
  "journal_verification": {
    "url": "official Guide for Authors URL",
    "checked_on": "YYYY-MM-DD"
  }
}
```

An empty string, `TBD`, or placeholder does not satisfy a field.

## Package contents

The preparation script writes:

- `manuscript.tex` — canonical peer-review manuscript entry; anonymized for JPI;
- `main.tex` — compatibility wrapper loading `manuscript.tex`, not a second source;
- `manuscript_body.tex` — Pandoc conversion output;
- `title_page.tex` — generated only when metadata support it;
- `declarations.tex` — generated only from author-supplied declaration text;
- `references.bib` — copied verified bibliography;
- `figures/` — copied assets when provided;
- `source_clean.md` — traceability markers removed, original content otherwise preserved;
- `requirements_report.md` — human-readable rule and gap report;
- `submission_manifest.json` — hashes, counts, transformations, source provenance, readiness state;
- `build/<timestamp>/` — fresh compile logs and PDF after compilation.

JPI requires the title page and anonymized manuscript as separate submission files. Portal-generated declaration forms are external artifacts and are listed rather than fabricated.

Modern Pathology submission mode requires a supplied cover letter. JPI submission mode requires the supplied Elsevier declaration-form file. Both are copied into `auxiliary/` and hashed.

When the package is embedded in `_manuscript_pipeline`, the derived package
belongs under `06_submission/latex/`. Its `figures/` directory contains only
the accepted files referenced by TeX. The complete figure-generation and
review record belongs separately under `06_submission/figures/`, with an
aggregate `figure_manifest.json` and `figure_review_report.md`; see
`methodology-figures.md`. Do not discard that record after copying assets into
the LaTeX package, and do not treat `latex/figures/` as a scratch workspace.

The ordered pipeline defaults to `svg_generation_enabled=false`. With that
switch off, an SVG in either submission figure tree must be an unchanged,
hash-matched intake asset; generated or reconstructed SVG is a blocking policy
violation. If no reviewed non-generated asset is available, keep the brief and
manual-art handoff, use `status: no_figures`, and record the missing figure in
the review report. This status does not mean the scientific need disappeared.

## Versioning and provenance

- Record SHA-256 hashes of every input and major output.
- Never overwrite the manuscript or bibliography.
- Use a new output directory for every target-journal/version combination.
- Retain the upstream draft/test-use state in `submission_manifest.json`.
