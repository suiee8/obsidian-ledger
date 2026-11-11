"""Filter the stored trades and expose the columns the metrics read."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Final

import polars as pl

LOW_CONFIDENCE_N: Final = 30


@dataclass(frozen=True)
class Filters:
    """Every filter is optional. Empty tuples mean no restriction."""

    date_from: date | None = None
    date_to: date | None = None
    accounts: tuple[str, ...] = ()
    symbols: tuple[str, ...] = ()
    setups: tuple[str, ...] = ()
    sides: tuple[str, ...] = ()
    tag: str | None = None

    def key(self) -> str:
        return repr(
            (
                self.date_from,
                self.date_to,
                self.accounts,
                self.symbols,
                self.setups,
                self.sides,
                self.tag,
            )
        )


@dataclass(frozen=True)
class Prepared:
    """Filtered trades plus the count of trades left out because they lack a base-currency value."""

    frame: pl.DataFrame
    excluded_no_fx: int


def prepare(raw: pl.DataFrame, filters: Filters) -> Prepared:
    """Restrict to filtered trades with base-currency P&L and add the derived columns.

    Costs are converted with the same rate as net P&L, so fee drag stays in base currency.
    """
    if raw.height == 0:
        return Prepared(raw, 0)
    no_fx = raw.filter(pl.col("net_pnl_base").is_null()).height
    frame = raw.filter(pl.col("net_pnl_base").is_not_null())
    if filters.date_from is not None:
        frame = frame.filter(pl.col("exit_time").dt.date() >= filters.date_from)
    if filters.date_to is not None:
        frame = frame.filter(pl.col("exit_time").dt.date() <= filters.date_to)
    if filters.accounts:
        frame = frame.filter(pl.col("account").is_in(list(filters.accounts)))
    if filters.symbols:
        frame = frame.filter(pl.col("symbol").is_in(list(filters.symbols)))
    if filters.setups:
        frame = frame.filter(pl.col("setup").is_in(list(filters.setups)))
    if filters.sides:
        frame = frame.filter(pl.col("side").is_in(list(filters.sides)))
    if filters.tag:
        needle = filters.tag.lower()
        frame = frame.filter(
            pl.col("tags").fill_null("").str.to_lowercase().str.contains(needle, literal=True)
            | pl.col("emotion").fill_null("").str.to_lowercase().eq(needle)
        )
    frame = frame.with_columns(
        pl.col("net_pnl_base").alias("pnl"),
        pl.when(pl.col("net_pnl") != 0)
        .then(pl.col("net_pnl_base") / pl.col("net_pnl"))
        .otherwise(pl.lit(1.0))
        .alias("fx"),
        (pl.col("fees") + pl.col("commission") + pl.col("swap")).alias("costs_native"),
        pl.col("exit_time").dt.date().alias("exit_day"),
        pl.col("entry_time").dt.date().alias("entry_day"),
    ).with_columns((pl.col("costs_native") * pl.col("fx")).alias("costs"))
    return Prepared(frame, no_fx)
