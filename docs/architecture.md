# Architecture

```mermaid
flowchart LR
  Browser["React + TypeScript PWA<br/>127.0.0.1:5173"] -->|"JSON, SSE later"| API["FastAPI service<br/>127.0.0.1:8000"]
  API --> Ingest["Streaming ingestion<br/>CSV, TSV, XLSX, JSON"]
  Ingest --> Raw["Parquet originals<br/>local filesystem"]
  Ingest --> Canonical["Canonical trades<br/>Polars validation"]
  Canonical --> DB[("DuckDB file<br/>allow-listed views")]
  DB --> Metrics["Deterministic metrics<br/>bootstrap and Monte Carlo"]
  Metrics --> Coach["Coach<br/>optional local or provider LLM"]
  Coach --> Browser
  Browser --> Export["Markdown, HTML, PDF export<br/>local only"]
```

## Boundaries

- The browser talks to a FastAPI process bound to `127.0.0.1`; default CORS allows only the local Vite origins.
- Raw uploads and the DuckDB database stay on the user's machine. The browser does not send files to a hosted service.
- Deterministic Python code owns parsing, normalization, arithmetic, confidence intervals, simulations, and report evidence.
- An optional Coach can call typed read tools to explain tool results. It never becomes the source of a number.
- `run_sql` will be a single-statement, `SELECT`-only interface over allow-listed views with row and time limits.
- User-authored write actions such as notes and goals require explicit confirmation.

## Phase boundaries

Phase 0 provides the shell, local health boundary, visual tokens, fixture contracts, and reproducible checks. Phase 1 adds ingestion and canonical storage. Phase 2 adds metrics. Later phases add charts, Coach tools, reports, and performance and accessibility hardening.
