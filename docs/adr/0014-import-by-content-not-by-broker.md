# ADR 0014: Import by content, not by broker

- Status: accepted
- Date: 2026-11-12

## Context

Trade-history exports vary by platform, account configuration, locale, and export version. A broker-name gate excludes unknown formats and becomes stale as export layouts change. Missing prices and P&L must remain unknown rather than being fabricated.

## Decision

Infer import layout and column roles from both headers and sampled cell content. Broker adapters may raise confidence, but they are optional. Present capabilities, evidence, samples, and warnings for user review; require explicit mapping when the evidence is ambiguous. Preserve missing financial values as null and provide activity-only summaries when P&L or prices are absent.

## Consequences

- New and unfamiliar formats can be imported without adding a broker adapter.
- Ambiguous and headerless files require manual mapping instead of silent assumptions.
- Metrics and Coach conclusions must reflect unavailable data rather than treating missing values as zero.
- Format-specific adapters remain useful as optional inference hints and regression fixtures.
