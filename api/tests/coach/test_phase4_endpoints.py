"""Phase 4 endpoints: explore points, behavior timeline, simulator, selections, settings, wipe.

Every test uses a throwaway data directory. Nothing touches the real ledger folder.
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

from obsidian_ledger.main import create_app
from obsidian_ledger.settings import Settings
from obsidian_ledger.store.db import Store

from . import synth
from .conftest import Dataset

WIPE = "delete all my data"


@pytest.fixture(scope="module")
def app_client(tmp_path_factory: pytest.TempPathFactory) -> TestClient:
    settings = Settings.model_validate({"data_dir": str(tmp_path_factory.mktemp("p4") / "data")})
    client = TestClient(create_app(settings), base_url="http://127.0.0.1")
    text = synth.planted(days=120)
    preview = client.post(
        "/api/imports/preview", params={"filename": "journal.csv"}, content=text.encode("utf-8")
    ).json()
    commit = client.post(f"/api/imports/{preview['preview_id']}/commit", json={})
    assert commit.status_code == 200, commit.text
    return client


# ----- explore -----


def test_explore_points_are_columnar_and_match_the_metrics(app_client: TestClient) -> None:
    explore = app_client.get("/api/explore").json()
    report = app_client.get("/api/metrics").json()
    points = explore["points"]
    assert points["n"] == report["core"]["trades"]
    for column in ("t", "pnl", "r", "mae", "mfe", "hold", "symbol"):
        assert len(points[column]) == points["n"]
    assert sum(points["pnl"]) == pytest.approx(report["core"]["net_pnl"], abs=1.0)
    assert explore["fee_drag"]["drag"] == pytest.approx(report["core"]["fee_drag"])
    assert explore["streaks"]["histogram"]
    assert points["t"] == sorted(points["t"])


def test_longest_streaks_match_the_behavior_metrics(app_client: TestClient) -> None:
    explore = app_client.get("/api/explore").json()["streaks"]
    behavior = app_client.get("/api/metrics").json()["behavior"]
    assert explore["longest_wins"][0]["length"] == behavior["longest_win_streak"]
    assert explore["longest_losses"][0]["length"] == behavior["longest_loss_streak"]


# ----- behavior timeline -----


def test_timeline_totals_agree_with_the_discipline_inputs(app_client: TestClient) -> None:
    timeline = app_client.get("/api/behavior/timeline").json()
    behavior = app_client.get("/api/metrics").json()["behavior"]
    assert timeline["totals"]["revenge_trades"] == behavior["revenge"]["flagged_trades"]
    assert timeline["totals"]["overtraded_days"] == behavior["overtrading"]["overtraded_days"]
    assert sum(day["trades"] for day in timeline["days"]) == timeline["trades"]
    assert sum(day["revenge"] for day in timeline["days"]) == timeline["totals"]["revenge_trades"]
    groups = {group["key"]: group for group in timeline["post_loss"]}
    assert groups["after_win"]["trades"] == behavior["after_win"]["trades"]
    assert groups["after_loss_calm"]["trades"] + groups["revenge"]["trades"] <= (
        behavior["after_loss"]["trades"] + groups["revenge"]["trades"]
    )


def test_discipline_exposes_its_weights(app_client: TestClient) -> None:
    discipline = app_client.get("/api/metrics").json()["discipline"]
    assert sum(discipline["weights"].values()) == pytest.approx(1.0)
    assert set(discipline["weights"]) == set(discipline["components"])


# ----- simulator -----


def _simulate(client: TestClient, **extra: Any) -> dict[str, Any]:
    body = {"rules": {"max_trades_per_day": 3}, **extra}
    response = client.post("/api/simulate", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def test_fast_simulation_has_no_interval_and_the_full_one_does(app_client: TestClient) -> None:
    fast = _simulate(app_client, intervals=False)
    full = _simulate(app_client, intervals=True)
    assert fast["intervals"] == "pending"
    assert fast["change"]["expectancy_per_trade_ci95"] is None
    assert full["intervals"] == "ready"
    low, high = full["change"]["expectancy_per_trade_ci95"]
    assert low <= full["change"]["expectancy_per_trade"] <= high
    assert fast["change"]["expectancy_per_trade"] == pytest.approx(
        full["change"]["expectancy_per_trade"]
    )
    assert full["change"]["net_pnl_ci95"][0] == pytest.approx(low * full["trades"])


def test_simulation_curves_end_at_the_net_pnl_figures(app_client: TestClient) -> None:
    result = _simulate(app_client)
    curves = result["curves"]
    assert curves["x"][-1] == result["trades"]
    assert curves["baseline"][-1] == pytest.approx(result["baseline"]["net_pnl"], abs=0.01)
    assert curves["simulated"][-1] == pytest.approx(result["simulated"]["net_pnl"], abs=0.01)
    assert len(curves["x"]) <= 300


def test_overfit_warning_is_always_present_and_explains_itself(app_client: TestClient) -> None:
    result = _simulate(app_client, rules={"exclude_hours": [14], "max_trades_per_day": 2})
    assert result["warning"]
    assert result["overfit"]["level"] == "high"
    assert result["overfit"]["active_rules"] == 2
    empty = _simulate(app_client, rules={})
    assert empty["overfit"]["level"] == "standard"
    assert empty["warning"]


# ----- selections and the Trades table -----


def test_a_brushed_range_becomes_a_selection_the_table_can_show(app_client: TestClient) -> None:
    losers = app_client.post(
        "/api/selections", json={"bounds": [{"field": "pnl", "high": -50.0}]}
    ).json()
    assert losers["count"] > 0
    page = app_client.get(
        "/api/trades/page", params={"selection": losers["selection_id"], "limit": 500}
    ).json()
    assert page["total"] == losers["count"]
    assert all(row["net_pnl_base"] <= -50.0 for row in page["rows"])


def test_two_bounds_must_both_hold(app_client: TestClient) -> None:
    both = app_client.post(
        "/api/selections",
        json={"bounds": [{"field": "pnl", "high": 0.0}, {"field": "hold", "high": 600}]},
    ).json()
    one = app_client.post(
        "/api/selections", json={"bounds": [{"field": "pnl", "high": 0.0}]}
    ).json()
    assert 0 < both["count"] <= one["count"]


def test_an_unknown_selection_is_a_clear_404(app_client: TestClient) -> None:
    response = app_client.get("/api/trades/page", params={"selection": "0" * 32})
    assert response.status_code == 404
    assert "expired" in response.json()["detail"]


# ----- settings, templates, export, wipe -----


def test_settings_roundtrip_and_privacy_defaults(tmp_path: Path) -> None:
    client = TestClient(
        create_app(Settings.model_validate({"data_dir": str(tmp_path / "d")})),
        base_url="http://127.0.0.1",
    )
    start = client.get("/api/settings").json()
    assert start["privacy"] == {
        "aggregates_only": True,
        "include_notes": False,
        "include_trade_rows": False,
    }
    assert start["starting_equity"] is None
    changed = client.put("/api/settings", json={"starting_equity": 25000}).json()
    assert changed["starting_equity"] == 25000
    # The master switch wins: turning it on clears the other two.
    forced = client.put(
        "/api/settings",
        json={"privacy": {"aggregates_only": True, "include_notes": True}},
    ).json()
    assert forced["privacy"]["include_notes"] is False
    opened = client.put(
        "/api/settings",
        json={"privacy": {"aggregates_only": False, "include_notes": True}},
    ).json()
    assert opened["privacy"] == {
        "aggregates_only": False,
        "include_notes": True,
        "include_trade_rows": False,
    }
    cleared = client.put("/api/settings", json={"starting_equity": None}).json()
    assert cleared["starting_equity"] is None
    assert cleared["privacy"]["include_notes"] is True  # untouched by the equity change


def test_privacy_changes_do_not_invalidate_the_analysis_cache(app_client: TestClient) -> None:
    first = app_client.get("/api/metrics").json()["dataset_version"]
    app_client.put("/api/settings", json={"privacy": {"aggregates_only": True}})
    assert app_client.get("/api/metrics").json()["dataset_version"] == first


def test_template_rename_and_delete(tmp_path: Path) -> None:
    app = create_app(Settings.model_validate({"data_dir": str(tmp_path / "d")}))
    client = TestClient(app, base_url="http://127.0.0.1")
    store = cast(Store, app.state.store)
    store.save_template("abc123", "Old name", {"Time": "entry_time"})
    renamed = client.patch("/api/templates/abc123", json={"name": "My broker"})
    assert renamed.status_code == 200
    assert client.get("/api/templates").json()[0]["name"] == "My broker"
    assert client.delete("/api/templates/abc123").status_code == 204
    assert client.get("/api/templates").json() == []
    assert client.delete("/api/templates/abc123").status_code == 404


def test_export_contains_everything(app_client: TestClient) -> None:
    response = app_client.get("/api/export")
    assert response.status_code == 200
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    names = set(archive.namelist())
    assert {"trades.csv", "imports.json", "saved_views.json", "settings.json"} <= names
    assert any(name.startswith("raw/") for name in names)
    rows = archive.read("trades.csv").decode().strip().splitlines()
    assert len(rows) - 1 == app_client.get("/api/metrics").json()["core"]["trades"]
    assert json.loads(archive.read("settings.json"))["preferences"] is not None


def test_wipe_needs_the_exact_phrase_and_removes_everything(tmp_path: Path) -> None:
    data = tmp_path / "data"
    client = TestClient(
        create_app(Settings.model_validate({"data_dir": str(data)})),
        base_url="http://127.0.0.1",
    )
    text = synth.planted(days=40)
    preview = client.post(
        "/api/imports/preview", params={"filename": "j.csv"}, content=text.encode("utf-8")
    ).json()
    client.post(f"/api/imports/{preview['preview_id']}/commit", json={})
    client.put("/api/settings", json={"starting_equity": 1000})
    assert client.get("/api/metrics").json()["core"]["trades"] > 0

    refused = client.post("/api/wipe", json={"confirm": "wipe"})
    assert refused.status_code == 422
    assert client.get("/api/metrics").json()["core"]["trades"] > 0

    done = client.post("/api/wipe", json={"confirm": WIPE})
    assert done.status_code == 200
    assert done.json()["removed"]["trades"] > 0
    assert client.get("/api/metrics").json()["core"]["trades"] == 0
    assert client.get("/api/settings").json()["starting_equity"] is None
    assert client.get("/api/imports").json() == []
    assert not any((data / "raw").iterdir())
    assert not any((data / "rejected").iterdir())


def test_explore_on_an_empty_selection(planted: Dataset) -> None:
    from obsidian_ledger.metrics.data import Filters

    result = planted.engine.explore(Filters(symbols=("NOPE",)))
    assert result["points"]["n"] == 0
    assert result["streaks"]["runs"] == 0
    assert planted.engine.behavior_timeline(Filters(symbols=("NOPE",)), _params())["days"] == []


def _params() -> Any:
    from obsidian_ledger.metrics.engine import Params

    return Params()
