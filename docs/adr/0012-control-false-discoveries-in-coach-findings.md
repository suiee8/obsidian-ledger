# ADR 0012: Control false discoveries in Coach findings

- Status: accepted
- Date: 2026-11-12

## Context

Testing many slices of a small trading journal can surface chance differences as apparent strengths or leaks.

## Decision

Keep the existing evidence controls: require minimum sample sizes for a slice and its comparison group, adjust the Coach comparison family with Benjamini–Hochberg, and reserve high confidence for sufficiently large samples with an interval excluding zero and a small adjusted q-value. Low-confidence slices are not ranked as findings.

## Consequences

- Findings are evidence triage, not proof of a durable trading edge.
- “No finding cleared the filter” means no result met the configured evidence rules; it does not prove that no effect exists.
- This ADR documents current controls and does not change their thresholds or the overtrading fixture.
