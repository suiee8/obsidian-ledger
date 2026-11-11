# ADR 0008: The P&L calendar and weekday-by-hour heatmap are CSS grids, not charts

Status: accepted (Phase 3)

## Context

Both the daily P&L calendar and the weekday-by-hour heatmap are grids of cells, each cell colored by a value. ECharts can draw both, but the cells then have no native table semantics for screen readers.

## Decision

Both are rendered as CSS grids of elements (`DailyCalendar.tsx`, `WeekdayHour.tsx`). The heatmap uses `role="table"` with row and cell roles. The calendar is a focusable region with an accessible label, and each cell names its date and P&L.

## Consequences

- The cells are real DOM elements that screen readers and keyboard users can reach, and they cost nothing in the chart bundle.
- Animating them, or drawing them on a canvas at very large scale, would need a different approach.
