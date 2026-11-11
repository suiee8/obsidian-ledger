"""Leak and strength detectors over segments and behavior.

Controls against false positives, in order:
1. A slice is only tested with at least `min_n` trades, and with at least `min_n` trades to
   compare it with.
2. Every test (all segment dimensions and the behavior comparisons) goes into one
   Benjamini-Hochberg family. A slice is reported only when its q-value is below the threshold.
3. Confidence is "high" only with n >= high_n, an interval that excludes zero, and a small
   q-value. Anything weaker is "medium" or "low", and low-confidence slices are never ranked.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

import numpy as np
import numpy.typing as npt

from obsidian_ledger.coach import templates
from obsidian_ledger.coach.effects import (
    EffectInterval,
    SliceStats,
    bootstrap_intervals,
    mean_bootstrap,
    p_value,
    slice_stats,
)
from obsidian_ledger.coach.fmt import figure
from obsidian_ledger.coach.models import (
    Confidence,
    EvidenceTrade,
    Figure,
    Finding,
    FindingKind,
    Interval,
    Unit,
    WhatIf,
)
from obsidian_ledger.coach.params import CoachParams
from obsidian_ledger.coach.slices import MEASURED_PATTERNS, SliceBuilder, SliceDef
from obsidian_ledger.metrics.stats import benjamini_hochberg

Array = npt.NDArray[np.float64]
Mask = npt.NDArray[np.bool_]
MAX_LEADS: Final = 5
LEAD_P: Final = 0.05
OVERLAP: Final = 0.9


@dataclass
class FindingSet:
    leaks: list[Finding] = field(default_factory=list[Finding])
    strengths: list[Finding] = field(default_factory=list[Finding])
    leads: list[Finding] = field(default_factory=list[Finding])
    patterns: list[Finding] = field(default_factory=list[Finding])
    tests_run: int = 0


@dataclass
class _Tested:
    defn: SliceDef
    stats: SliceStats
    p: float | None
    q: float | None = None


def confidence_for(
    n: int,
    excludes_zero: bool,
    q: float | None,
    params: CoachParams,
) -> Confidence:
    """High needs a large n, an interval that excludes zero, and a small q-value."""
    if n < params.min_n or not excludes_zero:
        return "low"
    if n >= params.high_n and q is not None and q < params.q_high:
        return "high"
    return "medium"


def _interval(
    low: float | None,
    high: float | None,
    unit: Unit,
    source: str,
    label: str,
    currency: str,
) -> Interval | None:
    if low is None or high is None:
        return None
    return Interval(
        low=figure(low, unit, f"{source}_low", f"{label} (lower bound)", currency, bootstrap=True),
        high=figure(
            high, unit, f"{source}_high", f"{label} (upper bound)", currency, bootstrap=True
        ),
    )


def _evidence(
    builder: SliceBuilder,
    mask: Mask,
    worst_first: bool,
    key: Array,
    currency: str,
) -> list[EvidenceTrade]:
    """Up to `evidence_limit` trades of the slice, ordered by `key` (worst or best first)."""
    positions = np.flatnonzero(mask)
    if positions.size == 0:
        return []
    order = np.argsort(key[positions], kind="stable")
    if not worst_first:
        order = order[::-1]
    chosen = positions[order[: builder.params.evidence_limit]]
    keys = builder.frame["trade_key"]
    ids = builder.frame["trade_id"]
    symbols = builder.frame["symbol"]
    return [
        EvidenceTrade(
            trade_key=str(keys[int(i)]),
            trade_id=str(ids[int(i)]),
            symbol=str(symbols[int(i)]),
            pnl=figure(
                float(builder.pnl[int(i)]),
                "currency",
                f"trade|{keys[int(i)]}|pnl",
                "Trade net P&L",
                currency,
            ),
        )
        for i in chosen
    ]


def _limit(builder: SliceBuilder, finding_id: str, currency: str) -> Figure | None:
    """The threshold a finding's rule quotes, as a sourced figure."""
    if finding_id != "beh~overtrading":
        return None
    return figure(
        builder.overtrading_threshold(),
        "count",
        "meta|overtrading_limit",
        "Trades per day above which a day counts as overtraded",
        currency,
    )


