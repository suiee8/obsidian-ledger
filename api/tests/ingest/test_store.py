"""Store behaviour: idempotent merge and the window-function view."""

from pathlib import Path

import pytest

from obsidian_ledger.ingest.analysis import analyze
from obsidian_ledger.ingest.options import ImportOptions
from obsidian_ledger.ingest.run import run_import
from obsidian_ledger.store.db import Store

HEADER = "trade_id,symbol,side,entry_time,exit_time,qty,entry_price,exit_price,net_pnl"

# Net P&L sequence: win, loss, loss, loss, win. Quantities change so size_change has values.
ROWS = [
    ("1", "2026-01-06T10:00:00Z", "2026-01-06T11:00:00Z", "10", "10"),
    ("2", "2026-01-07T10:00:00Z", "2026-01-07T11:00:00Z", "-5", "20"),
    ("3", "2026-01-08T10:00:00Z", "2026-01-08T11:00:00Z", "-5", "20"),
    ("4", "2026-01-09T10:00:00Z", "2026-01-09T11:00:00Z", "-5", "10"),
    ("5", "2026-01-12T10:00:00Z", "2026-01-12T11:00:00Z", "10", "10"),
]


def _write(
    tmp_path: Path, name: str = "series.csv", rows: list[tuple[str, str, str, str, str]] = ROWS
) -> Path:
    lines = [HEADER]
    for trade, entry, exit_time, net, qty in rows:
        lines.append(f"{trade},AAPL,long,{entry},{exit_time},{qty},100,101,{net}")
    path = tmp_path / name
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _import(store: Store, path: Path, **options: object) -> tuple[int, int]:
    opts = ImportOptions.model_validate(options)
    analysis = analyze(path, opts)
    outcome = run_import(analysis, opts)
    import_id = f"test{path.name}{len(outcome.trades)}"
    return store.insert_trades(import_id, outcome.trades, opts.base_currency)


def test_loss_streaks_equity_drawdown_and_size_change(tmp_path: Path) -> None:
    store = Store(tmp_path / "data")
    try:
        store.set_setting("starting_equity", "1000.0")
        inserted, present = _import(store, _write(tmp_path))
        assert (inserted, present) == (5, 0)
        rows = store.list_trades(100, 0)
        assert [row["loss_streak"] for row in rows] == [0, 1, 2, 3, 0]
        assert [bool(row["loss_streak_flag"]) for row in rows] == [False, False, False, True, False]
        assert [row["equity"] for row in rows] == pytest.approx([1010, 1005, 1000, 995, 1005])
        assert [row["drawdown"] for row in rows] == pytest.approx([0, -5, -10, -15, -5])
        assert rows[0]["size_change"] is None
        assert [row["size_change"] for row in rows[1:]] == pytest.approx([1.0, 0.0, -0.5, 0.0])
        assert rows[0]["risk_pct"] is None  # no planned risk in this file
    finally:
        store.close()


def test_reimport_of_the_same_file_adds_nothing(tmp_path: Path) -> None:
    store = Store(tmp_path / "data")
    try:
        path = _write(tmp_path)
        assert _import(store, path) == (5, 0)
        assert _import(store, path) == (0, 5)
        assert store.count_trades() == 5
    finally:
        store.close()


def test_merging_an_overlapping_file_only_adds_new_trades(tmp_path: Path) -> None:
    store = Store(tmp_path / "data")
    try:
        assert _import(store, _write(tmp_path, "first.csv", ROWS[:3])) == (3, 0)
        assert _import(store, _write(tmp_path, "second.csv", ROWS[1:])) == (2, 2)
        assert store.count_trades() == 5
    finally:
        store.close()


def test_equity_is_recomputed_when_a_later_file_adds_earlier_trades(tmp_path: Path) -> None:
    store = Store(tmp_path / "data")
    try:
        store.set_setting("starting_equity", "100.0")
        _import(store, _write(tmp_path, "late.csv", ROWS[4:]))
        _import(store, _write(tmp_path, "early.csv", ROWS[:4]))
        rows = store.list_trades(100, 0)
        assert rows[-1]["equity"] == pytest.approx(105.0 + 0.0)
        assert [row["loss_streak"] for row in rows] == [0, 1, 2, 3, 0]
    finally:
        store.close()


def test_templates_round_trip(tmp_path: Path) -> None:
    store = Store(tmp_path / "data")
    try:
        store.save_template("abc", "My broker", {"Ticket": "trade_id", "Notes": None})
        assert store.get_template("abc") == {"Ticket": "trade_id", "Notes": None}
        assert store.get_template("missing") is None
    finally:
        store.close()
