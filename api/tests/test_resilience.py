from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb
import pytest

from obsidian_ledger.atomic import atomic_path
from obsidian_ledger.llm.coach import Deadline, LLMCoach, Unusable
from obsidian_ledger.llm.config import LLMConfig
from obsidian_ledger.llm.provider import ProviderError, Reply
from obsidian_ledger.main import create_app
from obsidian_ledger.settings import Settings
from obsidian_ledger.store.db import Store


def test_atomic_path_keeps_previous_file_after_simulated_crash(tmp_path: Path) -> None:
    destination = tmp_path / "export.zip"
    destination.write_bytes(b"previous export")

    with pytest.raises(RuntimeError, match="simulated crash"):
        with atomic_path(destination) as temporary:
            temporary.write_bytes(b"partial export")
            raise RuntimeError("simulated crash")

    assert destination.read_bytes() == b"previous export"
    assert list(tmp_path.glob("*.tmp")) == []


def test_database_snapshots_precede_wipe_and_keep_only_three(tmp_path: Path) -> None:
    store = Store(tmp_path)
    store.set_setting("before_wipe", "preserved")
    store.wipe()
    snapshots = list((tmp_path / "backups").glob("ledger-*.duckdb"))
    preserved = max(snapshots, key=lambda path: path.stat().st_mtime_ns)
    snapshot = duckdb.connect(str(preserved), read_only=True)
    try:
        setting = snapshot.execute(
            "SELECT value FROM settings WHERE key = 'before_wipe'"
        ).fetchone()
        assert setting == ("preserved",)
    finally:
        snapshot.close()
    for _ in range(4):
        store.snapshot_database()
    assert len(list((tmp_path / "backups").glob("ledger-*.duckdb"))) == 3
    store.close()


def test_provider_circuit_opens_after_three_failures_and_closes_after_cooldown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = create_app(Settings(data_dir=tmp_path))
    llm: LLMCoach = app.state.llm
    provider = llm.provider(LLMConfig(provider="zai", model="test-model"), api_key="test-key")
    current_time = [10.0]
    monkeypatch.setattr("obsidian_ledger.llm.coach.time.monotonic", lambda: current_time[0])
    fail = [True]
    calls = [0]

    def fake_chat(messages: list[dict[str, Any]], *, timeout: float, **options: Any) -> Reply:
        calls[0] += 1
        if fail[0]:
            raise ProviderError("unreachable", "provider unavailable")
        return Reply("ok")

    monkeypatch.setattr(provider, "chat", fake_chat)
    for _ in range(3):
        with pytest.raises(Unusable, match="provider unavailable"):
            llm.complete(provider, [], Deadline(30))
    assert llm.provider_unavailable("zai")
    with pytest.raises(Unusable, match="temporarily unavailable"):
        llm.complete(provider, [], Deadline(30))
    assert calls == [3]

    current_time[0] += 61
    fail[0] = False
    assert llm.complete(provider, [], Deadline(30)) == Reply("ok")
    assert not llm.provider_unavailable("zai")
