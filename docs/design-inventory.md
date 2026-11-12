# Phase 6B design inventory

This is the pre-redesign contract and visual baseline for Part A. Keep the listed route IDs, test
selectors, accessible names, chart behaviors, and Playwright setup stable while changing presentation.

## Web source structure

```text
web/src/
  App.tsx
  cssTokens.test.ts
  index.css
  main.tsx
  routes.ts
  sampleCatalog.test.ts
  sampleCatalog.ts
  tokens.test.ts
  tokens.ts
  vite-env.d.ts
  components/
    CommandPalette.tsx
    DisciplineBreakdown.tsx
    DisciplineRing.test.tsx
    DisciplineRing.tsx
    FilterBar.test.tsx
    FilterBar.tsx
    FilterSheet.tsx
    Findings.tsx
    HealthBadge.tsx
    Kpi.tsx
    Panel.tsx
    ScreenStates.tsx
    Shell.tsx
    TradeDrawer.test.tsx
    TradeDrawer.tsx
    charts/
      Bars.tsx
      BrushScatter.tsx
      DailyCalendar.tsx
      EdgeRadar.tsx
      EquityAurora.tsx
      LineBands.tsx
      RHistogram.tsx
      WeekdayHour.tsx
    coach/
      AiSummary.tsx
      AskCoach.test.tsx
      AskCoach.tsx
      CoachDrawer.test.tsx
      CoachDrawer.tsx
      FindingCard.tsx
      FindingChart.tsx
      Timeline.tsx
    icons.tsx
  lib/
    api.ts
    cn.ts
    coach.ts
    dashboard.ts
    echarts.ts
    format.test.ts
    format.ts
    health.ts
    lib.test.ts
    llm.ts
    phase4.ts
    queries.ts
    schemas.ts
    theme.ts
    useChart.ts
    useChartPalette.ts
    useCountUp.ts
    useDebouncedValue.ts
    useHealth.ts
  screens/
    Analytics.tsx
    Behavior.tsx
    Dashboard.test.tsx
    Dashboard.tsx
    Import.tsx
    Samples.tsx
    Settings.tsx
    Simulator.tsx
    Trades.tsx
  state/
    filters.test.ts
    filters.ts
    ui.ts
```

## CSS custom properties

There are 73 custom-property declarations in `web/src/index.css`. The table captures each declaration,
including aliases and later overrides.

| Declaration group | Name | Current value |
|---|---|---|
| Root utility (lines 4–20) | `--surface-table-head` | `#0F1217` |
| | `--skeleton-highlight` | `#1E2A45` |
| | `--footer-scrim` | `rgba(11,13,17,0.72)` |
| | `--glass-edge-highlight` | `rgba(232,236,244,0.06)` |
| | `--border-status-warn` | `rgba(245,184,75,0.4)` |
| | `--glass-sheen-bottom` | `rgba(255,255,255,0.01)` |
| | `--glass-sheen-top` | `rgba(255,255,255,0.035)` |
| | `--fill-questions` | `rgba(52,84,192,0.08)` |
| | `--fill-badge` | `rgba(52,84,192,0.15)` |
| | `--glow-status-ok` | `rgba(61,220,151,0.35)` |
| | `--border-status-ok` | `rgba(61,220,151,0.4)` |
| | `--grid-line` | `rgba(65,105,225,0.05)` |
| | `--wash-royal-top` | `rgba(65,105,225,0.16)` |
| | `--wash-royal-dropzone` | `rgba(65,105,225,0.18)` |
| | `--glow-royal` | `rgba(65,105,225,0.35)` |
| | `--glow-royal-strong` | `rgba(65,105,225,0.45)` |
| | `--glow-royal-ring` | `rgba(65,105,225,0.5)` |
| Palette (lines 21–38) | `--palette-background` | `#0B0D11` |
| | `--palette-border` | `#262C38` |
| | `--palette-borderSubtle` | `#1D222C` |
| | `--palette-dim` | `#6B7488` |
| | `--palette-ice` | `#C9D6FF` |
| | `--palette-ink` | `#E8ECF4` |
| | `--palette-loss` | `#FF5C6C` |
| | `--palette-muted` | `#9AA4B8` |
| | `--palette-profit` | `#3DDC97` |
| | `--palette-royal300` | `#94ADF6` |
| | `--palette-royal400` | `#6384EE` |
| | `--palette-royal500` | `#4169E1` |
| | `--palette-royal600` | `#3454C0` |
| | `--palette-royal700` | `#27409A` |
| | `--palette-surface1` | `#11141A` |
| | `--palette-surface2` | `#171B23` |
| | `--palette-surface3` | `#1E232D` |
| | `--palette-warning` | `#F5B84B` |
| Status aliases (lines 41–43) | `--status-ok` | `var(--palette-profit)` |
| | `--status-warn` | `var(--palette-warning)` |
| | `--status-error` | `var(--palette-loss)` |
| Tailwind theme aliases (lines 49–70) | `--color-background` | `var(--palette-background)` |
| | `--color-surface-1` | `var(--palette-surface1)` |
| | `--color-surface-2` | `var(--palette-surface2)` |
| | `--color-surface-3` | `var(--palette-surface3)` |
| | `--color-line` | `var(--palette-border)` |
| | `--color-line-subtle` | `var(--palette-borderSubtle)` |
| | `--color-ink` | `var(--palette-ink)` |
| | `--color-muted` | `var(--palette-muted)` |
| | `--color-dim` | `var(--palette-dim)` |
| | `--color-royal-300` | `var(--palette-royal300)` |
| | `--color-royal-400` | `var(--palette-royal400)` |
| | `--color-royal-500` | `var(--palette-royal500)` |
| | `--color-royal-600` | `var(--palette-royal600)` |
| | `--color-royal-700` | `var(--palette-royal700)` |
| | `--color-ice` | `var(--palette-ice)` |
| | `--color-profit` | `var(--palette-profit)` |
| | `--color-loss` | `var(--palette-loss)` |
| | `--color-warning` | `var(--palette-warning)` |
| | `--font-display` | `"Sora", ui-sans-serif, sans-serif` |
| | `--font-sans` | `"Manrope", ui-sans-serif, sans-serif` |
| | `--font-mono` | `"JetBrains Mono", ui-monospace, monospace` |
| | `--radius-card` | `16px` |
| P&L aliases (root, lines 78–80) | `--pnl-profit` | `#3ddc97` |
| | `--pnl-loss` | `#ff5c6c` |
| | `--pnl-warning` | `#f5b84b` |
| Color-blind override (lines 83–85) | `--pnl-profit` | `#4169e1` |
| | `--pnl-loss` | `#f5b84b` |
| Legacy chart aliases (lines 680–687) | `--royal-500` | `#4169e1` |
| | `--royal-300` | `#94adf6` |
| | `--ice` | `#c9d6ff` |
| | `--ink` | `#e8ecf4` |
| | `--muted` | `#9aa4b8` |
| | `--dim` | `#6b7488` |
| | `--line` | `#262c38` |
| | `--surface-1` | `#11141a` |

