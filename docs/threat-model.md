# Threat model

This document describes the local journal's assets, trust boundaries, controls, and residual risks.

## Assets

- Trade history, notes and tags in `.ledger-data` (DuckDB and Parquet).
- Provider API keys in the OS keychain.
- Integrity of exports (CSV, ZIP, HTML, Markdown) that users open in other programs.
- Availability of the local API while importing.

## Entry points

| Entry point | Reached by |
| --- | --- |
| File upload (`/api/imports/*`) | Any file the user chooses, including files from third parties |
| HTTP API on 127.0.0.1 | Local processes, and web pages in the user's browser (cross-site requests, DNS rebinding) |
| Coach / AI layer | Model output rendered in the UI; notes sent as context |
| Exports | Spreadsheet apps opening CSV/XLSX |
| Public mode (opt-in) | Anyone who can reach the host |
| Dependencies and CI | Upstream packages and GitHub Actions |

## Attackers

1. A malicious file author (crafted CSV, XLSX, XLS, JSON).
2. A hostile web page trying to call the local API.
3. Injected content in notes, tags, symbols, filenames or model output.
4. A remote attacker, only if public mode is turned on.
5. A compromised upstream dependency.

## Mitigations

| Threat | Mitigation |
| --- | --- |
| Wrong or disguised file types | Type by magic bytes; only CSV/TSV/TXT, XLSX, XLS, JSON accepted |
| Macros, OLE embeds, external links, DDE | Rejected at validation (`security/files.py`) |
| Zip bombs, zip-slip, symlinks | Entry, size, ratio and nesting limits; traversal and symlink rejection |
| Parser crash, hang, memory blowup, regex DoS | Quarantine under random name, parse in a worker process with timeout and memory limit |
| Malware | Optional ClamAV or Defender scan before parsing; otherwise shown as "not scanned" |
| Cross-site and DNS-rebinding requests | Host and Origin allow-lists, exact-origin CORS, required `X-Ledger-Client` header on writes, method allow-list |
| Abuse | Body-size and time limits, per-client rate limit, concurrency limit for heavy jobs |
| Injection | Parameterised SQL with allow-listed identifiers; no `innerHTML`; sanitised Coach output; escaped exports |
| Spreadsheet formula injection | Leading apostrophe on risky cells in every export |
| Information leaks | Generic error bodies, no stack traces, paths or versions; security log holds no trade data or keys |
| Public access | `LEDGER_PUBLIC=1` adds scrypt login, HttpOnly Secure SameSite=Strict cookie, lockout backoff, idle timeout, docs off |
| Supply chain | Frozen lockfiles, blocked install scripts, Dependabot, SHA-pinned Actions, pip-audit, pnpm audit, gitleaks |

## Residual risks

- **Compromised machine.** Malware running as the user can read `.ledger-data` and the keychain.
- **Parser zero-days.** The worker limits damage but is not a sandbox. Third-party parsers may have unknown flaws.
- **Social engineering.** A user can be talked into importing a file, enabling public mode with a weak password, or exposing the port.
- **Scanner gaps.** Without ClamAV or Defender no malware scan happens; signature scanners miss new samples.
- **Windows permissions.** Folder restriction on Windows is documented, not enforced automatically.
- **Accepted dependency findings** are listed with their exceptions in `docs/security.md`.

## Deployment checklist

For a containerized deployment, apply these controls in the hosting configuration.

- [ ] Run as a non-root user in the container.
- [ ] Read-only root filesystem; one writable volume for the data folder.
- [ ] Drop all Linux capabilities (`cap_drop: [ALL]`).
- [ ] `no-new-privileges:true`.
- [ ] Pin the base image by digest.
- [ ] Container health check against `/health`.
- [ ] No inbound ports except the reverse proxy; the API stays on an internal network.
- [ ] TLS at the proxy; set `LEDGER_PUBLIC=1`, `LEDGER_PASSWORD_HASH` and an explicit `LEDGER_CORS_ORIGINS`.
