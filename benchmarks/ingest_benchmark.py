"""Time each stage of one ingestion: analysis, row processing, raw Parquet, and the DuckDB insert.

Run from the api folder so the package resolves:

    uv run --directory api python ../benchmarks/ingest_benchmark.py ../samples/synthetic_100k.csv
"""

from __future__ import annotations

import sys
import tempfile
import time
from collections.abc import Sequence
from pathlib import Path

from obsidian_ledger.ingest.analysis import analyze
from obsidian_ledger.ingest.options import ImportOptions
from obsidian_ledger.ingest.run import run_import
from obsidian_ledger.store.db import Store
from obsidian_ledger.store.raw import write_raw


def main(argv: Sequence[str]) -> int:
    if len(argv) != 2:
        print("usage: ingest_benchmark.py <journal.csv>", file=sys.stderr)
        return 2
    source_path = Path(argv[1]).resolve()
    options = ImportOptions()
    timings: dict[str, float] = {}

    with tempfile.TemporaryDirectory() as scratch:
        store = Store(Path(scratch) / "data")
        try:
            started = time.perf_counter()
            analysis = analyze(source_path, options)
            timings["analyze"] = time.perf_counter() - started
            if analysis.blocking:
                print("blocking questions:", [q.id for q in analysis.blocking], file=sys.stderr)
                return 1

            started = time.perf_counter()
            outcome = run_import(analysis, options)
            timings["process rows"] = time.perf_counter() - started

            started = time.perf_counter()
            raw_rows = write_raw(analysis.source, Path(scratch) / "raw.parquet")
            timings["raw parquet"] = time.perf_counter() - started

            started = time.perf_counter()
            inserted, _present = store.insert_frame("bench", outcome.frame, options.base_currency)
            timings["insert trades"] = time.perf_counter() - started

            started = time.perf_counter()
            store.list_trades(100, 0)
            timings["first page query"] = time.perf_counter() - started
        finally:
            store.close()

    total = sum(timings.values())
    print(f"file: {source_path.name}")
    print(
        f"rows: {outcome.rows_total} processed, {outcome.frame.height} accepted, "
        f"{len(outcome.rejected)} rejected, {inserted} inserted, {raw_rows} raw rows kept"
    )
    for stage, seconds in timings.items():
        print(f"  {stage:<18} {seconds:8.3f} s")
    print(f"  {'total':<18} {total:8.3f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
