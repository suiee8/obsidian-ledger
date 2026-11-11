"""Phase 5 checks: ranking across seeds, sourced figures and prose, cold speed, finding selection.

These sit on top of test_findings.py. They close the gaps that file leaves: bootstrap bounds,
numbers written inside sentences, a cold (not pre-warmed) report at 10,000 trades, and the trades
behind each finding.
"""

from __future__ import annotations

import re
import shutil
import time
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

from obsidian_ledger.coach.models import CoachReport, Figure, Finding
from obsidian_ledger.coach.service import CoachService
from obsidian_ledger.coach.sources import Resolver
from obsidian_ledger.main import create_app
from obsidian_ledger.metrics.data import Filters
from obsidian_ledger.metrics.engine import AnalysisEngine
from obsidian_ledger.settings import Settings

from . import synth
from .conftest import Dataset

# ----- ranking and noise across seeds -----


SEEDS = range(1, 11)


def test_planted_leaks_are_found_and_ranked_first_across_seeds(tmp_path: Path) -> None:
    """Over ten random journals with the same three planted leaks.

    Revenge and the losing hour are large effects and always rank. Overtrading is only six heavy
    days, so its p-value survives the false-discovery correction in most journals but not all. When
    it does not, it must still be reported with a negative gap as a behavior pattern, never absent.
    """
    all_three_on_top = 0
    hour_ranked = 0
    for seed in SEEDS:
        folder = tmp_path / f"s{seed}"
        folder.mkdir()
        store = synth.load(folder, synth.planted(seed=seed, days=170))
        try:
            report = CoachService(store, AnalysisEngine(store)).report(Filters())
        finally:
            store.close()
        ranked = [finding.id for finding in report.top_leaks]
        assert ranked[0] == "beh~revenge", (seed, ranked)
        hour = f"seg~hour~{synth.LOSING_HOUR}"
        hour_ranked += hour in ranked
        if hour not in ranked:
            # A broader slice that contains the hour (a session, say) may be ranked in its place,
            # because overlapping findings are merged. Then it must be a leak, not a gap.
            assert any(f.category == "segment" and f.kind == "leak" for f in report.top_leaks), (
                seed,
                ranked,
            )
        seen = {f.id: f for f in report.top_leaks + report.behavior_patterns}
        overtrading = seen.get("beh~overtrading")
        assert overtrading is not None, (seed, "overtrading was not reported at all")
        assert (overtrading.effect_currency.value or 0) < 0, seed
        all_three_on_top += set(ranked[:3]) == synth.PLANTED_IDS
    assert hour_ranked >= 8, f"the losing hour ranked in only {hour_ranked} of 10"
    assert all_three_on_top >= 7, f"all three ranked first in only {all_three_on_top} of 10"


@pytest.mark.parametrize("seed", [7, 8, 9, 10, 11, 12, 13, 14])
def test_random_journals_have_no_high_confidence_finding_or_verdict(
    tmp_path: Path, seed: int
) -> None:
    store = synth.load(tmp_path, synth.noise(seed=seed, days=120))
    try:
        report = CoachService(store, AnalysisEngine(store)).report(Filters())
    finally:
        store.close()
    every = report.top_leaks + report.top_strengths + report.low_confidence_leads
    assert [f.id for f in every if f.confidence == "high"] == []
    # An unproven verdict is the honest answer when nothing is there.
    assert report.verdict.label != "negative" or report.verdict.confidence != "high"


# ----- every figure has a source, and each one recomputes -----


def _walk(node: Any, out: list[Figure], texts: list[tuple[str, str]], path: str = "") -> None:
    """Collect every Figure and every sentence in a dumped report."""
    skip = {"id", "finding_id", "filter_key", "dataset_version", "generated_at", "report_id"}
    skip |= {"trade_key", "trade_id", "symbol", "filters", "params", "schema_version", "unit"}
    skip |= {"source", "kind", "method", "level", "status", "base_currency", "in_sample_note"}
    skip |= {
        "previous_report_id",
        "previous_generated_at",
        "new_finding_ids",
        "resolved_finding_ids",
    }
    if isinstance(node, dict):
        if {"value", "unit", "display", "source", "label", "kind"} <= node.keys():
            out.append(Figure.model_validate(node))
            return
        for key, child in node.items():  # pyright: ignore[reportUnknownVariableType]
            if key not in skip:
                _walk(child, out, texts, f"{path}.{key}")
    elif isinstance(node, list):
        for index, child in enumerate(cast(list[Any], node)):
            _walk(child, out, texts, f"{path}[{index}]")
    elif isinstance(node, str):
        texts.append((path, node))


