"""Risk and return: equity, drawdown, daily-return ratios, SQN, Kelly bound, and risk per trade."""

from __future__ import annotations

from typing import Any, Final

import numpy as np
import numpy.typing as npt

Array = npt.NDArray[np.float64]
TRADING_DAYS: Final = 252


def drawdown(pnl: Array, start_equity: float | None) -> dict[str, Any]:
    """Maximum drawdown with depth, duration, and recovery, all in trades.

    The equity path starts at the starting equity (or zero when none was given) and adds
    each trade's P&L in exit order. Depth is reported as a percentage only when a starting
    equity is known, because a percentage of a P&L path from zero has no meaning.
    """
    base = float(start_equity or 0.0)
    path = np.concatenate(([base], base + np.cumsum(pnl)))
    peak = np.maximum.accumulate(path)
    dd = path - peak
    trough = int(np.argmin(dd))
    depth = float(dd[trough])
    if depth >= 0:
        return {
            "max_drawdown": 0.0,
            "max_drawdown_pct": 0.0 if start_equity else None,
            "drawdown_trades": 0,
            "recovered": True,
            "recovery_trades": 0,
        }
    peak_value = float(peak[trough])
    peak_index = int(np.nonzero(path[: trough + 1] == peak_value)[0][-1])
    after = np.nonzero(path[trough + 1 :] >= peak_value)[0]
    recovery_index = trough + 1 + int(after[0]) if after.size else None
    return {
        "max_drawdown": depth,
        "max_drawdown_pct": depth / peak_value if start_equity and peak_value > 0 else None,
        "drawdown_trades": trough - peak_index,
        "recovered": recovery_index is not None,
        "recovery_trades": recovery_index - trough if recovery_index is not None else None,
    }


def daily_ratios(
    daily_pnl: Array,
    start_equity: float | None,
    max_drawdown_pct: float | None,
) -> dict[str, Any]:
    """Sharpe, Sortino, and Calmar on daily returns. Needs a starting equity.

    Daily return is the day's P&L divided by equity at the start of that day. Risk-free rate
    is zero. Ratios are annualized with 252 trading days.
    """
    if not start_equity or start_equity <= 0:
        return {
            "available": False,
            "reason": "Enter a starting equity to compute daily-return ratios. "
            "Without it, only P&L-based and R-based figures are shown.",
        }
    if daily_pnl.size == 0:
        return {"available": False, "reason": "No trading days in the selected range."}
    equity_before = start_equity + np.concatenate(([0.0], np.cumsum(daily_pnl)[:-1]))
    with np.errstate(divide="ignore", invalid="ignore"):
        returns = np.where(equity_before > 0, daily_pnl / equity_before, np.nan)
    returns = returns[np.isfinite(returns)]
    if returns.size < 2:
        return {"available": False, "reason": "At least two trading days are needed."}
    mean = float(returns.mean())
    std = float(returns.std(ddof=1))
    downside = float(np.sqrt(np.mean(np.minimum(returns, 0.0) ** 2)))
    end_equity = start_equity + float(daily_pnl.sum())
    years = returns.size / TRADING_DAYS
    cagr = (end_equity / start_equity) ** (1 / years) - 1 if end_equity > 0 else None
    calmar = None
    if cagr is not None and max_drawdown_pct is not None and max_drawdown_pct < 0:
        calmar = cagr / abs(max_drawdown_pct)
    return {
        "available": True,
        "sharpe": mean / std * np.sqrt(TRADING_DAYS) if std > 0 else None,
        "sortino": mean / downside * np.sqrt(TRADING_DAYS) if downside > 0 else None,
        "calmar": calmar,
        "cagr": cagr,
        "trading_days": int(returns.size),
    }


def sqn(r: Array) -> float | None:
    """System Quality Number: sqrt(n) x mean R / standard deviation of R."""
    finite = r[np.isfinite(r)]
    if finite.size < 2:
        return None
    std = float(finite.std(ddof=1))
    if std == 0:
        return None
    return float(np.sqrt(finite.size) * finite.mean() / std)


def kelly_upper_bound(win_rate: float | None, payoff: float | None) -> float | None:
    """Kelly fraction W - (1 - W) / payoff. An upper bound, never a position size."""
    if win_rate is None or payoff is None or payoff <= 0:
        return None
    return win_rate - (1 - win_rate) / payoff


def risk_per_trade(planned_risk: Array) -> dict[str, Any]:
    """Mean planned risk and its coefficient of variation (sample std / mean)."""
    finite = planned_risk[np.isfinite(planned_risk) & (planned_risk > 0)]
    if finite.size == 0:
        return {"known_trades": 0, "mean": None, "coefficient_of_variation": None}
    mean = float(finite.mean())
    cv = float(finite.std(ddof=1) / mean) if finite.size > 1 and mean > 0 else None
    return {"known_trades": int(finite.size), "mean": mean, "coefficient_of_variation": cv}
