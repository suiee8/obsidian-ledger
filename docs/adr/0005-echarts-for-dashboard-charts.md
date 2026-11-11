# ADR 0005: Apache ECharts for the dashboard charts

Status: accepted (Phase 3)

## Context

The master prompt names TradingView Lightweight Charts for the equity curve. The dashboard also needs an R histogram and an edge radar, which Lightweight Charts does not draw.

## Decision

Use Apache ECharts 6 (Apache-2.0) for the equity curve, the R histogram, and the edge radar. Only the chart types and components the app uses are registered (`web/src/lib/echarts.ts`).

## Consequences

- One chart library covers every dashboard chart, with one theme and one resize path.
- The ECharts code loads in its own chunk after the first paint, so the entry bundle stays at about 119 kB gzip. The chunk itself is 188 kB gzip.
- Lightweight Charts is not installed. The equity curve has no time-scale navigation of the kind Lightweight Charts provides. Revisit this if the Analytics screen needs it.
- The Apache-2.0 NOTICE file must stay with any redistributed copy (see `docs/dependencies.md`).
