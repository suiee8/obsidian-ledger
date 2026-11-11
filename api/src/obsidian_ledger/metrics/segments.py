"""Segment explorer: metrics for each value of one dimension, with sample size and significance."""

from __future__ import annotations

from typing import Any, Final

import numpy as np
import polars as pl

from obsidian_ledger.metrics.data import LOW_CONFIDENCE_N
from obsidian_ledger.metrics.stats import benjamini_hochberg, mean_interval, welch_p_value

DIMENSIONS: Final[tuple[str, ...]] = (
    "symbol",
    "setup",
    "side",
    "session",
    "weekday",
    "hour",
    "holding",
    "size",
    "emotion",
    "account",
    "tag",
)
Q_THRESHOLD: Final = 0.10
HOLDING_BUCKETS: Final = (
    (300, "under 5 min"),
    (1800, "5 to 30 min"),
    (7200, "30 min to 2 h"),
    (28800, "2 to 8 h"),
)
WEEKDAYS: Final = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def key_frame(frame: pl.DataFrame, dimension: str) -> pl.DataFrame:
    if dimension not in DIMENSIONS:
        raise ValueError(f"Unknown dimension '{dimension}'.")
    if dimension == "holding":
        bucket = pl.when(pl.col("holding_seconds") < HOLDING_BUCKETS[0][0]).then(
            pl.lit(HOLDING_BUCKETS[0][1])
        )
        for limit, label in HOLDING_BUCKETS[1:]:
            bucket = bucket.when(pl.col("holding_seconds") < limit).then(pl.lit(label))
        key = bucket.otherwise(pl.lit("8 h and over"))
        return frame.with_columns(key.alias("key"))
    if dimension == "size":
        quartiles = frame["qty"].quantile(0.33), frame["qty"].quantile(0.66)
        low, high = (float(quartiles[0] or 0.0), float(quartiles[1] or 0.0))
        key = (
            pl.when(pl.col("qty") <= low)
            .then(pl.lit("small (bottom third)"))
            .when(pl.col("qty") <= high)
            .then(pl.lit("medium (middle third)"))
            .otherwise(pl.lit("large (top third)"))
        )
        return frame.with_columns(key.alias("key"))
    if dimension == "weekday":
        labels = {index: name for index, name in enumerate(WEEKDAYS)}
        return frame.with_columns(
            pl.col("weekday").replace_strict(labels, return_dtype=pl.String).alias("key")
        )
    if dimension == "hour":
        return frame.with_columns(pl.col("hour_utc").cast(pl.String).alias("key"))
    if dimension == "tag":
        exploded = (
            frame.with_columns(pl.col("tags").fill_null("untagged").str.split(",").alias("key"))
            .explode("key")
            .with_columns(pl.col("key").str.strip_chars().str.to_lowercase())
            .with_columns(
                pl.when(pl.col("key") == "")
                .then(pl.lit("untagged"))
                .otherwise(pl.col("key"))
                .alias("key")
            )
        )
        return exploded
    column = {
        "symbol": "symbol",
        "setup": "setup",
        "side": "side",
        "session": "session",
        "emotion": "emotion",
        "account": "account",
    }[dimension]
    return frame.with_columns(pl.col(column).fill_null("unknown").cast(pl.String).alias("key"))


def segment_table(frame: pl.DataFrame, dimension: str, min_n: int) -> dict[str, Any]:
    """One row per value of the dimension, ranked by t-statistic.

    Each slice is compared with all other trades using Welch's t-test. P-values are
    adjusted across the slices of this dimension with Benjamini-Hochberg. Slices below
    min_n trades are marked low-confidence and cannot be labelled an edge or a leak.
    """
    keyed = key_frame(frame, dimension)
    if keyed.height == 0:
        return {"dimension": dimension, "min_n": min_n, "slices": [], "slices_tested": 0}
    pnl_all = keyed["pnl"].to_numpy()

    rows: list[dict[str, Any]] = []
    p_values: list[float | None] = []
    groups = keyed.partition_by("key", as_dict=True, include_key=False)
    for key_tuple, group in groups.items():
        label = str(key_tuple[0])
        pnl = group["pnl"].to_numpy()
        mask = keyed["key"].to_numpy() == label
        rest = pnl_all[~mask]
        r_values = group["r_multiple"].to_numpy()
        interval = mean_interval(pnl)
        decided = pnl[pnl != 0]
        wins = int((pnl > 0).sum())
        p_value = welch_p_value(pnl, rest) if rest.size else None
        p_values.append(p_value)
        r_finite = r_values[np.isfinite(r_values)]
        rows.append(
            {
                "value": label,
                "n": int(pnl.size),
                "low_confidence": pnl.size < min_n,
                "win_rate": wins / decided.size if decided.size else None,
                "net_pnl": float(pnl.sum()),
                "expectancy": interval["mean"],
                "expectancy_ci95": interval["ci95"],
                "expectancy_r": float(r_finite.mean()) if r_finite.size else None,
                "t_statistic": (
                    float(interval["mean"] / (interval["std"] / np.sqrt(pnl.size)))
                    if interval["std"] and interval["std"] > 0
                    else None
                ),
                "p_value": p_value,
                "rest_expectancy": float(rest.mean()) if rest.size else None,
            }
        )
    q_values = benjamini_hochberg(p_values)
    for row, q in zip(rows, q_values, strict=True):
        row["q_value"] = q
        row["verdict"] = _verdict(row)
    rows.sort(key=lambda item: (item["t_statistic"] is None, -(item["t_statistic"] or 0.0)))
    return {
        "dimension": dimension,
        "min_n": min_n,
        "slices_tested": sum(1 for p in p_values if p is not None),
        "multiple_comparisons": (
            "Slices are adjusted with Benjamini-Hochberg within this dimension. "
            "Checking many dimensions raises the chance of a false edge."
        ),
        "slices": rows,
        "low_confidence_threshold": LOW_CONFIDENCE_N,
    }


def _verdict(row: dict[str, Any]) -> str:
    if row["low_confidence"]:
        return "low confidence"
    q = row["q_value"]
    if q is None or q >= Q_THRESHOLD:
        return "inconclusive"
    if row["expectancy"] is not None and row["expectancy"] > 0:
        return "edge"
    return "leak"
