# Ingestion

This is the reference for how a trade file becomes stored trades. The code lives in `api/src/obsidian_ledger/ingest/`.

## Supported inputs

| Kind | How it is read |
| --- | --- |
| CSV, TSV, TXT | Delimiter (`,`, `;`, tab, or `|`) and header row are detected from the first 80 lines. Lines above the header, such as a preamble, are skipped. |
| XLSX, XLS | First sheet, cached cell values only. Formulas are never evaluated. |
| JSON | A list of objects, a list of lists, or a Google Sheets export with a `values` array. Nested objects (for example Notion properties) are stored as JSON text, so they are not parsed as values. |

Zip files are accepted only as XLSX workbooks. Archives with more than 5,000 members, more than 500 MB uncompressed, or a compression ratio above 100:1 are refused. Uploads are limited to 200 MB by default (`LEDGER_MAX_UPLOAD_MB`).

## Shapes

The analysis chooses one shape per file:

- `round_trip`: one row per closed trade, with entry and exit values on the same row. Used by MT5.
- `legs`: two rows per trade, an entry leg and an exit leg, paired by trade number. Used by TradingView.
- `executions`: raw fills with buy or sell and a quantity. Paired into round trips with FIFO. Used by IBKR.

Generic files are classified by the columns they contain. A file with exit prices, exit times, or P&L is a round trip. A file with side, quantity, and a price or time, and no exit, is executions.

## Column mapping

Each header is normalized (lowercase, punctuation becomes spaces, so `P&L` becomes `p l` and `S/L` becomes `s l`). It is then scored against synonyms for each canonical field:

- Exact match: high confidence.
- All synonym words appear in the header: medium.
- Fuzzy match with a similarity of 0.82 or more: low.

Each canonical field is assigned to at most one column. Precedence: broker adapter, then a saved template for the same headers, then synonyms, then your overrides in the import options. A saved template keys on the normalized header list.

## Assumptions and questions

The preview lists every assumption. Each one can be changed in the import options.

Blocking questions must be answered before commit. Commit returns `422 needs_answers` until they are.

| Question | When it blocks | Answer |
| --- | --- | --- |
| `shape` | The file is neither round trips nor executions | `round_trip`, `legs`, or `executions` |
| `default_symbol` | No symbol column | A symbol for every row |
| `side` | Round trips or executions with no column recognised as buy or sell | Map the column with `mapping` |
| `date_format` | Slash dates such as `01/06/2026` read both ways for every sample | `dayfirst` or `monthfirst` |

A missing exit time, a missing entry time, or a missing quantity does not block. Those rows are rejected with a specific code, so the valid rows still import. The rejected-rows file says what to fix.

Other assumptions are reported without blocking:

- Decimal style (`1.234,56` or `1,234.56`), from the sampled numbers.
- Timezone for timestamps without an offset. Default UTC. Set `timezone` if the broker used local time.
- Contract size per symbol. MT5 uses `XAUUSD` 100, `US500` 10, and 100,000 for six-letter FX pairs. Other symbols default to 1. Set `contract_sizes` to override.
- Currency and account, when there is no column for them.
- Date formats that matched the sample, with counts.

## Normalization rules

Money fields follow one sign rule. Negative means a cost.

- `fees` and taxes are written positive in most exports, so they are stored as negative costs.
- `commission` and `swap` keep the sign from the file. IBKR writes commissions as negative values.
- `net_pnl = gross_pnl + fees + commission + swap`. When only net P&L is given, gross is derived as net minus costs.

Derived values:

- `holding_seconds`: exit time minus entry time.
- `r_multiple`: net P&L divided by planned risk. Planned risk is the given value, or `|entry - stop| x qty x multiplier` when a stop exists. If neither exists, R is empty and the `missing_risk` note is added. A provided R that differs from the computed value raises `r_mismatch`.
- `session`: from the entry hour in UTC. Asia before 07:00, London until 13:00, New York after. A session column in the file takes precedence.
- `weekday` and `hour_utc`: from the entry time.
- `trade_key`: SHA-256 of account, symbol, side, entry, exit, quantity, prices, and net P&L. The same trade in two files is stored once.

Derived across the whole dataset, in the `trade_view` SQL view, so they stay correct when files are merged: `equity`, `peak_equity`, `drawdown`, `loss_streak`, `loss_streak_flag` (three or more consecutive losses), `size_change` (quantity against the previous trade), and `risk_pct` (only with `starting_equity` set). Equity uses base-currency P&L.

## P&L consistency

For round trips with prices, the price-implied P&L is `sign x (exit - entry) x qty x multiplier`. When the reported gross P&L differs from this by more than the rounding allowance, the row keeps the reported value and gets a `pnl_mismatch` warning. The sample `USDJPY` row triggers this, because the quote currency is JPY and the reported 240.00 is not converted.

## Duplicates

