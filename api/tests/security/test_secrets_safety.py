"""Secrets safety tests: confirming API keys are stored only in the keychain/secrets store
and never written to the database, logs, exports, or zip archive.
"""

from __future__ import annotations

import io
import logging
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from obsidian_ledger.main import create_app
from obsidian_ledger.settings import Settings

CANARY_KEY = "sk-antigravity-canary-secret-key-9876543210"


def test_secret_key_never_leaks_to_db_exports_or_zip(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    settings = Settings(data_dir=tmp_path, llm_secret_store="memory")
    app = create_app(settings)
    client = TestClient(app, base_url="http://127.0.0.1")

    # 1. Configure provider and store the secret key
    config_resp = client.put(
        "/api/llm/config",
        json={"provider": "openrouter", "consent": True},
    )
    assert config_resp.status_code == 200

    store_resp = client.put(
        "/api/llm/key",
        json={"provider": "openrouter", "api_key": CANARY_KEY},
    )
    assert store_resp.status_code == 200

    # 2. Check status response only gives a masked hint, never the full key
    status_resp = client.get("/api/llm/status")
    assert status_resp.status_code == 200
    status_text = status_resp.text
    assert CANARY_KEY not in status_text
    assert status_resp.json()["key_hint"] == f"…{CANARY_KEY[-4:]}"

    # 3. Check settings response
    settings_resp = client.get("/api/settings")
    assert CANARY_KEY not in settings_resp.text

    # 4. Check dashboard & metrics responses
    dash_resp = client.get("/api/dashboard")
    assert CANARY_KEY not in dash_resp.text

    # 5. Check trades export
    trades_resp = client.get("/api/trades/export")
    assert CANARY_KEY not in trades_resp.text

    # 6. Check full zip export
    export_resp = client.get("/api/export")
    assert export_resp.status_code == 200
    assert CANARY_KEY.encode() not in export_resp.content

    # Unpack the entire zip export and search every entry
    with zipfile.ZipFile(io.BytesIO(export_resp.content)) as archive:
        for info in archive.infolist():
            content = archive.read(info.filename)
            assert CANARY_KEY.encode() not in content, (
                f"Secret key found in zip archive member: {info.filename}"
            )

    # 7. Search captured logs and all files in data_dir (database, raw, rejected, staging).
    assert CANARY_KEY not in caplog.text
    app.state.store.close()
    canary_bytes = CANARY_KEY.encode()
    for file_path in tmp_path.rglob("*"):
        if file_path.is_file():
            data = file_path.read_bytes()
            assert canary_bytes not in data, f"Secret key found in stored file on disk: {file_path}"
