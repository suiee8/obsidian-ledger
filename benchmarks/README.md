# Benchmarks

Synthetic journals live here so performance numbers and statistical fixtures share one generator. The model is documented in `ledger_samples.py`.

## Population edge, before the flat $1 fee

| Setup | Weight | Win rate | Win R | Loss R | Expectancy |
| --- | --- | --- | --- | --- | --- |
| breakout | 0.45 | 0.48 | 1.8 | 1.0 | +0.344 R |
| mean_revert | 0.40 | 0.55 | 0.9 | 1.0 | +0.045 R |
| fomo | 0.15 | 0.35 | 1.1 | 1.0 | -0.265 R |

Stored `r_multiple` is net of the fee: `net_pnl / planned_risk`. Planned risk is 0.5% of notional. Every row is USD. Seed 42 is the default.

Revenge is offered on half of the trades that follow a losing trade, except FOMO setups, which are always tagged `fomo`. Calm trades follow the plan about 95% of the time. FOMO and revenge trades follow it about 30% and 25% of the time.

## Commands

From the repo root, with the API environment installed:

```bash
uv run --directory api python ../benchmarks/generate_trades.py --rows 1000 --out ../samples/synthetic_preview.csv
uv run --directory api python ../benchmarks/generate_trades.py --rows 100000 --out ../samples/synthetic_100k.csv
uv run --directory api python ../benchmarks/generate_trades.py --rows 1000000 --out benchmarks/out/synthetic_1m.csv
```

The 100k file is committed under `samples/` with its manifest, which records the SHA-256, the net P&L sum, and the win count. A 1M file can be generated into `benchmarks/out/`, which git ignores. The timings below are historical Phase 1/2 context; the Phase 6 performance run is limited to 10k trades.

## Phase 6 performance run

`pnpm bench` measures only 1k, 5k, and 10k trades, with ten runs per size. `benchmarks/RESULTS.md` records medians and min–max ranges, machine details, payload and JavaScript bundle sizes, and the optional 10k browser measurement. Historical Phase 1 and Phase 2 timings above are retained for context; they are not rerun by the Phase 6 command.

## Ingestion timings (Phase 1)

Measured with `benchmarks/ingest_benchmark.py` on 2026-11-11. Machine: Intel Core i5-1235U (laptop class), 7.7 GB RAM, Windows, Python 3.12, DuckDB 2.0.0, Polars 2.1.0. Times are wall-clock seconds for one run in a fresh store.

| Stage | 10,000 rows | 100,000 rows | 1,000,000 rows |
| --- | ---: | ---: | ---: |
| Analysis (header and sample) | 0.74 | 0.84 | 0.89 |
| Row processing (validate, derive) | 0.65 | 6.25 | 85.18 |
| Raw Parquet write | 0.32 | 1.01 | 11.78 |
| Insert into DuckDB | 0.15 | 1.78 | 24.03 |
| First page of `trade_view` | 0.11 | 0.69 | 7.60 |
| Total | 1.96 | 10.57 | 129.47 |

Targets from the product specification, and where the build stands:

- 100k rows to a rendered dashboard in under 3 seconds. Ingestion alone takes 10.6 seconds, so this is not met. The dashboard render is not built yet.
- 1M rows in under 15 seconds with progress shown. Not met: 129 seconds, with no progress reporting yet.

Known causes, for the Phase 6 performance pass: row processing runs several Python checks per cell, and `trade_view` recomputes its window functions over the whole table on each query. Caching the view's results or moving the per-row checks into vectorized Polars expressions would address the two largest costs.

Reproduce the 100k run from the repo root:

```powershell
uv run --directory api python ../benchmarks/ingest_benchmark.py ../samples/synthetic_100k.csv
```

## Analysis timings (Phase 2)

Measured with `benchmarks/metrics_benchmark.py` on 2026-11-11, on the same machine as the ingestion timings above. The journal is the committed 100k synthetic sample, loaded into a fresh store. Times are wall-clock seconds.

| Request | Time |
| --- | ---: |
| Full report, first request (cold) | 5.62 |
| Full report, repeat request (cache hit) | 0.001 |
| Segment table by symbol | 0.16 |
| Simulator with one rule, 1,000 resamples | 5.19 |

Targets from the product specification: filters and segment changes under 100 ms. The cache meets this for repeated requests. A changed filter is a cold request, so a new filter selection takes about 5 seconds for 100k trades. The cost is the bootstrap (1,000 resamples of 100,000 trades) and the Monte Carlo paths. Reducing either, or running them in a background job, is the next performance step. It is planned with the Phase 6 performance pass.
