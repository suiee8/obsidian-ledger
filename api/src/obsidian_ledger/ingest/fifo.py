"""Pair execution fills into round trips with first-in, first-out matching."""

from __future__ import annotations

from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

EPS = 1e-9


@dataclass(frozen=True)
class Fill:
    row: int
    account: str
    symbol: str
    asset_class: str | None
    currency: str
    side: Literal["long", "short"]  # long means buy, short means sell
    qty: float  # positive
    price: float
    time: datetime  # timezone-aware, UTC
    commission: float  # signed total for this fill; negative is a cost
    multiplier: float
    order_id: str | None
    has_offset: bool


@dataclass(frozen=True)
class Leg:
    open_fill: Fill
    close_fill: Fill
    qty: float
    commission: float  # the share of both fills' commissions that belongs to this leg
    sequence: int  # 1-based, per (account, symbol), in close order


@dataclass
class _Lot:
    fill: Fill
    remaining: float
    commission_per_unit: float


@dataclass(frozen=True)
class OpenRemainder:
    account: str
    symbol: str
    side: Literal["long", "short"]
    qty: float


def pair_fills(fills: Sequence[Fill]) -> tuple[list[Leg], list[OpenRemainder]]:
    """Match each closing fill against the oldest open lots of the same account and symbol.

    A fill in the same direction as the open position adds a lot. A fill in the other
    direction closes lots oldest-first, producing one leg per matched piece. Any quantity
    left over after the position is flat opens a new lot in the fill's direction.
    """
    books: dict[tuple[str, str], deque[_Lot]] = {}
    sequences: dict[tuple[str, str], int] = {}
    legs: list[Leg] = []
    for fill in sorted(fills, key=lambda item: (item.time, item.row)):
        key = (fill.account, fill.symbol)
        book = books.setdefault(key, deque())
        per_unit = fill.commission / fill.qty
        remaining = fill.qty
        while remaining > EPS:
            if not book or book[0].fill.side == fill.side:
                book.append(_Lot(fill, remaining, per_unit))
                break
            lot = book[0]
            matched = min(lot.remaining, remaining)
            commission = (lot.commission_per_unit + per_unit) * matched
            sequences[key] = sequences.get(key, 0) + 1
            legs.append(Leg(lot.fill, fill, matched, commission, sequences[key]))
            lot.remaining -= matched
            remaining -= matched
            if lot.remaining <= EPS:
                book.popleft()
    remainders = [
        OpenRemainder(account, symbol, book[0].fill.side, sum(lot.remaining for lot in book))
        for (account, symbol), book in books.items()
        if book
    ]
    return legs, remainders
