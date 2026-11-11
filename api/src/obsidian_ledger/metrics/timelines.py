"""Daily revenge, tilt, and overtrading timelines, and performance after a loss.

These reuse the detectors in behavior.py (`prior_context`, `revenge_mask`) and the same default
thresholds as the Discipline Score, so the timelines agree with the score's components.
"""

from __future__ import annotations

from typing import Any, Final

import numpy as np
import polars as pl

from obsidian_ledger.metrics.behavior import hit_rate, prior_context, revenge_mask

TILT_LOSSES: Final = 3


def _group(label: str, key: str, mask: np.ndarray, pnl: np.ndarray) -> dict[str, Any]:
    chosen = pnl[mask]
    return {
        "key": key,
        "label": label,
        "trades": int(mask.sum()),
        "win_rate": hit_rate(chosen > 0, chosen != 0),
        "expectancy": float(chosen.mean()) if chosen.size else None,
        "net_pnl": float(chosen.sum()) if chosen.size else 0.0,
    }


def behavior_timeline(
    frame: pl.DataFrame,
    *,
    overtrading_threshold: int,
    revenge_gap_minutes: float,
    size_jump: float,
    tilt_losses: int = TILT_LOSSES,
) -> dict[str, Any]:
    if frame.height == 0:
        return {"trades": 0, "days": []}

    by_exit = frame.sort(["exit_time", "trade_key"])
    pnl_exit = by_exit["pnl"].to_numpy().astype(np.float64)
    exit_day = by_exit["exit_day"].dt.epoch("d").to_numpy().astype(np.int64)
    exit_seconds = by_exit["exit_time"].dt.epoch("s").to_numpy().astype(np.float64)

    # Consecutive losses ending at each exit, restarted every day.
    run = 0
    last_day = -1
    streak = np.zeros(by_exit.height, dtype=np.int64)
    for i, (day, value) in enumerate(zip(exit_day.tolist(), pnl_exit.tolist(), strict=True)):
        if day != last_day:
            run, last_day = 0, day
        run = run + 1 if value < 0 else 0
        streak[i] = run

    context = prior_context(frame)
    entry = context.by_entry
    entry_seconds = entry["entry_time"].dt.epoch("s").to_numpy().astype(np.float64)
    entry_day = entry["entry_day"].dt.epoch("d").to_numpy().astype(np.int64)
    previous = np.searchsorted(exit_seconds, entry_seconds, side="right") - 1
    has_previous = previous >= 0
    safe = np.where(has_previous, previous, 0)
    same_day = has_previous & (exit_day[safe] == entry_day)
    tilt = same_day & (streak[safe] >= tilt_losses)

    revenge = revenge_mask(context, revenge_gap_minutes, size_jump)
    pnl = entry["pnl"].to_numpy().astype(np.float64)
    after_loss = context.has_previous & (context.prev_pnl < 0)
    after_win = context.has_previous & (context.prev_pnl > 0)

    table = pl.DataFrame(
        {
            "day": entry["entry_day"],
            "pnl": pnl,
            "revenge": revenge.astype(np.int64),
            "revenge_pnl": np.where(revenge, pnl, 0.0),
            "tilt": tilt.astype(np.int64),
            "tilt_pnl": np.where(tilt, pnl, 0.0),
        }
    )
    per_day = (
        table.group_by("day")
        .agg(
            pl.len().alias("trades"),
            pl.col("pnl").sum().alias("pnl"),
            pl.col("revenge").sum().alias("revenge"),
            pl.col("revenge_pnl").sum().alias("revenge_pnl"),
            pl.col("tilt").sum().alias("tilt"),
            pl.col("tilt_pnl").sum().alias("tilt_pnl"),
        )
        .sort("day")
    )
    days = [
        {
            "day": row["day"].isoformat(),
            "trades": int(row["trades"]),
            "pnl": float(row["pnl"]),
            "revenge": int(row["revenge"]),
            "revenge_pnl": float(row["revenge_pnl"]),
            "tilt": int(row["tilt"]),
            "tilt_pnl": float(row["tilt_pnl"]),
            "overtraded": int(row["trades"]) > overtrading_threshold,
        }
        for row in per_day.iter_rows(named=True)
    ]
    calm = after_loss & ~revenge & ~tilt
    return {
        "trades": int(frame.height),
        "days": days,
        "thresholds": {
            "overtrading_trades_per_day": overtrading_threshold,
            "revenge_gap_minutes": revenge_gap_minutes,
            "revenge_size_jump": size_jump,
            "tilt_losses": tilt_losses,
        },
        "rules": {
            "revenge": (
                f"A trade after a loss, re-entered within {revenge_gap_minutes:g} minutes or "
                f"at least {size_jump:.0%} larger."
            ),
            "tilt": (
                f"A trade entered after {tilt_losses} or more losing trades in a row "
                "earlier the same day."
            ),
            "overtrading": f"A day with more than {overtrading_threshold} trades.",
        },
        "totals": {
            "revenge_trades": int(revenge.sum()),
            "tilt_trades": int(tilt.sum()),
            "overtraded_days": sum(1 for d in days if d["overtraded"]),
            "days": len(days),
        },
        "post_loss": [
            _group("After a win", "after_win", after_win, pnl),
            _group("After a loss, calm", "after_loss_calm", calm, pnl),
            _group("After a loss, revenge-style", "revenge", revenge, pnl),
            _group("After a losing streak (tilt)", "tilt", tilt, pnl),
        ],
    }
