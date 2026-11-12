# ADR 0011: Check AI figures against same-turn tool results

- Status: accepted
- Date: 2026-11-12

## Context

An AI explanation must not introduce a plausible but unsupported trading figure. Model arithmetic and citations are not reliable sources of financial results.

## Decision

The API computes figures deterministically and checks every number in generated answers against the exact tool results provided in the same request. User-authored text is not an allowed source. A paragraph containing an unmatched number is withheld; the rules-based report remains authoritative.

## Consequences

- Precision and percentage context are part of matching; a rounded value is not accepted unless a tool result supports that representation.
- Symbols and short trade identifiers may be named but do not authorize their digits as figures.
- Any future change to matching rules requires focused tests and must preserve deterministic report values.
