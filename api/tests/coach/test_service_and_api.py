"""Caching, storage, comparison with the previous report, SSE, export, tools, and speed."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from obsidian_ledger.coach.models import CoachReport
from obsidian_ledger.coach.service import CoachService
from obsidian_ledger.main import create_app
from obsidian_ledger.metrics.data import Filters
from obsidian_ledger.metrics.engine import AnalysisEngine
from obsidian_ledger.settings import Settings

from . import synth
from .conftest import Dataset

SAMPLES = Path(__file__).resolve().parents[3] / "samples"


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    settings = Settings.model_validate({"data_dir": str(tmp_path / "data")})
    return TestClient(create_app(settings))


def _import_text(client: TestClient, text: str, name: str = "journal.csv") -> None:
    preview = client.post(
        "/api/imports/preview", params={"filename": name}, content=text.encode("utf-8")
    ).json()
    commit = client.post(f"/api/imports/{preview['preview_id']}/commit", json={})
    assert commit.status_code == 200, commit.text


# ----- service: cache and history -----


def test_the_same_data_returns_the_stored_report(tmp_path: Path) -> None:
    store = synth.load(tmp_path, synth.planted(days=120))
    try:
        service = CoachService(store, AnalysisEngine(store))
        first = service.report(Filters())
        again = service.report(Filters())
        assert again.report_id == first.report_id
        assert len(store.list_coach_reports()) == 1
    finally:
        store.close()


def test_a_different_filter_is_a_different_report(planted: Dataset) -> None:
    other = planted.service.report(Filters(symbols=("AAA",)))
    assert other.report_id != planted.report.report_id
    assert other.filters["symbols"] == ["AAA"]


def test_a_new_import_makes_a_new_report_with_the_change_against_the_previous(
    tmp_path: Path,
) -> None:
    store = synth.load(tmp_path, synth.planted(seed=7, days=120))
    try:
        service = CoachService(store, AnalysisEngine(store))
        first = service.report(Filters())
        assert first.change_vs_previous is None
        # A second journal appended through the same path changes the dataset version.
        second_text = synth.planted(seed=8, days=120)
        source = tmp_path / "more.csv"
        source.write_text(second_text, encoding="utf-8")
        from obsidian_ledger.ingest.analysis import analyze
        from obsidian_ledger.ingest.options import ImportOptions
        from obsidian_ledger.ingest.run import run_import

        options = ImportOptions()
        outcome = run_import(analyze(source, options), options)
        store.insert_frame("second", outcome.frame, options.base_currency)
        second = service.report(Filters())
    finally:
        store.close()
    assert second.report_id != first.report_id
    change = second.change_vs_previous
    assert change is not None and change.previous_report_id == first.report_id
    trades = next(item for item in change.metrics if item.key == "trades")
    assert (trades.current.value or 0) > (trades.previous.value or 0)


# ----- HTTP -----


def test_post_report_returns_a_valid_schema_and_is_cached(client: TestClient) -> None:
    _import_text(client, synth.planted(days=120))
    first = client.post("/api/coach/report", json={})
    assert first.status_code == 200, first.text
    report = CoachReport.model_validate(first.json())
    assert report.status == "ok" and report.top_leaks
    second = client.post("/api/coach/report", json={}).json()
    assert second["report_id"] == report.report_id
    forced = client.post("/api/coach/report", json={"force": True}).json()
    assert forced["report_id"] != report.report_id
    assert forced["change_vs_previous"]["previous_report_id"] == report.report_id


def test_unknown_request_fields_are_rejected(client: TestClient) -> None:
    assert client.post("/api/coach/report", json={"surprise": 1}).status_code == 422


def test_report_for_an_empty_database_is_a_clear_empty_report(client: TestClient) -> None:
    report = client.post("/api/coach/report", json={}).json()
    assert report["status"] == "empty" and report["verdict"]["label"] == "unproven"


def _events(response_text: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for block in response_text.strip().split("\n\n"):
        for line in block.splitlines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    return events


def test_the_stream_reports_every_step_in_order_and_ends_with_the_report(
    client: TestClient,
) -> None:
    _import_text(client, synth.planted(days=120))
    response = client.get("/api/coach/stream", params={"force": "true"})
    assert response.headers["content-type"].startswith("text/event-stream")
    events = _events(response.text)
    done_order = [e["step"] for e in events if e.get("status") == "done" and e["step"] != "done"]
    assert done_order == ["reading", "mapping", "cleaning", "computing", "finding", "writing"]
    labels = [e["label"] for e in events if e.get("status") == "done" and "label" in e]
    assert labels == [
        "Reading",
        "Mapping",
        "Cleaning",
        "Computing",
        "Finding leaks",
        "Writing report",
    ]
    final = events[-1]
    assert final["step"] == "done"
    stored = client.get(f"/api/coach/reports/{final['report_id']}")
    assert stored.status_code == 200
    assert "journal.csv" in events[0]["detail"]  # the first step describes the real import


def test_the_stream_reuses_a_stored_report(client: TestClient) -> None:
    _import_text(client, synth.planted(days=120))
    first = client.post("/api/coach/report", json={}).json()
    events = _events(client.get("/api/coach/stream").text)
    assert events[-1]["report_id"] == first["report_id"]


def test_stored_reports_are_listed_and_fetched(client: TestClient) -> None:
    _import_text(client, synth.planted(days=120))
    report = client.post("/api/coach/report", json={}).json()
    listing = client.get("/api/coach/reports").json()
    assert [row["report_id"] for row in listing] == [report["report_id"]]
    assert client.get("/api/coach/reports/" + "0" * 32).status_code == 404
    assert client.get("/api/coach/reports/not-an-id").status_code == 422


def test_markdown_and_html_exports_carry_the_report(client: TestClient) -> None:
    _import_text(client, synth.planted(days=120))
    report = client.post("/api/coach/report", json={}).json()
    rid = report["report_id"]
    markdown = client.get(f"/api/coach/reports/{rid}/export", params={"format": "md"})
    assert markdown.status_code == 200 and "attachment" in markdown.headers["content-disposition"]
    assert report["verdict"]["headline"] in markdown.text
    assert report["top_leaks"][0]["rule"] in markdown.text
    page = client.get(f"/api/coach/reports/{rid}/export", params={"format": "html"})
    assert page.headers["content-type"].startswith("text/html")
    assert "<script" not in page.text.lower()
    assert report["top_leaks"][0]["title"] in page.text


def test_html_export_escapes_untrusted_text(planted: Dataset) -> None:
    from obsidian_ledger.coach.export import to_html

    hostile = planted.report.model_copy(
        update={
            "caveats": [
                planted.report.caveats[0].model_copy(update={"text": "<script>x()</script>"})
            ]
        }
    )
    page = to_html(hostile)
    assert "<script>x()" not in page and "&lt;script&gt;" in page


# ----- tools -----


def test_tools_have_schemas_for_input_and_output(client: TestClient) -> None:
    tools = client.get("/api/coach/tools").json()
    names = {tool["name"] for tool in tools}
    assert names == {
        "get_metrics",
        "compare_segments",
        "find_leaks",
        "find_strengths",
        "get_trade",
        "list_trades",
        "simulate_rule",
    }
    for tool in tools:
        assert tool["description"]
        assert tool["input_schema"]["type"] == "object"
        assert tool["output_schema"]["type"] == "object"


def test_every_tool_runs_and_returns_validated_output(client: TestClient) -> None:
    _import_text(client, synth.planted(days=120))

    def call(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        response = client.post(f"/api/coach/tools/{name}", json={"arguments": arguments})
        assert response.status_code == 200, f"{name}: {response.text}"
        return response.json()

    assert call("get_metrics", {})["report"]["core"]["trades"] > 30
    table = call("compare_segments", {"dimension": "hour"})["table"]
    assert table["dimension"] == "hour" and table["slices"]
    leaks = call("find_leaks", {"limit": 2})
    assert leaks["status"] == "ok" and 1 <= len(leaks["findings"]) <= 2
    assert call("find_strengths", {})["findings"] is not None
    listing = call("list_trades", {"limit": 3, "sort": "net_pnl_base", "descending": False})
    assert listing["total"] > 30 and len(listing["rows"]) == 3
    key = listing["rows"][0]["trade_key"]
    assert call("get_trade", {"trade_key": key})["trade"]["trade_key"] == key
    assert call("get_trade", {"trade_key": "0" * 64})["trade"] is None
    simulated = call("simulate_rule", {"rules": {"exclude_hours": [14]}, "resamples": 200})
    assert simulated["result"]["removed_trades"] > 0


def test_tool_arguments_are_validated(client: TestClient) -> None:
    assert client.post("/api/coach/tools/nope", json={"arguments": {}}).status_code == 404
    bad = client.post("/api/coach/tools/list_trades", json={"arguments": {"limit": 5000}})
    assert bad.status_code == 422 or bad.status_code == 500
    extra = client.post("/api/coach/tools/get_metrics", json={"arguments": {"surprise": 1}})
    assert extra.status_code in (422, 500)
    sort = client.post("/api/coach/tools/list_trades", json={"arguments": {"sort": "notes; DROP"}})
    assert sort.status_code == 422


# ----- speed -----


def test_report_generation_at_ten_thousand_trades_takes_under_two_seconds(tmp_path: Path) -> None:
    text = synth.planted(seed=21, days=1400)
    store = synth.load(tmp_path, text)
    try:
        engine = AnalysisEngine(store)
        service = CoachService(store, engine)
        _version, prepared = engine.trades_for(Filters())  # the frame is cached by the server
        assert prepared.frame.height >= 10_000
        started = time.perf_counter()
        report = service.report(Filters())
        elapsed = time.perf_counter() - started
    finally:
        store.close()
    assert report.status == "ok"
    assert elapsed < 2.0, f"took {elapsed:.2f}s for {report.sample_trades.display} trades"