def _collect(report: CoachReport) -> tuple[list[Figure], list[tuple[str, str]]]:
    figures: list[Figure] = []
    texts: list[tuple[str, str]] = []
    _walk(report.model_dump(mode="json"), figures, texts)
    return figures, texts


def _filtered(data: Dataset, filters: Filters) -> tuple[CoachReport, Resolver]:
    report = data.service.report(filters)
    _version, prepared = data.engine.trades_for(filters)
    resolver = Resolver(
        prepared.frame,
        data.service.params,
        starting_equity=data.engine.starting_equity(),
        excluded_no_fx=prepared.excluded_no_fx,
        currency=report.base_currency,
    )
    return report, resolver


def _cases(planted: Dataset, noise: Dataset) -> list[tuple[str, Dataset, Filters]]:
    first_day: date = planted.trades["exit_day"].min()  # type: ignore[assignment]
    return [
        ("planted", planted, Filters()),
        ("noise", noise, Filters()),
        ("planted, long only", planted, Filters(sides=("long",))),
        ("planted, one day", planted, Filters(date_from=first_day, date_to=first_day)),
        ("no match", planted, Filters(symbols=("NOPE",))),
    ]


def test_every_figure_recomputes_including_bootstrap_bounds(
    planted: Dataset, noise: Dataset
) -> None:
    bootstrap_seen = 0
    for name, data, filters in _cases(planted, noise):
        report, resolver = _filtered(data, filters)
        figures, _texts = _collect(report)
        assert figures, name
        mismatches: list[str] = []
        for fig in figures:
            assert fig.source and "|" in fig.source, f"{name}: figure without a source: {fig.label}"
            bootstrap_seen += fig.kind == "bootstrap"
            recomputed = resolver.resolve(fig.source)
            if fig.value is None or recomputed is None:
                if fig.value is None and fig.display == "n/a":
                    continue  # withheld on purpose (too few trades): no number is shown
                if fig.value != recomputed:
                    mismatches.append(f"{fig.source}: report {fig.value}, recomputed {recomputed}")
            elif recomputed != pytest.approx(fig.value, rel=1e-6, abs=1e-6):
                mismatches.append(f"{fig.source}: report {fig.value}, recomputed {recomputed}")
        assert mismatches == [], name
    assert bootstrap_seen > 10, "the bounds should have been recomputed too"


def test_figure_counts_by_kind(planted: Dataset) -> None:
    figures, _ = _collect(planted.report)
    kinds = {fig.kind for fig in figures}
    assert kinds == {"exact", "bootstrap"}
    assert len(figures) > 100


NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _numbers(text: str) -> set[float]:
    return {float(token.replace(",", "")) for token in NUMBER.findall(text)}


def _allowed_numbers(report: CoachReport, figures: list[Figure]) -> set[float]:
    """Numbers a sentence may contain: those shown by some figure, and the documented settings."""
    allowed: set[float] = set()
    for fig in figures:
        allowed |= _numbers(fig.display) | _numbers(fig.label)
    for value in report.params.values():
        if isinstance(value, int | float) and not isinstance(value, bool):
            allowed.add(float(value))
            allowed.add(float(value) * 100)  # a share such as 0.35 is written as 35%
    allowed |= {95.0, 100.0}  # the interval level, and "100%"
    for finding in _findings(report):
        allowed |= _numbers(finding.id)  # an hour or a count the finding is named for
    return allowed


def test_no_number_in_a_sentence_lacks_a_figure(planted: Dataset, noise: Dataset) -> None:
    """Every number written in prose is shown by a sourced figure or is a documented setting."""
    unsourced: list[str] = []
    for name, data, filters in _cases(planted, noise):
        report, _resolver = _filtered(data, filters)
        figures, texts = _collect(report)
        allowed = _allowed_numbers(report, figures)
        for path, text in texts:
            # Numbers inside a finding's own id (an hour, say) are named by that finding.
            for number in _numbers(text):
                if number in allowed:
                    continue
                unsourced.append(f"{name} {path}: {number:g} in {text!r}")
    assert unsourced == []


def _findings(report: CoachReport) -> list[Finding]:
    return (
        report.top_leaks
        + report.top_strengths
        + report.low_confidence_leads
        + report.behavior_patterns
    )


# ----- speed: a cold report at 10,000 trades -----


