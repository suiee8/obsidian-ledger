"""Broker adapters: recognise a known export and map its columns by position or exact name."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from obsidian_ledger.ingest.canonical import normalize_header

# Contract sizes assumed when a file has no multiplier column. Each value is an assumption
# that the analysis reports to the user. Values come from the sample files: XAUUSD 0.2 lot
# = 20 oz gives the sample P&L of -174.00, and US500 0.5 lot at 10 gives +82.50.
MT5_DEFAULT_CONTRACT_SIZES: Final[dict[str, float]] = {"XAUUSD": 100.0, "US500": 10.0}
MT5_STANDARD_FX_LOT: Final = 100_000.0
_FX_PAIR: Final = re.compile(r"^[A-Z]{6}$")

IBKR_ASSET_CLASSES: Final[dict[str, str]] = {
    "STK": "stock",
    "CASH": "forex",
    "FUT": "future",
    "OPT": "option",
    "CRYPTO": "crypto",
    "CFD": "cfd",
    "IND": "index",
}


@dataclass(frozen=True)
class AdapterSpec:
    name: str
    shape: str  # round_trip | legs | executions
    required: frozenset[str]  # normalized header names that identify the export


MT5: Final = AdapterSpec(
    "mt5", "round_trip", frozenset({"ticket", "open time", "close time", "profit"})
)
TRADINGVIEW: Final = AdapterSpec(
    "tradingview", "legs", frozenset({"trade number", "type", "date and time"})
)
IBKR: Final = AdapterSpec(
    "ibkr", "executions", frozenset({"clientaccountid", "buy sell", "tradeprice", "datetime"})
)
ADAPTERS: Final[tuple[AdapterSpec, ...]] = (MT5, TRADINGVIEW, IBKR)

_DUPLICATE_SUFFIX: Final = re.compile(r"\s\(\d+\)$")

_MT5_BY_NAME: Final[dict[str, str]] = {
    "ticket": "trade_id",
    "open time": "entry_time",
    "type": "side",
    "size": "qty",
    "item": "symbol",
    "s l": "stop_loss",
    "t p": "take_profit",
    "close time": "exit_time",
    "commission": "commission",
    "taxes": "fees",
    "swap": "swap",
    "profit": "gross_pnl",
}

_IBKR_BY_NAME: Final[dict[str, str]] = {
    "clientaccountid": "account",
    "assetclass": "asset_class",
    "symbol": "symbol",
    "currencyprimary": "currency",
    "buy sell": "side",
    "quantity": "qty",
    "tradeprice": "fill_price",
    "datetime": "fill_time",
    "ibcommission": "commission",
    "multiplier": "multiplier",
    "orderid": "order_id",
}


def detect_adapter(headers: Sequence[str]) -> AdapterSpec | None:
    names = {normalize_header(header) for header in headers}
    for spec in ADAPTERS:
        if spec.required <= names:
            return spec
    return None


def map_columns(spec: AdapterSpec, headers: Sequence[str]) -> dict[int, str]:
    """Return column index -> canonical or adapter field for the columns this adapter knows."""
    mapping: dict[int, str] = {}
    if spec.name == "mt5":
        price_seen = 0
        for index, header in enumerate(headers):
            name = normalize_header(_DUPLICATE_SUFFIX.sub("", header))
            if name == "price":
                # MT5 writes the open price and the close price under the same header.
                mapping[index] = "entry_price" if price_seen == 0 else "exit_price"
                price_seen += 1
            elif name in _MT5_BY_NAME:
                mapping[index] = _MT5_BY_NAME[name]
    elif spec.name == "tradingview":
        for index, header in enumerate(headers):
            name = normalize_header(header)
            if name == "trade number":
                mapping[index] = "trade_id"
            elif name == "type":
                mapping[index] = "leg"
            elif name == "date and time":
                mapping[index] = "leg_time"
            elif name == "signal":
                mapping[index] = "setup"
            elif name.startswith("position size"):
                mapping[index] = "qty"
            elif name.startswith("price"):
                mapping[index] = "leg_price"
            elif name.startswith("net p l"):
                mapping[index] = "net_pnl"
            elif name.startswith("favorable excursion"):
                mapping[index] = "mfe"
            elif name.startswith("adverse excursion"):
                mapping[index] = "mae"
    elif spec.name == "ibkr":
        for index, header in enumerate(headers):
            name = normalize_header(header)
            if name in _IBKR_BY_NAME:
                mapping[index] = _IBKR_BY_NAME[name]
    return mapping


def tradingview_currency(headers: Sequence[str]) -> str | None:
    """TradingView writes the currency into the price header, for example "Price USD"."""
    for header in headers:
        parts = normalize_header(header).split()
        if len(parts) == 2 and parts[0] == "price" and len(parts[1]) == 3:
            return parts[1].upper()
    return None


def default_contract_size(adapter: str | None, symbol: str) -> float | None:
    """A labelled default for MT5 symbols only. Other adapters need an explicit multiplier."""
    if adapter != "mt5":
        return None
    if symbol in MT5_DEFAULT_CONTRACT_SIZES:
        return MT5_DEFAULT_CONTRACT_SIZES[symbol]
    if _FX_PAIR.match(symbol):
        return MT5_STANDARD_FX_LOT
    return None
