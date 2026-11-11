"""Deterministic synthetic trades for fixtures and benchmarks.

The generative model is the contract. Later metric tests can recompute
population parameters from this file instead of trusting a stored total.

Population R, before the flat 1.00 fee, using the setup's own win rate:

- breakout:     0.48 * 1.8 + 0.52 * -1.0 = +0.344 R
- mean_revert:  0.55 * 0.9 + 0.45 * -1.0 = +0.045 R
- fomo:         0.35 * 1.1 + 0.65 * -1.0 = -0.265 R

Setup weights are breakout 0.45, mean_revert 0.40, fomo 0.15.
Every row is USD. A flat 1.00 fee is subtracted after R is applied, and the
stored r_multiple is net_pnl / planned_risk (fee included).
Planned risk is 0.5% of notional. A model win stays a net win at these sizes.
"""

from __future__ import annotations

import csv
import hashlib
import json
import random
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import TypedDict

COLUMNS: tuple[str, ...] = (
    "trade_id",
    "account",
    "symbol",
    "asset_class",
    "side",
    "entry_time",
    "exit_time",
    "qty",
    "entry_price",
    "exit_price",
    "fees",
    "planned_risk",
    "r_multiple",
    "net_pnl",
    "currency",
    "setup",
    "session",
    "emotion",
    "plan_followed",
    "notes",
)

FEE = 1.0
RISK_FRACTION = 0.005


class TradeRow(TypedDict):
    trade_id: str
    account: str
    symbol: str
    asset_class: str
    side: str
    entry_time: str
    exit_time: str
    qty: str
    entry_price: str
    exit_price: str
    fees: str
    planned_risk: str
    r_multiple: str
    net_pnl: str
    currency: str
    setup: str
    session: str
    emotion: str
    plan_followed: str
    notes: str


@dataclass(frozen=True)
class SymbolSpec:
    symbol: str
    asset_class: str
    price: float
    digits: int
    quantities: tuple[float, ...]


@dataclass(frozen=True)
class SetupSpec:
    name: str
    weight: float
    win_rate: float
    win_r: float
    loss_r: float
    hold_min: int
    hold_max: int


SYMBOLS: tuple[SymbolSpec, ...] = (
    SymbolSpec("AAPL", "equity", 190.0, 2, (10, 25, 50, 100)),
    SymbolSpec("MSFT", "equity", 420.0, 2, (5, 10, 20, 40)),
    SymbolSpec("NVDA", "equity", 880.0, 2, (5, 10, 20)),
    SymbolSpec("EURUSD", "forex", 1.085, 5, (10_000, 20_000, 50_000)),
    SymbolSpec("BTCUSD", "crypto", 65_000.0, 2, (0.05, 0.1, 0.25)),
)

SETUPS: tuple[SetupSpec, ...] = (
    SetupSpec("breakout", 0.45, 0.48, 1.8, 1.0, 45, 180),
    SetupSpec("mean_revert", 0.40, 0.55, 0.9, 1.0, 20, 90),
    SetupSpec("fomo", 0.15, 0.35, 1.1, 1.0, 5, 40),
)


def generate_rows(count: int, seed: int = 42) -> list[TradeRow]:
    if count < 1:
        raise ValueError("count must be at least 1")
    rng = random.Random(seed)
    cursor = datetime(2024, 1, 1, 22, 0, tzinfo=UTC)
    previous_loss = False
    rows: list[TradeRow] = []
    for index in range(count):
        entry = _next_entry(cursor, rng)
        symbol = SYMBOLS[rng.randrange(len(SYMBOLS))]
        setup = _pick_setup(rng)
        side = "long" if rng.random() < 0.5 else "short"
        win = rng.random() < setup.win_rate
        signed_r = setup.win_r if win else -setup.loss_r
        quantity = symbol.quantities[rng.randrange(len(symbol.quantities))]
        entry_price = round(symbol.price * (1 + rng.uniform(-0.01, 0.01)), symbol.digits)
        planned_risk = round(entry_price * RISK_FRACTION * quantity, 2)
        if planned_risk <= 0:
            raise RuntimeError(f"planned risk collapsed for {symbol.symbol}")
        gross = signed_r * planned_risk
        net = round(gross - FEE, 2)
        price_delta = (net + FEE) / quantity
        exit_price = entry_price + price_delta if side == "long" else entry_price - price_delta
        exit_price = round(exit_price, symbol.digits)
        # Rebuild net from the rounded exit so the row is internally consistent.
        signed_points = (exit_price - entry_price) if side == "long" else (entry_price - exit_price)
        net = round(signed_points * quantity - FEE, 2)
        r_multiple = round(net / planned_risk, 4)
        hold = rng.randint(setup.hold_min, setup.hold_max)
        exit_time = _exit_at(entry, hold)
        emotion = _emotion(setup.name, previous_loss, rng)
        plan_followed = _plan_followed(emotion, rng)
        notes = _notes(emotion, rng)
        rows.append(
            TradeRow(
                trade_id=f"T{index + 1:06d}",
                account="primary",
                symbol=symbol.symbol,
                asset_class=symbol.asset_class,
                side=side,
                entry_time=_iso(entry),
                exit_time=_iso(exit_time),
                qty=_qty(quantity),
                entry_price=f"{entry_price:.{symbol.digits}f}",
                exit_price=f"{exit_price:.{symbol.digits}f}",
                fees=f"{FEE:.2f}",
                planned_risk=f"{planned_risk:.2f}",
                r_multiple=f"{r_multiple:.4f}",
                net_pnl=f"{net:.2f}",
                currency="USD",
                setup=setup.name,
                session=_session(entry.hour),
                emotion=emotion,
                plan_followed="true" if plan_followed else "false",
                notes=notes,
            )
        )
        previous_loss = net < 0
        cursor = exit_time
    return rows


