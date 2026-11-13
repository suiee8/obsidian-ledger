"""Chart series and the workspace endpoints: paging, sorting, filters, edits, and saved views."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
import pytest
from fastapi.testclient import TestClient

from obsidian_ledger.main import create_app
from obsidian_ledger.metrics.views import (
    daily_series,
    edge_radar,
    equity_series,
    lttb_indices,
    r_histogram,
    weekday_hour_heatmap,
)
from obsidian_ledger.settings import Settings

SAMPLES = Path(__file__).resolve().parents[3] / "samples"
ZERO_KEY = "0" * 64


def _frame(rows: list[dict[str, Any]]) -> pl.DataFrame:
    exits = [datetime.fromisoformat(r["exit"]).replace(tzinfo=None) for r in rows]
    entries = [datetime.fromisoformat(r["entry"]).replace(tzinfo=None) for r in rows]
    return pl.DataFrame(
        {
            "pnl": [float(r["pnl"]) for r in rows],
            "exit_time": pl.Series(exits, dtype=pl.Datetime("us")),
            "entry_time": pl.Series(entries, dtype=pl.Datetime("us")),
            "exit_day": [e.date() for e in exits],
            "weekday": [e.weekday() for e in entries],
            "hour_utc": [e.hour for e in entries],
            "r_multiple": [r.get("r") for r in rows],
            "setup": [r.get("setup") for r in rows],
            "plan_followed": [r.get("plan") for r in rows],
            "planned_risk": [r.get("risk") for r in rows],
        },
        schema_overrides={
            "pnl": pl.Float64,
            "r_multiple": pl.Float64,
            "planned_risk": pl.Float64,
            "plan_followed": pl.Boolean,
            "setup": pl.String,
        },
    )


def test_lttb_keeps_endpoints_and_the_spike() -> None:
    x = np.arange(100, dtype=np.float64)
    y = np.zeros(100)
    y[37] = 50.0  # a single spike must survive downsampling
    picked = lttb_indices(x, y, 10)
    assert len(picked) == 10
    assert picked[0] == 0 and picked[-1] == 99
    assert 37 in picked.tolist()
    assert np.all(np.diff(picked) > 0)


def test_lttb_returns_everything_when_under_threshold() -> None:
    picked = lttb_indices(np.arange(5.0), np.arange(5.0), 10)
    assert picked.tolist() == [0, 1, 2, 3, 4]


def test_equity_series_matches_cumulative_pnl_and_drawdown() -> None:
    frame = _frame(
        [
            {"pnl": 100, "entry": "2026-01-06T10:00:00", "exit": "2026-01-06T11:00:00"},
            {"pnl": -50, "entry": "2026-01-07T10:00:00", "exit": "2026-01-07T11:00:00"},
            {"pnl": -100, "entry": "2026-01-08T10:00:00", "exit": "2026-01-08T11:00:00"},
        ]
    )
    series = equity_series(frame, 1000.0)
    equities = [p["equity"] for p in series["points"]]
    drawdowns = [p["drawdown"] for p in series["points"]]
    assert equities == [1100.0, 1050.0, 950.0]
    assert drawdowns == [0.0, -50.0, -150.0]
    assert series["downsampled"] is False


def test_daily_series_groups_by_exit_day() -> None:
    frame = _frame(
        [
            {"pnl": 100, "entry": "2026-01-06T10:00:00", "exit": "2026-01-06T11:00:00"},
            {"pnl": -30, "entry": "2026-01-06T12:00:00", "exit": "2026-01-06T13:00:00"},
            {"pnl": 5, "entry": "2026-01-07T10:00:00", "exit": "2026-01-07T11:00:00"},
        ]
    )
    days = daily_series(frame)
    assert days == [
        {"day": "2026-01-06", "pnl": 70.0, "trades": 2},
        {"day": "2026-01-07", "pnl": 5.0, "trades": 1},
    ]


def test_r_histogram_counts_every_finite_value() -> None:
    frame = _frame(
        [
            {"pnl": 1, "entry": "2026-01-06T10:00:00", "exit": "2026-01-06T11:00:00", "r": r}
            for r in [-1.0, -0.5, 0.0, 0.5, 1.0, 2.0, None]
        ]
    )
    result = r_histogram(frame, bins=4)
    assert result["n"] == 6
    assert sum(b["count"] for b in result["bins"]) == 6
    assert result["median"] == pytest.approx(0.25)


def test_heatmap_cells_match_trade_counts() -> None:
    frame = _frame(
        [
            {"pnl": 10, "entry": "2026-01-06T10:00:00", "exit": "2026-01-06T11:00:00"},
            {"pnl": -4, "entry": "2026-01-06T10:30:00", "exit": "2026-01-06T11:30:00"},
            {"pnl": 3, "entry": "2026-01-07T14:00:00", "exit": "2026-01-07T15:00:00"},
        ]
    )
    cells = {(c["weekday"], c["hour"]): c for c in weekday_hour_heatmap(frame)}
    assert cells[(1, 10)] == {"weekday": 1, "hour": 10, "trades": 2, "pnl": 6.0, "expectancy": 3.0}
    assert cells[(2, 14)]["trades"] == 1


def test_radar_scales_each_axis_across_setups() -> None:
    frame = _frame(
        [
            {
                "pnl": 10,
                "entry": "2026-01-06T10:00:00",
                "exit": "2026-01-06T11:00:00",
                "setup": "breakout",
                "r": 1.0,
                "plan": True,
                "risk": 10.0,
            },
            {
                "pnl": -5,
                "entry": "2026-01-06T12:00:00",
                "exit": "2026-01-06T13:00:00",
                "setup": "fomo",
                "r": -0.5,
                "plan": False,
                "risk": 10.0,
            },
        ]
    )
    radar = edge_radar(frame, min_n=1)
    by_name = {row["setup"]: row for row in radar["setups"]}
    assert by_name["breakout"]["normalized"][2] == 100.0  # best expectancy in R
    assert by_name["fomo"]["normalized"][2] == 0.0
    assert by_name["breakout"]["raw"]["discipline"] == 1.0
    assert by_name["fomo"]["raw"]["discipline"] == 0.0


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    settings = Settings.model_validate({"data_dir": str(tmp_path / "data")})
    app = create_app(settings)
    client = TestClient(app, base_url="http://127.0.0.1")
    body = (SAMPLES / "ibkr_executions.csv").read_bytes()
    preview = client.post(
        "/api/imports/preview",
        params={"filename": "ibkr.csv"},
        content=body,
        headers={"content-type": "application/octet-stream"},
    ).json()
    assert client.post(f"/api/imports/{preview['preview_id']}/commit", json={}).status_code == 200
    return client


def test_trade_page_returns_total_and_sorted_rows(client: TestClient) -> None:
    body = client.get(
        "/api/trades/page", params={"limit": 2, "sort": "net_pnl_base", "dir": "asc"}
    ).json()
    assert body["total"] == 4
    assert len(body["rows"]) == 2
    assert body["rows"][0]["symbol"] == "MNQ"  # -124.80 is the smallest net P&L
    assert body["rows"][0]["exit_time"].endswith("Z")


def test_trade_page_filters_by_symbol(client: TestClient) -> None:
    body = client.get("/api/trades/page", params={"symbol": ["AAPL", "MSFT"]}).json()
    assert body["total"] == 2
    assert {row["symbol"] for row in body["rows"]} == {"AAPL", "MSFT"}


def test_trade_page_rejects_unsortable_columns(client: TestClient) -> None:
    response = client.get("/api/trades/page", params={"sort": "notes; DROP TABLE trades"})
    assert response.status_code == 422


def test_trade_page_offset_moves_through_the_table(client: TestClient) -> None:
    first = client.get("/api/trades/page", params={"limit": 3, "offset": 0}).json()["rows"]
    last = client.get("/api/trades/page", params={"limit": 3, "offset": 3}).json()["rows"]
    assert len(first) == 3 and len(last) == 1
    assert first[0]["trade_key"] != last[0]["trade_key"]


def test_patch_edits_notes_tags_and_emotion_and_is_visible_on_reload(client: TestClient) -> None:
    key = client.get("/api/trades/page", params={"limit": 1}).json()["rows"][0]["trade_key"]
    response = client.patch(
        f"/api/trades/{key}",
        json={"notes": "held through the news", "tags": "news,patience", "emotion": "calm"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["notes"] == "held through the news"
    assert body["tags"] == "news,patience"
    reloaded = client.get(f"/api/trades/{key}").json()
    assert reloaded["emotion"] == "calm"


def test_patch_clears_notes_with_null(client: TestClient) -> None:
    key = client.get("/api/trades/page", params={"limit": 1}).json()["rows"][0]["trade_key"]
    client.patch(f"/api/trades/{key}", json={"notes": "x"})
    assert client.patch(f"/api/trades/{key}", json={"notes": None}).json()["notes"] == ""


def test_patch_refuses_derived_fields(client: TestClient) -> None:
    key = client.get("/api/trades/page", params={"limit": 1}).json()["rows"][0]["trade_key"]
    response = client.patch(f"/api/trades/{key}", json={"net_pnl": 999})
    assert response.status_code == 422


def test_patch_unknown_trade_is_404(client: TestClient) -> None:
    assert client.patch(f"/api/trades/{ZERO_KEY}", json={"notes": "x"}).status_code == 404
    assert client.get(f"/api/trades/{ZERO_KEY}").status_code == 404


def test_edit_changes_dataset_version_so_caches_refresh(client: TestClient) -> None:
    before = client.get("/api/dashboard").json()["dataset_version"]
    key = client.get("/api/trades/page", params={"limit": 1}).json()["rows"][0]["trade_key"]
    client.patch(f"/api/trades/{key}", json={"emotion": "fomo"})
    after = client.get("/api/dashboard").json()["dataset_version"]
    assert before != after


def test_filter_options_list_distinct_values(client: TestClient) -> None:
    options = client.get("/api/filter-options").json()
    assert options["symbols"] == ["AAPL", "EUR.USD", "MNQ", "MSFT"]
    assert options["accounts"] == ["U1234567"]


def test_saved_views_round_trip(client: TestClient) -> None:
    created = client.post(
        "/api/views", json={"name": "Losers", "config": {"sort": "net_pnl_base", "dir": "asc"}}
    )
    assert created.status_code == 201
    names = [view["name"] for view in client.get("/api/views").json()]
    assert names == ["Losers"]
    assert client.delete("/api/views/Losers").status_code == 204
    assert client.delete("/api/views/Losers").status_code == 404


def test_dashboard_bundles_every_panel(client: TestClient) -> None:
    body = client.get("/api/dashboard").json()
    for key in ("report", "equity", "daily", "r_histogram", "heatmap", "radar", "findings"):
        assert key in body
    assert body["report"]["core"]["trades"] == 4
    assert len(body["equity"]["points"]) == 4
    assert body["findings"]["slices_tested"] >= 0


def test_empty_dashboard_has_no_panels_data(tmp_path: Path) -> None:
    client = TestClient(
        create_app(Settings.model_validate({"data_dir": str(tmp_path / "empty")})),
        base_url="http://127.0.0.1",
    )
    body = client.get("/api/dashboard").json()
    assert body["equity"]["points"] == []
    assert body["report"]["sample"]["trades"] == 0


_ = UTC
