"""The verdict: is there evidence of an edge in this sample?

Rule (expectancy in R, or in currency when R is not available for enough trades):
- 95% bootstrap interval lower bound above 0  -> edge present
- 95% bootstrap interval upper bound below 0  -> negative
- interval spans 0, or fewer than `min_n` trades -> unproven
"""

from __future__ import annotations

from typing import Final

import numpy as np
import numpy.typing as npt

from obsidian_ledger.coach.effects import mean_bootstrap
from obsidian_ledger.coach.fmt import figure
from obsidian_ledger.coach.models import (
    Confidence,
    Figure,
    Finding,
    Interval,
    Verdict,
    VerdictLabel,
)
from obsidian_ledger.coach.params import CoachParams

Array = npt.NDArray[np.float64]
LABELS: Final[dict[VerdictLabel, str]] = {
    "edge_present": "Edge present",
    "unproven": "Unproven",
    "negative": "Negative",
}


def label_for(low: float | None, high: float | None, n: int, min_n: int) -> VerdictLabel:
    if n < min_n or low is None or high is None:
        return "unproven"
    if low > 0:
        return "edge_present"
    if high < 0:
        return "negative"
    return "unproven"


def confidence_for_verdict(
    label: VerdictLabel, n: int, low: float | None, high: float | None, params: CoachParams
) -> Confidence:
    if n < params.min_n or low is None or high is None:
        return "low"
    excludes_zero = label != "unproven"
    if excludes_zero and n >= params.high_n:
        return "high"
    if excludes_zero or n >= params.high_n:
        return "medium"
    return "low"


def build_verdict(
    pnl: Array,
    r: Array,
    leaks: list[Finding],
    strengths: list[Finding],
    params: CoachParams,
    currency: str,
) -> Verdict:
    finite_r = r[np.isfinite(r)]
    use_r = finite_r.size >= params.min_n
    values = finite_r if use_r else pnl
    unit = "R" if use_r else "currency"
    metric = "expectancy_r" if use_r else "expectancy"
    basis = (
        f"expectancy in R over {int(finite_r.size)} trades with a planned risk"
        if use_r
        else "expectancy in currency, because fewer than "
        f"{params.min_n} trades have a planned risk to measure R"
    )
    n = int(values.size)
    mean = float(values.mean()) if n else None
    bounds = mean_bootstrap(values, params.resamples, params.seed) if n >= 2 else None
    low, high = bounds if bounds is not None else (None, None)
    label = label_for(low, high, n, params.min_n)
    confidence = confidence_for_verdict(label, n, low, high, params)

    source = f"core|{metric}"
    expectancy = figure(mean, unit, source, "Average result per trade", currency)  # type: ignore[arg-type]
    interval = (
        Interval(
            low=figure(
                low,
                unit,
                f"core|ci_{unit.lower()}_low",
                "Interval lower bound",
                currency,
                bootstrap=True,
            ),  # type: ignore[arg-type]
            high=figure(
                high,
                unit,
                f"core|ci_{unit.lower()}_high",
                "Interval upper bound",
                currency,
                bootstrap=True,
            ),  # type: ignore[arg-type]
        )
        if low is not None and high is not None
        else None
    )
    n_fig = figure(n, "count", "core|r_trades" if use_r else "core|trades", "Trades measured")

    lines = [_first_line(label, expectancy, interval, n_fig)]
    if leaks:
        top = leaks[0]
        lines.append(
            f"Biggest leak: {top.title}. If those {top.n.display} trades had matched your others, "
            f"net P&L would be {top.what_if.pnl_change.display} higher."
        )
    else:
        lines.append(
            "No leak cleared the false-discovery filter. That means none is proven, "
            "not that none exists."
        )
    if strengths:
        top = strengths[0]
        lines.append(
            f"Strongest edge: {top.title}. Those {top.n.display} trades added "
            f"{top.what_if.pnl_change.display} above your average."
        )
    else:
        lines.append(
            "No strength cleared the false-discovery filter yet. Keep logging setups and "
            "emotions so the next report has more to test."
        )
    return Verdict(
        label=label,
        headline=LABELS[label],
        lines=lines,
        confidence=confidence,
        basis=basis,
        expectancy=expectancy,
        interval=interval,
        n=n_fig,
    )


def _first_line(
    label: VerdictLabel, expectancy: Figure, interval: Interval | None, n: Figure
) -> str:
    span = (
        f" (95% interval {interval.low.display} to {interval.high.display})"
        if interval is not None
        else ""
    )
    if label == "edge_present":
        meaning = "the interval is above zero, so this sample shows an edge"
    elif label == "negative":
        meaning = "the interval is below zero, so this sample shows a negative expectancy"
    else:
        meaning = "the interval spans zero or the sample is small, so an edge is not proven"
    return (
        f"{LABELS[label]}: you averaged {expectancy.display} per trade over {n.display} "
        f"trades{span}; {meaning}."
    )
