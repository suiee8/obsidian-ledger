# User guide

Obsidian Ledger is a local-first journal for reviewing completed trades. It computes the metrics on this computer; it does not predict markets or recommend trades.

## Install and start

Install Node.js 22 or newer, pnpm 12.18.0, Python 3.12, and [uv](https://docs.astral.sh/uv/). From the repository root in PowerShell:

```powershell
pnpm bootstrap
pnpm dev
```

Open <http://127.0.0.1:5173>. The API runs on <http://127.0.0.1:8000> and binds to loopback. `pnpm seed` optionally imports the 1,000-trade sample journal. See [ingestion.md](./ingestion.md) for accepted file formats and mapping details.

## Import a journal

Choose **Import** and select a CSV, TSV, text, XLSX, XLS, or JSON export. The app infers roles from the file's contents; you do not need to choose a broker. Review the **What we found** card, capability checklist, confidence, examples, warnings, and rejected rows before committing. You can override a role, and ambiguous or headerless files require an explicit mapping. Blocking questions must be answered first. XLS/XLSX formulas are not evaluated; only cached cell values are read.

Uploads are limited to 200 MB by default. Archives are accepted only as XLSX files and are rejected if they contain unsafe paths, too many files, excessive expanded size, or an unusually high compression ratio. Imported files and the local database remain on this computer.

Missing prices, fees, stops, and P&L stay unavailable; the app never substitutes zero. If a file has no P&L, activity counts and symbol/time summaries are still shown, while P&L-dependent metrics and the Coach verdict are marked unavailable/cannot be assessed. Notional is not treated as P&L.

## Read the results and Coach

- **Overview** summarizes the current journal and links to the detailed analysis.
- **Trades** shows imported trades and supports editing journal fields such as notes and tags.
- **Analytics**, **Behavior**, and **Simulator** provide deterministic summaries, comparisons, and what-if calculations. Small samples and multiple comparisons are marked to avoid overstating evidence.
- The **Coach** explains its deterministic report. Numbers are computed by the API; AI-generated paragraphs with unsupported figures are withheld.

The Coach works with AI turned off. When using an AI provider, the current application offers optional cloud providers; each requires your own key and explicit consent. AI output is explanatory and does not change the underlying metrics.

### Optional Ollama setup

Ollama is the only local runtime selected for a future local-model adapter. To install it and download the documented model:

```powershell
ollama pull qwen2.5:7b
ollama run qwen2.5:7b
```

**Current-build limitation:** the application does not yet include an Ollama provider adapter. These commands install and run Ollama independently; they do not connect it to Obsidian Ledger or make it appear in the provider selector. Do not enter an Ollama URL as a cloud-provider credential.

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
