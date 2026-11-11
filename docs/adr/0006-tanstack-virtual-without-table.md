# ADR 0006: TanStack Virtual with plain column definitions, no TanStack Table

Status: accepted (Phase 3)

## Context

The master prompt asks for a virtualized trades table. TanStack Table v9 was evaluated and rejected because its feature-based API is unfamiliar to this codebase and adds a dependency layer the table does not need.

## Decision

The Trades screen uses `@tanstack/react-virtual` for row virtualization. Columns are a plain array of keys with labels, widths, and cell renderers (`web/src/screens/Trades.tsx`). Rows are a fixed height and memoized (`GridRow`), so a scroll step re-renders only rows whose data changed. Rows are loaded in blocks through the offset-based trades page endpoint.

## Consequences

- No table library to learn or upgrade. Sorting, column visibility, and inline editing are written against the app's own state.
- Keyset pagination is not used yet. Offset paging is fast enough at 10,000 rows (the measured page query is about 0.13 s) and is the first thing to change if the table grows past that.
- Column resizing and grouping are not built.
