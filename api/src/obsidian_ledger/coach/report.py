"""Build the Coach report from filtered trades. Pure and deterministic: no I/O, no randomness
beyond the seeded bootstrap, and no LLM."""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import numpy as np
import polars as pl

from obsidian_ledger.coach.findings import FindingSet, find_all
from obsidian_ledger.coach.fmt import figure, plain_money
from obsidian_ledger.coach.models import (
    ActionDay,
    Caveat,
    ChecklistItem,
    CoachReport,
    Figure,
    Finding,
    RiskItem,
    Verdict,
)
from obsidian_ledger.coach.params import CoachParams
from obsidian_ledger.coach.slices import SliceBuilder
from obsidian_ledger.coach.verdict import build_verdict
from obsidian_ledger.metrics.behavior import analyze_behavior
from obsidian_ledger.metrics.core import core_metrics
from obsidian_ledger.metrics.risk import drawdown, kelly_upper_bound, risk_per_trade, sqn

TOP = 3


def _ignore(_stage: str) -> None:
    """Progress callback used when the caller does not want updates."""


def key_figures(builder: SliceBuilder, starting: float | None, currency: str) -> dict[str, Figure]:
    """Headline numbers that are compared between reports."""
    core = core_metrics(builder.pnl, builder.costs, builder.r)
    by_exit = builder.frame.sort(["exit_time", "trade_key"])
    dd = drawdown(by_exit["pnl"].to_numpy(), starting)
    return {
        "trades": figure(core.get("trades"), "count", "core|trades", "Trades", currency),
        "net_pnl": figure(core.get("net_pnl"), "currency", "core|net_pnl", "Net P&L", currency),
        "expectancy": figure(
            core.get("expectancy"), "currency", "core|expectancy", "Average P&L per trade", currency
        ),
        "expectancy_r": figure(
            core.get("expectancy_r"), "R", "core|expectancy_r", "Average R per trade", currency
        ),
        "win_rate": figure(core.get("win_rate"), "ratio", "core|win_rate", "Win rate", currency),
        "max_drawdown": figure(
            dd["max_drawdown"], "currency", "risk|max_drawdown", "Largest drawdown", currency
        ),
    }


def _risk_review(builder: SliceBuilder, starting: float | None, currency: str) -> list[RiskItem]:
    core = core_metrics(builder.pnl, builder.costs, builder.r)
    by_exit = builder.frame.sort(["exit_time", "trade_key"])
    dd = drawdown(by_exit["pnl"].to_numpy(), starting)
    behavior = analyze_behavior(builder.frame, 10, 10.0, 0.5)
    risk = risk_per_trade(builder.risk)
    items: list[RiskItem] = [
        RiskItem(
            key="max_drawdown",
            title="Largest drawdown",
            figure=figure(
                dd["max_drawdown"], "currency", "risk|max_drawdown", "Largest drawdown", currency
            ),
            note="The deepest fall from a running equity peak, in exit order.",
        ),
        RiskItem(
            key="largest_loss",
            title="Worst single trade",
            figure=figure(
                core.get("largest_loss"), "currency", "core|largest_loss", "Worst trade", currency
            ),
            note="Compare it with the planned risk you set for a normal trade.",
        ),
        RiskItem(
            key="longest_loss_streak",
            title="Longest losing streak",
            figure=figure(
                behavior.get("longest_loss_streak"),
                "count",
                "behavior|longest_loss_streak",
                "Longest losing streak",
            ),
            note="Trades in a row that closed at a loss.",
        ),
        RiskItem(
            key="profit_factor",
            title="Profit factor",
            figure=figure(
                core.get("profit_factor"), "number", "core|profit_factor", "Profit factor", currency
            ),
            note="Gross wins divided by gross losses. Above 1 means wins outweigh losses.",
        ),
        RiskItem(
            key="sqn",
            title="System quality number",
            figure=figure(sqn(builder.r), "number", "risk|sqn", "SQN"),
            note="Square root of trades times mean R over the spread of R. Needs planned risk.",
        ),
    ]
    if risk["mean"] is not None:
        items.append(
            RiskItem(
                key="risk_cv",
                title="Planned-risk consistency",
                figure=figure(
                    risk["coefficient_of_variation"],
                    "number",
                    "risk|risk_cv",
                    "Spread of planned risk",
                ),
                note="Spread of planned risk relative to its average. Lower means steadier sizing.",
            )
        )
    kelly = kelly_upper_bound(core.get("win_rate"), core.get("payoff_ratio"))
    if kelly is not None:
        items.append(
            RiskItem(
                key="kelly_upper_bound",
                title="Kelly fraction (upper bound)",
                figure=figure(kelly, "ratio", "risk|kelly", "Kelly upper bound"),
                note="An upper bound if the measured edge were real and stable. Not a size.",
            )
        )
    return items


