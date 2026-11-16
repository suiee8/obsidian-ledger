"""Spoofed Host and Origin, missing client header, rate limits, traversal, SQL injection, errors."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from obsidian_ledger.main import create_app
from obsidian_ledger.settings import Settings

SAMPLES = Path(__file__).resolve().parents[3] / "samples"

INJECTIONS = [
    "' OR '1'='1",
    "'; DROP TABLE trades; --",
    '" OR ""="',
    "1; SELECT * FROM trades",
    "x') UNION SELECT * FROM imports --",
    "%27%20OR%201%3D1",
    "\\'; DELETE FROM trades; --",
    "AAPL\x00",
]


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    settings = Settings.model_validate({"data_dir": str(tmp_path / "data")})
    api = TestClient(create_app(settings), base_url="http://127.0.0.1")
    preview = api.post(
        "/api/imports/preview",
        params={"filename": "ibkr_executions.csv"},
        content=(SAMPLES / "ibkr_executions.csv").read_bytes(),
        headers={"content-type": "application/octet-stream"},
    ).json()
    commit = api.post(f"/api/imports/{preview['preview_id']}/commit", json={})
    assert commit.status_code == 200, commit.text
    return api


def _no_leak(text: str) -> None:
    for needle in ("Traceback", "site-packages", "/vercel/", "duckdb.", 'File "'):
        assert needle not in text


def test_spoofed_host_is_refused(client: TestClient) -> None:
    for host in ("evil.example", "127.0.0.1.evil.example", "localhost:80@evil.example"):
        response = client.get("/health", headers={"Host": host})
        assert response.status_code == 400, host
        _no_leak(response.text)


def test_spoofed_origin_is_refused_on_reads_and_writes(client: TestClient) -> None:
    for origin in ("http://evil.example", "null", "http://127.0.0.1:5173.evil.example"):
        assert client.get("/api/trades", headers={"Origin": origin}).status_code == 403
        write = client.patch("/api/trades/x", json={}, headers={"Origin": origin})
        assert write.status_code == 403


def test_missing_client_header_blocks_every_write(client: TestClient) -> None:
    del client.headers["X-Ledger-Client"]
    calls = [
        ("POST", "/api/imports/preview"),
        ("POST", "/api/imports/abc/commit"),
        ("PATCH", "/api/trades/x"),
        ("DELETE", "/api/views/x"),
        ("POST", "/api/simulate"),
    ]
    for method, path in calls:
        response = client.request(method, path, json={})
        assert response.status_code == 403, (method, path, response.status_code)
    assert client.get("/api/trades").status_code == 200


def test_disallowed_methods_are_refused(client: TestClient) -> None:
    for method in ("TRACE", "CONNECT", "PROPFIND"):
        response = client.request(method, "/api/trades")
        assert response.status_code in {403, 405, 400}


def test_rate_limit_returns_429_and_is_logged(tmp_path: Path) -> None:
    settings = Settings.model_validate(
        {"data_dir": str(tmp_path / "data"), "requests_per_minute": 5}
    )
    api = TestClient(create_app(settings), base_url="http://127.0.0.1")
    codes = [api.get("/api/trades").status_code for _ in range(12)]
    assert 429 in codes
    log = (tmp_path / "data" / "logs" / "security.log").read_text(encoding="utf-8")
    assert "rate_limited" in log


@pytest.mark.parametrize(
    "path",
    [
        "/api/imports/..%2f..%2fetc%2fpasswd/rejected.csv",
        "/api/imports/../../../etc/passwd/rejected.csv",
        "/api/imports/%2e%2e/rejected.csv",
        "/api/imports/" + "a" * 5 + "/rejected.csv",
    ],
)
def test_file_route_rejects_path_traversal(client: TestClient, path: str) -> None:
    response = client.get(path)
    assert response.status_code in {404, 422}
    _no_leak(response.text)
    assert "root:" not in response.text


@pytest.mark.parametrize("payload", INJECTIONS)
def test_sql_injection_strings_in_every_filter_are_inert(client: TestClient, payload: str) -> None:
    filters = {
        "account": payload,
        "symbol": payload,
        "setup": payload,
        "side": payload,
        "tag": payload,
        "date_from": payload,
        "date_to": payload,
    }
    endpoints = [
        "/api/trades/page",
        "/api/metrics",
        "/api/dashboard",
        "/api/explore",
        "/api/segments",
    ]
    for endpoint in endpoints:
        for name, value in filters.items():
            response = client.get(endpoint, params={name: value})
            assert response.status_code in {200, 400, 422}, (endpoint, name, response.status_code)
            _no_leak(response.text)
    for sort in (payload, "exit_time; DROP TABLE trades", "(SELECT 1)", "1"):
        response = client.get("/api/trades/page", params={"sort": sort})
        assert response.status_code in {200, 422}
        _no_leak(response.text)
    for direction in (payload, "asc; --"):
        assert client.get("/api/trades/page", params={"dir": direction}).status_code == 422
    assert len(client.get("/api/trades").json()) == 4


def test_errors_never_reveal_internals(client: TestClient) -> None:
    responses = [
        client.get("/api/trades/does-not-exist"),
        client.get("/api/nope"),
        client.post("/api/imports/preview", content=b"x"),
        client.post(
            "/api/simulate", content=b"{not json", headers={"content-type": "application/json"}
        ),
        client.get("/api/trades/page", params={"limit": "abc"}),
    ]
    for response in responses:
        assert response.status_code >= 400
        _no_leak(response.text)
        assert "version" not in response.text.lower()
    assert "server" not in {key.lower() for key in responses[0].headers} or "uvicorn" not in (
        responses[0].headers.get("server", "").lower()
    )


def test_docs_are_on_locally_and_off_in_public_mode(tmp_path: Path) -> None:
    local = TestClient(
        create_app(Settings.model_validate({"data_dir": str(tmp_path / "a")})),
        base_url="http://127.0.0.1",
    )
    assert local.get("/docs").status_code == 200
    assert local.get("/openapi.json").status_code == 200
    public = Settings.model_validate(
        {
            "data_dir": str(tmp_path / "b"),
            "public": True,
            "password_hash": "scrypt$16384$8$1$AAAA$AAAA",
            "cors_origins": "https://ledger.example",
        }
    )
    hosted = TestClient(create_app(public), base_url="http://127.0.0.1")
    assert hosted.get("/docs").status_code in {401, 404}
    assert hosted.get("/openapi.json").status_code in {401, 404}
    assert hosted.get("/api/trades").status_code == 401
