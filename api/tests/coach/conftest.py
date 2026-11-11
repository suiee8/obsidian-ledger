"""Shared datasets. Each is imported once per test session through the real ingestion pipeline."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import polars as pl
import pytest

from obsidian_ledger.coach.models import CoachReport
from obsidian_ledger.coach.service import CoachService
from obsidian_ledger.metrics.data import Filters
from obsidian_ledger.metrics.engine import AnalysisEngine
from obsidian_ledger.store.db import Store

from . import synth


@dataclass
class Dataset:
    store: Store
    engine: AnalysisEngine
    service: CoachService
    report: CoachReport
    trades: pl.DataFrame


def _dataset(root: Path, name: str, text: str) -> Dataset:
    folder = root / name
    folder.mkdir()
    store = synth.load(folder, text)
    engine = AnalysisEngine(store)
    service = CoachService(store, engine)
    report = service.report(Filters())
    _version, prepared = engine.trades_for(Filters())
    return Dataset(store, engine, service, report, prepared.frame)


@pytest.fixture(scope="session")
def planted(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Dataset]:
    data = _dataset(tmp_path_factory.mktemp("planted"), "d", synth.planted())
    yield data
    data.store.close()


@pytest.fixture(scope="session")
def noise(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Dataset]:
    data = _dataset(tmp_path_factory.mktemp("noise"), "d", synth.noise())
    yield data
    data.store.close()
