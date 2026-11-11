"""Sentence templates. Every number in a sentence is the display text of a Figure."""

from __future__ import annotations

import numpy as np

from obsidian_ledger.coach.fmt import duration, plain_money
from obsidian_ledger.coach.models import Figure, FindingKind
from obsidian_ledger.coach.slices import SliceBuilder, SliceDef


def _sentence_case(text: str) -> str:
    return text[:1].upper() + text[1:]


def title(defn: SliceDef, kind: FindingKind) -> str:
    label = _sentence_case(defn.label)
    if defn.category == "behavior" and defn.dimension in MEASURED_TITLES:
        return MEASURED_TITLES[defn.dimension]
    if kind == "leak":
        return f"{label} underperform your other trades"
    if kind == "strength":
        return f"{label} outperform your other trades"
    return f"{label}: how they compare"


MEASURED_TITLES = {
    "fee_drag": "Trading costs are eating into your results",
    "early_exit": "Winners are closed well before their best price",
    "late_exit": "Losers run past the planned risk",
}


def what_if(defn: SliceDef, kind: FindingKind, n: Figure, impact: Figure) -> str:
    if kind == "leak":
        return (
            f"If these {n.display} trades had matched your other trades, "
            f"net P&L would have been {impact.display} higher."
        )
    if kind == "strength":
        return (
            f"These {n.display} trades earned {impact.display} more than the same number of "
            f"your average trades."
        )
    return f"These {n.display} trades are shown for context and are not scored."


def rule(
    builder: SliceBuilder,
    defn: SliceDef,
    kind: FindingKind,
    n: Figure,
    mean: Figure,
    effect: Figure | None,
) -> str:
    """One sentence a trader can act on, built from the figures."""
    params = builder.params
    worse = effect.display if effect is not None else "n/a"
    if defn.category == "segment":
        if kind == "leak":
            return (
                f"Pause {defn.label} until they improve: they averaged {mean.display} per trade "
                f"over {n.display} trades, {worse} per trade against your other trades."
            )
        if kind == "strength":
            return (
                f"Keep taking {defn.label}: they averaged {mean.display} per trade over "
                f"{n.display} trades, {worse} per trade against your other trades."
            )
        return f"Watch {defn.label}: {n.display} trades averaged {mean.display} per trade."
    match defn.dimension:
        case "revenge":
            return (
                f"After a loss, wait at least {params.revenge_gap_minutes:g} minutes and do not "
                f"increase size: revenge-style re-entries averaged {mean.display} per trade "
                f"over {n.display} trades."
            )
        case "overtrading":
            return (
                f"Stop for the day after {builder.overtrading_threshold()} trades: trades on "
                f"overtraded days averaged {mean.display} per trade over {n.display} trades."
            )
        case "post_loss":
            return (
                f"Decide before a trade closes whether you will trade again if it loses: the "
                f"{n.display} trades right after a loss averaged {mean.display} per trade."
            )
        case "disposition":
            hold = duration(_winner_hold(builder))
            return (
                f"Close a losing trade by about {hold}, the length of your average winner: "
                f"{n.display} losers held much longer averaged {mean.display} per trade."
            )
        case "oversize":
            return (
                f"Keep planned risk at or below "
                f"{plain_money(risk_limit(builder), builder.currency)}: "
                f"the {n.display} oversized trades averaged {mean.display} per trade."
            )
        case _:
            return f"Review {defn.label}: {n.display} trades averaged {mean.display} per trade."


def _winner_hold(builder: SliceBuilder) -> float:
    winners = builder.pnl > 0
    return float(builder.holding[winners].mean()) if winners.any() else float("nan")


def risk_limit(builder: SliceBuilder) -> float:
    known = np.isfinite(builder.risk) & (builder.risk > 0)
    median = float(np.median(builder.risk[known])) if known.any() else float("nan")
    return median * builder.params.oversize_multiple


# ----- measured patterns -----


def measured_label(name: str) -> str:
    return {
        "fee_drag": "trading costs",
        "early_exit": "early-exit winners",
        "late_exit": "late-exit losers",
    }[name]


def measured_impact_label(name: str) -> str:
    return {
        "fee_drag": "Total trading costs paid",
        "early_exit": "Price left unused on early-exit winners",
        "late_exit": "Loss beyond planned risk",
    }[name]


def measured_what_if(name: str, n: Figure, impact: Figure) -> str:
    if name == "fee_drag":
        return (
            f"You paid {impact.display} in costs over {n.display} trades. "
            f"That is the most cutting costs could recover."
        )
    if name == "early_exit":
        return (
            f"{n.display} winners left {impact.display} of their best price unused. "
            f"That is an upper bound, since no exit catches the exact peak."
        )
    return (
        f"{n.display} losers ran {impact.display} past planned risk. "
        f"That is the most that honoring the stop would have saved."
    )


def measured_rule(builder: SliceBuilder, name: str, n: Figure, impact: Figure) -> str:
    params = builder.params
    if name == "fee_drag":
        return (
            f"Trade fewer, higher-quality setups: costs took {impact.display} over "
            f"{n.display} trades."
        )
    if name == "early_exit":
        return (
            f"Hold winners toward the target: {n.display} winners kept under "
            f"{params.early_capture:.0%} of their best price, leaving {impact.display} unused."
        )
    return (
        f"Honor the stop: {n.display} losing trades ran more than "
        f"{(params.late_overrun - 1):.0%} past planned risk, costing {impact.display} extra."
    )
