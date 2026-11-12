# Dependencies and licenses

Every dependency is free and open source. Versions below are the ones resolved in the committed lockfiles (`pnpm-lock.yaml` and `api/uv.lock`) and installed on the development machine when this list was made.

The project is MIT licensed. Apache-2.0 packages require that their `NOTICE` file, if any, stays with redistributed copies. The OFL-1.1 fonts may be bundled and self-hosted with their license text included.

## Shipped to the browser (web runtime)

| Package | Version | License | Purpose |
| --- | --- | --- | --- |
| react | 19.3.1 | MIT | UI rendering |
| react-dom | 19.3.1 | MIT | DOM rendering |
| cmdk | 1.1.1 | MIT | Command palette |
| zod | 3.25.76 | MIT | Runtime validation of API responses |
| clsx | 2.1.1 | MIT | Class name composition |
| tailwind-merge | 3.7.0 | MIT | Tailwind class conflict resolution |
| @fontsource/sora | 5.3.0 | OFL-1.1 | Self-hosted display font |
| @fontsource/manrope | 5.3.0 | OFL-1.1 | Self-hosted UI font |
| @fontsource/jetbrains-mono | 5.3.0 | OFL-1.1 | Self-hosted numeric font |

`cmdk` brings in Radix UI packages (MIT), `aria-hidden`, `react-remove-scroll`, `react-style-singleton`, `use-sidecar`, and `get-nonce` (all MIT). `tslib` (0BSD) is also included.

## Build and development only (web)

| Package | Version | License |
| --- | --- | --- |
| vite | 6.4.6 | MIT |
| vite-plugin-pwa | 1.3.0 | MIT |
| @vitejs/plugin-react | 4.7.0 | MIT |
| tailwindcss | 4.3.5 | MIT |
| @tailwindcss/vite | 4.3.5 | MIT |
| typescript | 5.9.3 | Apache-2.0 |
| vitest | 3.2.7 | MIT |
| eslint | 9.39.5 | MIT |
| @eslint/js | 9.39.5 | MIT |
| typescript-eslint | 8.72.2 | MIT |
| eslint-plugin-react-hooks | 5.2.0 | MIT |
| eslint-plugin-react-refresh | 0.4.26 | MIT |
| globals | 14.0.0 and 16.5.0 | MIT |
| @types/react | 19.3.0 | MIT |
| @types/react-dom | 19.3.0 | MIT |
| @types/node | 22.20.5 | MIT |

Two transitive build-time packages have non-MIT licenses. Neither is shipped in the browser bundle:

- `lightningcss` 1.33.0 (MPL-2.0) is a CSS build tool. MPL-2.0 applies per file, so it is compatible with distributing this MIT project.
- `caniuse-lite` 1.0.30001823 (CC-BY-4.0) is browser-support data used by build tools.

## Runtime (API)

| Package | Version | License | Purpose |
| --- | --- | --- | --- |
| fastapi | 0.162.4 | MIT | HTTP API |
| starlette | 1.10.0 | BSD-3-Clause | Web framework under FastAPI |
| uvicorn | 0.54.0 | BSD-3-Clause | ASGI server |
| pydantic | 2.14.3 | MIT | Data validation |
| pydantic-settings | 2.16.2 | MIT | Environment configuration |
| polars | 2.1.0 | MIT | ETL and metrics |
| duckdb | 2.0.0 | MIT | Embedded database, trade views, and Parquet writer for raw rows |
| pyarrow | 26.0.1 | Apache-2.0 | Arrow bridge DuckDB uses to read Polars frames during bulk inserts |
| keyring | 25.7.0 | MIT | Stores provider credentials in the operating-system keychain |
| tzdata | 2026.6 | Apache-2.0 | IANA timezone database, needed on Windows |
| numpy | 2.5.4 | BSD-3-Clause and others | Numerical arrays |
| scipy | 1.18.1 | BSD-3-Clause | Statistics |
| openpyxl | 3.1.5 | MIT | XLSX support in the test suite |
| python-calamine | 0.9.1 | MIT | Reads XLSX and XLS cached values |
| charset-normalizer | 3.5.2 | MIT | Encoding detection for non-UTF-8 text |

`uvicorn[standard]` adds `httptools` (MIT), `watchfiles` (MIT), and `websockets` (BSD-3-Clause).

## Development and tests (API)

