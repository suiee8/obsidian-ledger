"""The trade-position endpoint must agree with the table pages the UI reads."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from obsidian_ledger.main import create_app
from obsidian_ledger.settings import Settings

from . import synth


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    settings = Settings.model_validate({"data_dir": str(tmp_path / "data")})
    api = TestClient(create_app(settings), base_url="http://127.0.0.1")
    preview = api.post(
        "/api/imports/preview",
        params={"filename": "j.csv"},
        content=synth.planted(days=60).encode("utf-8"),
    ).json()
    assert api.post(f"/api/imports/{preview['preview_id']}/commit", json={}).status_code == 200
    return api


@pytest.mark.parametrize(("sort", "direction"), [("exit_time", "desc"), ("net_pnl_base", "asc")])
def test_position_matches_the_row_in_the_page(
    client: TestClient, sort: str, direction: str
) -> None:
    params = {"sort": sort, "dir": direction, "limit": 500}
    rows = client.get("/api/trades/page", params=params).json()["rows"]
    for index in (0, 7, len(rows) - 1):
        key = rows[index]["trade_key"]
        found = client.get(f"/api/trades/{key}/position", params={"sort": sort, "dir": direction})
        assert found.json()["index"] == index


def test_position_respects_filters_and_misses_hidden_trades(client: TestClient) -> None:
    rows = client.get("/api/trades/page", params={"limit": 500}).json()["rows"]
    symbol = rows[0]["symbol"]
    other = next(row for row in rows if row["symbol"] != symbol)
    hidden = client.get(f"/api/trades/{other['trade_key']}/position", params={"symbol": symbol})
    assert hidden.status_code == 200 and hidden.json()["index"] is None
    shown = client.get(f"/api/trades/{rows[0]['trade_key']}/position", params={"symbol": symbol})
    assert shown.json()["index"] is not None


def test_position_rejects_a_bad_key_and_sort(client: TestClient) -> None:
    assert client.get("/api/trades/xyz/position").status_code == 422
    key = "0" * 64
    assert (
        client.get(f"/api/trades/{key}/position", params={"sort": "notes; DROP"}).status_code == 422
    )
