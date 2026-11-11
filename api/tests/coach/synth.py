"""Synthetic journals for Coach tests.

`planted` hides three leaks in an otherwise random journal: revenge re-entries, a losing entry
hour, and overtrading days. Symbol, setup, side, session, and hold time are drawn independently
of the result. Quantity is not: revenge re-entries are double size by design, so the size bucket
is confounded with them and can show up as a true but derived finding.

`noise` is pure noise: every result is drawn from the same distribution whatever the trade does.
"""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np

from obsidian_ledger.ingest.analysis import analyze
from obsidian_ledger.ingest.options import ImportOptions
from obsidian_ledger.ingest.run import run_import
from obsidian_ledger.store.db import Store

HEADER = [
    "trade_id",
    "account",
    "symbol",
    "asset_class",
    "side",
    "entry_time",
    "exit_time",
    "qty",
    "entry_price",
    "exit_price",
    "fees",
    "planned_risk",
    "r_multiple",
    "net_pnl",
    "currency",
    "setup",
    "session",
    "emotion",
    "plan_followed",
    "notes",
]
SYMBOLS = ("AAA", "BBB", "CCC", "DDD")
SETUPS = ("breakout", "pullback", "range")
SESSIONS = ("asia", "london", "new_york")
RISK = 100.0
LOSING_HOUR = 14
PLANTED_IDS = {"beh~revenge", "beh~overtrading", f"seg~hour~{LOSING_HOUR}"}


def _row(
    rng: np.random.Generator,
    number: int,
    entry: datetime,
    hold_min: int,
    qty: int,
    pnl: float,
    account: str,
) -> list[str]:
    side = "long" if rng.random() < 0.5 else "short"
    entry_price = 100.0
    move = (pnl + 1.0) / qty  # gross P&L = net + the 1.00 fee
    exit_price = entry_price + move if side == "long" else entry_price - move
    exit_time = entry + timedelta(minutes=hold_min)
    return [
        f"T{number:06d}",
        account,
        str(rng.choice(SYMBOLS)),
        "equity",
        side,
        entry.strftime("%Y-%m-%dT%H:%M:%SZ"),
        exit_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        str(qty),
        f"{entry_price:.4f}",
        f"{exit_price:.4f}",
        "1.00",
        f"{RISK:.2f}",
        f"{pnl / RISK:.6f}",
        f"{pnl:.2f}",
        "USD",
        str(rng.choice(SETUPS)),
        str(rng.choice(SESSIONS)),
        "calm",
        "true",
        "",
    ]


def _write(rows: list[list[str]]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(HEADER)
    writer.writerows(rows)
    return buffer.getvalue()


def planted(seed: int = 7, days: int = 170) -> str:
    """A journal with revenge re-entries, a losing hour (14:00 UTC), and overtrading days."""
    rng = np.random.default_rng(seed)
    start = datetime(2024, 1, 2, tzinfo=UTC)
    weekdays = [
        start + timedelta(days=i)
        for i in range(days * 2)
        if (start + timedelta(days=i)).weekday() < 5
    ][:days]
    picks = [int(i) for i in rng.choice(days, size=min(8, days // 20), replace=False)]
    heavy = {weekdays[i] for i in picks}
    rows: list[list[str]] = []
    number = 0
    for day in weekdays:
        is_heavy = day in heavy
        clock = day + timedelta(hours=7 if is_heavy else 8, minutes=int(rng.integers(0, 25)))
        wanted = 18 if is_heavy else int(rng.integers(6, 10))
        revenge = False
        for _ in range(wanted):
            if clock.hour >= 18:
                break
            qty = 24 if revenge else int(rng.choice([8, 10, 12]))
            if revenge:
                mean = -80.0
            elif is_heavy:
                mean = -45.0
            elif clock.hour == LOSING_HOUR:
                mean = -70.0
            else:
                mean = 6.0
            pnl = float(rng.normal(mean, RISK))
            hold = int(rng.integers(10, 31))
            number += 1
            rows.append(_row(rng, number, clock, hold, qty, pnl, "main"))
            # After a loss on a normal day, half the time the next entry is a quick, larger one.
            revenge = pnl < 0 and not is_heavy and bool(rng.random() < 0.5)
            if revenge:
                gap = int(rng.integers(2, 7))
            elif is_heavy:
                gap = int(rng.integers(6, 16))
            else:
                gap = int(rng.integers(25, 61))
            clock = clock + timedelta(minutes=hold + gap)
    return _write(rows)


def noise(seed: int = 11, days: int = 160) -> str:
    """Results drawn from one distribution no matter what the trade looks like."""
    rng = np.random.default_rng(seed)
    start = datetime(2024, 1, 2, tzinfo=UTC)
    weekdays = [
        start + timedelta(days=i)
        for i in range(days * 2)
        if (start + timedelta(days=i)).weekday() < 5
    ][:days]
    rows: list[list[str]] = []
    number = 0
    for day in weekdays:
        clock = day + timedelta(hours=8, minutes=int(rng.integers(0, 30)))
        for _ in range(int(rng.integers(3, 8))):
            if clock.hour >= 18:
                break
            hold = int(rng.integers(10, 31))
            number += 1
            rows.append(
                _row(
                    rng,
                    number,
                    clock,
                    hold,
                    int(rng.choice([10, 10, 20])),
                    float(rng.normal(0.0, RISK)),
                    "noise",
                )
            )
            clock = clock + timedelta(minutes=hold + int(rng.integers(5, 91)))
    return _write(rows)


def load(tmp_path: Path, text: str) -> Store:
    """Import CSV text through the real pipeline into a fresh store."""
    source = tmp_path / "journal.csv"
    source.write_text(text, encoding="utf-8")
    options = ImportOptions()
    analysis = analyze(source, options)
    assert not analysis.blocking, [question.id for question in analysis.blocking]
    outcome = run_import(analysis, options)
    store = Store(tmp_path / "data")
    store.insert_frame("synthetic", outcome.frame, options.base_currency)
    return store
