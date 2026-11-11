# ADR 0002: Numbers come from deterministic code, not the LLM

- Status: accepted
- Date: 2026-11-09

## Decision

Every figure shown in the dashboard, reports, and Coach answers is computed by typed Python functions and returned as a tool result. The language model selects tools and explains their output. It never does arithmetic and never writes a number that is absent from a tool result in the same turn.

## Reasons

- A trader acting on a wrong profit factor or drawdown can lose money. Models make arithmetic and citation errors that are hard to spot.
- Deterministic code can be unit-tested against hand-calculated fixtures and property-tested with Hypothesis.
- The app must work with no model attached, so the rules-based Coach needs the same numbers.

## Consequences

- Every metric needs a definition in `docs/metrics-definitions.md` and a test before the UI uses it.
- The model's output is checked against tool results. A number that does not appear in the tool output is a failing check (planned for Phase 5).
- Model quality changes only the wording and the choice of tools, so a weaker local model degrades presentation rather than accuracy.
