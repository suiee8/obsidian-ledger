"""The committed Coach samples must be exactly what the generator writes."""

from __future__ import annotations

from pathlib import Path

import pytest

from . import synth

SAMPLES = Path(__file__).resolve().parents[3] / "samples"


@pytest.mark.parametrize(
    ("name", "text"),
    [
        ("coach_planted.csv", synth.planted(seed=7, days=170)),
        ("coach_noise.csv", synth.noise(seed=11, days=160)),
    ],
)
def test_sample_matches_the_generator(name: str, text: str) -> None:
    committed = (SAMPLES / name).read_bytes().decode("utf-8").replace("\r\n", "\n")
    assert committed == text, f"{name} is out of date. Run benchmarks/generate_coach_samples.py."
