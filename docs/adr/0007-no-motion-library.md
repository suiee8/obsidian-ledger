# ADR 0007: Use browser APIs for interface motion

Status: accepted, with implementation notes updated for the current shell

## Context

The original decision covered KPI count-up, loading states, and chart entry effects. The shell now also includes a wordmark flip, social links, and a pointer trail.

## Decision

Use CSS for the shell and loading effects, React hooks for count-up, and Pointer Events with a Canvas overlay for the cursor trail. Shell effects have reduced-motion alternatives and native cursor behavior on form controls. See the [accessibility notes](../accessibility.md).

## Consequences

- No additional runtime dependency, which keeps the license list short.
- More complex choreography (page transitions, shared-element moves) would need Motion or the View Transitions API. Add it when a screen needs that behaviour, with a new license entry.
