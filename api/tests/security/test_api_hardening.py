"""API hardening unit tests: binding to 127.0.0.1 and origin validation."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from pydantic import ValidationError

from obsidian_ledger.main import create_app
from obsidian_ledger.settings import Settings


def test_api_binds_only_to_localhost_by_default() -> None:
    settings = Settings()
    assert settings.host == "127.0.0.1", f"API host must be 127.0.0.1, got {settings.host}"
    assert "0.0.0.0" not in settings.host


def test_api_host_setting_rejects_non_loopback_bind_addresses() -> None:
    try:
        Settings.model_validate({"host": "0.0.0.0"})
    except ValidationError:
        return
    raise AssertionError("Non-loopback host setting must be rejected")


def test_wrong_host_is_rejected(tmp_path: Path) -> None:
    client = TestClient(create_app(Settings(data_dir=tmp_path)), base_url="http://attacker.example")
    response = client.get("/health")
    assert response.status_code == 400
    assert response.headers["x-content-type-options"] == "nosniff"


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
    client = TestClient(app, base_url="http://127.0.0.1")

    # 127.0.0.1:5173 is in default cors_origins
    response = client.get("/health", headers={"Origin": "http://127.0.0.1:5173"})
    assert response.status_code == 200

    # localhost:5173 is in default cors_origins
    response2 = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert response2.status_code == 200


def test_request_from_unlisted_origin_is_rejected(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    app = create_app(settings)
    client = TestClient(app, base_url="http://127.0.0.1")

    response = client.get("/health", headers={"Origin": "http://evil.com"})
    assert response.status_code == 403
    assert b"Disallowed origin" in response.content

    response_attacker = client.post(
        "/api/llm/config",
        json={"consent": True},
        headers={"Origin": "http://attacker.example.org"},
    )
    assert response_attacker.status_code == 403

    simple_post = client.post(
        "/api/llm/config",
        content="cross-origin",
        headers={
            "Origin": "http://attacker.example.org",
            "Content-Type": "text/plain",
        },
    )
    assert simple_post.status_code == 403


def test_all_api_responses_have_security_headers(tmp_path: Path) -> None:
    client = TestClient(create_app(Settings(data_dir=tmp_path)), base_url="http://127.0.0.1")
    response = client.get("/health")
    assert response.status_code == 200
    assert response.headers["content-security-policy"] == (
        "default-src 'none'; base-uri 'none'; frame-ancestors 'none'"
    )
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["x-frame-options"] == "DENY"
    assert "camera=()" in response.headers["permissions-policy"]


def test_global_request_body_limit_rejects_non_upload_endpoint(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, max_upload_mb=1)
    client = TestClient(create_app(settings), base_url="http://127.0.0.1")
    response = client.post(
        "/api/llm/config",
        content=b"x" * (1024 * 1024 + 1),
        headers={"Content-Type": "application/octet-stream"},
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "body_too_large"


def test_per_client_rate_limit_rejects_runaway_requests(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, requests_per_minute=1)
    client = TestClient(create_app(settings), base_url="http://127.0.0.1")
    assert client.get("/").status_code == 200

    limited = client.get("/")
    assert limited.status_code == 429
    assert limited.headers["retry-after"] == "60"


def test_cors_options_preflight_from_unlisted_origin_rejected(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    app = create_app(settings)
    client = TestClient(app, base_url="http://127.0.0.1")

    response = client.options(
        "/health",
        headers={
            "Origin": "http://malicious-site.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    # Both Starlette CORSMiddleware (400) or our middleware (403) reject unlisted preflight
    assert response.status_code in (400, 403)


def test_json_endpoints_use_a_small_body_cap_below_the_upload_limit(tmp_path: Path) -> None:
    client = TestClient(create_app(Settings(data_dir=tmp_path)), base_url="http://127.0.0.1")
    oversized = client.post(
        "/api/llm/config",
        content=b"x" * (1024 * 1024 + 1),
        headers={"Content-Type": "application/json"},
    )
    assert oversized.status_code == 413
    assert oversized.json()["error"]["code"] == "body_too_large"


def test_upload_endpoint_keeps_the_larger_upload_limit(tmp_path: Path) -> None:
    client = TestClient(create_app(Settings(data_dir=tmp_path)), base_url="http://127.0.0.1")
    response = client.post(
        "/api/imports/preview",
        content=b"a,b\n" + b"1,2\n" * (512 * 1024),
        headers={"Content-Type": "text/csv", "X-Filename": "big.csv"},
    )
    assert response.status_code != 413


def test_streamed_body_without_content_length_is_cut_off(tmp_path: Path) -> None:
    client = TestClient(create_app(Settings(data_dir=tmp_path)), base_url="http://127.0.0.1")

    def chunks() -> object:
        for _ in range(3):
            yield b"x" * (512 * 1024)

    response = client.put(
        "/api/llm/config",
        content=chunks(),  # type: ignore[arg-type]
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 413