def _comparison_finding(
    builder: SliceBuilder,
    tested: _Tested,
    interval: EffectInterval | None,
    kind: FindingKind,
    currency: str,
    *,
    passed: bool,
) -> Finding:
    params = builder.params
    defn = tested.defn
    stats = tested.stats
    base = f"slice|{defn.id}"
    excludes_zero = bool(
        interval is not None
        and interval.pnl_low is not None
        and interval.pnl_high is not None
        and (interval.pnl_low > 0 or interval.pnl_high < 0)
    )
    confidence = confidence_for(stats.n, excludes_zero, tested.q, params)
    if defn.mode == "test" and not passed:
        confidence = "low"  # did not clear the false-discovery gate
    n_fig = figure(stats.n, "count", f"{base}|n", "Trades in this slice")
    mean_fig = figure(
        stats.mean_pnl, "currency", f"{base}|mean_pnl", "Average P&L per trade", currency
    )
    effect = figure(
        stats.diff_pnl,
        "currency",
        f"{base}|diff_pnl",
        "Average P&L per trade versus your other trades",
        currency,
    )
    effect_r = (
        figure(stats.diff_r, "R", f"{base}|diff_r", "Average R per trade versus the rest")
        if stats.diff_r is not None
        else None
    )
    total = figure(
        stats.total_pnl, "currency", f"{base}|total_pnl", "Total P&L of this slice", currency
    )
    leak = stats.diff_pnl < 0
    impact_value = -stats.n * stats.diff_pnl if leak else stats.n * stats.diff_pnl
    impact = figure(
        impact_value,
        "currency",
        f"{base}|impact",
        "Net P&L change if the slice matched your other trades"
        if leak
        else "Net P&L these trades added above your other trades",
        currency,
    )
    worst_first = kind != "strength"
    return Finding(
        id=defn.id,
        kind=kind,
        category=defn.category,
        dimension=defn.dimension,
        title=templates.title(defn, kind),
        n=n_fig,
        mean_currency=mean_fig,
        effect_currency=effect,
        effect_r=effect_r,
        total_currency=total,
        interval_currency=_interval(
            interval.pnl_low if interval else None,
            interval.pnl_high if interval else None,
            "currency",
            f"{base}|ci_pnl",
            "Effect per trade",
            currency,
        ),
        interval_r=_interval(
            interval.r_low if interval else None,
            interval.r_high if interval else None,
            "R",
            f"{base}|ci_r",
            "Effect per trade in R",
            currency,
        ),
        confidence=confidence,
        p_value=tested.p,
        q_value=tested.q,
        evidence=_evidence(builder, defn.mask, worst_first, builder.pnl, currency),
        what_if=WhatIf(description=templates.what_if(defn, kind, n_fig, impact), pnl_change=impact),
        rule=templates.rule(builder, defn, kind, n_fig, mean_fig, effect),
        filter=defn.filter,
        limit=_limit(builder, defn.id, currency),
        note=None
        if tested.q is not None
        else "Described for context. It is not ranked as a leak or a strength.",
    )


def _untestable_pattern(
    builder: SliceBuilder, defn: SliceDef, currency: str, reason: str
) -> Finding | None:
    """A behavior slice that exists but cannot be tested, shown as a low-confidence pattern."""
    n = int(defn.mask.sum())
    if n == 0:
        return None
    base = f"slice|{defn.id}"
    pnl = builder.pnl[defn.mask]
    n_fig = figure(n, "count", f"{base}|n", "Trades in this slice")
    mean_fig = figure(
        float(pnl.mean()), "currency", f"{base}|mean_pnl", "Average P&L per trade", currency
    )
    total = figure(
        float(pnl.sum()), "currency", f"{base}|total_pnl", "Total P&L of this slice", currency
    )
    stats = slice_stats(builder.pnl, builder.r, defn.mask, defn.rest)
    diff = stats.diff_pnl if stats is not None else None
    impact_value = None if diff is None else (-n * diff if diff < 0 else n * diff)
    impact = figure(
        impact_value,
        "currency",
        f"{base}|impact",
        "Size of the gap (not tested: too few trades)",
        currency,
    )
    return Finding(
        id=defn.id,
        kind="pattern",
        category=defn.category,
        dimension=defn.dimension,
        title=templates.title(defn, "pattern"),
        n=n_fig,
        mean_currency=mean_fig,
        effect_currency=figure(
            diff, "currency", f"{base}|diff_pnl", "Average P&L per trade versus the rest", currency
        ),
        effect_r=(
            figure(stats.diff_r, "R", f"{base}|diff_r", "Average R per trade versus the rest")
            if stats is not None and stats.diff_r is not None
            else None
        ),
        total_currency=total,
        interval_currency=None,
        interval_r=None,
        confidence="low",
        p_value=None,
        q_value=None,
        evidence=_evidence(builder, defn.mask, True, builder.pnl, currency),
        what_if=WhatIf(description=reason, pnl_change=impact),
        rule=templates.rule(builder, defn, "pattern", n_fig, mean_fig, None),
        filter=defn.filter,
        limit=_limit(builder, defn.id, currency),
        note=reason,
    )


