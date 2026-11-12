# Benchmark results

## Machine

- os: Windows 11 (10.0.26300)
- python: 3.12.16
- polars: 2.1.0
- obsidian_ledger: 0.1.0
- cpu: 12th Gen Intel(R) Core(TM) i5-1235U (10 cores, 12 threads)
- ram: 7.7 GB

Cells show the median in seconds and, when recorded, the min–max range. Run counts are shown in each column header; older labels retain their original counts.

## Phase 6 validation (2026-11-12)

`pnpm bench` measured 1,000, 5,000, and 10,000 trades, ten runs per size. The dashboard-response measurement now calls the same `AnalysisEngine.dashboard_bytes` JSON-and-gzip path used by the API instead of timing a separate standard-library serializer.

| Target | 10k median | Observed range | Result |
| --- | ---: | ---: | --- |
| Ingest under 1 s | 0.653 s | 0.571–0.781 s | Pass |
| Dashboard payload under 300 ms | 0.287 s | 0.269–0.322 s | Median passes; slowest run was 22 ms over |
| Filter change under 100 ms | 0.084 s | 0.066–0.099 s | Pass |
| Monte Carlo, 5,000 paths, under 2 s | 0.143 s | 0.136–0.152 s | Pass |
| Initial JavaScript at most 250 KB gzip | 127.8 kB | — | Pass |

The 10k ingest step was optimized by building the Polars validation pipeline lazily and collecting the calculated rows once, rather than evaluating each eager transformation separately. The benchmark was rerun for ten trials at all three sizes. The previous dashboard-response median of 0.340 s was caused by the harness using a slower serializer than the API; the harness now measures the production JSON-and-gzip implementation.

Lighthouse CLI 13.6.0, desktop preset, Microsoft Edge, on the production preview:

| Category | Score |
| --- | ---: |
| Performance | 100 |
| Accessibility | 100 |
| Best practices | 96 |
| SEO | 91 |
| Agentic browsing (Lighthouse 13.6.0 additional category) | 50 |

The performance audit's only score-lowering metrics were Largest Contentful Paint (0.7 s, audit score 0.99) and Speed Index (0.9 s, audit score 0.99); the category score rounded to 100. Outside the requested performance target, Best Practices was lowered by `errors-in-console`: the audit was run against the web preview without starting the local API, so requests to `127.0.0.1:8000` were refused. SEO was lowered by `robots-txt`: the Vite preview returned its HTML fallback for `/robots.txt`. The additional Agentic Browsing category reported missing `llms.txt` guidance and a malformed ARD manifest fallback; neither file is part of this local application.

The host was Windows 11 (10.0.26300), Python 3.12.16, Polars 2.1.0, a 12th Gen Intel Core i5-1235U (10 cores, 12 threads), and 7.7 GB RAM. Other open applications were not closed or independently verified, so timings are indicative rather than isolated-machine measurements. The ranges above are retained to show run-to-run variation; in particular, the maximum dashboard response exceeded the target although its median met it.

## 1,000 trades

| Measure | before (5 runs) | after (5 runs) | latest (10 runs) |
|---|---|---|---|
| Ingest total | 0.134 s | 0.254 s | 0.330 s (0.257–0.497) |
|   analyze | 0.027 s | 0.034 s | 0.039 s (0.029–0.170) |
|   process rows | 0.058 s | 0.157 s | 0.203 s (0.152–0.263) |
|   insert trades | 0.051 s | 0.067 s | 0.086 s (0.071–0.121) |
| Dashboard, cold | 0.100 s | 0.103 s | 0.108 s (0.099–0.154) |
| Dashboard response (JSON + gzip), cold | 0.105 s | 0.103 s | 0.122 s (0.106–0.146) |
| Dashboard, cached | 0.001 s | 0.001 s | 0.001 s (0.001–0.001) |
| Filter change (dashboard, warm frame) | 0.042 s | 0.034 s | 0.036 s (0.035–0.050) |
| Filter change (segments, warm frame) | 0.007 s | 0.006 s | 0.006 s (0.005–0.009) |
| Trades page, first | 0.043 s | 0.045 s | 0.060 s (0.051–0.076) |
| Trades page, middle | 0.042 s | 0.046 s | 0.076 s (0.065–0.101) |
| Coach report, warm frame | n/a | 0.061 s | 0.072 s (0.069–0.094) |
| Simulator, one rule | 0.048 s | 0.059 s | 0.084 s (0.071–0.097) |
| Monte Carlo, 5,000 paths | 0.159 s | 0.129 s | 0.134 s (0.126–0.143) |

## 5,000 trades

