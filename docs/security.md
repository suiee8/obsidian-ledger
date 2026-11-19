# Security notes

## Local data and network boundary

- The supported development commands bind the API and web server to loopback (`127.0.0.1`). The API rejects any request carrying an Origin header that is not in its configured allow-list.
- Uploads are size-limited. XLSX archive validation rejects excessive expansion, excessive member counts, and absolute or parent-traversal member paths. File extension and content signatures are checked before parsing.
- Imported files and the DuckDB/Parquet store remain local. Provider requests are optional, require explicit consent, and use the selected provider endpoint. No telemetry is configured.

## Export and credential controls

- CSV output is parsed after serialization and every cell is checked. Cells beginning with `=`, `+`, `-`, `@`, tab, carriage return, or optional leading spaces before those prefixes receive a leading apostrophe. This covers trade, segment, Coach-report, rejected-row, and CSV-in-ZIP exports. JSON numbers remain numeric.
- Provider keys are stored through `keyring` in the OS keychain. The API returns only a masked hint; the database, captured logs, exports, and every ZIP member are checked by a canary-key test.
- ZIP exports are assembled locally and do not contain the provider key.

## Historical backend audit (2026-11-13)

Each item was re-verified with a test run. "Fixed" means a test failed or the control was missing and was changed in this phase.

| # | Control | Result | Evidence |
| --- | --- | --- | --- |
| 1 | API binds only to 127.0.0.1; Host guard allows `127.0.0.1` and `localhost` | Verified | `test_api_binds_only_to_localhost_by_default`, `test_api_host_setting_rejects_non_loopback_bind_addresses`, `test_wrong_host_is_rejected` |
| 2 | Origin present and not allow-listed is rejected, including simple cross-origin POSTs and preflights | Fixed (middleware and tests tightened) | `test_request_from_unlisted_origin_is_rejected`, `test_cors_options_preflight_from_unlisted_origin_rejected` |
| 3 | Body-size limits on every endpoint (small JSON cap, larger upload cap, streamed bodies without Content-Length cut off); archive traversal and zip-bomb rejection | Fixed (limits applied to every endpoint) / archive checks verified | `test_global_request_body_limit_rejects_non_upload_endpoint`, `test_json_endpoints_use_a_small_body_cap_below_the_upload_limit`, `test_streamed_body_without_content_length_is_cut_off`, existing XLSX archive tests |
| 4 | Security headers on API responses | Verified | `test_all_api_responses_have_security_headers` |
| 4 | CSP and headers on the Vite dev and preview servers; shader runs under the CSP | See the web header results in `docs/test-report.txt` (`shader.spec.ts`) | `web/vite.config.ts` |
| 5 | Provider keys only in the OS keychain; no key in DB, logs, exports or ZIP | Verified | Canary-key test (existing) |
| 5 | Logs never contain notes, trade ids or file names | Verified (new) | `api/tests/security/test_data_handling.py::test_notes_trade_ids_and_filenames_never_reach_the_logs` |
| 6 | Imports treat cells as data: formula neutralisation on export, no instruction-following from notes | Verified | Existing export-escaping tests; notes are stored and returned as plain strings and are never interpreted. The AI mapping help sends value shapes only. |
| 7 | `pip-audit` and `pnpm audit` | See the dependency audit below | |
| 8 | SQL path accepting model-written queries | None exists. Coach tools take typed arguments only. | `test_coach_tools_expose_no_free_form_sql_or_query_argument`, `test_coach_tool_call_rejects_unknown_arguments`. A SELECT-only guard is therefore not needed; if a SQL tool is ever added it must ship with one. |

## Dated dependency audit results

The November 12–13, 2026 runs provide historical evidence. On November 13, `pip-audit` reports no known vulnerabilities, and `pnpm audit` reports 7 findings (1 high, 5 moderate, 1 low), all listed below. There are no critical findings.

Commands:

```powershell
uv run --directory api --with pip-audit pip-audit --local
pnpm audit
```

`pip-audit` reported no known vulnerabilities in the installed API environment. The first JavaScript audit found two critical Tinypool advisories, one high Zod advisory, five moderate advisories, and one low advisory. Tinypool was `1.1.1`; it is now pinned to patched `2.1.2` via `pnpm-workspace.yaml`. A repeat audit removed both critical findings.

