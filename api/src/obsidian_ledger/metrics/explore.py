"""Per-trade points for the Trade Constellation and MAE/MFE chart, streak runs, and fee drag.

Everything here is computed from the same prepared frame the dashboard uses, so a figure on the
Analytics screen matches the same figure elsewhere.
"""

from __future__ import annotations

from typing import Any, Final

import numpy as np
import numpy.typing as npt
import polars as pl

Array = npt.NDArray[np.float64]

# Fields a client may use to brush trades. "t" is the exit time in epoch milliseconds.
AXIS_FIELDS: Final[tuple[str, ...]] = ("t", "pnl", "r", "mae", "mfe", "hold")
ROUND: Final = 4
TOP_RUNS: Final = 5
TOP_SYMBOLS: Final = 8


def _sorted(frame: pl.DataFrame) -> pl.DataFrame:
    return frame.sort(["exit_time", "trade_key"])


def axis_values(rows: pl.DataFrame, field: str) -> Array:
    """One value per row of an exit-ordered frame, for a brush field. Missing values are NaN."""
    if field == "t":
        return rows["exit_time"].dt.epoch("ms").to_numpy().astype(np.float64)
    if field == "pnl":
        return rows["pnl"].to_numpy().astype(np.float64)
    if field == "r":
        return rows["r_multiple"].to_numpy().astype(np.float64)
    if field == "mae":
        return np.abs(rows["mae"].to_numpy().astype(np.float64))
    if field == "mfe":
        return np.abs(rows["mfe"].to_numpy().astype(np.float64))
    if field == "hold":
        return rows["holding_seconds"].to_numpy().astype(np.float64)
    raise ValueError(f"Unknown field '{field}'.")


def select_keys(
    frame: pl.DataFrame, bounds: list[tuple[str, float | None, float | None]]
) -> list[str]:
    """Trade keys whose values fall inside every (field, low, high) bound. Open ends are None."""
    rows = _sorted(frame)
    keep = np.ones(rows.height, dtype=bool)
    for field, low, high in bounds:
        values = axis_values(rows, field)
        keep &= np.isfinite(values)
        if low is not None:
            keep &= values >= low
        if high is not None:
            keep &= values <= high
    return rows["trade_key"].filter(pl.Series(keep)).to_list()


def points(frame: pl.DataFrame) -> dict[str, Any]:
    """Columnar per-trade values in exit order. NaN stands for a missing value."""
    rows = _sorted(frame)
    symbols = sorted(set(rows["symbol"].fill_null("unknown").to_list()))
    index = {symbol: i for i, symbol in enumerate(symbols)}
    return {
        "n": rows.height,
        "t": axis_values(rows, "t").astype(np.int64),
        "pnl": np.round(axis_values(rows, "pnl"), ROUND),
        "r": np.round(axis_values(rows, "r"), ROUND),
        "mae": np.round(axis_values(rows, "mae"), ROUND),
        "mfe": np.round(axis_values(rows, "mfe"), ROUND),
        "hold": axis_values(rows, "hold").astype(np.int64),
        "symbol": np.array(
            [index[s] for s in rows["symbol"].fill_null("unknown").to_list()], dtype=np.int32
        ),
        "symbols": symbols,
    }


def mae_mfe(frame: pl.DataFrame) -> dict[str, Any]:
    """How far trades went against and for you, and how much of the best move winners kept."""
    rows = _sorted(frame)
    pnl = rows["pnl"].to_numpy().astype(np.float64)
    mae = axis_values(rows, "mae")
    mfe = axis_values(rows, "mfe")
    both = np.isfinite(mae) & np.isfinite(mfe)
    winners = both & (pnl > 0) & (mfe > 0)
    capture = pnl[winners] / mfe[winners]
    losers = both & (pnl < 0)
    return {
        "trades_with_excursions": int(both.sum()),
        "trades_total": int(rows.height),
        "winner_capture_ratio": float(capture.mean()) if capture.size else None,
        "winner_capture_n": int(winners.sum()),
        "avg_mae_winners": float(mae[both & (pnl > 0)].mean())
        if (both & (pnl > 0)).any()
        else None,
        "avg_mae_losers": float(mae[losers].mean()) if losers.any() else None,
        "avg_mfe_losers": float(mfe[losers].mean()) if losers.any() else None,
        "note": (
            "MAE and MFE are the values in your file, shown as sizes. Capture ratio is P&L "
            "divided by MFE for winners that report an MFE."
        ),
    }