| Measure | before (5 runs) | after (5 runs) | latest (10 runs) |
|---|---|---|---|
| Ingest total | 0.556 s | 0.414 s | 0.452 s (0.427–0.537) |
|   analyze | 0.039 s | 0.029 s | 0.040 s (0.037–0.047) |
|   process rows | 0.410 s | 0.303 s | 0.304 s (0.270–0.355) |
|   insert trades | 0.112 s | 0.091 s | 0.117 s (0.103–0.143) |
| Dashboard, cold | 0.227 s | 0.161 s | 0.194 s (0.169–0.254) |
| Dashboard response (JSON + gzip), cold | 0.232 s | 0.208 s | 0.248 s (0.203–0.355) |
| Dashboard, cached | 0.001 s | 0.001 s | 0.001 s (0.001–0.002) |
| Filter change (dashboard, warm frame) | 0.091 s | 0.060 s | 0.067 s (0.063–0.074) |
| Filter change (segments, warm frame) | 0.011 s | 0.007 s | 0.007 s (0.006–0.009) |
| Trades page, first | 0.109 s | 0.090 s | 0.104 s (0.090–0.128) |
| Trades page, middle | 0.108 s | 0.082 s | 0.109 s (0.090–0.142) |
| Coach report, warm frame | n/a | 0.160 s | 0.165 s (0.153–0.186) |
| Simulator, one rule | 0.193 s | 0.163 s | 0.193 s (0.175–0.302) |
| Monte Carlo, 5,000 paths | 0.140 s | 0.132 s | 0.132 s (0.124–0.137) |

## 10,000 trades

| Measure | before (5 runs) | after (5 runs) | latest (10 runs) |
|---|---|---|---|
| Ingest total | 1.227 s | 0.673 s | 0.653 s (0.571–0.781) |
|   analyze | 0.048 s | 0.036 s | 0.038 s (0.037–0.050) |
|   process rows | 0.915 s | 0.503 s | 0.436 s (0.386–0.559) |
|   insert trades | 0.243 s | 0.118 s | 0.169 s (0.148–0.201) |
| Dashboard, cold | 0.452 s | 0.256 s | 0.288 s (0.248–0.313) |
| Dashboard response (JSON + gzip), cold | 0.810 s | 0.263 s | 0.287 s (0.269–0.322) |
| Dashboard, cached | 0.001 s | 0.001 s | 0.001 s (0.001–0.001) |
| Filter change (dashboard, warm frame) | 0.114 s | 0.078 s | 0.084 s (0.066–0.099) |
| Filter change (segments, warm frame) | 0.040 s | 0.009 s | 0.009 s (0.008–0.013) |
| Trades page, first | 0.354 s | 0.128 s | 0.137 s (0.122–0.164) |
| Trades page, middle | 0.301 s | 0.129 s | 0.142 s (0.113–0.182) |
| Coach report, warm frame | n/a | 0.335 s | 0.342 s (0.295–0.393) |
| Simulator, one rule | 0.853 s | 0.301 s | 0.315 s (0.290–0.410) |
| Monte Carlo, 5,000 paths | 0.149 s | 0.150 s | 0.143 s (0.136–0.152) |

## Payload and bundle

- before: dashboard payload gzip by size: 1,000 rows 23.0 kB, 5,000 rows 88.5 kB, 10,000 rows 104.1 kB
- before: initial JavaScript 116.0 kB gzip (385.6 kB raw)
- before: browser (10k rows): table scroll 59.0 fps, p95 frame 16.9 ms; this run scrolled over placeholder rows, because the table only loaded its first block, so its fps does not describe real rows; dashboard ready 3.15 s, filter to ready 1.81 s
- after: dashboard payload gzip by size: 1,000 rows 23.0 kB, 5,000 rows 88.5 kB, 10,000 rows 104.1 kB
- after: initial JavaScript 120.8 kB gzip (401.0 kB raw)
- after: browser (10k rows): table scroll 30.0 fps, p95 frame 33.6 ms; an empty scroll container reaches 30.0 fps in this headless browser, which is the most any page can show here; main-thread work is 6.3 ms per scrolled frame against a 16.7 ms budget; 40 of 40 visible rows held real data after scrolling; dashboard ready 3.88 s, filter to ready 2.07 s
- latest: dashboard payload gzip by size: 1,000 rows 23.0 kB, 5,000 rows 88.5 kB, 10,000 rows 104.1 kB
- latest: initial JavaScript 127.8 kB gzip (424.8 kB raw)
- latest: browser (10k rows): table scroll 60.0 fps, p95 frame 16.9 ms; an empty scroll container reaches 60.0 fps in this headless browser, which is the most any page can show here; main-thread work is 5.4 ms per scrolled frame against a 16.7 ms budget; 40 of 40 visible rows held real data after scrolling; dashboard ready 3.32 s, filter to ready 2.29 s