### High finding resolved

| Package | Finding | Current version | Patched version | Reason and mitigation |
| --- | --- | --- | --- | --- |
| zod | GHSA-mrhx-c7xc-m3w5: memory exhaustion while validating oversized constrained collections | 3.25.76 | 4.6.6 or later | Resolved 2026-11-17: migrated to Zod 4.6.7. The only code change was the `parseWith` schema type in `web/src/lib/api.ts`; lint, typecheck, 62 unit tests and the production build pass. |

### Remaining lower-severity advisories

Before the 2026-11-17 upgrades the audit reported five moderate advisories and one low advisory:

- Vitest and `@vitest/mocker` advisories are resolved by upgrading to Vitest 4.1.12 (2026-11-17).
- `glob` and `minimatch` advisories arrive transitively through `vite-plugin-pwa`/`workbox-build` and `typescript-eslint`; the published patched ranges require major versions. They are build/development dependencies.
- `deepmerge` 4.3.1 has a low-severity advisory with no patched version listed, through `workbox-build`.

The November 17, 2026 run reported two moderate findings (`glob` and `minimatch`) and one low finding (`deepmerge`) through build dependencies. Consult the [current CI workflow](../.github/workflows/ci.yml) for the checks run on each revision.

## Known limitations

- The current provider catalog has no Ollama adapter; installing Ollama does not connect it to this app.
- Browser printing an exported HTML report to PDF is controlled by the browser and is not an application-generated PDF export.
- Optional cloud AI use sends selected result data to the chosen provider only after consent. Review that provider's own retention and billing terms before enabling it.

## Security settings

These settings are opt-in.

| Setting | Effect |
| --- | --- |
| `LEDGER_PUBLIC=1` | Requires a scrypt `LEDGER_PASSWORD_HASH` and explicit `LEDGER_CORS_ORIGINS`. Enables login and disables the API documentation endpoints. |
| `LEDGER_DEMO_READONLY=1` | Import, edit, delete, wipe, key storage and settings writes refused; read-only banner in the UI |
| `LEDGER_SCANNER=clamd` or `defender` | Scan the quarantined upload before parsing |

In public mode the API sets the journal directory to mode `700` on POSIX systems. On Windows run
`icacls .ledger-data /inheritance:r /grant:r "%USERNAME%:(OI)(CI)F"`.

### Bandit findings (Ruff `S` rules)

- `S608` in `store/db.py` and `store/raw.py`: interpolated parts are constants, table names from fixed
  tuples, column names checked against an allow-list, or WHERE/ORDER fragments built from allow-listed
  fields. Every value is bound as a parameter.
- `S101`: `assert` only narrows types for the checker; no security decision depends on it.
- `S105`: `llm_secret_store` is a mode name (`keyring` or `memory`), not a secret.
- `S112`: a keychain failure must not undo a data wipe.

### CI exceptions policy

CI fails on any high or critical `pnpm audit` finding and on any `pip-audit` finding. An
exception is allowed only when it is recorded in this file with the package, advisory, reason and
review date.

## Test coverage

- `api/tests/security/test_malicious_corpus.py`: zip bombs, zip-slip, macro and external-link workbooks, wrong magic bytes, polyglots, DDE formulas, oversized rows and columns, nested JSON, prototype keys, and seeded fuzzing. Every file is refused or gets a structured error, never a 500. The EICAR case runs only when ClamAV is installed.
- `api/tests/security/test_request_attacks.py`: spoofed Host and Origin, missing client header, rate limiting, path traversal, SQL injection strings in every filter and sort, and error bodies that never show internals.
- `web/e2e/zz-security.spec.ts`: hostile symbols render as text, the web app sends `X-Ledger-Client`, strict page headers, and forged requests are refused.
- Known limits: `style-src` keeps `'unsafe-inline'` because charts and React inline styles need it. The dev server also allows inline scripts for the Vite refresh preamble; The configured Vite preview server uses a stricter script policy. Production hosting must serve the corresponding headers.
