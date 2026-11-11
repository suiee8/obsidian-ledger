"""Write the two Coach sample journals into samples/.

    coach_planted.csv   revenge re-entries, a losing 14:00 UTC hour, and overtrading days
    coach_noise.csv     pure noise: the Coach should report no leak and no strength

They come from the generator the Coach tests use (api/tests/coach/synth.py), with fixed seeds, so
the files can be rebuilt byte for byte:

    uv run --directory api python ../benchmarks/generate_coach_samples.py
"""

from __future__ import annotations

import importlib
import sys
from collections.abc import Callable
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api" / "tests"))
synth = importlib.import_module("coach.synth")  # the test generator, found through the path above
planted = cast(Callable[..., str], synth.planted)
noise = cast(Callable[..., str], synth.noise)


def main() -> int:
    samples = ROOT / "samples"
    outputs = {
        "coach_planted.csv": planted(seed=7, days=170),
        "coach_noise.csv": noise(seed=11, days=160),
    }
    for name, text in outputs.items():
        (samples / name).write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {name}: {text.count(chr(10)) - 1} trades")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
