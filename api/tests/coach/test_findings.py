"""Planted leaks are found and ranked first. Noise produces nothing. Every number recomputes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from obsidian_ledger.coach.fmt import figure
from obsidian_ledger.coach.models import CoachReport, Figure, Unit
from obsidian_ledger.coach.service import CoachService
from obsidian_ledger.coach.sources import Resolver
from obsidian_ledger.coach.verdict import label_for
from obsidian_ledger.metrics.data import Filters
from obsidian_ledger.metrics.engine import AnalysisEngine

from . import synth
from .conftest import Dataset


def test_planted_leaks_are_the_top_three_and_revenge_is_first(planted: Dataset) -> None:
    ids = [finding.id for finding in planted.report.top_leaks]
    assert set(ids[:3]) == synth.PLANTED_IDS
    assert ids[0] == "beh~revenge"  # by far the largest effect


def test_planted_leaks_have_evidence_intervals_and_a_rule(planted: Dataset) -> None:
    for finding in planted.report.top_leaks:
        assert finding.confidence in ("high", "medium")
        assert finding.n.value is not None and finding.n.value >= 30
        assert finding.effect_currency.value is not None and finding.effect_currency.value < 0
        interval = finding.interval_currency
        assert interval is not None and interval.high.value is not None and interval.high.value < 0
        assert 1 <= len(finding.evidence) <= 20
        assert finding.rule.endswith(".") and finding.rule.count(". ") == 0
        assert (finding.what_if.pnl_change.value or 0) > 0


def test_every_finding_respects_the_minimum_sample(planted: Dataset) -> None:
    every = (
        planted.report.top_leaks
        + planted.report.top_strengths
        + planted.report.low_confidence_leads
    )
    for finding in every:
        if finding.category == "segment":
            assert (finding.n.value or 0) >= 30, finding.id


def test_low_confidence_leads_are_never_ranked(planted: Dataset) -> None:
    ranked = {f.id for f in planted.report.top_leaks + planted.report.top_strengths}
    for lead in planted.report.low_confidence_leads:
        assert lead.confidence == "low"
        assert lead.id not in ranked


def test_noise_journal_has_no_leaks_or_strengths(noise: Dataset) -> None:
    assert noise.report.top_leaks == []
    assert noise.report.top_strengths == []
    assert noise.report.verdict.label == "unproven"


def test_noise_journal_has_no_high_confidence_findings(noise: Dataset) -> None:
    every = (
        noise.report.top_leaks
        + noise.report.top_strengths
        + noise.report.low_confidence_leads
        + [p for p in noise.report.behavior_patterns if p.q_value is not None]
    )
    assert [f.id for f in every if f.confidence == "high"] == []


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5, 6])
def test_no_high_confidence_findings_in_random_journals(tmp_path: Path, seed: int) -> None:
    store = synth.load(tmp_path, synth.noise(seed=seed, days=120))
    try:
        report = CoachService(store, AnalysisEngine(store)).report(Filters())
    finally:
        store.close()
    tested = report.top_leaks + report.top_strengths + report.low_confidence_leads
    assert [f.id for f in tested if f.confidence == "high"] == []


def test_planted_verdict_is_negative_and_noise_is_unproven(
    planted: Dataset, noise: Dataset
) -> None:
    assert planted.report.verdict.label == "negative"
    assert planted.report.verdict.interval is not None
    assert (planted.report.verdict.interval.high.value or 0) < 0
    assert noise.report.verdict.label == "unproven"


@pytest.mark.parametrize(
    ("low", "high", "n", "expected"),
    [
        (0.05, 0.30, 100, "edge_present"),
        (-0.10, 0.20, 100, "unproven"),
        (-0.30, -0.05, 100, "negative"),
        (0.05, 0.30, 29, "unproven"),  # a clear interval on too few trades is still unproven
        (None, None, 100, "unproven"),
    ],
)
def test_verdict_rule(low: float | None, high: float | None, n: int, expected: str) -> None:
    assert label_for(low, high, n, 30) == expected


def test_a_small_journal_is_not_tested(tmp_path: Path) -> None:
    store = synth.load(tmp_path, synth.planted(days=3))
    try:
        service = CoachService(store, AnalysisEngine(store))
        report = service.report(Filters())
    finally:
        store.close()
    assert report.status == "too_few_trades"
    assert report.verdict.label == "unproven" and report.verdict.confidence == "low"
    assert report.top_leaks == [] and report.top_strengths == []
    assert any("At least 30" in line or "30 trades" in line for line in report.verdict.lines)


def test_a_filter_with_no_matches_gives_an_empty_report(planted: Dataset) -> None:
    report = planted.service.report(Filters(symbols=("NOPE",)))
    assert report.status == "empty"
    assert report.verdict.label == "unproven"


def test_report_round_trips_through_its_schema(planted: Dataset) -> None:
    again = CoachReport.model_validate_json(planted.report.model_dump_json())
    assert again == planted.report
    assert "properties" in CoachReport.model_json_schema()


# ----- every number recomputes -----


def _figures(node: Any) -> list[Figure]:
    """Every Figure inside a report, found by walking its dumped structure."""
    found: list[Figure] = []
    if isinstance(node, dict):
        if {"value", "unit", "display", "source", "label", "kind"} <= node.keys():
            found.append(Figure.model_validate(node))
        else:
            for child in node.values():  # pyright: ignore[reportUnknownVariableType]
                found.extend(_figures(child))
    elif isinstance(node, list):
        for child in node:  # pyright: ignore[reportUnknownVariableType]
            found.extend(_figures(child))
    return found


def _resolver(data: Dataset) -> Resolver:
    return Resolver(
        data.trades,
        data.service.params,
        starting_equity=data.engine.starting_equity(),
        currency=data.report.base_currency,
    )


@pytest.mark.parametrize("which", ["planted", "noise"])
def test_every_exact_figure_recomputes_from_its_source(
    which: str, planted: Dataset, noise: Dataset
) -> None:
    data = planted if which == "planted" else noise
    resolver = _resolver(data)
    figures = _figures(data.report.model_dump(mode="json"))
    exact = [f for f in figures if f.kind == "exact"]
    assert len(exact) > 50, "the report should carry many sourced figures"
    mismatches: list[str] = []
    for fig in exact:
        recomputed = resolver.resolve(fig.source)
        if fig.value is None or recomputed is None:
            if fig.value != recomputed:
                mismatches.append(f"{fig.source}: report {fig.value}, recomputed {recomputed}")
            continue
        if recomputed != pytest.approx(fig.value, rel=1e-6, abs=1e-6):
            mismatches.append(f"{fig.source}: report {fig.value}, recomputed {recomputed}")
    assert mismatches == []


def test_every_figure_display_matches_its_value(planted: Dataset) -> None:
    for fig in _figures(planted.report.model_dump(mode="json")):
        unit: Unit = fig.unit
        rebuilt = figure(fig.value, unit, fig.source, fig.label, planted.report.base_currency)
        assert fig.display == rebuilt.display, fig.source


def test_sentences_use_the_displays_of_their_figures(planted: Dataset) -> None:
    for finding in planted.report.top_leaks + planted.report.top_strengths:
        if finding.category == "segment":
            assert finding.n.display in finding.rule
            assert finding.mean_currency.display in finding.rule
        assert finding.what_if.pnl_change.display in finding.what_if.description
    for line in planted.report.verdict.lines[:1]:
        assert planted.report.verdict.expectancy.display in line
        assert planted.report.verdict.n.display in line


def test_bootstrap_bounds_bracket_their_point_estimates(planted: Dataset) -> None:
    for finding in planted.report.top_leaks + planted.report.top_strengths:
        interval = finding.interval_currency
        assert interval is not None
        low, high = interval.low.value, interval.high.value
        point = finding.effect_currency.value
        assert low is not None and high is not None and point is not None
        assert low <= point <= high, finding.id
        assert interval.low.kind == "bootstrap" and interval.high.kind == "bootstrap"


def test_the_bootstrap_is_reproducible(planted: Dataset) -> None:
    again = planted.service.report(Filters(), force=True)
    first = planted.report.top_leaks[0].interval_currency
    second = again.top_leaks[0].interval_currency
    assert first is not None and second is not None
    assert first.low.value == second.low.value and first.high.value == second.high.value
