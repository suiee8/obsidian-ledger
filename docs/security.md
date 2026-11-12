# Security notes

## Local data and network boundary

- The supported development commands bind the API and web server to loopback (`127.0.0.1`). The API rejects any request carrying an Origin header that is not in its configured allow-list.
- Uploads are size-limited. XLSX archive validation rejects excessive expansion, excessive member counts, and absolute or parent-traversal member paths. File extension and content signatures are checked before parsing.
- Imported files and the DuckDB/Parquet store remain local. Provider requests are optional, require explicit consent, and use the selected provider endpoint. No telemetry is configured.

## Export and credential controls

- CSV output is parsed after serialization and every cell is checked. Cells beginning with `=`, `+`, `-`, `@`, tab, carriage return, or optional leading spaces before those prefixes receive a leading apostrophe. This covers trade, segment, Coach-report, rejected-row, and CSV-in-ZIP exports. JSON numbers remain numeric.
- Provider keys are stored through `keyring` in the OS keychain. The API returns only a masked hint; the database, captured logs, exports, and every ZIP member are checked by a canary-key test.
- ZIP exports are assembled locally and do not contain the provider key.

## Dependency audit — 2026-11-12

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