def write_csv(rows: Sequence[TradeRow], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_manifest(
    rows: Sequence[TradeRow], csv_path: Path, manifest_path: Path, seed: int
) -> None:
    digest = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    wins = sum(1 for row in rows if float(row["net_pnl"]) > 0)
    net_sum = round(sum(float(row["net_pnl"]) for row in rows), 2)
    payload = {
        "currency": "USD",
        "fee_per_trade": FEE,
        "model_expectancy_r_before_fees": {
            "breakout": 0.344,
            "fomo": -0.265,
            "mean_revert": 0.045,
        },
        "net_pnl_sum": net_sum,
        "risk_fraction": RISK_FRACTION,
        "rows": len(rows),
        "seed": seed,
        "setup_weights": {setup.name: setup.weight for setup in SETUPS},
        "sha256": digest,
        "wins": wins,
    }
    manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _pick_setup(rng: random.Random) -> SetupSpec:
    weights = [setup.weight for setup in SETUPS]
    return rng.choices(SETUPS, weights=weights, k=1)[0]


def _next_entry(cursor: datetime, rng: random.Random) -> datetime:
    if rng.random() < 0.18:
        day = _next_weekday(cursor.date() + timedelta(days=1))
        return datetime.combine(day, time(rng.randint(0, 6), rng.randint(0, 59)), tzinfo=UTC)
    if cursor.hour >= 17:
        day = _next_weekday(cursor.date() + timedelta(days=1))
        return datetime.combine(day, time(rng.randint(8, 12), rng.randint(0, 59)), tzinfo=UTC)
    return cursor + timedelta(minutes=rng.randint(3, 45))


def _exit_at(entry: datetime, hold: int) -> datetime:
    exit_time = entry + timedelta(minutes=hold)
    same_day = exit_time.date() == entry.date() and exit_time.weekday() < 5 and exit_time.hour < 21
    if same_day and exit_time > entry:
        return exit_time
    clamped = entry.replace(hour=20, minute=50)
    if clamped > entry and clamped.weekday() < 5:
        return clamped
    return entry + timedelta(minutes=15)


def _emotion(setup: str, previous_loss: bool, rng: random.Random) -> str:
    if setup == "fomo":
        return "fomo"
    if previous_loss and rng.random() < 0.5:
        return "revenge"
    return "calm"


def _plan_followed(emotion: str, rng: random.Random) -> bool:
    if emotion == "calm":
        return rng.random() >= 0.05
    if emotion == "fomo":
        return rng.random() >= 0.70
    return rng.random() >= 0.75


def _notes(emotion: str, rng: random.Random) -> str:
    if emotion == "revenge" and rng.random() < 0.30:
        return "sized up after a loss"
    if emotion == "fomo" and rng.random() < 0.30:
        return "chased the move"
    return ""


def _session(hour: int) -> str:
    if hour < 7:
        return "asia"
    if hour < 13:
        return "london"
    return "new_york"


def _next_weekday(day: date) -> date:
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _qty(quantity: float) -> str:
    if float(quantity).is_integer():
        return str(int(quantity))
    return f"{quantity:.8f}".rstrip("0").rstrip(".")
