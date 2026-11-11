"""Profile the three paths that miss their targets at 10k trades: ingest, dashboard, and segments.

Prints the top functions by internal time for each path. Run from api/:

    uv run --directory api python ../benchmarks/profile_hotspots.py \
        ../benchmarks/out/synthetic_10k.csv
"""

from __future__ import annotations

import cProfile
import io
import pstats
import sys
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from obsidian_ledger.ingest.analysis import analyze
from obsidian_ledger.ingest.options import ImportOptions
from obsidian_ledger.ingest.run import run_import
from obsidian_ledger.metrics.data import Filters
from obsidian_ledger.metrics.engine import AnalysisEngine
from obsidian_ledger.store.db import Store

TOP = 12


def profiled(label: str, action: Callable[[], Any]) -> Any:
    profiler = cProfile.Profile()
    profiler.enable()
    result = action()
    profiler.disable()
    buffer = io.StringIO()
    stats = pstats.Stats(profiler, stream=buffer).sort_stats("tottime")
    stats.print_stats(TOP)
    print(f"\n### {label}: top {TOP} by internal time")
    lines = [line for line in buffer.getvalue().splitlines() if line.strip()]
    start = next((i for i, line in enumerate(lines) if "ncalls" in line), 0)
    for line in lines[start : start + TOP + 1]:
        print(line[:200])
    return result


def main(argv: Sequence[str]) -> int:
    if len(argv) != 2:
        print("usage: profile_hotspots.py <journal.csv>", file=sys.stderr)
        return 2
    source = Path(argv[1]).resolve()
    options = ImportOptions()
    with tempfile.TemporaryDirectory() as scratch:
        store = Store(Path(scratch) / "data")
        try:
            analysis = profiled("ingest: analyze", lambda: analyze(source, options))
            outcome = profiled("ingest: process rows", lambda: run_import(analysis, options))
            profiled(
                "ingest: insert trades",
                lambda: store.insert_frame("profile", outcome.frame, options.base_currency),
            )
            # The server keeps the loaded frame, so filter changes are profiled on a warm engine.
            engine = AnalysisEngine(store)
            profiled(
                "first dashboard request (loads the frame)", lambda: engine.dashboard(Filters())
            )
            profiled(
                "dashboard after a symbol filter (warm)",
                lambda: engine.dashboard(Filters(symbols=("NVDA",))),
            )
            profiled(
                "segments after a setup filter (warm)",
                lambda: engine.segments(Filters(setups=("breakout",)), "symbol", 30),
            )
        finally:
            store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
