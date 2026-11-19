# User guide

Obsidian Ledger is a local-first journal for reviewing completed trades. It computes the metrics on this computer; it does not predict markets or recommend trades.

## Install and start

Install Node.js 22 or newer, pnpm 12.18.0, Python 3.12, and [uv](https://docs.astral.sh/uv/). From the repository root in PowerShell:

```powershell
pnpm bootstrap
pnpm dev
```

Open <http://127.0.0.1:5173>. For a demo, run `pnpm seed` before starting the servers. See [ingestion.md](./ingestion.md) for accepted file formats and mapping details.

## Local configuration

| Item | Default or location |
| --- | --- |
| Web app | `http://127.0.0.1:5173` |
| API | `http://127.0.0.1:8000` |
| Journal directory | `api/.ledger-data/` when launched from the repository root |
| API overrides | Set `LEDGER_*` in the process environment or `api/.env`. The API resolves a relative data directory from its working directory. Use an absolute `LEDGER_DATA_DIR` to choose a specific folder. |
| Web API endpoint | Set `VITE_API_URL` in the frontend process environment or `web/.env`, then restart Vite or rebuild. |

Use the values in [`.env.example`](../.env.example) as a reference. The standard `pnpm dev` launcher uses ports 5173 and 8000. `pnpm dev:web` and `pnpm dev:api` start the services separately on those defaults.

If the badge reads **offline · stale**, check the API at <http://127.0.0.1:8000/health/ready> and review its terminal output. If the API reports a database lock, close the other Ledger API process before restarting.

## Navigate the app

Use the black navigation rail to switch screens and the top bar to filter the journal or open **Coach**. The arrow cursor leaves a short trail for fine pointers and uses the native cursor on text fields, selects, and resize handles. The app respects reduced motion for the cursor, wordmark, and footer effects. The social links are at the bottom of the page. See the [accessibility notes](accessibility.md).

## Import a journal

Choose **Import** and select a CSV, TSV, text, XLSX, XLS, or JSON export. The app infers roles from the file's contents; you do not need to choose a broker. Review the **What we found** card, capability checklist, confidence, examples, warnings, and rejected rows before committing. You can override a role, and ambiguous or headerless files require an explicit mapping. Blocking questions must be answered first. XLS/XLSX formulas are not evaluated; only cached cell values are read.

When trades are already in the journal, the Import screen shows an **A trade file is already uploaded** card with the symbols and accounts on file and an **Open dashboard** button. Importing another file adds only trades that are not already present.

Uploads are limited to 200 MB by default. Archives are accepted only as XLSX files and are rejected if they contain unsafe paths, too many files, excessive expanded size, or an unusually high compression ratio. Imported files and the local database remain on this computer.

Missing prices, fees, stops, and P&L stay unavailable; the app never substitutes zero. If a file has no P&L, activity counts and symbol/time summaries are still shown, while P&L-dependent metrics and the Coach verdict are marked unavailable/cannot be assessed. Notional is not treated as P&L.

## Read the results and Coach

- **Filters** at the top of the screen narrow every view by account, symbol, and side. Use **Clear** to remove them. There are no date-range, setup, or tag filters in the interface.
- **Dashboard** summarizes the current journal: key figures, equity curve, P&L calendar, edge radar by setup, and a weekday-and-hour heatmap.
- **Trades** shows imported trades and supports editing journal fields such as notes and tags.
- **Analytics** has the segment explorer (symbol, side, session, weekday, entry hour, holding time, position size, account), the Trade Constellation, MAE and MFE, streaks, fee drag, and a Monte Carlo fan. Before a file is imported, or when filters match nothing, it shows an empty state with an **Import a file** or **Clear filters** button.
- **Behavior** and **Simulator** provide deterministic summaries and what-if calculations. Small samples and multiple comparisons are marked to avoid overstating evidence.
- The **Coach** explains its deterministic report. It can call seven read-only tools: `get_metrics`, `compare_segments`, `find_leaks`, `find_strengths`, `get_trade`, `list_trades`, and `simulate_rule`. Numbers are computed by the API; AI-generated paragraphs with unsupported figures are withheld.

The Coach works with AI turned off. When using an AI provider, the current application offers optional cloud providers; each requires your own key and explicit consent. AI output is explanatory and does not change the underlying metrics.

The optional cloud catalog includes Z.ai, Moonshot, and OpenRouter. **Settings → AI provider** lists the models available in the app. Ollama is a planned adapter and currently runs independently of Ledger. See the [model-runtime decision](adr/0009-ollama-local-model-no-new-paid-providers.md).

## Privacy choices

In **Settings → Privacy**, the default **Aggregates only** sends totals, rates, ranges, and finding descriptions to a selected AI provider, never individual trades. To include individual trade rows or notes, turn off the aggregates-only setting and enable the desired fields. Only do this if you understand the provider's data handling and have consented to sending results.

Provider keys are stored in the operating-system keychain (Windows Credential Manager on Windows). The app displays only a masked hint. The full key is not stored in the journal database or included in exports. Leaving the provider set to **None (AI off)** prevents AI requests.

No telemetry is configured. The app does not upload trade files. A user-enabled cloud AI request is the exception: selected result data is sent to the configured provider only after consent.

## Exports

- **Settings → Export all data** downloads a ZIP assembled locally. It contains trades as CSV, imports, saved views, templates, Coach reports, settings, and original uploaded files.
- The Coach report can be downloaded as Markdown or HTML; the API also provides CSV.
- To make a PDF copy of an exported HTML report, open it in a browser and use **Print → Save as PDF**. There is no Reports screen or application-generated PDF export.
- CSV values that begin with spreadsheet formula characters are prefixed so spreadsheet software treats them as text. JSON numeric values remain numbers.

Keep exports in a secure location: they contain financial and behavioral journal data. Delete local data only after exporting anything you want to retain; wiping data is permanent.

## Important notice

Obsidian Ledger is an organizational and educational tool. It is not financial, investment, tax, or legal advice, and its historical calculations do not predict future results. Verify imported data and consult a qualified professional for decisions.