def streaks(frame: pl.DataFrame) -> dict[str, Any]:
    """Every winning and losing run in exit order, with the longest runs and a length histogram."""
    rows = _sorted(frame)
    pnl = rows["pnl"].to_numpy().astype(np.float64)
    exits = rows["exit_time"].dt.strftime("%Y-%m-%d").to_list()
    runs: list[dict[str, Any]] = []
    kind: str | None = None
    start = 0
    total = 0.0

    def close(end: int) -> None:
        if kind is not None:
            runs.append(
                {
                    "kind": kind,
                    "length": end - start,
                    "start": exits[start],
                    "end": exits[end - 1],
                    "pnl": total,
                }
            )

    for i, value in enumerate(pnl.tolist()):
        current = "win" if value > 0 else "loss" if value < 0 else None
        if current != kind:
            close(i)
            kind, start, total = current, i, 0.0
        if current is not None:
            total += value
    close(len(pnl))

    def longest(which: str) -> list[dict[str, Any]]:
        chosen = [run for run in runs if run["kind"] == which]
        return sorted(chosen, key=lambda run: (-run["length"], run["start"]))[:TOP_RUNS]

    lengths = sorted({int(run["length"]) for run in runs})
    histogram = [
        {
            "length": length,
            "wins": sum(1 for r in runs if r["kind"] == "win" and r["length"] == length),
            "losses": sum(1 for r in runs if r["kind"] == "loss" and r["length"] == length),
        }
        for length in lengths
    ]
    return {
        "runs": len(runs),
        "longest_wins": longest("win"),
        "longest_losses": longest("loss"),
        "histogram": histogram,
    }


def fee_drag(frame: pl.DataFrame) -> dict[str, Any]:
    """Costs against gross P&L, overall and by symbol. Costs are signed: negative is a cost."""
    if frame.height == 0:
        return {"costs": 0.0, "gross": 0.0, "drag": None, "by_symbol": []}
    pnl = frame["pnl"].to_numpy().astype(np.float64)
    costs = frame["costs"].to_numpy().astype(np.float64)
    gross_total = float(pnl.sum() - costs.sum())
    costs_total = float(costs.sum())
    per_symbol = (
        frame.with_columns(
            pl.col("symbol").fill_null("unknown"),
            (pl.col("pnl") - pl.col("costs")).alias("gross"),
        )
        .group_by("symbol")
        .agg(
            pl.len().alias("trades"),
            pl.col("costs").sum().alias("costs"),
            pl.col("gross").sum().alias("gross"),
            pl.col("pnl").sum().alias("net"),
        )
        .sort("costs")
        .head(TOP_SYMBOLS)
    )
    by_symbol = [
        {
            "symbol": row["symbol"],
            "trades": row["trades"],
            "costs": float(row["costs"]),
            "gross": float(row["gross"]),
            "net": float(row["net"]),
            "drag": abs(float(row["costs"])) / abs(float(row["gross"])) if row["gross"] else None,
        }
        for row in per_symbol.iter_rows(named=True)
    ]
    return {
        "costs": costs_total,
        "gross": gross_total,
        "drag": abs(costs_total) / abs(gross_total) if gross_total != 0 else None,
        "by_symbol": by_symbol,
        "rule": "Fee drag is total costs divided by the size of gross P&L (net P&L before costs).",
    }