def _checklist(
    builder: SliceBuilder, leaks: list[Finding], patterns: list[Finding], currency: str
) -> list[ChecklistItem]:
    params = builder.params
    items: list[ChecklistItem] = []
    for leak in leaks[:TOP]:
        if leak.category == "segment":
            items.append(
                ChecklistItem(
                    question=f"Is this one of the {_label(leak)}?",
                    reason=(
                        f"These {leak.n.display} trades averaged {leak.mean_currency.display} per "
                        f"trade, {leak.effect_currency.display} against your others."
                    ),
                    finding_id=leak.id,
                    figure=leak.mean_currency,
                )
            )
    by_id = {pattern.id: pattern for pattern in patterns}
    if "beh~revenge" in by_id and by_id["beh~revenge"].confidence != "low":
        item = by_id["beh~revenge"]
        items.append(
            ChecklistItem(
                question=(
                    f"Did your last trade lose, and did it close less than "
                    f"{params.revenge_gap_minutes:g} minutes ago?"
                ),
                reason=f"Revenge-style re-entries averaged {item.mean_currency.display} per trade.",
                finding_id=item.id,
                figure=item.mean_currency,
            )
        )
    if "beh~overtrading" in by_id and by_id["beh~overtrading"].confidence != "low":
        item = by_id["beh~overtrading"]
        items.append(
            ChecklistItem(
                question=f"Have you already taken {builder.overtrading_threshold()} trades today?",
                reason=(
                    f"Trades on overtraded days averaged {item.mean_currency.display} per trade."
                ),
                finding_id=item.id,
                figure=item.limit or item.mean_currency,
            )
        )
    known = np.isfinite(builder.risk) & (builder.risk > 0)
    if known.any():
        median = float(np.median(builder.risk[known]))
        risk_fig = figure(
            median, "currency", "risk|median_planned_risk", "Median planned risk", currency
        )
        items.append(
            ChecklistItem(
                question=(
                    f"Is your planned risk set, and at or below "
                    f"{plain_money(median * params.oversize_multiple, currency)}?"
                ),
                reason=f"Your median planned risk is {risk_fig.display.lstrip('+')}.",
                finding_id=None,
                figure=risk_fig,
            )
        )
    items.append(
        ChecklistItem(
            question="Is your stop placed before you enter?",
            reason="Losses beyond the planned risk are the most avoidable loss in the data.",
            finding_id=None,
            figure=None,
        )
    )
    return items[:7]


def _label(finding: Finding) -> str:
    return finding.title.split(" underperform")[0].split(" outperform")[0].lower()


def _action_plan(leaks: list[Finding], strengths: list[Finding]) -> list[ActionDay]:
    first = leaks[0] if leaks else None
    second = leaks[1] if len(leaks) > 1 else None
    strength = strengths[0] if strengths else None
    return [
        ActionDay(
            day=1,
            focus="Review the evidence",
            task=(
                f"Open the {len(first.evidence)} worst trades behind '{first.title}' and write one "
                f"line on what you were thinking at each entry."
                if first
                else "Open your five worst trades and note what you were thinking at each entry."
            ),
            finding_id=first.id if first else None,
        ),
        ActionDay(
            day=2,
            focus="Write the rule",
            task=first.rule
            if first
            else "Write one rule you will follow for every trade this week.",
            finding_id=first.id if first else None,
        ),
        ActionDay(
            day=3,
            focus="Trade it with a filter",
            task=(
                "Apply the finding as a filter before each session, and skip the trades it selects."
                if first and first.filter
                else "Run the checklist below before each entry. Skip it if any answer is yes."
            ),
            finding_id=first.id if first else None,
        ),
        ActionDay(
            day=4,
            focus="Second leak",
            task=second.rule
            if second
            else "Tag every trade with a setup and an emotion so the next report can test them.",
            finding_id=second.id if second else None,
        ),
        ActionDay(
            day=5,
            focus="Protect the edge",
            task=strength.rule
            if strength
            else "Keep your size steady and log whether you followed your plan.",
            finding_id=strength.id if strength else None,
        ),
        ActionDay(
            day=6,
            focus="Dry run the checklist",
            task="Go through the pre-trade checklist on paper for every trade you take today.",
            finding_id=None,
        ),
        ActionDay(
            day=7,
            focus="Measure the change",
            task="Import the week's trades and compare the new report with this one.",
            finding_id=None,
        ),
    ]


