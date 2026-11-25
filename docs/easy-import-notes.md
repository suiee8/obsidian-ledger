# Easy import

## Baseline inventory

| What the existing Import screen asks or shows | Renderer | API field |
| --- | --- | --- |
| Date order | `Questions` | `preview.questions/date_format` → `commit.date_format` |
| Default symbol | `Questions` | `preview.questions/default_symbol` → `commit.default_symbol` |
| File shape and buy/sell direction | `Questions` | `preview.questions/shape` and `side` → `commit.shape` or `commit.mapping` |
| Netting for a buy/sell position history | `Questions` | `preview.questions/side_mode` → `commit.side_mode` |
| Headerless mapping and role conflicts | `Questions` and the mapping table in `PreviewPanel` | `preview.questions`, `columns`, `profiles` → `commit.mapping` |
| Exact symbol alias corrections | `PreviewPanel` | `preview.warnings`, `profiles.samples` → `commit.symbol_aliases` |
| Timezone and other defaults | `PreviewPanel` | `preview.timezone`, `preview.assumptions` and optional `commit.timezone`. The screen has no timezone input. |
| Starting equity | `StartingEquity` in Settings | `settings.starting_equity`. The commit API also accepts it, but the Import screen offers no equity input. |
| Duplicates, checklist, warnings, sample rows | `PreviewPanel` and `CommitPanel` | `preview.duplicate_rows`, `capabilities`, `warnings`, `sample_rows`; `commit.already_present`, `duplicates_in_file`, `issues` |
| Manual import confirmation and report navigation | `PreviewPanel` and `CommitPanel` | Existing preview ID, commit response, client navigation |

The work starts on `feat/easy-import` from `891fabe`. No dev launcher was running at the baseline.

## What changed

- A normal import reads and saves the file, then opens the Dashboard. The result line can be dismissed. Details shows the detected columns, capabilities, assumptions, and warnings.
- The import uses a confidence floor of 0.80 for the required column groups, with ties within 0.10 requiring review. Conflicting mappings still require review. At 95% valid rows or higher, it can finish automatically. From 50% to below 95%, it asks before saving the valid rows. Below 50%, the user gets an explanation and a template link.
- Time offsets in a file take precedence over the default timezone. The default is UTC until changed in Settings. Plain buys and sells are matched per instrument. If the file has no symbol, the importer tries its filename and falls back to `UNKNOWN`. Importing does not set starting equity.
- Re-import retains the selected source in the current browser session. It goes through the same duplicate checks as any new import. Previously saved trades are skipped, and identical rows within a single file are kept and explained in Details.
- Questions remain for unresolved columns, ambiguous date order, uncertain row shape, and partially readable files that need consent. The usual review screen, the assumption and warning checklist, and the manual Dashboard step are gone from the normal path.
- The template uses the 20 headers already in `samples/synthetic_preview.csv`. The [column guide](import-format.md) also documents `stop_loss` and `tags` when supplied by another export.

## Updated browser expectations

- `smoke.spec.ts` checks automatic Dashboard navigation and the one-line receipt. MEXC capability and warning assertions moved to Details. The Dashboard and Analytics assertions still cover unavailable profit metrics.
- `zz-coach.spec.ts` waits for the receipt before manually opening Coach. An easy import leaves a closed Coach closed.
- `analytics.spec.ts` uses the Settings panel's new name, “Improve your analysis”.

## Verification

- Baseline `pnpm check` passed 64 web tests and 411 API tests, with one API skip.
- Final `pnpm check` passed 64 web tests and 422 API tests, with the same API skip. Lint, type checks, and the production build passed.
- The focused Playwright run passed 12 import, Dashboard, and navigation tests against a production build. It covered the 476-trade MEXC fixture, the keyboard-only file chooser, re-import, accessibility at widths of 1440 and 390 px, and production CSP. The full e2e suite was not run.
- Five alternating local API runs per version measured preview and commit of the first 10,000 trades in `samples/synthetic_100k.csv`. Each run used a fresh database and inserted all 10,000 trades. The baseline at `891fabe` had a 2.879 s median (2.661–3.054 s). Easy Import had a 2.868 s median (2.678–2.977 s). The timings overlap and show no slowdown in this benchmark.
