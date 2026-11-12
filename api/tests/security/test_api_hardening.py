"""API hardening unit tests: binding to 127.0.0.1 and origin validation."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from obsidian_ledger.main import create_app
from obsidian_ledger.settings import Settings


def test_api_binds_only_to_localhost_by_default() -> None:
    settings = Settings()
    assert settings.host == "127.0.0.1", f"API host must be 127.0.0.1, got {settings.host}"
    assert "0.0.0.0" not in settings.host


def test_api_allowed_origins_default_to_local_only() -> None:
    settings = Settings()
    allowed = settings.cors_origin_list
    assert len(allowed) > 0
    for origin in allowed:
        assert origin.startswith("http://127.0.0.1:") or origin.startswith("http://localhost:"), (
            f"Non-local origin found in defaults: {origin}"
        )
    assert "*" not in allowed


def test_request_from_listed_origin_is_accepted(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    # 127.0.0.1:5173 is in default cors_origins
    response = client.get("/health", headers={"Origin": "http://127.0.0.1:5173"})
    assert response.status_code == 200

    # localhost:5173 is in default cors_origins
    response2 = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert response2.status_code == 200


def test_request_from_unlisted_origin_is_rejected(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    response = client.get("/health", headers={"Origin": "http://evil.com"})
    assert response.status_code == 403
    assert b"Disallowed origin" in response.content

    response_attacker = client.post(
        "/api/llm/config",
        json={"consent": True},
        headers={"Origin": "http://attacker.example.org"},
    )
    assert response_attacker.status_code == 403


def test_cors_options_preflight_from_unlisted_origin_rejected(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    response = client.options(
        "/health",
        headers={
            "Origin": "http://malicious-site.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    # Both Starlette CORSMiddleware (400) or our middleware (403) reject unlisted preflight
    assert response.status_code in (400, 403)
