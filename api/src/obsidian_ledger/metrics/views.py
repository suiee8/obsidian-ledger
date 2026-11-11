"""Chart-ready series for the Dashboard: equity, daily P&L, R distribution, heatmap, radar,
and the strongest edges and leaks."""

from __future__ import annotations

from typing import Any, Final

import numpy as np
import numpy.typing as npt
import polars as pl

from obsidian_ledger.metrics.behavior import hit_rate
from obsidian_ledger.metrics.risk import risk_per_trade
from obsidian_ledger.metrics.segments import DIMENSIONS, segment_table

Array = npt.NDArray[np.float64]
MAX_CHART_POINTS: Final = 5000
RADAR_AXES: Final[tuple[str, ...]] = (
    "win_rate",
    "payoff",
    "expectancy_r",
    "consistency",
    "discipline",
    "risk_control",
)
FINDING_DIMENSIONS: Final[tuple[str, ...]] = (
    "symbol",
    "setup",
    "side",
    "session",
    "weekday",
    "hour",
    "holding",
)


def lttb_indices(x: Array, y: Array, threshold: int) -> npt.NDArray[np.intp]:
    """Largest-Triangle-Three-Buckets downsampling. Keeps the first and last points and the
    points that change the shape of the series most.

    Bucket averages are computed once, vectorized. Each bucket's choice depends on the point
    chosen before it, so the selection itself is a sequential pass over the buckets.
    """
    n = int(x.size)
    if threshold >= n or threshold < 3:
        return np.arange(n, dtype=np.intp)
    buckets = threshold - 2
    every = (n - 2) / buckets
    index = np.arange(buckets, dtype=np.float64)
    avg_start = np.floor((index + 1) * every).astype(np.intp) + 1
    avg_end = np.minimum(np.floor((index + 2) * every).astype(np.intp) + 1, n)
    range_start = (np.floor(index * every).astype(np.intp) + 1).tolist()
    range_end = (np.floor((index + 1) * every).astype(np.intp) + 1).tolist()
    # Consecutive averaging windows touch, so one reduceat gives every window's sum.
    counts = (avg_end - avg_start).astype(np.float64)
    head = int(avg_end[-1])
    avg_x = (np.add.reduceat(x[:head], avg_start) / counts).tolist()
    avg_y = (np.add.reduceat(y[:head], avg_start) / counts).tolist()

    xs = x.tolist()
    ys = y.tolist()
    sampled = [0] * threshold
    anchor = 0
    for bucket in range(buckets):
        ax = xs[anchor]
        ay = ys[anchor]
        mx = avg_x[bucket]
        my = avg_y[bucket]
        best_area = -1.0
        best_at = range_start[bucket]
        for point in range(range_start[bucket], range_end[bucket]):
            area = abs((ax - mx) * (ys[point] - ay) - (ax - xs[point]) * (my - ay))
            if area > best_area:
                best_area = area
                best_at = point
        anchor = best_at
        sampled[bucket + 1] = anchor
    sampled[-1] = n - 1
    return np.asarray(sampled, dtype=np.intp)


def equity_series(frame: pl.DataFrame, starting_equity: float | None) -> dict[str, Any]:
    """Equity and drawdown after each trade in exit order, downsampled above 5,000 points."""
    if frame.height == 0:
        return {"points": [], "downsampled": False, "source_points": 0}
    base = float(starting_equity or 0.0)
    pnl = frame["pnl"].to_numpy()
    equity = base + np.cumsum(pnl)
    peak = np.maximum.accumulate(np.concatenate(([base], equity)))[1:]
    drawdown = equity - peak
    times = frame["exit_time"].dt.epoch("s").to_numpy().astype(np.float64)
    picked = lttb_indices(times, equity, MAX_CHART_POINTS)
    # Format timestamps only for the points that are returned.
    stamps = frame["exit_time"].gather(picked).dt.strftime("%Y-%m-%dT%H:%M:%SZ").to_list()
    points = [
        {
            "t": stamp,
            "equity": float(equity[index]),
            "drawdown": float(drawdown[index]),
        }
        for stamp, index in zip(stamps, picked.tolist(), strict=True)
    ]
    return {
        "points": points,
        "downsampled": len(picked) < frame.height,
        "source_points": frame.height,
        "starting_equity": starting_equity,
    }


def daily_series(frame: pl.DataFrame) -> list[dict[str, Any]]:
    """Net P&L and trade count per exit day, in date order."""
    if frame.height == 0:
        return []
    table = (
        frame.group_by("exit_day")
        .agg(pl.col("pnl").sum().alias("pnl"), pl.len().alias("trades"))
        .sort("exit_day")
    )
    return [
        {"day": row["exit_day"].isoformat(), "pnl": float(row["pnl"]), "trades": int(row["trades"])}
        for row in table.iter_rows(named=True)
    ]


def r_histogram(frame: pl.DataFrame, bins: int = 40) -> dict[str, Any]:
    """Histogram of R multiples. Values beyond the 0.5th and 99.5th percentiles are counted
    in the edge bins, and the number clipped is reported."""
    r = frame["r_multiple"].to_numpy().astype(np.float64)
    finite = r[np.isfinite(r)]
    if finite.size == 0:
        return {"bins": [], "n": 0, "clipped": 0, "mean": None, "median": None}
    low, high = np.percentile(finite, [0.5, 99.5])
    if high <= low:
        low, high = float(finite.min()) - 0.5, float(finite.max()) + 0.5
    clipped = int(((finite < low) | (finite > high)).sum())
    counts, edges = np.histogram(np.clip(finite, low, high), bins=bins, range=(low, high))
    return {
        "bins": [
            {"from": float(edges[i]), "to": float(edges[i + 1]), "count": int(counts[i])}
            for i in range(counts.size)
        ],
        "n": int(finite.size),
        "clipped": clipped,
        "mean": float(finite.mean()),
        "median": float(np.median(finite)),
    }


