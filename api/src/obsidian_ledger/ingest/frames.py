"""Accepted trades as Polars frames: the column schema, and conversions to and from Trade objects.

The store writes these frames to DuckDB in one Arrow insert. Trade objects are only built when a
caller asks for them, for example in tests.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, Final, cast

import polars as pl

from obsidian_ledger.ingest.trade import Reason, Trade

WARNING_COLUMN: Final = "warning_codes"

# Column names and types of an accepted trade. The store adds import_id and writes these columns
# by name, so the order here does not matter to DuckDB.
TRADE_DTYPES: Final[tuple[tuple[str, pl.DataType], ...]] = (
    ("trade_key", pl.String()),
    ("trade_id", pl.String()),
    ("account", pl.String()),
    ("symbol", pl.String()),
    ("asset_class", pl.String()),
    ("side", pl.String()),
    ("entry_time", pl.Datetime("us")),
    ("exit_time", pl.Datetime("us")),
    ("source_timezone", pl.String()),
    ("qty", pl.Float64()),
    ("multiplier", pl.Float64()),
    ("entry_price", pl.Float64()),
    ("exit_price", pl.Float64()),
    ("fees", pl.Float64()),
    ("commission", pl.Float64()),
    ("swap", pl.Float64()),
    ("gross_pnl", pl.Float64()),
    ("net_pnl", pl.Float64()),
    ("currency", pl.String()),
    ("net_pnl_base", pl.Float64()),
    ("base_currency", pl.String()),
    ("stop_loss", pl.Float64()),
    ("take_profit", pl.Float64()),
    ("planned_risk", pl.Float64()),
    ("r_multiple", pl.Float64()),
    ("mae", pl.Float64()),
    ("mfe", pl.Float64()),
    ("setup", pl.String()),
    ("timeframe", pl.String()),
    ("session", pl.String()),
    ("tags", pl.String()),
    ("notes", pl.String()),
    ("emotion", pl.String()),
    ("plan_followed", pl.Boolean()),
    ("holding_seconds", pl.Float64()),
    ("weekday", pl.Int32()),
    ("hour_utc", pl.Int32()),
    ("source_row", pl.Int32()),
    ("screenshot_path", pl.String()),
    ("confidence", pl.String()),
    ("time_precision", pl.String()),
    ("entry_notional", pl.Float64()),
    ("exit_notional", pl.Float64()),
    ("leverage", pl.Float64()),
    ("order_type", pl.String()),
    ("status", pl.String()),
    ("action", pl.String()),
)

ACCEPTED_SCHEMA: Final = pl.Schema({**dict(TRADE_DTYPES), WARNING_COLUMN: pl.List(pl.String())})


def empty_accepted() -> pl.DataFrame:
    return pl.DataFrame(schema=ACCEPTED_SCHEMA)


def frame_from_trades(trades: Sequence[Trade]) -> pl.DataFrame:
    """Build the accepted-trade frame from Trade objects (legs and executions shapes)."""
    if not trades:
        return empty_accepted()
    columns: dict[str, list[object]] = {
        name: [getattr(trade, name) for trade in trades] for name, _ in TRADE_DTYPES
    }
    columns[WARNING_COLUMN] = [[reason.code for reason in trade.warnings] for trade in trades]
    columns["entry_time"] = [_naive_utc(value) for value in columns["entry_time"]]
    columns["exit_time"] = [_naive_utc(value) for value in columns["exit_time"]]
    return pl.DataFrame(columns, schema=ACCEPTED_SCHEMA)


def _naive_utc(value: Any) -> datetime:
    assert isinstance(value, datetime)
    return value.astimezone(UTC).replace(tzinfo=None)


def trades_from_frame(frame: pl.DataFrame) -> list[Trade]:
    """Materialize Trade objects from the frame. Warning messages are the codes only."""
    trades: list[Trade] = []
    for row in frame.iter_rows(named=True):
        raw_codes = cast(list[str] | None, row.pop(WARNING_COLUMN))
        codes = list(raw_codes or [])
        entry: datetime = row["entry_time"]
        exit_time: datetime = row["exit_time"]
        row["entry_time"] = entry.replace(tzinfo=UTC)
        row["exit_time"] = exit_time.replace(tzinfo=UTC)
        row["warnings"] = [Reason(code, code) for code in codes]
        trades.append(Trade(**row))
    return trades
