# ADR 0007: No animation library. CSS transitions and a count-up hook only

Status: accepted (Phase 3)

## Context

The master prompt lists Motion as the animation library. Its use so far is limited: KPI count-up, skeleton shimmer, and the working indicator.

## Decision

Animation uses CSS (`@keyframes` for the shimmer and the working pulse) and one small hook (`web/src/lib/useCountUp.ts`) for the count-up. Every animation is disabled under `prefers-reduced-motion`. The equity chart's entry animation is turned off when reduced motion is requested (`prefersReducedMotion` in `theme.ts`).

## Consequences

- No additional runtime dependency, which keeps the license list short.
- More complex choreography (page transitions, shared-element moves) would need Motion or the View Transitions API. Add it when a screen needs that behaviour, with a new license entry.
