# Benchmark results

## Machine

- os: Windows 11 (10.0.26300)
- python: 3.12.16
- polars: 2.1.0
- obsidian_ledger: 0.1.0
- cpu: 12th Gen Intel(R) Core(TM) i5-1235U (10 cores, 12 threads)
- ram: 7.7 GB

Times are medians of 5 runs. Lower is better.

## 1,000 trades

| Measure | before | after |
|---|---|---|
| Ingest total | 0.134 s | 0.254 s |
|   analyze | 0.027 s | 0.034 s |
|   process rows | 0.058 s | 0.157 s |
|   insert trades | 0.051 s | 0.067 s |
| Dashboard, cold | 0.100 s | 0.103 s |
| Dashboard response (JSON + gzip), cold | 0.105 s | 0.103 s |
| Dashboard, cached | 0.001 s | 0.001 s |
| Filter change (dashboard, warm frame) | 0.042 s | 0.034 s |
| Filter change (segments, warm frame) | 0.007 s | 0.006 s |
| Trades page, first | 0.043 s | 0.045 s |
| Trades page, middle | 0.042 s | 0.046 s |
| Coach report, warm frame | n/a | 0.061 s |
| Simulator, one rule | 0.048 s | 0.059 s |
| Monte Carlo, 5,000 paths | 0.159 s | 0.129 s |

## 5,000 trades

| Measure | before | after |
|---|---|---|
| Ingest total | 0.556 s | 0.414 s |
|   analyze | 0.039 s | 0.029 s |
|   process rows | 0.410 s | 0.303 s |
|   insert trades | 0.112 s | 0.091 s |
| Dashboard, cold | 0.227 s | 0.161 s |
| Dashboard response (JSON + gzip), cold | 0.232 s | 0.208 s |
| Dashboard, cached | 0.001 s | 0.001 s |
| Filter change (dashboard, warm frame) | 0.091 s | 0.060 s |
| Filter change (segments, warm frame) | 0.011 s | 0.007 s |
| Trades page, first | 0.109 s | 0.090 s |
| Trades page, middle | 0.108 s | 0.082 s |
| Coach report, warm frame | n/a | 0.160 s |
| Simulator, one rule | 0.193 s | 0.163 s |
| Monte Carlo, 5,000 paths | 0.140 s | 0.132 s |

## 10,000 trades

| Measure | before | after |
|---|---|---|
| Ingest total | 1.227 s | 0.673 s |
|   analyze | 0.048 s | 0.036 s |
|   process rows | 0.915 s | 0.503 s |
|   insert trades | 0.243 s | 0.118 s |
| Dashboard, cold | 0.452 s | 0.256 s |
| Dashboard response (JSON + gzip), cold | 0.810 s | 0.263 s |
| Dashboard, cached | 0.001 s | 0.001 s |
| Filter change (dashboard, warm frame) | 0.114 s | 0.078 s |
| Filter change (segments, warm frame) | 0.040 s | 0.009 s |
| Trades page, first | 0.354 s | 0.128 s |
| Trades page, middle | 0.301 s | 0.129 s |
| Coach report, warm frame | n/a | 0.335 s |
| Simulator, one rule | 0.853 s | 0.301 s |
| Monte Carlo, 5,000 paths | 0.149 s | 0.150 s |

## Payload and bundle

- before: dashboard payload gzip by size: 1,000 rows 23.0 kB, 5,000 rows 88.5 kB, 10,000 rows 104.1 kB
- before: initial JavaScript 116.0 kB gzip (385.6 kB raw)
- before: browser (10k rows): table scroll 59.0 fps, p95 frame 16.9 ms; this run scrolled over placeholder rows, because the table only loaded its first block, so its fps does not describe real rows; dashboard ready 3.15 s, filter to ready 1.81 s
- after: dashboard payload gzip by size: 1,000 rows 23.0 kB, 5,000 rows 88.5 kB, 10,000 rows 104.1 kB
- after: initial JavaScript 120.8 kB gzip (401.0 kB raw)
- after: browser (10k rows): table scroll 30.0 fps, p95 frame 33.6 ms; an empty scroll container reaches 30.0 fps in this headless browser, which is the most any page can show here; main-thread work is 6.3 ms per scrolled frame against a 16.7 ms budget; 40 of 40 visible rows held real data after scrolling; dashboard ready 3.88 s, filter to ready 2.07 s
