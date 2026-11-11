# Phase 2: metrics and statistics engine

Status: built and tested. Waiting for review before Phase 3 (the Dashboard and Trades screens). Definitions: `docs/metrics-definitions.md`. Timings: `benchmarks/README.md`.

## What it does

Every number comes from deterministic code. The module lives in `api/src/obsidian_ledger/metrics/`:

| Module | Covers |
| --- | --- |
| `data.py` | Filters, base-currency handling, derived columns |
| `core.py` | Win rate, payoff, profit factor, expectancy, fee drag, best and worst day, week, month |
| `risk.py` | Drawdown with depth, duration, and recovery; Sharpe, Sortino, Calmar; SQN; Kelly bound; risk per trade |
| `stats.py` | Bootstrap intervals, Monte Carlo paths and fan chart, Benjamini-Hochberg, Student's t intervals |
| `_scipy.py` | The only place SciPy is called, wrapped with typed functions |
| `behavior.py` | Streaks, after-win and after-loss results, revenge, overtrading, disposition, exit efficiency, plan adherence |
| `discipline.py` | Discipline Score with its formula string |
| `segments.py` | Segment tables by 11 dimensions, with sample size, t-test, and q-value per slice |
| `simulator.py` | What-if rules replayed in time order, with a paired bootstrap and an overfitting warning |
| `engine.py` | Assembles the report, caches by dataset version and parameters |
| `routes.py` | `GET /api/metrics`, `GET /api/segments`, `POST /api/simulate` |

The store gained a dataset version that changes on every write and a frame loader over `trade_view`. Both are needed for correct caching.

## Decisions made while building

1. **Trade filters apply to exit date in UTC.** Trades without a base-currency value are counted in `excluded_no_fx` and left out, not treated as zero.
2. **The simulator never looks ahead.** A trade's result counts toward the daily loss cap only after it closes. A test covers this: a 200 loss that closes at noon must not block a trade entered at 10:30.
3. **Segment intervals use Student's t, bootstrap intervals are used for the overall report.** Running a bootstrap for every segment of a large file would cost too much time.
4. **Monte Carlo paths are capped at 1,000 trades.** Paths of 100,000 trades would need about 4 GB of memory at 5,000 paths. The cap is stated in the output.
5. **A starting equity is optional.** Without it, Sharpe, Sortino, Calmar, drawdown percentages, and risk of ruin are unavailable, and the report says why.
6. **Hypothesis is a development dependency** for the property tests, as the master prompt asks. Its license is MPL-2.0 and it is not shipped.

## Evidence

- **Hand-calculated fixtures** (`tests/metrics/test_hand_fixtures.py`): six trades with P&L 100, -50, 200, -100, 0, 50. Win rate 0.6, profit factor 350/150, median 25, drawdown -100 with one-trade duration, unrecovered. Also SQN, Kelly, Benjamini-Hochberg, and Student's t interval on values 1, 2, 3, each computed by hand.
- **Simulator and behavior fixtures** (`tests/metrics/test_statistics.py`): a daily loss cap that must not see a loss before it closes; a quick re-entry after a loss that must be flagged; a calm entry after a win that must not be; a segment comparison that separates an edge from a leak, and a small segment that must be marked low confidence.
- **Discipline score**: 0.30 x 80 + 0.25 x 50 + 0.20 x 75 + 0.15 x 90 + 0.10 x 50 = 70, checked, and the rescaling when components are missing.
- **Property tests** (`tests/metrics/test_properties.py`, Hypothesis, 150 examples per property): win rate is a proportion; profit factor is non-negative; scaling P&L scales expectancy and keeps win rate; totals do not depend on trade order; drawdown is never positive; Benjamini-Hochberg q-values lie between p and 1 and are monotone; the discipline score stays in 0 to 100.
- **End to end** (`tests/metrics/test_api_metrics.py`): the IBKR sample is imported through the API. Net P&L 120.95 and win rate 0.5 match the hand calculation. A starting equity turns on the daily ratios. A new import changes the dataset version and invalidates the cache. Unknown dimensions and unknown simulator fields return 422.
- Full API suite: 121 tests pass. Ruff and strict Pyright are clean on `api/src`, `api/tests`, and `benchmarks`.

## Known gaps against the master prompt, Section 5

- **Tilt score**: not defined separately from the revenge flag. Left out.
- **Monte Carlo horizon** is capped at 1,000 trades (see decision 4).
- **Performance**: a cold full report on 100k trades takes 5.6 seconds, against the 100 ms target for filter changes. Cached requests take about 1 ms. See `benchmarks/README.md`.
- **Permutation tests** are not used. Welch's t-test is used instead, which the spec allows ("permutation or simple significance flags").
- **Calendar and heatmap data** (weekday by hour, P&L calendar) is available as segment tables but is not shaped for a chart yet. That is Phase 3 work.
- **Coach-facing tools** (`get_metrics`, `compare_segments`, `find_leaks`) are not built. They wrap these functions in Phase 5.

## Steps

- [x] Data layer: filters, base currency, derived columns
- [x] Core metrics, period extremes
- [x] Risk and return: drawdown, daily ratios, SQN, Kelly, risk per trade
- [x] Statistics: bootstrap, Monte Carlo, Benjamini-Hochberg, t intervals
- [x] Behavior, discipline score, segments, simulator
- [x] Report engine with cache, routes, wiring into `main.py`
- [x] Hand-calculated, property, and end-to-end tests
- [x] Timings recorded
- [ ] Review by you, then Phase 3 (Dashboard and Trades screens)
