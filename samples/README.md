# Sample files

These are fixtures for ingestion. They stay on disk. Nothing in this folder is uploaded.

| File | What it is |
| --- | --- |
| `mt5_statement.csv` | MetaTrader 5 account-history export. The header repeats `Price` for the open and the close, which is how MT5 writes it. |
| `tradingview_trades.csv` | TradingView list-of-trades export. Each round trip is an entry row and an exit row, exit fields filled only on the close. |
| `ibkr_executions.csv` | Interactive Brokers executions, not round trips. DateTime uses the `YYYYMMDD;HHMMSS` form. MNQ carries a multiplier of 2. |
| `messy_journal.csv` | A deliberately bad export: preamble, semicolon delimiter, European decimals, a duplicate, a zero quantity, an impossible date, a close stamped before its open, a shifted row, a formula-injection cell, and a note that tries to instruct the model. Notes are data. |
| `synthetic_preview.csv` | 1,000 canonical USD trades from `benchmarks/ledger_samples.py`, seed 42. |
| `synthetic_100k.csv` | 100,000 trades from the same generator, with `synthetic_100k.manifest.json` (SHA-256, row count, net P&L sum, win count). |
| `coach_planted.csv` | 1,358 trades with three hidden leaks: revenge re-entries (quick, double-size trades after a loss), a losing entry hour (14:00 UTC), and eight overtrading days. The Coach tests expect it to find all three and rank them first. |
| `coach_noise.csv` | 819 trades whose results are pure noise. The Coach tests expect no leak and no strength. |

Regenerate the synthetic files from the repo root:

```powershell
uv run --directory api python ../benchmarks/generate_coach_samples.py
uv run --directory api python ../benchmarks/generate_trades.py --rows 1000 --out ../samples/synthetic_preview.csv
uv run --directory api python ../benchmarks/generate_trades.py --rows 100000 --out ../samples/synthetic_100k.csv
```