@pytest.fixture(scope="module")
def big_data(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    """A database with about 10,000 trades. Each test copies it, so each one starts cold."""
    folder = tmp_path_factory.mktemp("big") / "data"
    store = synth.load(folder.parent, synth.planted(seed=21, days=1400))
    count = store.count_trades()
    store.close()
    assert count >= 10_000
    yield folder.parent / "data"


def _cold_client(source: Path, destination: Path) -> TestClient:
    shutil.copytree(source, destination)
    return TestClient(create_app(Settings.model_validate({"data_dir": str(destination)})))


def test_a_cold_report_over_http_takes_under_two_seconds(big_data: Path, tmp_path: Path) -> None:
    client = _cold_client(big_data, tmp_path / "cold")
    started = time.perf_counter()
    response = client.post("/api/coach/report", json={})
    elapsed = time.perf_counter() - started
    body = response.json()
    assert response.status_code == 200 and body["status"] == "ok"
    assert int(body["sample_trades"]["value"]) >= 10_000
    assert elapsed < 2.0, (
        f"cold report took {elapsed:.2f}s (building it took {body['seconds_to_build']:.2f}s)"
    )


def test_a_cold_stream_with_all_six_steps_takes_under_two_seconds(
    big_data: Path, tmp_path: Path
) -> None:
    client = _cold_client(big_data, tmp_path / "cold")
    started = time.perf_counter()
    response = client.get("/api/coach/stream")
    elapsed = time.perf_counter() - started
    text = response.text
    for step in ("reading", "mapping", "cleaning", "computing", "finding", "writing", "done"):
        assert f'"step": "{step}"' in text, step
    assert elapsed < 2.0, f"cold stream took {elapsed:.2f}s"


# ----- the trades behind each finding -----


@pytest.fixture(scope="module")
def app_client(tmp_path_factory: pytest.TempPathFactory) -> TestClient:
    settings = Settings.model_validate({"data_dir": str(tmp_path_factory.mktemp("sel") / "data")})
    client = TestClient(create_app(settings))
    preview = client.post(
        "/api/imports/preview",
        params={"filename": "journal.csv"},
        content=synth.planted(days=120).encode("utf-8"),
    ).json()
    assert client.post(f"/api/imports/{preview['preview_id']}/commit", json={}).status_code == 200
    return client


@pytest.mark.parametrize("filters", [{}, {"sides": ["long"]}], ids=["all trades", "long only"])
def test_each_finding_opens_exactly_its_own_trades(
    app_client: TestClient, filters: dict[str, Any]
) -> None:
    report = CoachReport.model_validate(
        app_client.post("/api/coach/report", json={"filters": filters}).json()
    )
    findings = _findings(report)
    assert {"beh~revenge", "beh~overtrading"} <= {f.id for f in findings}
    assert any(f.id.startswith("seg~hour~") for f in findings)
    for finding in findings:
        picked = app_client.post(
            "/api/coach/findings/selection", json={"filters": filters, "finding_id": finding.id}
        )
        assert picked.status_code == 200, (finding.id, picked.text)
        selection = picked.json()
        # The count is the finding's own n, and the Trades table shows that many.
        assert selection["count"] == int(finding.n.value or -1), finding.id
        page = app_client.get(
            "/api/trades/page",
            params={"selection": selection["selection_id"], "limit": 1, **_query(filters)},
        ).json()
        assert page["total"] == selection["count"], finding.id


def _query(filters: dict[str, Any]) -> dict[str, Any]:
    return {"side": filters["sides"]} if "sides" in filters else {}


def test_a_revenge_selection_contains_only_trades_after_a_loss(app_client: TestClient) -> None:
    selection = app_client.post(
        "/api/coach/findings/selection", json={"finding_id": "beh~revenge"}
    ).json()
    page = app_client.get(
        "/api/trades/page", params={"selection": selection["selection_id"], "limit": 500}
    ).json()
    assert page["total"] > 0
    assert all(row["trade_key"] for row in page["rows"])


def test_an_unknown_finding_is_a_404_and_a_bad_id_a_422(app_client: TestClient) -> None:
    missing = app_client.post("/api/coach/findings/selection", json={"finding_id": "seg~hour~99"})
    assert missing.status_code == 404
    assert "not in this data" in missing.json()["detail"]
    assert (
        app_client.post("/api/coach/findings/selection", json={"finding_id": "x"}).status_code
        == 422
    )
    nothing = app_client.post(
        "/api/coach/findings/selection",
        json={"finding_id": "beh~revenge", "filters": {"symbols": ["NOPE"]}},
    )
    assert nothing.status_code == 404
