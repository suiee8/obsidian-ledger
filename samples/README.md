# Sample files

These are fixtures for trying the Import screen and exercising the ingestion tests. Use `pnpm seed` from the repository root to load the 1,000-trade synthetic preview into a local journal. See the [import guide](../docs/ingestion.md) for format and mapping details.

| File | What it is |
| --- | --- |
| `mt5_statement.csv` | MetaTrader 5 account-history export. The header repeats `Price` for the open and the close, which is how MT5 writes it. |
| `tradingview_trades.csv` | TradingView list-of-trades export. Each round trip is an entry row and an exit row, exit fields filled only on the close. |
| `ibkr_executions.csv` | Interactive Brokers executions, not round trips. DateTime uses the `YYYYMMDD;HHMMSS` form. MNQ carries a multiplier of 2. |
| `mexc_futures_order_history_normalized.csv` | MEXC futures order history with long and short sides, leverage, margin, fees, and realized P&L per trade. |
| `binance_futures_eu.csv`, `bybit_closed_pnl.csv` | Binance and Bybit futures exports used by the import API tests. |
| `mt4_open_close_times.csv`, `zerodha_separate_date_time.csv`, `spanish_closed_trades.csv`, `date_only_trades.csv`, `epoch_millisecond_times.csv`, `headerless_trades.csv`, `preamble_totals.xlsx` | Small import edge cases: separate or missing times, epoch timestamps, localized headers, no header row, and a spreadsheet with a preamble and totals row. |
| `messy_journal.csv` | A deliberately bad export: preamble, semicolon delimiter, European decimals, a duplicate, a zero quantity, an impossible date, a shifted row, a formula-injection cell, and a note that tries to instruct the model. Notes are data. |
| `synthetic_preview.csv` | 1,000 canonical USD trades from `benchmarks/ledger_samples.py`, seed 42. |
| `synthetic_100k.csv` | 100,000 trades from the same generator, with `synthetic_100k.manifest.json` (SHA-256, row count, net P&L sum, win count). |
| `coach_planted.csv` | 1,358 trades with three hidden leaks: revenge re-entries (quick, double-size trades after a loss), a losing entry hour (14:00 UTC), and eight overtrading days. The Coach tests expect it to find all three and rank them first. |
| `coach_noise.csv` | 819 trades whose results are pure noise. The Coach tests expect no leak and no strength. |

Regenerate the committed synthetic files and manifests from the repository root:

```powershell
uv run --directory api python ../benchmarks/generate_coach_samples.py
uv run --directory api python ../benchmarks/generate_trades.py --rows 1000 --out ../samples/synthetic_preview.csv
uv run --directory api python ../benchmarks/generate_trades.py --rows 100000 --out ../samples/synthetic_100k.csv
```
