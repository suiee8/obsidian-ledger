"""Behavioral patterns: streaks, after-win and after-loss results, revenge, overtrading,
disposition, exit efficiency, and plan adherence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import numpy.typing as npt
import polars as pl

Array = npt.NDArray[np.float64]


def _mean(values: Array) -> float | None:
    return float(values.mean()) if values.size else None


def _streaks(outcomes: Array) -> dict[str, Any]:
    """Longest winning and losing streaks in exit order, and the current streak."""
    longest_win = longest_loss = run = 0
    sign = 0
    for value in outcomes:
        current = 1 if value > 0 else -1 if value < 0 else 0
        if current == 0:
            run = 0
            sign = 0
            continue
        run = run + 1 if current == sign else 1
        sign = current
        if sign > 0:
            longest_win = max(longest_win, run)
        else:
            longest_loss = max(longest_loss, run)
    current_kind = "win" if sign > 0 else "loss" if sign < 0 else None
    return {
        "longest_win_streak": longest_win,
        "longest_loss_streak": longest_loss,
        "current_streak": {"kind": current_kind, "length": run if sign else 0},
    }


@dataclass(frozen=True)
class PriorContext:
    """For each trade in entry order, the most recent trade that had closed before it entered.

    Overlapping trades are ignored: a trade still open at entry is not the "previous" trade.
    Arrays are aligned with `by_entry`.
    """

    by_entry: pl.DataFrame
    has_previous: npt.NDArray[np.bool_]
    prev_pnl: Array
    prev_qty: Array
    gap_minutes: Array


def prior_context(frame: pl.DataFrame) -> PriorContext:
    by_exit = frame.sort(["exit_time", "trade_key"])
    pnl_exit = by_exit["pnl"].to_numpy()
    qty_exit = by_exit["qty"].to_numpy()
    exit_seconds = by_exit["exit_time"].dt.epoch("s").to_numpy().astype(np.float64)
    by_entry = frame.sort(["entry_time", "trade_key"])
    entry_seconds = by_entry["entry_time"].dt.epoch("s").to_numpy().astype(np.float64)
    previous = np.searchsorted(exit_seconds, entry_seconds, side="right") - 1
    has_previous = previous >= 0
    prev_index = np.where(has_previous, previous, 0)
    return PriorContext(
        by_entry=by_entry,
        has_previous=has_previous,
        prev_pnl=np.where(has_previous, pnl_exit[prev_index], np.nan),
        prev_qty=np.where(has_previous, qty_exit[prev_index], np.nan),
        gap_minutes=np.where(
            has_previous, (entry_seconds - exit_seconds[prev_index]) / 60.0, np.nan
        ),
    )


def revenge_mask(
    context: PriorContext, gap_minutes: float, size_jump: float
) -> npt.NDArray[np.bool_]:
    """Boolean mask (aligned with context.by_entry) of trades that look like revenge trades.

    A trade after a loss is flagged when it re-enters within `gap_minutes` of the loss, or is
    at least `size_jump` larger in quantity than the losing trade.
    """
    qty = context.by_entry["qty"].to_numpy()
    after_loss = context.has_previous & (context.prev_pnl < 0)
    jump = after_loss & (qty >= context.prev_qty * (1 + size_jump))
    quick = after_loss & (context.gap_minutes <= gap_minutes)
    return np.asarray(jump | quick, dtype=bool)


def analyze_behavior(
    frame: pl.DataFrame,
    overtrading_threshold: int,
    revenge_gap_minutes: float,
    size_jump: float,
) -> dict[str, Any]:
    """Behavior metrics for a filtered frame. Every rate states the count it is based on."""
    count = frame.height
    if count == 0:
        return {"trades": 0}

    by_exit = frame.sort(["exit_time", "trade_key"])
    pnl_exit = by_exit["pnl"].to_numpy()
    result: dict[str, Any] = {"trades": count, **_streaks(pnl_exit)}

    context = prior_context(frame)
    by_entry = context.by_entry
    pnl = by_entry["pnl"].to_numpy()
    qty = by_entry["qty"].to_numpy()
    has_previous = context.has_previous
    prev_pnl = context.prev_pnl
    prev_qty = context.prev_qty
    gap_minutes = context.gap_minutes

    after_win = has_previous & (prev_pnl > 0)
    after_loss = has_previous & (prev_pnl < 0)
    result["after_win"] = {
        "trades": int(after_win.sum()),
        "win_rate": hit_rate(pnl[after_win] > 0, pnl[after_win] != 0),
        "expectancy": _mean(pnl[after_win]),
    }
    result["after_loss"] = {
        "trades": int(after_loss.sum()),
        "win_rate": hit_rate(pnl[after_loss] > 0, pnl[after_loss] != 0),
        "expectancy": _mean(pnl[after_loss]),
    }

    jump = after_loss & (qty >= prev_qty * (1 + size_jump))
    quick = after_loss & (gap_minutes <= revenge_gap_minutes)
    revenge = jump | quick
    result["revenge"] = {
        "flagged_trades": int(revenge.sum()),
        "after_loss_trades": int(after_loss.sum()),
        "rate_after_loss": float(revenge.sum() / after_loss.sum()) if after_loss.sum() else None,
        "net_pnl_of_flagged": float(pnl[revenge].sum()) if revenge.any() else 0.0,
        "rule": (
            f"A trade after a loss is flagged when it re-enters within {revenge_gap_minutes:g} "
            f"minutes of the loss, or is at least {size_jump:.0%} larger in quantity."
        ),
    }

    per_day = by_entry.group_by("entry_day").agg(pl.len().alias("trades"), pl.col("pnl").sum())
    heavy = per_day.filter(pl.col("trades") > overtrading_threshold)
    heavy_days = set(heavy["entry_day"].to_list())
    day_flag = np.array([day in heavy_days for day in by_entry["entry_day"].to_list()], dtype=bool)
    result["overtrading"] = {
        "threshold_trades_per_day": overtrading_threshold,
        "days": per_day.height,
        "overtraded_days": heavy.height,
        "avg_pnl_per_trade_overtraded": _mean(pnl[day_flag]),
        "avg_pnl_per_trade_other": _mean(pnl[~day_flag]),
        "net_pnl_overtraded_days": float(heavy["pnl"].sum()) if heavy.height else 0.0,
    }

    winners = pnl_exit > 0
    losers = pnl_exit < 0
    holding = by_exit["holding_seconds"].to_numpy()
    win_hold = _mean(holding[winners])
    loss_hold = _mean(holding[losers])
    result["disposition"] = {
        "avg_holding_winners_seconds": win_hold,
        "avg_holding_losers_seconds": loss_hold,
        "losers_to_winners_ratio": loss_hold / win_hold
        if win_hold and loss_hold is not None
        else None,
    }

    mfe = by_exit["mfe"].to_numpy()
    mae = by_exit["mae"].to_numpy()
    capture_mask = winners & np.isfinite(mfe) & (mfe > 0)
    result["exit_efficiency"] = {
        "winners_with_mfe": int(capture_mask.sum()),
        "avg_capture_ratio": _mean(pnl_exit[capture_mask] / mfe[capture_mask]),
        "avg_left_on_table": _mean(mfe[capture_mask] - pnl_exit[capture_mask]),
        "losers_with_mae": int((losers & np.isfinite(mae)).sum()),
        "avg_adverse_excursion_losers": _mean(np.abs(mae[losers & np.isfinite(mae)])),
    }

    plan = by_exit["plan_followed"].to_numpy()
    known = by_exit["plan_followed"].is_not_null().to_numpy()
    followed = known & (plan == 1)
    broke = known & (plan == 0)
    result["plan"] = {
        "known_trades": int(known.sum()),
        "adherence_rate": float(followed.sum() / known.sum()) if known.any() else None,
        "rule_breaking_trades": int(broke.sum()),
        "rule_breaking_net_pnl": float(pnl_exit[broke].sum()) if broke.any() else 0.0,
        "expectancy_followed": _mean(pnl_exit[followed]),
        "expectancy_broke": _mean(pnl_exit[broke]),
    }
    return result


def hit_rate(hits: npt.NDArray[np.bool_], decided: npt.NDArray[np.bool_]) -> float | None:
    denominator = int(decided.sum())
    return float(hits.sum()) / denominator if denominator else None