The requested charcoal, royal-blue, ice, and text values already match the named palette tokens
(case-insensitively). Existing warning/status amber appears in the warning tokens and the color-blind
P&L override; it is a recorded deviation from the requested no-extra-hues palette. The existing
profit/loss green and red are intended for P&L use. Several legacy chart aliases repeat palette values.
`cssTokens.test.ts` protects the existing token-literal convention and P&L token usage.

## Chart theme

- `lib/theme.ts` defines `ChartPalette` fields `profit`, `loss`, `royal`, `royalSoft`, `ice`, `ink`,
  `muted`, `dim`, `line`, and `surface`.
- `readChartPalette()` reads the CSS variables `--pnl-profit`, `--pnl-loss`, `--royal-500`,
  `--royal-300`, `--ice`, `--ink`, `--muted`, `--dim`, `--line`, and `--surface-1`, with matching
  fallback values. `FALLBACK_COLOR_BLIND` maps profit to royal blue and loss to amber.
- `useChartPalette()` tracks the existing UI `colorBlind` state. Preserve its behavior and the token
  names.
- ECharts uses the canvas renderer. Components create their options locally and use the shared
  palette: royal equity curve and area, P&L drawdown/result colors, token-colored axes and grid, and
  tooltips. Chart animation is disabled when reduced motion is requested.
- Charts are mounted through `useChart()` and lazy-loaded with their screens; there is no separate
  global ECharts theme.

## Playwright baseline

`web/playwright.config.ts` runs the `e2e` directory serially with one worker (`fullyParallel: false`),
60-second test timeouts, 15-second assertion timeouts, and the list reporter. It uses installed
Microsoft Edge (`channel: "msedge"`), a 1440 × 1000 default viewport, and
`http://127.0.0.1:5173`. Playwright starts an isolated API using a fresh temporary data directory,
the local mock model server, and the Vite preview server. Browser screenshots are generated by
`e2e/screens.spec.ts` and `e2e/zz-coach-screens.spec.ts`.

The pre-change baseline was 332 API tests, 43 web unit tests, and 78 browser tests. `docs/screens/`
contained 33 generated baseline screenshots:

- `import-{1440,1024,390}.png`
- `dashboard-{1440,1024,390}.png`
- `dashboard-empty-{1440,1024,390}.png`
- `dashboard-loading-{1440,1024,390}.png`
- `dashboard-error-{1440,1024,390}.png`
- `trades-{1440,1024,390}.png`
- `coach-{empty,error,few-trades,ready,running}-{1440,1024,390}.png`

SHA-256 hashes for these baseline images are retained in the session comparison record so changed
screenshots can be reported exactly after the redesign. The screenshots are generated artifacts; the
compatibility assertions live in the E2E tests.

## Routes and stable selectors

The values below are internal route IDs from `routes.ts`, not browser URL paths. Keep IDs and labels:

| Route ID | Current label |
|---|---|
| `dashboard` | Dashboard |
| `analytics` | Analytics |
| `behavior` | Behavior |
| `simulator` | Simulator |
| `trades` | Trades |
| `import` | Import |
| `samples` | Sample files |
| `settings` | Settings |

