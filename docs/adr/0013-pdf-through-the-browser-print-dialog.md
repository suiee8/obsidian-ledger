# ADR 0013: Use the browser print dialog for PDF output

- Status: accepted
- Date: 2026-11-12

## Context

The project has no Reports screen or PDF-generation pipeline. Maintaining a PDF engine would add dependencies and a second rendering path to validate.

## Decision

When a user wants a PDF copy of an exported HTML Coach report, use the browser's print dialog and its “Save as PDF” destination. Do not add an application-generated PDF export or a Reports screen in Phase 6.

## Consequences

- PDF layout and pagination are controlled by the browser and the user's print settings.
- Markdown and HTML remain the portable report formats; there is no guarantee of identical PDF output across browsers.
- A dedicated Reports screen or PDF generator requires a separate product decision.