- Two identical rows in one file: the second is rejected as `duplicate_in_file`.
- Identical IBKR fills in one file: the second is rejected as `duplicate_fill`.
- A trade already in the store from an earlier import: counted as `already_present` and not inserted again.

## FIFO pairing (executions)

Fills are sorted by time. A fill in the same direction as the open position adds a lot. A fill in the other direction closes the oldest lots first, producing one leg per matched piece. Commissions are split by quantity. Quantity left open at the end of the file is reported as `open_position` and is not counted as a trade.

## Rejection and warning codes

Rejected rows go to the rejected-rows CSV with a code and a message.

| Code | Meaning |
| --- | --- |
| `field_count` | The row has a different number of cells from the header. Not guessed. |
| `bad_time`, `missing_entry_time`, `missing_exit_time` | A timestamp is unreadable or missing. |
| `negative_duration` | Exit is before entry. |
| `missing_symbol`, `bad_side`, `zero_quantity`, `bad_quantity` | Required values are missing or invalid. |
| `bad_number` | A numeric cell is not a number. |
| `no_pnl_or_prices` | No P&L and no entry and exit prices. |
| `duplicate_in_file`, `duplicate_fill` | Repeated row. |
| `unknown_leg`, `duplicate_leg`, `missing_trade_id`, `missing_entry_leg`, `missing_exit_leg` | TradingView leg pairing failed. |

Accepted trades can carry warnings:

| Code | Severity | Meaning |
| --- | --- | --- |
| `pnl_mismatch` | warning | Reported P&L differs from the price-implied value. |
| `net_mismatch` | warning | Net differs from gross plus costs. |
| `r_mismatch` | warning | Provided R differs from net over risk. |
| `formula_like_cell` | warning | A cell starts like a formula. It is stored as text. |
| `missing_risk` | info | No stop or planned risk, so R is empty. |
| `timezone_assumed` | info | Naive timestamps were read in the configured timezone. |
| `open_position` | info | Fills still open at end of file. |
| `fx_missing` | warning | No FX rate for a currency, so base-currency P&L is empty. |
| `outlier` | warning | Net P&L far from the median by a robust score (modified z above 5). Kept and flagged. |

Each issue in the report has a severity, a count, up to ten example source rows, and a suggested fix.

## Security

- Cells that start with `=`, `+`, `-`, `@`, or a tab are stored as text and never evaluated.
- The rejected-rows CSV prefixes such cells with an apostrophe, so a spreadsheet will not run them. Plain numbers such as `-0.70` are left alone.
- Notes are data. Text such as "ignore previous instructions" is stored as-is and does not affect parsing or analysis.

## API

All routes are under `/api` and bind to the loopback address.

| Method and path | Purpose |
| --- | --- |
| `POST /api/imports/preview?filename=...` | Body is the raw file. Returns layout, columns, questions, assumptions, and sample rows, plus a `preview_id`. |
| `POST /api/imports/{preview_id}/commit` | JSON `ImportOptions` (see below). Returns counts and issues, or `422 needs_answers`. A preview can be committed once. |
| `GET /api/imports` | Import history. |
| `GET /api/imports/{import_id}` | One import record, with its assumptions and options. |
| `GET /api/imports/{import_id}/rejected.csv` | Rejected rows with reasons. Formula cells neutralized. |
| `GET /api/trades?limit=&offset=` | Stored trades with derived fields, in exit-time order. |
| `GET /api/templates` | Saved column mappings. |

Errors use one shape: `{"error": {"code", "message", "details"}}`.

`ImportOptions` fields: `mapping`, `shape`, `date_format`, `decimal`, `timezone`, `default_symbol`, `default_account`, `default_currency`, `base_currency` (default USD), `fx_rates`, `contract_sizes`, `starting_equity`, `template_name`. Unknown fields are refused.

## Storage

- `.ledger-data/ledger.duckdb`: trades, settings, import records, templates, and the `trade_view` view.
- `.ledger-data/raw/<import_id>.parquet`: every source row as text, kept for audit.
- `.ledger-data/rejected/<import_id>.csv`: rejected rows.
- `.ledger-data/staging/`: uploads waiting for commit. Removed on commit.

The directory is set by `LEDGER_DATA_DIR` and is git-ignored.

## Known limits (Phase 1)

- Forex pip and lot conversion beyond the MT5 contract sizes is not implemented. Set `contract_sizes` explicitly.
- Option contracts and crypto funding rates are read only through the generic columns (multiplier, swap). No dedicated option model yet.
- Broker PDF statements and Notion API JSON are not supported.
- Multi-account, multi-currency conversion needs `fx_rates` entered by you. No online rates are fetched.
- `messy_journal.csv` has one timestamp column, so none of its rows has an exit time. Its README mentions a "close stamped before its open" row, which cannot be detected in this file. The negative-duration rule is covered by a test with inline data.
- Performance: 100k rows ingest in about 10.6 seconds and 1M rows in about 129 seconds on the measured machine. See `benchmarks/README.md`.
