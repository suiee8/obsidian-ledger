# Security notes

## Local data and network boundary

- The supported development commands bind the API and web server to loopback (`127.0.0.1`). The API rejects any request carrying an Origin header that is not in its configured allow-list.
- Uploads are size-limited. XLSX archive validation rejects excessive expansion, excessive member counts, and absolute or parent-traversal member paths. File extension and content signatures are checked before parsing.
- Imported files and the DuckDB/Parquet store remain local. Provider requests are optional, require explicit consent, and use the selected provider endpoint. No telemetry is configured.

## Export and credential controls

- CSV output is parsed after serialization and every cell is checked. Cells beginning with `=`, `+`, `-`, `@`, tab, carriage return, or optional leading spaces before those prefixes receive a leading apostrophe. This covers trade, segment, Coach-report, rejected-row, and CSV-in-ZIP exports. JSON numbers remain numeric.
- Provider keys are stored through `keyring` in the OS keychain. The API returns only a masked hint; the database, captured logs, exports, and every ZIP member are checked by a canary-key test.
- ZIP exports are assembled locally and do not contain the provider key.

## Phase 6B backend audit — 2026-11-13

Each item was re-verified with a test run. "Fixed" means a test failed or the control was missing and was changed in this phase.

| # | Control | Result | Evidence |
| --- | --- | --- | --- |
| 1 | API binds only to 127.0.0.1; TrustedHost allows `127.0.0.1` and `localhost` | Verified | `test_api_binds_only_to_localhost_by_default`, `test_api_host_setting_rejects_non_loopback_bind_addresses`, `test_wrong_host_is_rejected` |
| 2 | Origin present and not allow-listed is rejected, including simple cross-origin POSTs and preflights | Fixed (middleware and tests tightened) | `test_request_from_unlisted_origin_is_rejected`, `test_cors_options_preflight_from_unlisted_origin_rejected` |
| 3 | Body-size limits on every endpoint (small JSON cap, larger upload cap, streamed bodies without Content-Length cut off); archive traversal and zip-bomb rejection | Fixed (limits applied to every endpoint) / archive checks verified | `test_global_request_body_limit_rejects_non_upload_endpoint`, `test_json_endpoints_use_a_small_body_cap_below_the_upload_limit`, `test_streamed_body_without_content_length_is_cut_off`, existing XLSX archive tests |
| 4 | Security headers on API responses | Verified | `test_all_api_responses_have_security_headers` |
| 4 | CSP and headers on the Vite dev and preview servers; shader runs under the CSP | See the web header results in `docs/test-report.txt` (`shader.spec.ts`) | `web/vite.config.ts` |
| 5 | Provider keys only in the OS keychain; no key in DB, logs, exports or ZIP | Verified | Canary-key test (existing) |
| 5 | Logs never contain notes, trade ids or file names | Verified (new) | `api/tests/security/test_data_handling.py::test_notes_trade_ids_and_filenames_never_reach_the_logs` |
| 6 | Imports treat cells as data: formula neutralisation on export, no instruction-following from notes | Verified | Existing export-escaping tests; notes are stored and returned as plain strings and are never interpreted. The AI mapping help sends value shapes only. |
| 7 | `pip-audit` and `pnpm audit` | See the dependency audit below | |
| 8 | SQL path accepting model-written queries | None exists. Coach tools take typed arguments only. | `test_coach_tools_expose_no_free_form_sql_or_query_argument`, `test_coach_tool_call_rejects_unknown_arguments`. A SELECT-only guard is therefore not needed; if a SQL tool is ever added it must ship with one. |

## Dependency audit — 2026-11-12 (repeated 2026-11-13)

The 2026-11-13 repeat gave the same result: `pip-audit` reports no known vulnerabilities, and `pnpm audit` reports 7 findings (1 high, 5 moderate, 1 low), all listed below. There are no critical findings.

Commands:

```powershell
uv run --directory api --with pip-audit pip-audit --local
pnpm audit
```

`pip-audit` reported no known vulnerabilities in the installed API environment. The first JavaScript audit found two critical Tinypool advisories, one high Zod advisory, five moderate advisories, and one low advisory. Tinypool was `1.1.1`; it is now pinned to patched `2.1.2` via `pnpm-workspace.yaml`. A repeat audit removed both critical findings.

### High finding retained with reason

| Package | Finding | Current version | Patched version | Reason and mitigation |
| --- | --- | --- | --- | --- |
| zod | GHSA-mrhx-c7xc-m3w5: memory exhaustion while validating oversized constrained collections | 3.25.76 | 4.6.6 or later | The advisory lists no patched Zod 3 release; the project uses Zod throughout the web response-validation schemas. Moving to Zod 4 is a major-version migration that needs a dedicated compatibility pass rather than a lockfile-only update. The API is intended for loopback use and the app validates local API responses, but this does not remove the finding. Track a tested Zod 4 migration; until then the high finding remains open. |

### Remaining lower-severity advisories

The repeat `pnpm audit` reported five moderate advisories and one low advisory:

- Vitest 3.2.7 and `@vitest/mocker` have advisories whose patched versions are Vitest 4.1.11/4.1.12 or later. These are development/test-only; upgrading Vitest is a major change and should be validated separately.
- `glob` and `minimatch` advisories arrive transitively through `vite-plugin-pwa`/`workbox-build` and `typescript-eslint`; the published patched ranges require major versions. They are build/development dependencies.
- `deepmerge` 4.3.1 has a low-severity advisory with no patched version listed, through `workbox-build`.

The full audit output remains nonzero because Zod and the lower-severity advisories are unresolved. Do not treat the tool's nonzero exit as a clean audit.

## Known limitations

- The current provider catalog has no Ollama adapter; installing Ollama does not connect it to this app.
- Browser printing an exported HTML report to PDF is controlled by the browser and is not an application-generated PDF export.
- Optional cloud AI use sends selected result data to the chosen provider only after consent. Review that provider's own retention and billing terms before enabling it.
