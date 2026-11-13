"""Schemas for the Coach report. Every number is a Figure that names where it came from.

A Figure's `source` is a reference that `sources.resolve` can recompute from the trade data, so
a test (and later the LLM phase) can check any number in the report against the data.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Unit = Literal["currency", "R", "count", "ratio", "number", "seconds", "score", "text"]
Confidence = Literal["high", "medium", "low"]
FindingKind = Literal["leak", "strength", "pattern"]
Category = Literal["segment", "behavior"]
VerdictLabel = Literal["edge_present", "unproven", "negative", "cannot_be_assessed"]
ReportStatus = Literal["ok", "too_few_trades", "empty", "cannot_be_assessed"]


class Strict(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Figure(Strict):
    """One number, how to show it, and where it came from.

    `kind` is "exact" when the value is a deterministic function of the data (it can be
    recomputed exactly) and "bootstrap" for resampled interval bounds (it is reproducible with the
    same seed and must bracket the point estimate).
    """

    value: float | None
    unit: Unit
    display: str
    source: str
    label: str
    kind: Literal["exact", "bootstrap"] = "exact"


class Interval(Strict):
    low: Figure
    high: Figure
    level: float = 0.95
    method: str = "percentile bootstrap, resampling trades with replacement"


class EvidenceTrade(Strict):
    trade_key: str
    trade_id: str
    symbol: str
    pnl: Figure


class WhatIf(Strict):
    description: str
    pnl_change: Figure
    in_sample_note: str = (
        "Measured on the same trades the finding came from, so it is likely overstated."
    )


class FilterHint(Strict):
    """Filters that select this finding's trades, when the app's filters can express them."""

    symbols: list[str] = Field(default_factory=list[str])
    setups: list[str] = Field(default_factory=list[str])
    sides: list[str] = Field(default_factory=list[str])
    accounts: list[str] = Field(default_factory=list[str])
    tag: str | None = None


class Finding(Strict):
    id: str
    kind: FindingKind
    category: Category
    dimension: str
    title: str
    n: Figure
    mean_currency: Figure
    effect_currency: Figure
    effect_r: Figure | None
    total_currency: Figure
    interval_currency: Interval | None
    interval_r: Interval | None
    confidence: Confidence
    p_value: float | None
    q_value: float | None
    evidence: list[EvidenceTrade]
    what_if: WhatIf
    rule: str
    filter: FilterHint | None
    note: str | None = None
    # A threshold the rule quotes, such as the trades-per-day limit for overtrading.
    limit: Figure | None = None


class Verdict(Strict):
    label: VerdictLabel
    headline: str
    lines: list[str]
    confidence: Confidence
    basis: str
    expectancy: Figure
    interval: Interval | None
    n: Figure


class RiskItem(Strict):
    key: str
    title: str
    figure: Figure
    note: str


class ActionDay(Strict):
    day: int
    focus: str
    task: str
    finding_id: str | None


class ChecklistItem(Strict):
    question: str
    reason: str
    finding_id: str | None
    figure: Figure | None


class Caveat(Strict):
    text: str
    figure: Figure | None = None


class ChangeItem(Strict):
    key: str
    label: str
    previous: Figure
    current: Figure


class Change(Strict):
    previous_report_id: str
    previous_generated_at: str
    metrics: list[ChangeItem]
    new_finding_ids: list[str]
    resolved_finding_ids: list[str]


class CoachReport(Strict):
    schema_version: Literal[1] = 1
    report_id: str
    dataset_version: str
    filter_key: str
    filters: dict[str, Any]
    generated_at: str
    status: ReportStatus
    base_currency: str
    sample_trades: Figure
    verdict: Verdict
    top_leaks: list[Finding]
    top_strengths: list[Finding]
    low_confidence_leads: list[Finding]
    behavior_patterns: list[Finding]
    risk_review: list[RiskItem]
    action_plan: list[ActionDay]
    checklist: list[ChecklistItem]
    caveats: list[Caveat]
    key_figures: dict[str, Figure] = Field(default_factory=dict[str, Figure])
    change_vs_previous: Change | None = None
    seconds_to_build: float
    params: dict[str, Any]
