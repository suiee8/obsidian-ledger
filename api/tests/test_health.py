from pathlib import Path

import duckdb
import pytest
from fastapi.testclient import TestClient

from obsidian_ledger.llm.config import LLMConfig
from obsidian_ledger.main import create_app
from obsidian_ledger.settings import Settings


def _defaults() -> Settings:
    # model_validate applies field defaults without reading .env or LEDGER_* variables.
    return Settings.model_validate({})


def test_health() -> None:
    client = TestClient(create_app(_defaults()), base_url="http://127.0.0.1")
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["service"] == "obsidian-ledger"
    assert isinstance(response.json()["version"], str)
    assert response.headers["x-content-type-options"] == "nosniff"


def test_ready_is_degraded_when_provider_circuit_is_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = create_app(Settings(data_dir=tmp_path))
    monkeypatch.setattr(app.state.llm, "config", lambda: LLMConfig(provider="zai", model="model"))

    def circuit_is_open(provider_id: str) -> bool:
        return provider_id == "zai"

    monkeypatch.setattr(app.state.llm, "provider_unavailable", circuit_is_open)
    client = TestClient(app, base_url="http://127.0.0.1")

    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
    assert response.json()["checks"]["ai"] == "unavailable"


def test_ready_reports_down_and_database_locked_message(tmp_path: Path) -> None:
    app = create_app(Settings(data_dir=tmp_path))

    class LockedConnection:
        def execute(self, _: str) -> None:
            raise duckdb.IOException("database is locked")

    app.state.store._conn = LockedConnection()
    client = TestClient(app, base_url="http://127.0.0.1")

    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["status"] == "down"
    assert response.json()["checks"]["database_message"] == "database_locked"


def test_root_names_phase() -> None:
    client = TestClient(create_app(_defaults()), base_url="http://127.0.0.1")
    body = client.get("/").json()
    assert body["service"] == "obsidian-ledger"
    assert body["phase"] == "1"


def test_default_bind_is_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LEDGER_HOST", raising=False)
    monkeypatch.delenv("LEDGER_PORT", raising=False)
    monkeypatch.delenv("LEDGER_CORS_ORIGINS", raising=False)
    settings = _defaults()
    assert settings.host == "127.0.0.1"
    assert settings.port == 8000


def test_cors_allows_only_configured_origins() -> None:
    client = TestClient(create_app(_defaults()), base_url="http://127.0.0.1")
    blocked = client.get("/health", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in {key.lower() for key in blocked.headers}
    allowed = client.get("/health", headers={"Origin": "http://127.0.0.1:5173"})
    assert allowed.headers.get("access-control-allow-origin") == "http://127.0.0.1:5173"