| Package | Version | License |
| --- | --- | --- |
| pytest | 9.2.0 | MIT |
| ruff | 0.17.4 | MIT |
| pyright | 1.1.414 | MIT |
| httpx | 0.28.1 | BSD-3-Clause | HTTP client used by API tests and provider adapters |
| httpx2 | 2.16.0 | BSD-3-Clause |

`certifi` (MPL-2.0) is installed as a transitive dependency of the HTTP client. MPL-2.0 is file-level copyleft, so it does not change the license of this project.

## Build tools (web icons)

| Package | Version | License | Purpose |
| --- | --- | --- | --- |
| @resvg/resvg-js | 2.6.2 | MPL-2.0 | Renders `web/icons/icon.svg` to PNG icons. Build-time only, not shipped. MPL-2.0 is file-level copyleft, so it does not change the license of this project. |

## Added in Phase 3.5 (quality gates, development only)

| Package | Version | License | Purpose |
| --- | --- | --- | --- |
| @playwright/test | 1.65.0 | Apache-2.0 | End-to-end tests and screenshots. Uses the installed Microsoft Edge, so no browser download. |
| playwright-core | 1.65.0 | Apache-2.0 | Installed with `@playwright/test`. |
| @axe-core/playwright | 4.14.0 | MPL-2.0 | Accessibility checks in the Playwright tests. Not shipped. MPL-2.0 is file-level copyleft, so it does not change the license of this project. |
| axe-core | 4.14.0 | MPL-2.0 | Installed with `@axe-core/playwright`. Not shipped. |

## Added in Phase 3 (web)

| Package | Version | License | Purpose |
| --- | --- | --- | --- |
| echarts | 6.1.0 | Apache-2.0 | Equity, R histogram, and edge radar charts. Only the chart types and components the app uses are registered. Apache-2.0 requires keeping the NOTICE file with redistributed copies. |
| @tanstack/react-query | 5.107.1 | MIT | Server state, caching, and request retries |
| @tanstack/react-virtual | 3.14.26 | MIT | Virtualized rows in the Trades table |
| zustand | 5.1.0 | MIT | Filter and UI state |
| react-dropzone | 20.2.0 | MIT | Drag-and-drop file selection on the Import screen |

Development and test only (web):

| Package | Version | License |
| --- | --- | --- |
| jsdom | 31.0.0 | MIT |
| @testing-library/react | 16.3.3 | MIT |
| @testing-library/dom | 10.4.2 | MIT |

Phase 3 also uses `@resvg/resvg-js` 2.6.2 (MPL-2.0) for the PNG icon build, listed above.

Two libraries were considered and not added. TanStack Table v9 was rejected because its API is unfamiliar for this codebase, so the Trades table uses TanStack Virtual with plain column definitions. Motion (animation) was deferred.

## Transitive security override

| Package | Version | License | Purpose |
| --- | --- | --- | --- |
| tinypool | 2.1.2 | MIT | Vitest worker pool; pinned through `pnpm-workspace.yaml` to the patched release |

Phase 6 does not add a model client or paid provider package. Ollama is installed separately by users and is not yet integrated with the app.

## Audit and browser tools (not application dependencies)

| Tool | Version | License | Use |
| --- | --- | --- | --- |
| pip-audit | 2.10.1 | Apache-2.0 | Ephemeral API dependency audit via `uv run --with pip-audit pip-audit --local`; not added to a project manifest or lockfile |
| Lighthouse CLI | 13.6.0 | Apache-2.0 | Ephemeral desktop performance audit in Microsoft Edge; not added to a package manifest or lockfile |

`pip-audit` is invoked ephemerally for the API dependency audit, so it is not added to `api/pyproject.toml` or `api/uv.lock`. Lighthouse is likewise invoked with `npx` and is not a shipped dependency.

## Regenerate this inventory

```powershell
pnpm -C web licenses list --json
uv run --directory api python -c "from importlib.metadata import distributions; [print(d.metadata['Name'], d.version, d.metadata.get('License-Expression') or d.metadata.get('License')) for d in distributions()]"
```

## Added in Phase 2

| Package | Version | License | Purpose |
| --- | --- | --- | --- |
| hypothesis | 6.170.15 | MPL-2.0 | Property tests. Development only. Not shipped. |
| sortedcontainers | 2.4.0 | Apache-2.0 | Installed with Hypothesis. Development only. |
| scipy | 1.18.1 | BSD-3-Clause | t-distribution quantiles and Welch's t-test. Now used at runtime through `metrics/_scipy.py`. |
