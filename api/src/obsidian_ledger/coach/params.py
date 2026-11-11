"""Thresholds the Coach uses. They are part of the cache key and are stored with each report."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class CoachParams:
    # Statistics
    min_n: int = 30  # smallest slice, and smallest rest, that is tested at all
    q_threshold: float = 0.05  # Benjamini-Hochberg q below which a slice is reported
    q_high: float = 0.01  # q needed, with n >= high_n and an interval that excludes 0, for "high"
    high_n: int = 100
    resamples: int = 1000
    seed: int = 42
    evidence_limit: int = 20
    # Behavior detectors
    revenge_gap_minutes: float = 10.0
    size_jump: float = 0.5
    overtrading_threshold: int = 10  # trades per day, raised to twice the median day if higher
    oversize_multiple: float = 1.5  # planned risk above this multiple of the median is oversized
    disposition_ratio: float = 1.5  # losers held this many times a winner's average hold
    early_capture: float = 0.4  # winners that kept under this share of their best price
    late_overrun: float = 1.25  # losses beyond this multiple of planned risk
    fee_drag_threshold: float = 0.15  # costs as a share of gross P&L worth reporting
    early_exit_share: float = 0.10  # left on the table, as a share of gross winning P&L

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)