def _measured_finding(builder: SliceBuilder, name: str, currency: str) -> Finding | None:
    """Fee drag, early exits, and late exits. These are measured amounts, not comparisons."""
    found = builder.amounts(name)
    if found is None:
        return None
    mask, amount = found
    n = int(mask.sum())
    if n == 0:
        return None
    params = builder.params
    values = amount[mask]
    total_amount = float(values.sum())
    if total_amount <= 0:
        return None
    gross_win = float(builder.pnl[builder.pnl > 0].sum())
    gross = float(builder.pnl.sum() + total_amount)
    if name == "fee_drag" and gross > 0 and total_amount / gross < params.fee_drag_threshold:
        return None
    if name == "early_exit" and total_amount < params.early_exit_share * gross_win:
        return None
    base = f"slice|beh~{name}"
    mean_amount = float(values.mean())
    interval = mean_bootstrap(values, params.resamples, params.seed)
    n_fig = figure(n, "count", f"{base}|n", "Trades this applies to")
    mean_fig = figure(
        builder.pnl[mask].mean(), "currency", f"{base}|mean_pnl", "Average P&L per trade", currency
    )
    effect = figure(
        -mean_amount, "currency", f"{base}|mean_amount", "Average shortfall per trade", currency
    )
    impact = figure(
        total_amount,
        "currency",
        f"{base}|total_amount",
        templates.measured_impact_label(name),
        currency,
    )
    ci = (
        _interval(
            -interval[1],
            -interval[0],
            "currency",
            f"{base}|ci_amount",
            "Shortfall per trade",
            currency,
        )
        if interval is not None
        else None
    )
    excludes = interval is not None and interval[0] > 0
    if n >= params.high_n and excludes:
        confidence: Confidence = "high"
    elif n >= params.min_n and excludes:
        confidence = "medium"
    else:
        confidence = "low"
    defn = SliceDef(
        id=f"beh~{name}",
        category="behavior",
        dimension=name,
        value="",
        label=templates.measured_label(name),
        mask=mask,
        rest=~mask,
        mode="pattern",
        filter=None,
    )
    return Finding(
        id=defn.id,
        kind="pattern",
        category="behavior",
        dimension=name,
        title=templates.title(defn, "pattern"),
        n=n_fig,
        mean_currency=mean_fig,
        effect_currency=effect,
        effect_r=None,
        total_currency=figure(
            builder.pnl[mask].sum(),
            "currency",
            f"{base}|total_pnl",
            "Total P&L of these trades",
            currency,
        ),
        interval_currency=ci,
        interval_r=None,
        confidence=confidence,
        p_value=None,
        q_value=None,
        evidence=_evidence(builder, mask, True, -amount, currency),
        what_if=WhatIf(
            description=templates.measured_what_if(name, n_fig, impact), pnl_change=impact
        ),
        rule=templates.measured_rule(builder, name, n_fig, impact),
        filter=None,
        note="Measured from your data. It is an upper bound, not a forecast.",
    )


def _overlap(a: Mask, b: Mask) -> float:
    smaller = min(int(a.sum()), int(b.sum()))
    return float((a & b).sum()) / smaller if smaller else 0.0


