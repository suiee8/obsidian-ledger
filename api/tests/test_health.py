import pytest
from fastapi.testclient import TestClient

from obsidian_ledger.main import create_app
from obsidian_ledger.settings import Settings


def _defaults() -> Settings:
    # model_validate applies field defaults without reading .env or LEDGER_* variables.
    return Settings.model_validate({})


def test_health() -> None:
    client = TestClient(create_app(_defaults()))
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "obsidian-ledger"}
    assert response.headers["x-content-type-options"] == "nosniff"


def test_root_names_phase() -> None:
    client = TestClient(create_app(_defaults()))
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
    client = TestClient(create_app(_defaults()))
    blocked = client.get("/health", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in {key.lower() for key in blocked.headers}
    allowed = client.get("/health", headers={"Origin": "http://127.0.0.1:5173"})
    assert allowed.headers.get("access-control-allow-origin") == "http://127.0.0.1:5173"
