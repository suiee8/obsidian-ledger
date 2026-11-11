# ADR 0001: Local-first storage

- Status: accepted
- Date: 2026-11-09

## Decision

Store original uploads as local Parquet files and normalized/queryable data in one local DuckDB database. Bind the API to `127.0.0.1` by default and keep cloud LLM calls optional.

## Reasons

- Trading journals contain sensitive financial and behavioral information.
- DuckDB and Parquet provide columnar analytics without a managed database or paid service.
- A local store keeps the core product useful with no internet connection or LLM.
- Raw rows remain available for audit and rejected rows can be explained without re-fetching a remote source.

## Consequences

- Backups, disk usage, and data deletion are the user's responsibility and must be exposed in the UI.
- Multi-device synchronization is out of scope for the local-first default.
- Optional provider calls require explicit privacy settings, an endpoint, and a user-owned key. Aggregates-only is the default.
- The database must use allow-listed SQL views and a read-only tool boundary for Coach queries.
