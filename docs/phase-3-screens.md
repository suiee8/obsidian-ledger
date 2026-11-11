# Phase 3: Dashboard, Trades, and Import screens

Status: built and tested. Waiting for review before Phase 4.

## Scope

- Dashboard: headline KPIs with count-up numbers, a discipline ring, equity curve with drawdown, P&L calendar, edge radar by setup, R histogram, weekday-by-hour heatmap, and ranked findings. Each finding is a leads-to-test-not-proof note, with a sample-size caveat.
- Trades: virtualized table with sortable headers, column visibility, inline editing of journal fields (double-click or Enter, Escape cancels, blur saves), Ctrl+Z to undo the last save, and a detail drawer on row click.
- Import: drag-and-drop or file picker, layout detection, questions for ambiguous fields, a preview panel, commit, and a downloadable rejected-rows CSV.
- Shell: left rail (Dashboard, Trades, Import), top filter bar (date range, account, symbol, setup, side, tag or emotion), saved views, command palette (Ctrl+K), color-blind palette toggle, and an API health badge.
- Samples: a read-only catalog of the committed fixtures.

The left rail shows only the three screens built here. Analytics, Behavior, Simulator, Reports, and Settings are Phase 4 and later.

## Backend additions

- `GET /api/dashboard` returns the report, equity series, daily P&L, R histogram, heatmap, radar, and findings in one payload. Series are downsampled with LTTB (largest-triangle-three-buckets) above 5,000 points.
- `GET /api/trades/page` (limit up to 500, sort whitelist), `GET` and `PATCH /api/trades/{trade_key}`, `GET /api/filter-options`, and `GET|POST /api/views`, `DELETE /api/views/{name}`.
- Editable fields are notes (5,000 characters), tags (300), emotion (40), and confidence (40). Every edit bumps `dataset_version`, so cached reports are invalidated.
- A new `saved_views` table stores named filter sets.

## Decisions

- `confidence` is the trader's own rating, entered by hand. It sits with emotion and plan-followed in the spec. It is stored as text.
- `screenshot_path` is mapped from columns named like "screenshot" or "chart" during import.
- Edits through `PATCH` do not ask for confirmation. Future agent writes will.
- The calendar and the weekday-by-hour heatmap are plain CSS grids, not charts. This keeps them accessible as tables and keeps them out of the ECharts bundle.
- Color-blind mode swaps the profit and loss colors to `#4169E1` and `#F5B84B`. It is applied through a `data-cb` attribute on the root element.
- Dashboard charts load lazily. The entry bundle includes the shell and KPIs, and ECharts loads in its own chunk after first paint.

## Deviations from the master prompt

- Equity Aurora uses ECharts, not TradingView Lightweight Charts. ECharts is already needed for the radar and histogram, and one chart library keeps the bundle smaller.
- TanStack Table was not used. The Trades table uses TanStack Virtual with plain column definitions.
- Motion (animation library) was not added. Animations use CSS and the count-up hook.
- Playwright was not added. There is no browser end-to-end test yet. The screenshot below was taken by hand with headless Edge.

## Evidence

Commands run from the repository root:

- `pnpm test` exits 0. It runs web lint, strict typecheck, 23 Vitest tests in 9 files, the production build, then Ruff, Pyright (0 errors), and 141 pytest tests.
- Build output: the entry bundle (`index-*.js`) is 119.3 kB gzip. The Dashboard route chunk is 4.5 kB gzip. Startup JS is about 124 kB gzip, under the 250 kB budget.
- The ECharts chunk is 187.6 kB gzip. It loads right after the layout paints, so a dashboard with charts downloads about 312 kB gzip in total. The 250 kB figure in the master prompt holds for initial JS only.
- Screenshot: `docs/screenshots/dashboard.png` (1440×1100). It shows 1,000 synthetic trades from `samples/synthetic_preview.csv`, imported through the API.

Bugs found by the screenshot and fixed:

- Calendar cells stacked in import order, not weekday order. Each cell now sets its grid row from its weekday.
- Caveat chips rendered at 18×18 pixels because of a leftover swatch rule. The dead rule is removed.
- The Equity panel left empty space below its chart. The chart now fills the panel.

## Not measured

- Dashboard response time for 100k and 1M trades at the 3 s and 15 s targets. Phase 2 measured a cold report at 5.6 s for 100k rows, and the dashboard adds the equity, heatmap, and radar series on top. These targets are still open.
- The 100 ms filter-change target in the master prompt. Phase 2 measured a simulator run at 5.2 s for 100k rows. Dashboard filter changes were not timed.
- Table scroll at 60 fps with 100k rows. Not measured.
- Accessibility audit with a screen reader. Not run. Keyboard reachability of the drawer, palette, and table editing was checked by unit tests only.

## Tests

- `src/lib/format.test.ts` (6): number and date formatting.
- `src/state/filters.test.ts` (3): filter parameter encoding.
- `src/components/DisciplineRing.test.tsx` (2).
- `src/components/FilterBar.test.tsx` (2): chips and menu.
- `src/screens/Dashboard.test.tsx` (2): headline numbers, low-confidence caveat, and API error state.
- `src/components/TradeDrawer.test.tsx` (2): saving notes sends a PATCH with only the changed fields, and Escape closes the drawer.
- Existing: `tokens.test.ts`, `lib.test.ts`, `sampleCatalog.test.ts`.
- API: 20 new workspace tests cover the trade page, edits, filter options, and saved views.

## Known gaps

- The 1M-row path and the Phase 3 performance targets above are open.
- No browser end-to-end tests.
- Undo covers only the last save in the current session.
- The Trades screen has no bulk edit.