def _caveats(
    builder: SliceBuilder, found: FindingSet, excluded_no_fx: int, currency: str
) -> list[Caveat]:
    params = builder.params
    notes: list[Caveat] = []
    trades = builder.count
    if trades < params.min_n:
        notes.append(
            Caveat(
                text=(
                    f"Only {trades} trades in this selection. "
                    f"Nothing below {params.min_n} trades is tested."
                ),
                figure=figure(trades, "count", "core|trades", "Trades"),
            )
        )
    notes.append(
        Caveat(
            text=(
                f"{found.tests_run} comparisons were run together. Results are filtered with "
                f"Benjamini-Hochberg at q below {params.q_threshold:g}, which keeps about "
                f"{params.q_threshold:.0%} of reported findings expected to be false."
            ),
            figure=figure(found.tests_run, "count", "meta|tests_run", "Comparisons run"),
        )
    )
    notes.append(
        Caveat(text="Impacts use the trades the findings came from, so they are likely overstated.")
    )
    no_risk = int((~(np.isfinite(builder.risk) & (builder.risk > 0))).sum())
    if no_risk:
        notes.append(
            Caveat(
                text=f"{no_risk} trades have no planned risk, so their R multiple is unavailable.",
                figure=figure(
                    no_risk, "count", "meta|no_risk_trades", "Trades without planned risk"
                ),
            )
        )
    if not np.isfinite(builder.mfe).any():
        notes.append(
            Caveat(text="No trade has MFE or MAE, so early-exit and late-exit checks were skipped.")
        )
    if excluded_no_fx:
        notes.append(
            Caveat(
                text=(
                    f"{excluded_no_fx} trades were left out because no FX rate "
                    f"converts them to {currency}."
                ),
                figure=figure(excluded_no_fx, "count", "meta|excluded_no_fx", "Trades left out"),
            )
        )
    return notes


def build_report(
    trades: pl.DataFrame,
    *,
    filters: dict[str, Any],
    filter_key: str,
    dataset_version: str,
    params: CoachParams,
    currency: str,
    starting_equity: float | None,
    excluded_no_fx: int = 0,
    progress: Callable[[str], None] | None = None,
) -> CoachReport:
    """Build the full report. `trades` is the prepared (filtered) frame from the metrics engine.

    `progress` is called with "computing", "finding", and "writing" as each stage starts.
    """
    started = time.perf_counter()
    notify: Callable[[str], None] = progress if progress is not None else _ignore
    notify("computing")
    trade_count = trades.height
    generated = datetime.now(UTC).isoformat(timespec="seconds")
    common: dict[str, Any] = {
        "report_id": "",
        "dataset_version": dataset_version,
        "filter_key": filter_key,
        "filters": filters,
        "generated_at": generated,
        "base_currency": currency,
        "params": params.as_dict(),
    }
    if trade_count == 0:
        return _empty(common, params, currency, "empty", started)
    builder = SliceBuilder(trades, params, currency)
    if trade_count < params.min_n:
        return _empty(common, params, currency, "too_few_trades", started, builder, starting_equity)

    notify("finding")
    found = find_all(builder, currency)
    notify("writing")
    top_leaks = found.leaks[:TOP]
    top_strengths = found.strengths[:TOP]
    verdict = build_verdict(builder.pnl, builder.r, top_leaks, top_strengths, params, currency)
    return CoachReport(
        status="ok",
        sample_trades=figure(trade_count, "count", "core|trades", "Trades analysed"),
        verdict=verdict,
        top_leaks=top_leaks,
        top_strengths=top_strengths,
        low_confidence_leads=found.leads,
        behavior_patterns=found.patterns,
        risk_review=_risk_review(builder, starting_equity, currency),
        action_plan=_action_plan(top_leaks, top_strengths),
        checklist=_checklist(builder, top_leaks, found.patterns, currency),
        caveats=_caveats(builder, found, excluded_no_fx, currency),
        seconds_to_build=time.perf_counter() - started,
        key_figures=key_figures(builder, starting_equity, currency),
        **common,
    )


def _empty(
    common: dict[str, Any],
    params: CoachParams,
    currency: str,
    status: str,
    started: float,
    builder: SliceBuilder | None = None,
    starting_equity: float | None = None,
) -> CoachReport:
    trades = builder.count if builder is not None else 0
    reason = (
        "There are no trades in this selection."
        if status == "empty"
        else f"Only {trades} trades. At least {params.min_n} are needed before anything is tested."
    )
    n_fig = figure(trades, "count", "core|trades", "Trades analysed")
    verdict = Verdict(
        label="unproven",
        headline="Unproven",
        lines=[
            reason,
            "No leaks or strengths were tested.",
            "Import more trades, then run the report again.",
        ],
        confidence="low",
        basis="sample too small to measure",
        expectancy=figure(None, "R", "core|expectancy_r", "Average result per trade"),
        interval=None,
        n=n_fig,
    )
    key = key_figures(builder, starting_equity, currency) if builder is not None else {}
    return CoachReport(
        status=status,  # type: ignore[arg-type]
        sample_trades=n_fig,
        verdict=verdict,
        top_leaks=[],
        top_strengths=[],
        low_confidence_leads=[],
        behavior_patterns=[],
        risk_review=[],
        action_plan=[],
        checklist=[],
        caveats=[Caveat(text=reason, figure=n_fig)],
        seconds_to_build=time.perf_counter() - started,
        key_figures=key,
        **common,
    )