The only `data-testid` found in `web/src` and `web/e2e` is test-only:

- `finding-chart` — mock element in `components/coach/CoachDrawer.test.tsx`.

Keep all current `aria-label` names and expression patterns (static labels are quoted verbatim;
dynamic labels are shown as JSX expressions):

- `App.tsx`: `"Loading screen"`.
- `screens/Analytics.tsx`: `` `${dimensionLabel} segments table` ``, `"Longest runs table"`.
- `screens/Behavior.tsx`: `"Post-loss performance table"`.
- `screens/Dashboard.tsx`: `"Loading dashboard"`, `"Headline numbers"`, `"Daily-return ratios"`,
  `"Data caveats"`.
- `screens/Import.tsx`: `"Questions to answer before importing"`,
  `"Drop a trade file here, or press Enter to choose one"`, `"Trade file"`.
- `screens/Trades.tsx`: `` `${field} for ${row.symbol}` ``, `"Saved views"`,
  `"Apply a saved view"`, `"New view name"`, `"Trades"`.
- `components/DisciplineBreakdown.tsx`: `"How the Discipline Score is calculated"`,
  `discipline.score === null ? "Score not available" : \`Score ${fmtNumber(discipline.score, 0)} of 100\``,
  `` `${LABELS[key]}: ${fmtNumber(value, 0)} out of 100` ``.
- `components/FilterBar.tsx`: `"Filters"`, `"From date"`, `"To date"`,
  `` `Add ${LIST_LABELS[key]} filter` ``, `` `Remove ${LIST_LABELS[key]} filter ${item}` ``,
  `"Tag or emotion filter"`.
- `components/FilterSheet.tsx`: `"Filters"`.
- `components/HealthBadge.tsx`: `{label}`.
- `components/Kpi.tsx`: `` `${label}: ${value === null ? "not available" : format(value)}` ``.
- `components/Panel.tsx`: `"Loading chart"`, `{title}`.
- `components/ScreenStates.tsx`: `{label}`.
- `components/Shell.tsx`: `"Primary"`, `{ROUTE_LABELS[item.id]}`.
- `components/TradeDrawer.tsx`: `"Trade detail"`, `` `Trade ${trade.trade_id}` ``,
  `"Close trade detail"`, `` `Held for ${fmtDuration(trade.holding_seconds)}` ``.
- `components/charts/Bars.tsx`: `{label}` on each of its three chart wrappers.
- `components/charts/BrushScatter.tsx`: `{label}`.
- `components/charts/DailyCalendar.tsx`: `` `P&L calendar across ${days.length} trading days, scrolls sideways` ``,
  `{label}`.
- `components/charts/EdgeRadar.tsx`: `` `Edge radar for ${setups.length} setups across six axes` ``.
- `components/charts/EquityAurora.tsx`:
  `` `Equity curve over ${equity.source_points} trades${equity.downsampled ? ", downsampled for display" : ""}` ``.
- `components/charts/LineBands.tsx`: `{label}` on each of its two chart wrappers.
- `components/charts/RHistogram.tsx`:
  `` `R distribution of ${histogram.n} trades. Median ${fmtNumber(histogram.median)} R.` ``.
- `components/charts/WeekdayHour.tsx`: `"Average P&L by weekday and UTC entry hour"`, `{text}`.
- `components/coach/AiSummary.tsx`: `"AI summary"`.
- `components/coach/AskCoach.tsx`: `"Trades this paragraph is about"`,
  `` `Show trade ${chip.trade_id} in the Trades table, ${chip.pnl}` ``, `"Ask the Coach"`,
  `"Questions and answers"`, `"Example questions"`.
- `components/coach/CoachDrawer.tsx`: `{id}` on coach sections, `"Verdict"`,
  `"Resize the Coach panel"`, `"Coach"`, `"Coach views"`.
- `components/coach/FindingCard.tsx`: `{headingId}` on finding cards,
  `` `Evidence trades for ${finding.title}` ``,
  `` `Show trade ${trade.trade_id} in the Trades table, ${trade.pnl.display}` ``,
  `` `Apply as filter: ${finding.title}` ``.
- `components/coach/FindingChart.tsx`: the average-per-trade accessible name, composed from the
  finding's slice and other-trades values and optional 95% interval.
- `components/coach/Timeline.tsx`: `"Report steps"`.
- `components/DisciplineRing.tsx`: `{label}`.
- `screens/Simulator.tsx`: `"Overfitting warning"`, `"Before and after table"`,
  `"Why trades were skipped"`.
- `screens/Settings.tsx`: `` `Rename ${name}` ``, `` `Confirm delete ${name}` ``,
  `` `Delete ${name}` ``.

Also preserve the `aria-labelledby` IDs: `empty-title`, `preview-title`, `result-title`,
`samples-heading`, `findings-title`, `empty-screen-title`, the existing generated coach-section IDs,
`coach-tab-ask`, and `coach-tab-report`. The E2E tests also select the `"Loading dashboard"` and
`"Filters"` accessible names.
