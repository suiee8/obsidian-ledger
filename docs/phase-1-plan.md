# Phase 1: ingestion, canonical schema, data-quality report

Status: built and tested. Waiting for review before Phase 2. Reference docs: `docs/ingestion.md` (rules and API) and `benchmarks/README.md` (timings).

## Scope (master prompt, Section 4)

- Read CSV, TSV, TXT, XLSX, XLS, and JSON (list of objects, list of lists, or Google Sheets `values`).
- Sniff encoding, delimiter, header row, decimal style, date format, and timezone.
- Map columns with synonyms and broker adapters (MT5, TradingView, IBKR).
- Normalize to the canonical schema and derive holding time, R, risk, session, weekday, hour, equity, drawdown, loss streaks, and size change.
- Pair fills with FIFO, including partial closes and shorts.
- Data-quality report: code, severity, count, example rows, and suggested fix for each issue.
- Idempotent re-import, raw rows kept as Parquet, rejected rows downloadable with formula cells neutralized.
- Upload limits and zip-bomb guard.

## Decisions made while building

1. Upload uses a raw request body, not multipart, so no `python-multipart` dependency is added.
2. A missing required column does not block. Each affected row is rejected with a specific code. Blocking questions are limited to cases where one answer fixes every row: shape, a missing symbol (`default_symbol`), a missing side column (`side`), and ambiguous slash dates (`date_format`).
3. Money is `DOUBLE`. Fees are stored as negative costs. Commission and swap keep the sign from the file.
4. Equity, drawdown, loss streaks, and size change are computed by the `trade_view` SQL view over the whole table, so merging files keeps them correct.
5. Trade identity is a SHA-256 of account, symbol, side, times, quantity, prices, and net P&L.
6. Bulk writes go through Polars frames registered with DuckDB. DuckDB reads Polars frames through Arrow, so `pyarrow` (Apache-2.0) stays a runtime dependency even though no module imports it directly. Removing it broke every insert, and the test suite caught it.
7. PNG icons are rendered from `web/icons/icon.svg` with `@resvg/resvg-js` (MPL-2.0, build-time only).

## What was found while testing

- MT5 writes the open and close price under the same header. Duplicate headers are renamed to `Price (2)`, and the adapter had to ignore that suffix. A test with the real sample caught it.
- DuckDB `executemany` runs one statement per row. A 10,000-row insert took 119 seconds. The insert now uses one Polars frame per batch, which takes 0.15 seconds for 10,000 rows.
- A DuckDB result left unfinished by `fetchone` blocks the next registration. Single-row reads now consume their results.
- The header detector scored every cell with fuzzy matching. Caching and skipping long cells cut analysis time from 5.4 seconds to under 1 second.
- The `messy_journal.csv` fixture has no exit-time column, so none of its rows can be paired. Its README mentions a "close stamped before its open" case that this file cannot show. The negative-duration rule is covered by an inline test instead.

## Evidence

- API tests: 74 passed (`uv run pytest` in `api/`). Coverage areas: header matching, number and time parsing, file readers, zip and JSON guards, FIFO pairing (hand-calculated), each validation rule, the three broker samples and the synthetic preview against their manifest, the window view (loss streaks, equity, drawdown, size change), idempotent re-import, the HTTP flows, and upload limits.
- Ruff and strict Pyright: clean on `api/src`, `api/tests`, and `benchmarks`.
- Live API run with `pnpm dev:api`: IBKR sample imports 4 trades with cumulative equity; the messy sample returns 9 rejected rows with reasons and a neutralized rejected-rows CSV.
- Benchmark on the committed 100k sample: 10.6 seconds end to end. 1M rows: 129 seconds.
- Icons: `pnpm -C web icons` writes 192, 512, and 180 px PNGs; dimensions verified.

## Known gaps against the targets

- Performance targets from Section 8 are not met: 100k in under 3 seconds and 1M in under 15 seconds, both for ingestion alone. The first page of trades on 1M rows takes 7.6 seconds because `trade_view` recomputes its windows per query. Planned for the Phase 6 performance pass.
- Progress reporting for large files (live step timeline) is not implemented yet; the import is a single request.
- The web import screen (drop zone, mapping table, data-quality card) belongs to Phase 3 and is not built.

## Steps

- [x] Icons rendered to PNG, manifest updated
- [x] `tzdata` added (Windows has no IANA database)
- [x] Canonical fields, header scoring, parsing helpers, with tests
- [x] File readers (text, XLSX, XLS, JSON), zip guard, encoding, with tests
- [x] Adapters (MT5, TradingView, IBKR), analysis with questions and assumptions
- [x] Row validation, FIFO, run loops, quality report, export with tests
- [x] Store: idempotent insert, `trade_view`, templates, import records, with tests
- [x] Service, routes, error shape, settings, `main.py` wiring, HTTP tests
- [x] Benchmark script and timings recorded
- [x] Live API check with the samples
- [x] Documentation: `docs/ingestion.md`, dependency list, ADR-level decisions above
- [ ] Review by you, then Phase 2 (metrics and statistics)