def weekday_hour_heatmap(frame: pl.DataFrame) -> list[dict[str, Any]]:
    """Trade count, net P&L, and expectancy for each populated weekday and UTC entry hour."""
    if frame.height == 0:
        return []
    table = (
        frame.group_by(["weekday", "hour_utc"])
        .agg(
            pl.len().alias("trades"),
            pl.col("pnl").sum().alias("pnl"),
            pl.col("pnl").mean().alias("expectancy"),
        )
        .sort(["weekday", "hour_utc"])
    )
    return [
        {
            "weekday": int(row["weekday"]),
            "hour": int(row["hour_utc"]),
            "trades": int(row["trades"]),
            "pnl": float(row["pnl"]),
            "expectancy": float(row["expectancy"]),
        }
        for row in table.iter_rows(named=True)
    ]


def _normalize(values: list[float | None]) -> list[float | None]:
    present = [v for v in values if v is not None]
    if not present:
        return [None for _ in values]
    low, high = min(present), max(present)
    if high == low:
        return [50.0 if v is not None else None for v in values]
    return [None if v is None else 100.0 * (v - low) / (high - low) for v in values]


def edge_radar(frame: pl.DataFrame, min_n: int) -> dict[str, Any]:
    """Six axes per setup, each scaled 0 to 100 across the setups shown.

    win_rate and payoff come from the setup's trades. expectancy_r is mean R. consistency is
    the share of calendar months with a positive net P&L. discipline is the plan-followed rate.
    risk_control is 100 minus the coefficient of variation of planned risk (capped at 1).
    A setup with fewer than min_n trades is shown but flagged low confidence.
    """
    if frame.height == 0:
        return {"axes": list(RADAR_AXES), "setups": []}
    keyed = frame.with_columns(pl.col("setup").fill_null("unknown").alias("setup_key"))
    raw_rows: list[dict[str, Any]] = []
    for setup_name, group in keyed.partition_by("setup_key", as_dict=True).items():
        label = str(setup_name[0])
        pnl = group["pnl"].to_numpy()
        r = group["r_multiple"].to_numpy().astype(np.float64)
        wins = pnl > 0
        losses = pnl < 0
        avg_win = float(pnl[wins].mean()) if wins.any() else None
        avg_loss = float(-pnl[losses].mean()) if losses.any() else None
        finite_r = r[np.isfinite(r)]
        months = group.with_columns(pl.col("exit_time").dt.truncate("1mo").alias("month"))
        monthly = months.group_by("month").agg(pl.col("pnl").sum())["pnl"].to_numpy()
        plan = group["plan_followed"].drop_nulls().to_list()
        risk = risk_per_trade(group["planned_risk"].to_numpy().astype(np.float64))
        cv = risk["coefficient_of_variation"]
        raw_rows.append(
            {
                "setup": label,
                "n": int(pnl.size),
                "low_confidence": bool(pnl.size < min_n),
                "raw": {
                    "win_rate": hit_rate(wins, pnl != 0),
                    "payoff": avg_win / avg_loss if avg_win is not None and avg_loss else None,
                    "expectancy_r": float(finite_r.mean()) if finite_r.size else None,
                    "consistency": float((monthly > 0).mean()) if monthly.size else None,
                    "discipline": (
                        float(sum(1 for value in plan if value) / len(plan)) if plan else None
                    ),
                    "risk_control": (1.0 - min(float(cv), 1.0) if cv is not None else None),
                },
            }
        )
    raw_rows.sort(key=lambda row: -row["n"])
    normalized_by_axis: dict[str, list[float | None]] = {}
    for axis in RADAR_AXES:
        normalized_by_axis[axis] = _normalize([row["raw"][axis] for row in raw_rows])
    for index, row in enumerate(raw_rows):
        row["normalized"] = [normalized_by_axis[axis][index] for axis in RADAR_AXES]
    return {"axes": list(RADAR_AXES), "setups": raw_rows}


def top_findings(frame: pl.DataFrame, min_n: int, limit: int = 3) -> dict[str, Any]:
    """The strongest edges and worst leaks across the segment dimensions.

    Each dimension is tested separately with Benjamini-Hochberg correction. Testing seven
    dimensions still raises the chance of a false finding, so the caveat is returned too.
    """
    edges: list[dict[str, Any]] = []
    leaks: list[dict[str, Any]] = []
    checked = 0
    for dimension in FINDING_DIMENSIONS:
        if dimension not in DIMENSIONS:
            continue
        table = segment_table(frame, dimension, min_n)
        checked += int(table["slices_tested"])
        for slice_ in table["slices"]:
            if slice_["verdict"] not in ("edge", "leak"):
                continue
            entry = {
                "dimension": dimension,
                "value": slice_["value"],
                "n": slice_["n"],
                "expectancy": slice_["expectancy"],
                "expectancy_ci95": slice_["expectancy_ci95"],
                "t_statistic": slice_["t_statistic"],
                "q_value": slice_["q_value"],
            }
            (edges if slice_["verdict"] == "edge" else leaks).append(entry)
    edges.sort(key=lambda item: -(item["t_statistic"] or 0.0))
    leaks.sort(key=lambda item: item["t_statistic"] or 0.0)
    return {
        "edges": edges[:limit],
        "leaks": leaks[:limit],
        "slices_tested": checked,
        "caveat": (
            "Findings are ranked from many slices. Treat them as leads to test, not proof. "
            "Each slice is corrected only within its own dimension."
        ),
    }
