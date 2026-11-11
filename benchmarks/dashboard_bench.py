"""Time the dashboard response path, 10 runs each, with median and standard deviation.

    uv run --directory api python ../benchmarks/dashboard_bench.py \
        ../benchmarks/out/synthetic_10k.csv

Rows:
  cold      a new engine: loads the trade frame, computes the dashboard, serializes, compresses
  warm      frame already loaded, a new filter: compute, serialize, compress
  repeat    same filters again: served from the serialized cache
"""

from __future__ import annotations

import statistics
import sys
import tempfile
import time
from collections.abc import Callable, Sequence
from pathlib import Path

from obsidian_ledger.coach.service import CoachService
from obsidian_ledger.ingest.analysis import analyze
from obsidian_ledger.ingest.options import ImportOptions
from obsidian_ledger.ingest.run import run_import
from obsidian_ledger.metrics.data import Filters
from obsidian_ledger.metrics.engine import AnalysisEngine
from obsidian_ledger.store.db import Store

RUNS = 10
SYMBOLS = ("NVDA", "MSFT", "AAPL", "EURUSD", "BTCUSD")


def measure(action: Callable[[], object]) -> float:
    started = time.perf_counter()
    action()
    return time.perf_counter() - started


def summary(samples: list[float]) -> str:
    return (
        f"median {statistics.median(samples) * 1000:7.1f} ms   "
        f"stdev {statistics.stdev(samples) * 1000:6.1f} ms   "
        f"min {min(samples) * 1000:7.1f}   max {max(samples) * 1000:7.1f}"
    )


def main(argv: Sequence[str]) -> int:
    source = Path(argv[1]).resolve()
    options = ImportOptions()
    with tempfile.TemporaryDirectory() as scratch:
        store = Store(Path(scratch) / "data")
        try:
            outcome = run_import(analyze(source, options), options)
            store.insert_frame("bench", outcome.frame, options.base_currency)
            cold = [
                measure(lambda: AnalysisEngine(store).dashboard_bytes(Filters()))
                for _ in range(RUNS)
            ]
            engine = AnalysisEngine(store)
            engine.dashboard_bytes(Filters())

            def fresh_warm() -> float:
                # Drop the computed results but keep the loaded frame, as a new filter would.
                engine.clear_results()
                return measure(lambda: engine.dashboard_bytes(Filters()))

            warm = [fresh_warm() for _ in range(RUNS)]
            repeat = [measure(lambda: engine.dashboard_bytes(Filters())) for _ in range(RUNS)]
            # The Coach on a loaded frame. force=True skips the stored report and recomputes.
            service = CoachService(store, engine)
            coach = [measure(lambda: service.report(Filters(), force=True)) for _ in range(RUNS)]
        finally:
            store.close()
    print(f"{source.name}, {outcome.frame.height} trades, {RUNS} runs")
    print(f"  cold    {summary(cold)}")
    print(f"  warm    {summary(warm)}")
    print(f"  repeat  {summary(repeat)}")
    print(f"  coach   {summary(coach)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
