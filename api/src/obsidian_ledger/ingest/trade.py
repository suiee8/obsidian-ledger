"""Shared data types for the ingestion pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

Severity = Literal["error", "warning", "info"]


@dataclass(frozen=True)
class Reason:
    code: str
    message: str


@dataclass
class Draft:
    """A trade before validation. Fields are None when the source did not provide them."""

    source_rows: tuple[int, ...]
    trade_id: str | None
    account: str
    symbol: str
    asset_class: str | None
    side: Literal["long", "short"] | None
    entry_time: datetime | None  # timezone-aware, UTC
    exit_time: datetime | None  # timezone-aware, UTC
    has_offset: bool
    qty: float | None
    multiplier: float | None
    entry_price: float | None
    exit_price: float | None
    price_decimals: int
    fees: float | None
    commission: float | None
    swap: float | None
    gross_pnl: float | None
    net_pnl: float | None
    currency: str
    stop_loss: float | None = None
    take_profit: float | None = None
    planned_risk: float | None = None
    provided_r: float | None = None
    mae: float | None = None
    mfe: float | None = None
    setup: str | None = None
    timeframe: str | None = None
    session: str | None = None
    emotion: str | None = None
    tags: str | None = None
    notes: str = ""
    plan_followed: bool | None = None
    confidence: str | None = None
    screenshot_path: str | None = None
    time_precision: str = "second"
    entry_notional: float | None = None
    exit_notional: float | None = None
    leverage: float | None = None
    order_type: str | None = None
    status: str | None = None
    action: str | None = None


@dataclass
class Trade:
    """A validated, normalized trade with derived fields, ready to store."""

    trade_key: str
    trade_id: str
    account: str
    symbol: str
    asset_class: str | None
    side: Literal["long", "short"]
    entry_time: datetime
    exit_time: datetime
    source_timezone: str | None
    qty: float
    multiplier: float
    entry_price: float | None
    exit_price: float | None
    fees: float | None
    commission: float | None
    swap: float | None
    gross_pnl: float | None
    net_pnl: float | None
    currency: str
    net_pnl_base: float | None
    base_currency: str
    stop_loss: float | None
    take_profit: float | None
    planned_risk: float | None
    r_multiple: float | None
    mae: float | None
    mfe: float | None
    setup: str | None
    timeframe: str | None
    session: str
    tags: str | None
    notes: str
    emotion: str | None
    plan_followed: bool | None
    holding_seconds: float | None
    weekday: int
    hour_utc: int
    source_row: int
    confidence: str | None = None
    screenshot_path: str | None = None
    time_precision: str = "second"
    entry_notional: float | None = None
    exit_notional: float | None = None
    leverage: float | None = None
    order_type: str | None = None
    status: str | None = None
    action: str | None = None
    warnings: list[Reason] = field(default_factory=list[Reason])


@dataclass
class Rejected:
    source_row: int
    reasons: list[Reason]
    cells: list[str]


@dataclass(frozen=True)
class Issue:
    code: str
    severity: Severity
    title: str
    count: int
    example_rows: tuple[int, ...]
    suggested_fix: str
