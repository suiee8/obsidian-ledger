"""Run the performance benchmark and write results.

Measures, for 1k, 5k, and 10k synthetic trades:
  - ingest stages (analyze, process rows, raw Parquet, bulk insert)
  - dashboard payload (cold and cached) and its gzip size
  - a filter change (cold dashboard and cold segment table)
  - a trades page from the table query
  - the simulator with one rule
  - initial JavaScript (gzip) from the built web app
  - optionally, browser measurements (table scroll fps, time to dashboard) with --ui

Each run writes benchmarks/out/bench-<label>.json. RESULTS.md is rendered from every label found.

    pnpm bench -- --label before
    pnpm bench -- --label after --ui

Run from the repository root through pnpm, or from api/ with uv:
    uv run --directory api python ../benchmarks/bench.py --label after
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import platform
import re
import shutil
import socket
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.request
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import polars as pl

import generate_trades
from obsidian_ledger import __version__
from obsidian_ledger.coach.service import CoachService
from obsidian_ledger.ingest.analysis import analyze
from obsidian_ledger.ingest.options import ImportOptions
from obsidian_ledger.ingest.run import run_import
from obsidian_ledger.metrics.data import Filters, prepare
from obsidian_ledger.metrics.engine import AnalysisEngine
from obsidian_ledger.metrics.simulator import Rules
from obsidian_ledger.metrics.stats import monte_carlo
from obsidian_ledger.store.db import Store
from obsidian_ledger.store.queries import order_clause, where_clause

ROOT = Path(__file__).resolve().parent.parent
BENCH = ROOT / "benchmarks"
OUT = BENCH / "out"
SIZES = (1_000, 5_000, 10_000)
DATASETS = {
    1_000: OUT / "synthetic_1k.csv",
    5_000: OUT / "synthetic_5k.csv",
    10_000: OUT / "synthetic_10k.csv",
}
BROWSER_SIZE = 10_000
DATASET_RUNS = 10
SYMBOL_FILTER = Filters(symbols=("NVDA",))
SETUP_FILTER = Filters(setups=("breakout",))
RULE = Rules(daily_loss_cap=500.0)
SIMULATOR_RESAMPLES = 1000


def machine_specs() -> dict[str, str]:
    specs = {
        "os": f"{platform.system()} {platform.release()} ({platform.version()})",
        "python": platform.python_version(),
        "polars": pl.__version__,
        "obsidian_ledger": __version__,
        "cpu": platform.processor() or "unknown",
        "ram": "unknown",
    }
    try:
        script = (
            "$c=Get-CimInstance Win32_Processor | Select-Object -First 1; "
            "$o=Get-CimInstance Win32_OperatingSystem; "
            "Write-Output ($c.Name.Trim()); "
            "Write-Output ($c.NumberOfCores); "
            "Write-Output ($c.NumberOfLogicalProcessors); "
            "Write-Output ([math]::Round($o.TotalVisibleMemorySize/1MB,1))"
        )
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
        if len(lines) >= 4:
            specs["cpu"] = f"{lines[0]} ({lines[1]} cores, {lines[2]} threads)"
            specs["ram"] = f"{lines[3]} GB"
    except (OSError, subprocess.SubprocessError):
        pass
    return specs


def ensure_datasets(sizes: Sequence[int]) -> None:
    for size in sizes:
        path = DATASETS[size]
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            print(f"generating {size} rows at {path}", flush=True)
            generate_trades.main(["--rows", str(size), "--out", str(path)])


def timed(action: Callable[[], Any]) -> tuple[float, Any]:
    started = time.perf_counter()
    result = action()
    return time.perf_counter() - started, result


def ingest_once(source: Path, scratch: Path) -> tuple[dict[str, float], Store, int]:
    """Run one import into a fresh store. Returns stage times, the store, and the accepted count."""
    options = ImportOptions()
    stages: dict[str, float] = {}
    store = Store(scratch / f"data-{time.perf_counter_ns()}")
    seconds, analysis = timed(lambda: analyze(source, options))
    stages["analyze"] = seconds
    if analysis.blocking:
        raise SystemExit(
            f"blocking questions for {source.name}: {[q.id for q in analysis.blocking]}"
        )
    seconds, outcome = timed(lambda: run_import(analysis, options))
    stages["process rows"] = seconds
    seconds, _ = timed(lambda: store.insert_frame("bench", outcome.frame, options.base_currency))
    stages["insert trades"] = seconds
    stages["total"] = sum(stages.values())
    return stages, store, outcome.frame.height


def dashboard_payload_bytes(payload: dict[str, Any]) -> tuple[int, int]:
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return len(raw), len(gzip.compress(raw, compresslevel=6))


def measure_size(size: int, scratch: Path) -> dict[str, Any]:
    runs = DATASET_RUNS
    source = DATASETS[size]
    print(f"\n== {size:,} trades from {source.name} ({runs} run(s) each)", flush=True)
    result: dict[str, Any] = {"rows": size, "runs": runs, "ranges": {}}

    def measure(name: str, action: Callable[[], float]) -> float:
        values = [action() for _ in range(runs)]
        result["ranges"][name] = {"min": min(values), "max": max(values)}
        return statistics.median(values)

    ingest_runs: list[dict[str, float]] = []
    store: Store | None = None
    accepted = 0
    for _ in range(runs):
        if store is not None:
            store.close()
        stages, store, accepted = ingest_once(source, scratch)
        ingest_runs.append(stages)
    assert store is not None
    result["ingest"] = {
        key: statistics.median(run[key] for run in ingest_runs) for key in ingest_runs[0]
    }
    for key in ingest_runs[0]:
        values = [run[key] for run in ingest_runs]
        result["ranges"][f"ingest.{key}"] = {"min": min(values), "max": max(values)}
    result["accepted_trades"] = accepted
    print(f"  ingest total       {result['ingest']['total']:8.3f} s", flush=True)

    try:

        def cold_dashboard(filters: Filters) -> Callable[[], float]:
            def run() -> float:
                engine = AnalysisEngine(store)
                seconds, _ = timed(lambda: engine.dashboard(filters))
                return seconds

            return run

        result["dashboard_cold"] = measure("dashboard_cold", cold_dashboard(Filters()))
        engine = AnalysisEngine(store)
        engine.dashboard(Filters())
        result["dashboard_cached"] = measure(
            "dashboard_cached",
            lambda: timed(lambda: engine.dashboard(Filters()))[0],
        )
        payload = engine.dashboard(Filters())
        raw_bytes, gzip_bytes = dashboard_payload_bytes(payload)
        result["dashboard_bytes"] = {"raw": raw_bytes, "gzip": gzip_bytes}
        print(f"  dashboard cold     {result['dashboard_cold']:8.3f} s", flush=True)

        # The running server keeps the loaded trade frame per dataset version, so a filter change
        # is measured on an engine that already holds the frame. The first request after an import
        # is measured separately (see dashboard_cold).
        def warm_filter_change(
            filters: Filters, call: Callable[[AnalysisEngine, Filters], Any]
        ) -> Callable[[], float]:
            def run() -> float:
                engine = AnalysisEngine(store)
                engine.dashboard(Filters())
                seconds, _ = timed(lambda: call(engine, filters))
                return seconds

            return run

        result["filter_change_dashboard"] = measure(
            "filter_change_dashboard",
            warm_filter_change(SYMBOL_FILTER, lambda engine, f: engine.dashboard(f)),
        )
        result["filter_change_segments"] = measure(
            "filter_change_segments",
            warm_filter_change(SETUP_FILTER, lambda engine, f: engine.segments(f, "symbol", 30)),
        )
        print(f"  filter change      {result['filter_change_dashboard']:8.3f} s", flush=True)

        def page(offset: int) -> float:
            where, params = where_clause(Filters())
            order = order_clause("exit_time", True)
            seconds, _ = timed(lambda: store.query_page(where, params, order, 200, offset))
            return seconds

        total = store.count_trades()
        result["page_first"] = measure("page_first", lambda: page(0))
        result["page_middle"] = measure("page_middle", lambda: page(max(0, total // 2)))

        def simulate() -> float:
            fresh = AnalysisEngine(store)
            seconds, _ = timed(lambda: fresh.simulate(Filters(), RULE, SIMULATOR_RESAMPLES, 42))
            return seconds

        coach_engine = AnalysisEngine(store)
        coach_engine.trades_for(Filters())  # the server keeps the loaded frame
        coach_service = CoachService(store, coach_engine)
        result["coach_report"] = measure(
            "coach_report",
            lambda: timed(lambda: coach_service.report(Filters(), force=True))[0],
        )
        print(f"  coach report       {result['coach_report']:8.3f} s", flush=True)

        result["simulator"] = measure("simulator", simulate)
        print(f"  simulator          {result['simulator']:8.3f} s", flush=True)

        def cold_response() -> float:
            fresh = AnalysisEngine(store)
            started = time.perf_counter()
            fresh.dashboard_bytes(Filters())
            return time.perf_counter() - started

        result["dashboard_response"] = measure("dashboard_response", cold_response)

        pnl = prepare(store.load_frame(), Filters()).frame["pnl"].to_numpy()

        def monte_carlo_run() -> float:
            seconds, _ = timed(lambda: monte_carlo(pnl, 5000, 42, 10_000.0, 2_000.0, 1_000.0))
            return seconds

        result["monte_carlo_5000"] = measure("monte_carlo_5000", monte_carlo_run)
        print(f"  monte carlo 5,000  {result['monte_carlo_5000']:8.3f} s", flush=True)
    finally:
        store.close()
    return result


def bundle_sizes(dist: Path) -> dict[str, Any] | None:
    """Gzip size of the JavaScript the browser loads before the first screen."""
    index = dist / "index.html"
    if not index.exists():
        return None
    html = index.read_text(encoding="utf-8")
    hrefs = re.findall(r'(?:src|href)="(/assets/[^"]+\.js)"', html)
    files = [dist / href.lstrip("/") for href in hrefs]
    chunks: dict[str, int] = {}
    total_raw = 0
    total_gzip = 0
    for file in files:
        if not file.exists():
            continue
        raw = file.read_bytes()
        gz = len(gzip.compress(raw, compresslevel=9))
        chunks[file.name] = gz
        total_raw += len(raw)
        total_gzip += gz
    return {"initial_js_gzip": total_gzip, "initial_js_raw": total_raw, "chunks": chunks}


def _wait_for(url: str, seconds: int = 60) -> None:
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2):  # noqa: S310 - local URL only
                return
        except OSError:
            time.sleep(0.5)
    raise SystemExit(f"timed out waiting for {url}")


def browser_measurements(size: int) -> dict[str, Any] | None:
    """Start the API on a scratch data folder, load the dataset, and run the browser script."""
    if size not in DATASETS or not DATASETS[size].exists():
        return None
    for port in (8000, 5173):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                raise SystemExit(
                    f"port {port} is already in use. Stop the running server before measuring."
                )
        except OSError:
            pass
    scratch = Path(tempfile.mkdtemp(prefix="ledger-ui-"))
    env = {**os.environ, "LEDGER_DATA_DIR": str(scratch / "data")}
    api = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "obsidian_ledger.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
        ],
        env=env,
        cwd=ROOT,
    )
    preview = None
    try:
        _wait_for("http://127.0.0.1:8000/health")
        body = DATASETS[size].read_bytes()
        request = urllib.request.Request(
            f"http://127.0.0.1:8000/api/imports/preview?filename={DATASETS[size].name}",
            data=body,
            method="POST",
            headers={"Content-Type": "text/csv"},
        )
        with urllib.request.urlopen(request, timeout=900) as response:  # noqa: S310
            preview_id = json.loads(response.read())["preview_id"]
        commit = urllib.request.Request(
            f"http://127.0.0.1:8000/api/imports/{preview_id}/commit",
            data=b"{}",
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(commit, timeout=900):  # noqa: S310
            pass
        preview = subprocess.Popen(
            [
                "node",
                str(ROOT / "web" / "node_modules" / "vite" / "bin" / "vite.js"),
                "preview",
                "--host",
                "127.0.0.1",
                "--port",
                "5173",
            ],
            cwd=ROOT / "web",
            stdout=subprocess.DEVNULL,
        )
        _wait_for("http://127.0.0.1:5173/")
        completed = subprocess.run(
            ["node", "web/scripts/bench-ui.mjs", "http://127.0.0.1:5173/"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=900,
            check=False,
        )
        if completed.returncode != 0:
            print(completed.stderr, file=sys.stderr)
            return None
        return json.loads(completed.stdout.strip().splitlines()[-1])
    finally:

        def stop(process: subprocess.Popen[Any] | None) -> None:
            if process is not None and process.poll() is None:
                subprocess.run(
                    [
                        "powershell",
                        "-NoProfile",
                        "-Command",
                        f"Stop-Process -Id {process.pid}",
                    ],
                    capture_output=True,
                    check=True,
                )
                process.wait(timeout=15)

        try:
            stop(preview)
        finally:
            try:
                stop(api)
            finally:
                shutil.rmtree(scratch)


def _ui_summary(label: str, ui: dict[str, Any]) -> str:
    """One line for the browser run. Measures a run did not record are left out, not shown as 0."""
    parts = [
        f"table scroll {ui['scroll_fps']:.1f} fps, p95 frame {ui['scroll_p95_frame_ms']:.1f} ms"
    ]
    if "scroll_ceiling_fps" in ui:
        parts.append(
            f"an empty scroll container reaches {ui['scroll_ceiling_fps']:.1f} fps in this "
            "headless browser, which is the most any page can show here"
        )
    if "main_thread_ms_per_frame" in ui:
        parts.append(
            f"main-thread work is {ui['main_thread_ms_per_frame']:.1f} ms per scrolled frame "
            "against a 16.7 ms budget"
        )
    if "rows_loaded" in ui:
        parts.append(
            f"{ui['rows_loaded']} of {ui['rows_on_screen']} visible rows held real data after "
            "scrolling"
        )
    else:
        parts.append(
            "this run scrolled over placeholder rows, because the table only loaded its first "
            "block, so its fps does not describe real rows"
        )
    parts.append(
        f"dashboard ready {ui['dashboard_ready_s']:.2f} s, "
        f"filter to ready {ui['filter_ready_s']:.2f} s"
    )
    return f"- {label}: browser (10k rows): " + "; ".join(parts)


def render_results(labels: list[str]) -> None:
    """Build RESULTS.md from every bench-<label>.json present."""
    runs: dict[str, dict[str, Any]] = {}
    for label in labels:
        path = OUT / f"bench-{label}.json"
        if path.exists():
            runs[label] = json.loads(path.read_text(encoding="utf-8"))
    if not runs:
        return
    lines = ["# Benchmark results", ""]
    first = runs.get("latest", next(iter(runs.values())))
    lines += ["## Machine", ""]
    for key, value in first["machine"].items():
        lines.append(f"- {key}: {value}")
    run_counts = {
        label: max((size.get("runs", 0) for size in run["sizes"]), default=0)
        for label, run in runs.items()
    }
    lines += [
        "",
        "Cells show the median in seconds and, when recorded, the min–max range. "
        "Run counts are shown in each column header; older labels retain their original counts.",
        "",
    ]

    def cell(
        label: str,
        rows: int,
        getter: Callable[[dict[str, Any]], Any],
        range_key: str,
    ) -> str:
        run = runs.get(label)
        if run is None:
            return "n/a"
        size = next((s for s in run["sizes"] if s["rows"] == rows), None)
        if size is None:
            return "n/a"
        try:
            value = getter(size)
        except KeyError:  # a run from before this measure existed
            return "n/a"
        if value is None:
            return "n/a"
        if isinstance(value, str):
            return value
        bounds = size.get("ranges", {}).get(range_key)
        if bounds:
            return f"{value:.3f} s ({bounds['min']:.3f}–{bounds['max']:.3f})"
        return f"{value:.3f} s"

    metrics: list[tuple[str, Callable[[dict[str, Any]], Any], str]] = [
        ("Ingest total", lambda s: s["ingest"]["total"], "ingest.total"),
        ("  analyze", lambda s: s["ingest"]["analyze"], "ingest.analyze"),
        ("  process rows", lambda s: s["ingest"]["process rows"], "ingest.process rows"),
        ("  insert trades", lambda s: s["ingest"]["insert trades"], "ingest.insert trades"),
        ("Dashboard, cold", lambda s: s["dashboard_cold"], "dashboard_cold"),
        (
            "Dashboard response (JSON + gzip), cold",
            lambda s: s["dashboard_response"],
            "dashboard_response",
        ),
        ("Dashboard, cached", lambda s: s["dashboard_cached"], "dashboard_cached"),
        (
            "Filter change (dashboard, warm frame)",
            lambda s: s["filter_change_dashboard"],
            "filter_change_dashboard",
        ),
        (
            "Filter change (segments, warm frame)",
            lambda s: s["filter_change_segments"],
            "filter_change_segments",
        ),
        ("Trades page, first", lambda s: s["page_first"], "page_first"),
        ("Trades page, middle", lambda s: s["page_middle"], "page_middle"),
        ("Coach report, warm frame", lambda s: s["coach_report"], "coach_report"),
        ("Simulator, one rule", lambda s: s["simulator"], "simulator"),
        ("Monte Carlo, 5,000 paths", lambda s: s["monte_carlo_5000"], "monte_carlo_5000"),
    ]
    labels_shown = list(runs.keys())
    for rows in SIZES:
        if not any(any(s["rows"] == rows for s in run["sizes"]) for run in runs.values()):
            continue
        lines += [f"## {rows:,} trades", ""]
        header = "| Measure | " + " | ".join(
            f"{label} ({run_counts[label]} runs)" for label in labels_shown
        ) + " |"
        lines += [header, "|" + "---|" * (len(labels_shown) + 1)]
        for name, getter, range_key in metrics:
            row = [cell(label, rows, getter, range_key) for label in labels_shown]
            lines.append(f"| {name} | " + " | ".join(row) + " |")
        lines.append("")

    lines += ["## Payload and bundle", ""]
    for label, run in runs.items():
        payload = {s["rows"]: s.get("dashboard_bytes") for s in run["sizes"]}
        lines.append(
            f"- {label}: dashboard payload gzip by size: "
            + ", ".join(
                f"{rows:,} rows {value['gzip'] / 1024:.1f} kB"
                for rows, value in payload.items()
                if value
            )
        )
        bundle = run.get("bundle")
        if bundle:
            lines.append(
                f"- {label}: initial JavaScript {bundle['initial_js_gzip'] / 1024:.1f} kB gzip "
                f"({bundle['initial_js_raw'] / 1024:.1f} kB raw)"
            )
        ui = run.get("ui")
        if ui:
            lines.append(_ui_summary(label, ui))
    (BENCH / "RESULTS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--label", required=True, help="Name for this run, for example before or after."
    )
    parser.add_argument("--sizes", default=",".join(str(size) for size in SIZES))
    parser.add_argument(
        "--ui", action="store_true", help="Also measure the browser (needs pnpm -C web build)."
    )
    args = parser.parse_args(list(argv))
    sizes = [int(item) for item in args.sizes.split(",") if item.strip()]
    unknown = [size for size in sizes if size not in DATASETS]
    if unknown:
        raise SystemExit(f"sizes must be drawn from {list(SIZES)}; got {unknown}")
    OUT.mkdir(parents=True, exist_ok=True)
    ensure_datasets(sizes)

    report: dict[str, Any] = {"label": args.label, "machine": machine_specs(), "sizes": []}
    with tempfile.TemporaryDirectory(prefix="ledger-bench-") as scratch_name:
        scratch = Path(scratch_name)
        for size in sizes:
            report["sizes"].append(measure_size(size, scratch))

    dist = ROOT / "web" / "dist"
    report["bundle"] = bundle_sizes(dist)
    if args.ui:
        print(f"\n== browser measurements ({BROWSER_SIZE:,} rows)", flush=True)
        report["ui"] = browser_measurements(BROWSER_SIZE)

    (OUT / f"bench-{args.label}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    render_results(["before", "after", args.label])
    print(f"\nwrote {OUT / f'bench-{args.label}.json'} and benchmarks/RESULTS.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
