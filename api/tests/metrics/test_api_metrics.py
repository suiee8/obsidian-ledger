"""End to end: import the IBKR sample through the API, then check the analysis endpoints."""

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from obsidian_ledger.main import create_app
from obsidian_ledger.settings import Settings

SAMPLES = Path(__file__).resolve().parents[3] / "samples"
# Net P&L of the four IBKR round trips in samples/ibkr_executions.csv.
IBKR_NET = [22.0, 261.0, -124.8, -37.25]


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    settings = Settings.model_validate({"data_dir": str(tmp_path / "data")})
    return TestClient(create_app(settings), base_url="http://127.0.0.1")


def _import(client: TestClient, name: str, options: dict[str, Any] | None = None) -> None:
    body = (SAMPLES / name).read_bytes()
    preview = client.post(
        "/api/imports/preview",
        params={"filename": name},
        content=body,
        headers={"content-type": "application/octet-stream"},
    ).json()
    response = client.post(f"/api/imports/{preview['preview_id']}/commit", json=options or {})
    assert response.status_code == 200, response.text


def test_metrics_report_matches_the_imported_trades(client: TestClient) -> None:
    _import(client, "ibkr_executions.csv")
    report = client.get("/api/metrics", params={"bootstrap": 200, "paths": 500}).json()
    core = report["core"]
    assert core["trades"] == 4
    assert core["net_pnl"] == pytest.approx(sum(IBKR_NET))
    assert core["win_rate"] == pytest.approx(0.5)
    assert core["profit_factor"] == pytest.approx((22 + 261) / (124.8 + 37.25))
    assert report["sample"]["low_confidence"] is True
    assert any("low confidence" in note for note in report["caveats"])
    assert report["risk"]["daily_ratios"]["available"] is False
    assert report["statistics"]["monte_carlo"]["paths"] == 500
    assert 0 <= report["discipline"]["score"] is None or report["discipline"]["score"] >= 0


def test_starting_equity_enables_daily_ratios_and_drawdown_percentage(client: TestClient) -> None:
    _import(client, "ibkr_executions.csv", {"starting_equity": 10000.0})
    report = client.get("/api/metrics", params={"bootstrap": 200, "paths": 500}).json()
    assert report["risk"]["daily_ratios"]["available"] is True
    assert report["risk"]["drawdown"]["max_drawdown_pct"] is not None


def test_cache_is_invalidated_by_a_new_import(client: TestClient) -> None:
    _import(client, "ibkr_executions.csv")
    first = client.get("/api/metrics", params={"bootstrap": 200, "paths": 500}).json()
    second = client.get("/api/metrics", params={"bootstrap": 200, "paths": 500}).json()
    assert first["dataset_version"] == second["dataset_version"]
    _import(client, "ibkr_executions.csv", {"starting_equity": 5000.0})
    third = client.get("/api/metrics", params={"bootstrap": 200, "paths": 500}).json()
    assert third["dataset_version"] != first["dataset_version"]
    assert third["sample"]["starting_equity"] == 5000.0


def test_segments_by_symbol_and_bad_dimension(client: TestClient) -> None:
    _import(client, "ibkr_executions.csv")
    table = client.get("/api/segments", params={"by": "symbol", "min_n": 1}).json()
    symbols = {slice_["value"] for slice_ in table["slices"]}
    assert symbols == {"AAPL", "EUR.USD", "MNQ", "MSFT"}
    refused = client.get("/api/segments", params={"by": "moon_phase"})
    assert refused.status_code == 422


def test_simulator_endpoint_reports_changes_and_warning(client: TestClient) -> None:
    _import(client, "ibkr_executions.csv")
    body = {"rules": {"exclude_symbols": ["MSFT"]}, "resamples": 200}
    result = client.post("/api/simulate", json=body).json()
    assert result["trades"] == 4
    assert result["removed_trades"] == 1
    assert result["simulated"]["net_pnl"] == pytest.approx(sum(IBKR_NET) + 37.25)
    assert "overstated" in result["warning"]


def test_simulator_rejects_unknown_rule_fields(client: TestClient) -> None:
    response = client.post("/api/simulate", json={"rules": {"moon": True}})
    assert response.status_code == 422


def test_empty_selection_returns_a_clear_message(client: TestClient) -> None:
    _import(client, "ibkr_executions.csv")
    report = client.get("/api/metrics", params={"symbol": "NOPE"}).json()
    assert report["sample"]["trades"] == 0
    assert report["caveats"] == ["No trades match these filters."]
