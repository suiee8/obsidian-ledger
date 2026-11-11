# ADR 0004: Commit the 100k synthetic sample and its manifest

- Status: accepted
- Date: 2026-11-09

## Decision

Commit `samples/synthetic_100k.csv` (about 15 MB) and `samples/synthetic_100k.manifest.json`. The 1M-row file stays out of git under `benchmarks/out/`.

## Reasons

- The product specification lists a 100k-trade synthetic file as a Phase 0 sample dataset.
- A fresh clone then runs the 100k benchmark without a generation step.
- The generator is deterministic. Re-running it with seed 42 produced the same SHA-256 as the committed file (`1d6e64f6…f1296`), so the file can be verified.

## Consequences

- Each regeneration that changes the output must update the manifest in the same commit.
- Repository size grows by about 15 MB. The 1M-row file (roughly 155 MB, scaled from the 100k file's size) would exceed a comfortable limit, so it is not committed. If larger samples are needed, use Git LFS or a release asset.