def find_all(builder: SliceBuilder, currency: str) -> FindingSet:
    """Run every detector and return leaks, strengths, leads, and behavior patterns."""
    params = builder.params
    pnl, r = builder.pnl, builder.r
    result = FindingSet()

    candidates = builder.all_segment_slices() + builder.behavior_slices()
    tested: list[_Tested] = []
    untestable: list[SliceDef] = []
    for defn in candidates:
        n = int(defn.mask.sum())
        rest_n = int(defn.rest.sum())
        if n < params.min_n or rest_n < params.min_n:
            if defn.category == "behavior":
                untestable.append(defn)
            continue
        stats = slice_stats(pnl, r, defn.mask, defn.rest)
        if stats is None:
            continue
        tested.append(_Tested(defn, stats, p_value(pnl, defn.mask, defn.rest)))

    family = [item for item in tested if item.defn.mode == "test" and item.p is not None]
    result.tests_run = len(family)
    adjusted = benjamini_hochberg([item.p for item in family])
    for item, q in zip(family, adjusted, strict=True):
        item.q = q

    selected: list[_Tested] = []
    lead_pool: list[_Tested] = []
    for item in tested:
        if item.defn.mode == "pattern":
            selected.append(item)
        elif item.q is not None and item.q < params.q_threshold:
            selected.append(item)
        elif item.defn.category == "behavior":
            selected.append(item)  # shown as a pattern, not as a leak or a strength
        elif item.p is not None and item.p < LEAD_P:
            lead_pool.append(item)
    lead_pool.sort(key=lambda item: item.p if item.p is not None else 1.0)
    leads = lead_pool[:MAX_LEADS]

    pairs = [(item.defn.mask, item.defn.rest) for item in selected + leads]
    intervals = bootstrap_intervals(pnl, r, pairs, params.resamples, params.seed)
    by_id = {
        item.defn.id: interval for item, interval in zip(selected + leads, intervals, strict=True)
    }

    ranked: list[tuple[Finding, Mask]] = []
    for item in selected:
        interval = by_id[item.defn.id]
        passed = item.q is not None and item.q < params.q_threshold
        if item.defn.mode == "pattern":
            kind: FindingKind = "pattern"
        elif passed:
            kind = "leak" if item.stats.diff_pnl < 0 else "strength"
        else:
            kind = "pattern"
        finding = _comparison_finding(builder, item, interval, kind, currency, passed=passed)
        if item.defn.category == "behavior":
            result.patterns.append(finding)
        if kind in ("leak", "strength") and finding.confidence != "low":
            ranked.append((finding, item.defn.mask))
        elif kind in ("leak", "strength"):
            result.leads.append(finding)
    for item in leads:
        kind = "leak" if item.stats.diff_pnl < 0 else "strength"
        result.leads.append(
            _comparison_finding(builder, item, by_id[item.defn.id], kind, currency, passed=False)
        )
    for defn in untestable:
        reason = (
            f"Only {int(defn.mask.sum())} matching trades, or too few to compare with. "
            f"At least {params.min_n} are needed to test it."
        )
        pattern = _untestable_pattern(builder, defn, currency, reason)
        if pattern is not None:
            result.patterns.append(pattern)
    for name in MEASURED_PATTERNS:
        measured = _measured_finding(builder, name, currency)
        if measured is not None:
            result.patterns.append(measured)

    # High-confidence findings come first. Within a tier, the larger impact comes first.
    tier = {"high": 0, "medium": 1, "low": 2}
    ranked.sort(
        key=lambda pair: (
            tier[pair[0].confidence],
            -(pair[0].what_if.pnl_change.value or 0.0),
            pair[0].id,
        )
    )
    kept: list[tuple[Finding, Mask]] = []
    for finding, mask in ranked:
        duplicate = any(
            other_finding.kind == finding.kind and _overlap(mask, other_mask) >= OVERLAP
            for other_finding, other_mask in kept
        )
        if not duplicate:
            kept.append((finding, mask))
    result.leaks = [f for f, _ in kept if f.kind == "leak"]
    result.strengths = [f for f, _ in kept if f.kind == "strength"]
    result.leads = result.leads[: MAX_LEADS * 2]
    return result
