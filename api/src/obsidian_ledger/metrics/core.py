"""Core performance metrics: win rate, payoff, profit factor, expectancy, and period extremes."""

from __future__ import annotations

from typing import Any, Final

import numpy as np
import numpy.typing as npt
import polars as pl

Array = npt.NDArray[np.float64]
TRADING_DAYS: Final = 252


def core_metrics(pnl: Array, costs: Array, r: Array) -> dict[str, Any]:
    """Metrics that need only trade outcomes.

    Flat trades (P&L exactly zero) are counted in the trade total but not in win rate.
    Costs are signed (negative is a cost). Gross P&L is net minus costs.
    """
    count = int(pnl.size)
    if count == 0:
        return {"trades": 0}
    wins = pnl > 0
    losses = pnl < 0
    win_count = int(wins.sum())
    loss_count = int(losses.sum())
    decided = win_count + loss_count
    gross_win = float(pnl[wins].sum())
    gross_loss = float(-pnl[losses].sum())
    avg_win = float(pnl[wins].mean()) if win_count else None
    avg_loss = float(-pnl[losses].mean()) if loss_count else None
    finite_r = r[np.isfinite(r)]
    gross_total = float(pnl.sum() - costs.sum())
    costs_total = float(costs.sum())
    return {
        "trades": count,
        "wins": win_count,
        "losses": loss_count,
        "flat": count - decided,
        "net_pnl": float(pnl.sum()),
        "gross_pnl": gross_total,
        "costs": costs_total,
        "win_rate": win_count / decided if decided else None,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "payoff_ratio": avg_win / avg_loss if avg_win is not None and avg_loss else None,
        "profit_factor": gross_win / gross_loss if gross_loss > 0 else None,
        "expectancy": float(pnl.mean()),
        "expectancy_r": float(finite_r.mean()) if finite_r.size else None,
        "r_trades": int(finite_r.size),
        "median_trade": float(np.median(pnl)),
        "largest_win": float(pnl.max()),
        "largest_loss": float(pnl.min()),
        "fee_drag": abs(costs_total) / abs(gross_total) if gross_total != 0 else None,
    }


def period_extremes(frame: pl.DataFrame) -> dict[str, Any]:
    """Best and worst day, week, and month by net P&L, grouped on exit date in UTC."""
    if frame.height == 0:
        return {}
    days = frame.group_by("exit_day").agg(pl.col("pnl").sum().alias("pnl"))
    weeks = (
        frame.with_columns(pl.col("exit_time").dt.truncate("1w").alias("period"))
        .group_by("period")
        .agg(pl.col("pnl").sum())
    )
    months = (
        frame.with_columns(pl.col("exit_time").dt.truncate("1mo").alias("period"))
        .group_by("period")
        .agg(pl.col("pnl").sum())
    )
    result: dict[str, Any] = {}
    for name, table, key in (
        ("day", days, "exit_day"),
        ("week", weeks, "period"),
        ("month", months, "period"),
    ):
        ordered = table.sort("pnl")
        worst = ordered.row(0, named=True)
        best = ordered.row(-1, named=True)
        result[name] = {
            "best": {"period": str(best[key]), "pnl": float(best["pnl"])},
            "worst": {"period": str(worst[key]), "pnl": float(worst["pnl"])},
            "periods": ordered.height,
        }
    return result
