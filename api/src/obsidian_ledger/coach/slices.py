"""Slice definitions: which trades a finding is about, and which trades it is compared with.

A slice is a boolean mask over the trades in entry order. Segment slices come from the Phase 2
segment keys (symbol, setup, side, session, weekday, hour, holding bucket, size bucket, tag).
Behavior slices come from the behavior module's prior-trade context. The comparison group
("rest") is every other trade unless a detector says otherwise.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal, cast

import numpy as np
import numpy.typing as npt
import polars as pl

from obsidian_ledger.coach.models import FilterHint
from obsidian_ledger.coach.params import CoachParams
from obsidian_ledger.metrics.behavior import PriorContext, prior_context, revenge_mask
from obsidian_ledger.metrics.segments import key_frame

Mask = npt.NDArray[np.bool_]
Array = npt.NDArray[np.float64]

SEGMENT_DIMENSIONS: Final[tuple[str, ...]] = (
    "symbol",
    "setup",
    "side",
    "session",
    "weekday",
    "hour",
    "holding",
    "size",
    "tag",
)
# Catch-all keys carry no information about the trader's choices, so they are not findings.
SKIPPED_VALUES: Final = frozenset({"unknown", "untagged"})
MEASURED_PATTERNS: Final[tuple[str, ...]] = ("fee_drag", "early_exit", "late_exit")
BEHAVIOR_SLICES: Final[tuple[str, ...]] = (
    "revenge",
    "overtrading",
    "post_loss",
    "disposition",
    "oversize",
)

SliceMode = Literal["test", "pattern"]


@dataclass(frozen=True)
class SliceDef:
    id: str
    category: Literal["segment", "behavior"]
    dimension: str
    value: str
    label: str
    mask: Mask
    rest: Mask
    mode: SliceMode
    filter: FilterHint | None


def slice_id(category: str, dimension: str, value: str = "") -> str:
    return f"seg~{dimension}~{value}" if category == "segment" else f"beh~{dimension}"


def phrase(dimension: str, value: str) -> str:
    """How a segment is named in a sentence."""
    match dimension:
        case "symbol":
            return f"{value} trades"
        case "setup":
            return f"{value} setup trades"
        case "side":
            return f"{value} trades"
        case "session":
            return f"{value} session trades"
        case "weekday":
            return f"{value} trades"
        case "hour":
            return f"trades entered at {int(value):02d}:00 UTC"
        case "holding":
            return f"trades held {value}"
        case "size":
            return f"{value} trades"
        case "tag":
            return f"trades tagged '{value}'"
        case _:
            return f"{dimension} {value} trades"


def filter_hint(dimension: str, value: str) -> FilterHint | None:
    """The app filter that selects a segment, when one exists."""
    if dimension == "symbol":
        return FilterHint(symbols=[value])
    if dimension == "setup":
        return FilterHint(setups=[value])
    if dimension == "side":
        return FilterHint(sides=[value])
    if dimension == "tag":
        return FilterHint(tag=value)
    return None


class SliceBuilder:
    """Builds slices for a set of trades. Arrays and masks follow `frame` (entry order)."""

    def __init__(self, trades: pl.DataFrame, params: CoachParams, currency: str = "") -> None:
        self.params = params
        self.currency = currency
        self.context: PriorContext = prior_context(trades)
        self.frame = self.context.by_entry.with_row_index("pos")
        self.count = self.frame.height
        self.pnl: Array = self.frame["pnl"].to_numpy().astype(np.float64)
        self.r: Array = self.frame["r_multiple"].to_numpy().astype(np.float64)
        self.risk: Array = self.frame["planned_risk"].to_numpy().astype(np.float64)
        self.mfe: Array = self.frame["mfe"].to_numpy().astype(np.float64)
        self.mae: Array = self.frame["mae"].to_numpy().astype(np.float64)
        self.holding: Array = self.frame["holding_seconds"].to_numpy().astype(np.float64)
        self.costs: Array = self.frame["costs"].to_numpy().astype(np.float64)

    # ----- segments -----

    def segment_slices(self, dimension: str) -> list[SliceDef]:
        keyed = key_frame(self.frame, dimension)
        if keyed.height == 0:
            return []
        grouped = keyed.group_by("key").agg(pl.col("pos"))
        if grouped.height < 2:
            return []
        found: list[SliceDef] = []
        for row in grouped.iter_rows():
            value, positions = row[0], cast(list[int], row[1])
            text = str(value)
            if text in SKIPPED_VALUES:
                continue
            mask = np.zeros(self.count, dtype=bool)
            mask[np.asarray(positions, dtype=np.intp)] = True
            found.append(
                SliceDef(
                    id=slice_id("segment", dimension, text),
                    category="segment",
                    dimension=dimension,
                    value=text,
                    label=phrase(dimension, text),
                    mask=mask,
                    rest=~mask,
                    mode="test",
                    filter=filter_hint(dimension, text),
                )
            )
        found.sort(key=lambda item: item.id)
        return found

    def all_segment_slices(self) -> list[SliceDef]:
        return [item for name in SEGMENT_DIMENSIONS for item in self.segment_slices(name)]

    # ----- behavior -----

    def overtrading_threshold(self) -> int:
        """Trades per day above which a day counts as overtraded.

        The configured threshold, raised to twice the median day when the trader normally takes
        more than that, so a high-volume trader is not flagged every day.
        """
        per_day = self.frame.group_by("entry_day").len()["len"]
        median = float(cast(float, per_day.median()) or 0.0)
        return max(self.params.overtrading_threshold, int(np.ceil(2 * median)))

    def behavior_slice(self, name: str) -> SliceDef | None:
        params = self.params
        mask: Mask
        rest: Mask
        mode: SliceMode = "test"  # post_loss is the one comparison that is only described
        label: str
        if name == "revenge":
            mask = revenge_mask(self.context, params.revenge_gap_minutes, params.size_jump)
            rest = ~mask
            label = "revenge-style re-entries after a loss"
        elif name == "overtrading":
            day_count = self.frame.select(pl.len().over("entry_day").alias("n"))["n"].to_numpy()
            mask = day_count > self.overtrading_threshold()
            rest = ~mask
            label = "trades on overtraded days"
        elif name == "post_loss":
            after_loss = self.context.has_previous & (self.context.prev_pnl < 0)
            mask = np.asarray(after_loss, dtype=bool)
            rest = np.asarray(self.context.has_previous & ~after_loss, dtype=bool)
            mode = "pattern"
            label = "trades taken right after a loss"
        elif name == "disposition":
            winners = self.pnl > 0
            if not winners.any():
                return None
            winner_hold = float(self.holding[winners].mean())
            losers = self.pnl < 0
            mask = losers & (self.holding > params.disposition_ratio * winner_hold)
            rest = losers & ~mask
            label = "losing trades held much longer than winners"
        elif name == "oversize":
            known = np.isfinite(self.risk) & (self.risk > 0)
            if not known.any():
                return None
            median = float(np.median(self.risk[known]))
            mask = known & (self.risk > params.oversize_multiple * median)
            rest = known & ~mask
            label = "trades with oversized planned risk"
        else:
            raise ValueError(f"Unknown behavior slice '{name}'.")
        return SliceDef(
            id=slice_id("behavior", name),
            category="behavior",
            dimension=name,
            value="",
            label=label,
            mask=mask,
            rest=rest,
            mode=mode,
            filter=None,
        )

    def behavior_slices(self) -> list[SliceDef]:
        found = [self.behavior_slice(name) for name in BEHAVIOR_SLICES]
        return [item for item in found if item is not None]

    # ----- measured amounts (no comparison group) -----

    def amounts(self, name: str) -> tuple[Mask, Array] | None:
        """Trades a measured pattern applies to, and the amount each one cost, in currency.

        fee_drag     every trade; the amount is the trading cost paid (fees, commission, swap)
        early_exit   winners that kept little of their best price; the amount is price left unused
        late_exit    losers that ran well past planned risk; the amount is the loss beyond plan
        """
        params = self.params
        if name == "fee_drag":
            return np.ones(self.count, dtype=bool), -self.costs
        if name == "early_exit":
            usable = np.isfinite(self.mfe) & (self.mfe > 0) & (self.pnl > 0)
            with np.errstate(divide="ignore", invalid="ignore"):
                capture = np.where(usable, self.pnl / self.mfe, np.inf)
            mask = usable & (capture < params.early_capture)
            return mask, np.where(mask, self.mfe - self.pnl, 0.0)
        if name == "late_exit":
            usable = (
                (self.pnl < 0) & np.isfinite(self.mae) & np.isfinite(self.risk) & (self.risk > 0)
            )
            mask = usable & (
                np.abs(np.where(usable, self.mae, 0.0)) > params.late_overrun * self.risk
            )
            return mask, np.where(mask, np.maximum(-self.pnl - self.risk, 0.0), 0.0)
        return None

    # ----- lookup -----

    def get(self, wanted: str) -> SliceDef | None:
        """Rebuild one slice from its id. Used to recompute a figure from its source."""
        parts = wanted.split("~")
        if parts[0] == "beh" and len(parts) == 2:
            return self.behavior_slice(parts[1])
        if parts[0] == "seg" and len(parts) == 3:
            for item in self.segment_slices(parts[1]):
                if item.id == wanted:
                    return item
        return None
