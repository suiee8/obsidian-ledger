# ADR 0003: One repository with pnpm for the web app and uv for the API

- Status: accepted
- Date: 2026-11-09

## Decision

Keep `web/` and `api/` in one git repository. The web app uses pnpm 12.18.0 through `pnpm-workspace.yaml`. The API uses uv with its own `pyproject.toml` and `uv.lock`. The root `package.json` provides the scripts that drive both.

## Reasons

- The two halves ship together and share fixtures in `samples/` and generators in `benchmarks/`.
- pnpm and uv both produce lockfiles, so installs are reproducible without a container.
- No Docker or task runner is needed on Windows, where `make` is not installed by default.

## Consequences

- `pnpm bootstrap` runs both installs. Contributors need Node 22+, pnpm, Python 3.12, and uv.
- pnpm 11 and later block install scripts unless they are allowed. `pnpm-workspace.yaml` allows `esbuild` only.
- The name `setup` is not used for a root script because pnpm reserves it.
- `docker compose` (named in the product specification) is deferred. It adds a container requirement without a Phase 0 need.
