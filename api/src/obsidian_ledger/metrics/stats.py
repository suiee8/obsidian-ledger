"""Confidence intervals, bootstrap, Monte Carlo paths, and multiple-testing correction."""

from __future__ import annotations

from typing import Any, Final

import numpy as np
import numpy.typing as npt

from obsidian_ledger.metrics._scipy import t_quantile, welch_two_sided_p

Array = npt.NDArray[np.float64]

ELEMENT_BUDGET: Final = 2_000_000  # cap on array size per chunk, to bound memory
MAX_PATH_LENGTH: Final = 1000
FAN_CHECKPOINTS: Final = 20
ASSUMPTION: Final = (
    "Trades are treated as independent and resampled with replacement. "
    "Clustered trades (for example, one bad day) make these intervals too narrow."
)


def _interval(values: Array) -> list[float] | None:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return None
    low, high = np.percentile(finite, [2.5, 97.5])
    return [float(low), float(high)]


def bootstrap_summary(pnl: Array, resamples: int, seed: int) -> dict[str, Any]:
    """Percentile bootstrap 95% intervals for expectancy, win rate, and profit factor."""
    n = int(pnl.size)
    if n == 0:
        return {"resamples": 0}
    rng = np.random.default_rng(seed)
    chunk = max(1, min(resamples, ELEMENT_BUDGET // n))
    expectancy: list[Array] = []
    win_rate: list[Array] = []
    profit_factor: list[Array] = []
    done = 0
    while done < resamples:
        m = min(chunk, resamples - done)
        sample = pnl[rng.integers(0, n, size=(m, n))]
        wins = sample > 0
        losses = sample < 0
        win_n = wins.sum(axis=1).astype(np.float64)
        loss_n = losses.sum(axis=1).astype(np.float64)
        decided = win_n + loss_n
        gross_win = np.where(wins, sample, 0.0).sum(axis=1)
        gross_loss = -np.where(losses, sample, 0.0).sum(axis=1)
        with np.errstate(divide="ignore", invalid="ignore"):
            expectancy.append(sample.mean(axis=1))
            win_rate.append(np.where(decided > 0, win_n / decided, np.nan))
            profit_factor.append(np.where(gross_loss > 0, gross_win / gross_loss, np.nan))
        done += m
    point = {
        "expectancy": float(pnl.mean()),
        "win_rate": float((pnl > 0).sum() / max(1, ((pnl > 0).sum() + (pnl < 0).sum()))),
    }
    return {
        "resamples": resamples,
        "seed": seed,
        "method": "percentile bootstrap",
        "assumption": ASSUMPTION,
        "expectancy": {"point": point["expectancy"], "ci95": _interval(np.concatenate(expectancy))},
        "win_rate": {"point": point["win_rate"], "ci95": _interval(np.concatenate(win_rate))},
        "profit_factor": {
            "ci95": _interval(np.concatenate(profit_factor)),
            "note": "Resamples with no losses have no profit factor and are excluded.",
        },
    }


def monte_carlo(
    pnl: Array,
    paths: int,
    seed: int,
    start_equity: float | None,
    drawdown_threshold: float,
    target: float,
    ruin_fraction: float = 0.5,
) -> dict[str, Any]:
    """Resample trade outcomes into equity paths and report probabilities and a fan chart.

    Paths are as long as the sample, capped at MAX_PATH_LENGTH trades. Thresholds are in
    P&L currency. Drawdown is the largest fall from a running peak. Ruin means equity falls
    below ruin_fraction of the starting equity, and needs a starting equity.
    """
    n = int(pnl.size)
    if n == 0:
        return {"paths": 0}
    horizon = min(n, MAX_PATH_LENGTH)
    rng = np.random.default_rng(seed)
    chunk = max(1, min(paths, ELEMENT_BUDGET // (horizon + 1)))
    checkpoints = np.unique(np.linspace(1, horizon, FAN_CHECKPOINTS).round().astype(int))
    finals: list[Array] = []
    fan: list[Array] = []
    drawdown_hits = 0
    target_hits = 0
    ruin_hits = 0
    done = 0
    while done < paths:
        m = min(chunk, paths - done)
        steps = pnl[rng.integers(0, n, size=(m, horizon))]
        cumulative = np.concatenate((np.zeros((m, 1)), np.cumsum(steps, axis=1)), axis=1)
        peak = np.maximum.accumulate(cumulative, axis=1)
        worst = (cumulative - peak).min(axis=1)
        finals.append(cumulative[:, -1])
        fan.append(cumulative[:, checkpoints])
        drawdown_hits += int((worst <= -drawdown_threshold).sum())
        target_hits += int((cumulative[:, -1] >= target).sum())
        if start_equity:
            ruin_hits += int((cumulative.min(axis=1) <= -ruin_fraction * start_equity).sum())
        done += m

    final = np.concatenate(finals)
    base = float(start_equity or 0.0)
    fan_values = np.concatenate(fan, axis=0) + base
    percentiles = [5, 25, 50, 75, 95]
    fan_table = [
        {
            "trade": int(checkpoint),
            "p5": float(p[0]),
            "p25": float(p[1]),
            "p50": float(p[2]),
            "p75": float(p[3]),
            "p95": float(p[4]),
        }
        for checkpoint, p in zip(
            checkpoints,
            np.percentile(fan_values, percentiles, axis=0).T,
            strict=True,
        )
    ]
    return {
        "paths": paths,
        "horizon_trades": horizon,
        "seed": seed,
        "assumption": ASSUMPTION,
        "drawdown_threshold": drawdown_threshold,
        "target": target,
        "probability_drawdown_at_least_threshold": drawdown_hits / paths,
        "probability_reaching_target": target_hits / paths,
        "probability_ruin": ruin_hits / paths if start_equity else None,
        "final_percentiles": {
            "p5": float(np.percentile(final + base, 5)),
            "p50": float(np.percentile(final + base, 50)),
            "p95": float(np.percentile(final + base, 95)),
        },
        "fan": fan_table,
    }


def mean_interval(values: Array) -> dict[str, Any]:
    """Two-sided 95% interval for a mean using Student's t. Needs at least two values."""
    n = int(values.size)
    if n < 2:
        return {"n": n, "mean": float(values.mean()) if n else None, "ci95": None, "std": None}
    mean = float(values.mean())
    std = float(values.std(ddof=1))
    half = t_quantile(0.975, n - 1) * std / np.sqrt(n)
    return {"n": n, "mean": mean, "std": std, "ci95": [mean - half, mean + half]}


def welch_p_value(sample: Array, rest: Array) -> float | None:
    """Two-sided Welch t-test p-value comparing a segment with the rest of the trades."""
    if sample.size < 2 or rest.size < 2:
        return None
    if float(sample.std()) == 0 and float(rest.std()) == 0:
        return None
    value = welch_two_sided_p(sample, rest)
    return value if np.isfinite(value) else None


def benjamini_hochberg(p_values: list[float | None]) -> list[float | None]:
    """BH-adjusted q-values. Entries that are None (not testable) stay None and are not counted."""
    indexes = [i for i, p in enumerate(p_values) if p is not None]
    result: list[float | None] = [None] * len(p_values)
    if not indexes:
        return result
    raw = np.array([p_values[i] for i in indexes], dtype=np.float64)
    m = raw.size
    order = np.argsort(raw)
    ranked = raw[order] * m / np.arange(1, m + 1)
    adjusted = np.minimum.accumulate(ranked[::-1])[::-1]
    adjusted = np.clip(adjusted, 0.0, 1.0)
    values = np.empty(m)
    values[order] = adjusted
    for position, index in enumerate(indexes):
        result[index] = float(values[position])
    return result
