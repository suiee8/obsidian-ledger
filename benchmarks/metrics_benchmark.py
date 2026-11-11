"""Time the analysis endpoints on one journal: full report, a segment table, and a simulation.

Run from the api folder:

    uv run --directory api python ../benchmarks/metrics_benchmark.py ../samples/synthetic_100k.csv
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
from obsidian_ledger.metrics.data import Filters
from obsidian_ledger.metrics.engine import AnalysisEngine, Params
from obsidian_ledger.metrics.simulator import Rules
from obsidian_ledger.store.db import Store


def main(argv: Sequence[str]) -> int:
    if len(argv) != 2:
        print("usage: metrics_benchmark.py <journal.csv>", file=sys.stderr)
        return 2
    source = Path(argv[1]).resolve()
    timings: dict[str, float] = {}
    with tempfile.TemporaryDirectory() as scratch:
        store = Store(Path(scratch) / "data")
        try:
            options = ImportOptions()
            outcome = run_import(analyze(source, options), options)
            store.insert_frame("bench", outcome.frame, options.base_currency)
            engine = AnalysisEngine(store)

            started = time.perf_counter()
            engine.report(Filters(), Params(bootstrap_resamples=1000, mc_paths=5000))
            timings["full report (cold)"] = time.perf_counter() - started

            started = time.perf_counter()
            engine.report(Filters(), Params(bootstrap_resamples=1000, mc_paths=5000))
            timings["full report (cached)"] = time.perf_counter() - started

            started = time.perf_counter()
            engine.segments(Filters(), "symbol", 30)
            timings["segments by symbol"] = time.perf_counter() - started

            started = time.perf_counter()
            engine.simulate(Filters(), Rules(daily_loss_cap=500.0), 1000, 42)
            timings["simulator with one rule"] = time.perf_counter() - started
        finally:
            store.close()

    print(f"file: {source.name}, {outcome.frame.height} trades")
    for label, seconds in timings.items():
        print(f"  {label:<26} {seconds:8.3f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
