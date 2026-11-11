"""Effect sizes, significance, and bootstrap intervals for a slice compared with its rest.

The bootstrap resamples whole trades with replacement. Each resample is a vector of how many
times every trade was drawn, so the slice and the rest of every finding are scored from the same
resamples with one matrix product, instead of one resampling loop per finding.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
import numpy.typing as npt

from obsidian_ledger.metrics.stats import welch_p_value

Array = npt.NDArray[np.float64]
Mask = npt.NDArray[np.bool_]

ELEMENT_BUDGET: Final = 4_000_000  # array cells per chunk of resamples


@dataclass(frozen=True)
class SliceStats:
    n: int
    rest_n: int
    mean_pnl: float
    rest_mean_pnl: float
    diff_pnl: float
    total_pnl: float
    r_n: int
    mean_r: float | None
    rest_mean_r: float | None
    diff_r: float | None


@dataclass(frozen=True)
class EffectInterval:
    pnl_low: float | None
    pnl_high: float | None
    r_low: float | None
    r_high: float | None


def slice_stats(pnl: Array, r: Array, mask: Mask, rest: Mask) -> SliceStats | None:
    """Means of the slice and its rest, and the difference. None when either group is empty."""
    n = int(mask.sum())
    rest_n = int(rest.sum())
    if n == 0 or rest_n == 0:
        return None
    mean_pnl = float(pnl[mask].mean())
    rest_mean = float(pnl[rest].mean())
    slice_r = r[mask & np.isfinite(r)]
    rest_r = r[rest & np.isfinite(r)]
    mean_r = float(slice_r.mean()) if slice_r.size else None
    rest_mean_r = float(rest_r.mean()) if rest_r.size else None
    diff_r = mean_r - rest_mean_r if mean_r is not None and rest_mean_r is not None else None
    return SliceStats(
        n=n,
        rest_n=rest_n,
        mean_pnl=mean_pnl,
        rest_mean_pnl=rest_mean,
        diff_pnl=mean_pnl - rest_mean,
        total_pnl=float(pnl[mask].sum()),
        r_n=int(slice_r.size),
        mean_r=mean_r,
        rest_mean_r=rest_mean_r,
        diff_r=diff_r,
    )


def p_value(pnl: Array, mask: Mask, rest: Mask) -> float | None:
    """Two-sided Welch p-value for slice versus rest. None when it cannot be computed."""
    if mask.sum() < 2 or rest.sum() < 2:
        return None
    return welch_p_value(pnl[mask], pnl[rest])


def _interval(values: Array) -> tuple[float, float] | tuple[None, None]:
    finite = values[np.isfinite(values)]
    if finite.size < 20:
        return None, None
    low, high = np.percentile(finite, [2.5, 97.5])
    return float(low), float(high)


def bootstrap_intervals(
    pnl: Array,
    r: Array,
    pairs: list[tuple[Mask, Mask]],
    resamples: int,
    seed: int,
) -> list[EffectInterval]:
    """95% percentile intervals for (slice mean - rest mean), in currency and in R.

    The slice and rest sizes vary from resample to resample, which is the honest behavior of
    resampling trades: how many trades land in a slice is itself uncertain.
    """
    if not pairs:
        return []
    count = int(pnl.size)
    finite = np.isfinite(r)
    r_zero = np.where(finite, r, 0.0)
    finite_f = finite.astype(np.float64)
    columns: list[Array] = []
    for mask, rest in pairs:
        for group in (mask, rest):
            weight = group.astype(np.float64)
            columns.extend((pnl * weight, weight, r_zero * weight, finite_f * weight))
    design = np.column_stack(columns)
    rng = np.random.default_rng(seed)
    chunk = max(1, min(resamples, ELEMENT_BUDGET // max(count, 1)))
    sums: list[Array] = []
    done = 0
    while done < resamples:
        rows = min(chunk, resamples - done)
        draws = rng.integers(0, count, size=(rows, count))
        counts = np.empty((rows, count), dtype=np.float64)
        for row in range(rows):
            counts[row] = np.bincount(draws[row], minlength=count)
        sums.append(counts @ design)
        done += rows
    totals = np.concatenate(sums, axis=0)
    results: list[EffectInterval] = []
    with np.errstate(divide="ignore", invalid="ignore"):
        for index in range(len(pairs)):
            base = index * 8
            slice_mean = totals[:, base] / totals[:, base + 1]
            rest_mean = totals[:, base + 4] / totals[:, base + 5]
            slice_r = totals[:, base + 2] / totals[:, base + 3]
            rest_r = totals[:, base + 6] / totals[:, base + 7]
            pnl_low, pnl_high = _interval(slice_mean - rest_mean)
            r_low, r_high = _interval(slice_r - rest_r)
            results.append(EffectInterval(pnl_low, pnl_high, r_low, r_high))
    return results


def mean_bootstrap(values: Array, resamples: int, seed: int) -> tuple[float, float] | None:
    """95% percentile interval for the mean of a small set of values."""
    if values.size < 2:
        return None
    rng = np.random.default_rng(seed)
    means = values[rng.integers(0, values.size, size=(resamples, values.size))].mean(axis=1)
    low, high = np.percentile(means, [2.5, 97.5])
    return float(low), float(high)
