"""Turn one parsed row into a validated trade, or into the reasons it was rejected."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Final
from zoneinfo import ZoneInfo

from obsidian_ledger.ingest.adapters import default_contract_size
from obsidian_ledger.ingest.parse import (
    DecimalStyle,
    parse_number,
    parse_side,
    parse_time,
    time_precision,
)
from obsidian_ledger.ingest.trade import Draft, Reason, Trade

PRICE_TOLERANCE_FLOOR: Final = 0.01
R_TOLERANCE: Final = 0.0006
NET_TOLERANCE: Final = 0.01
_DECIMALS: Final = re.compile(r"[.,](\d+)$")


@dataclass(frozen=True)
class Context:
    tz: ZoneInfo
    tz_name: str
    slash_family: str | None
    decimal: DecimalStyle
    default_symbol: str | None
    default_account: str
    default_currency: str
    adapter: str | None
    base_currency: str
    contract_sizes: Mapping[str, float]
    symbol_aliases: Mapping[str, str]


@dataclass
class Checks:
    """Errors reject the row. Warnings are kept on the trade for the quality report."""

    errors: list[Reason] = field(default_factory=list[Reason])
    warnings: list[Reason] = field(default_factory=list[Reason])


def session_for_hour(hour_utc: int) -> str:
    if hour_utc < 7:
        return "asia"
    if hour_utc < 13:
        return "london"
    return "new_york"


def resolve_symbol(symbol: str, ctx: Context) -> str:
    value = symbol.strip()
    return ctx.symbol_aliases.get(value, value)


def parse_timestamp(raw: str, ctx: Context) -> tuple[datetime, bool] | None:
    """Return (UTC-aware time, had_offset). Naive times are read in the file's timezone."""
    parsed = parse_time(raw, ctx.slash_family)
    if parsed is None:
        return None
    value, has_offset = parsed
    if has_offset:
        return value.astimezone(UTC), True
    return value.replace(tzinfo=ctx.tz).astimezone(UTC), False


def _decimals(raw: str) -> int:
    match = _DECIMALS.search(raw.strip())
    return len(match.group(1)) if match else 0


def number_field(
    values: Mapping[str, str], name: str, ctx: Context, checks: Checks
) -> float | None:
    raw = values.get(name, "").strip()
    if not raw:
        return None
    value = parse_number(raw, ctx.decimal)
    if value is None:
        checks.errors.append(Reason("bad_number", f"{name} '{raw}' is not a number."))
    return value


def parse_bool(raw: str) -> bool | None:
    text = raw.strip().lower()
    if text in {"true", "yes", "y", "1"}:
        return True
    if text in {"false", "no", "n", "0"}:
        return False
    return None


def resolve_multiplier(
    symbol: str, values: Mapping[str, str], ctx: Context, checks: Checks
) -> float | None:
    if symbol in ctx.contract_sizes:
        return ctx.contract_sizes[symbol]
    if values.get("multiplier", "").strip():
        return number_field(values, "multiplier", ctx, checks)
    return default_contract_size(ctx.adapter, symbol)


def draft_from_values(
    values: Mapping[str, str],
    source_rows: tuple[int, ...],
    ctx: Context,
    checks: Checks,
    *,
    round_trip: bool,
) -> Draft:
    """Build a draft from the mapped cells of one row. Parse errors go into checks."""
    symbol = resolve_symbol(values.get("symbol", ""), ctx) or (ctx.default_symbol or "")
    if not symbol:
        checks.errors.append(
            Reason("missing_symbol", "The row has no symbol and no default was given.")
        )

    side = parse_side(values.get("side", ""))
    if side is None:
        checks.errors.append(
            Reason("bad_side", f"Side '{values.get('side', '')}' is not buy, sell, long, or short.")
        )

    entry_raw = values.get("entry_time", "").strip()
    if values.get("entry_clock", "").strip() and not re.search(r"\d{1,2}:\d{2}", entry_raw):
        entry_raw = f"{entry_raw} {values['entry_clock'].strip()}".strip()
    entry_time: datetime | None = None
    has_offset = False
    if not entry_raw:
        checks.errors.append(Reason("missing_entry_time", "The row has no entry time."))
    else:
        parsed = parse_timestamp(entry_raw, ctx)
        if parsed is None:
            checks.errors.append(
                Reason("bad_time", f"Entry time '{entry_raw}' is not a recognised date.")
            )
        else:
            entry_time, has_offset = parsed

    exit_time: datetime | None = None
    exit_raw = values.get("exit_time", "").strip()
    if values.get("exit_clock", "").strip() and not re.search(r"\d{1,2}:\d{2}", exit_raw):
        exit_raw = f"{exit_raw} {values['exit_clock'].strip()}".strip()
    if round_trip:
        if not exit_raw:
            checks.errors.append(Reason("missing_exit_time", "The row has no exit time."))
        else:
            parsed_exit = parse_timestamp(exit_raw, ctx)
            if parsed_exit is None:
                checks.errors.append(
                    Reason("bad_time", f"Exit time '{exit_raw}' is not a recognised date.")
                )
            else:
                exit_time = parsed_exit[0]

    qty_raw = values.get("qty", "").strip()
    qty: float | None = None
    if not qty_raw:
        checks.errors.append(Reason("bad_quantity", "The row has no quantity."))
    else:
        value = number_field(values, "qty", ctx, checks)
        if value is not None:
            if value == 0:
                checks.errors.append(Reason("zero_quantity", "Quantity is zero."))
            else:
                qty = abs(value)

    entry_price = number_field(values, "entry_price", ctx, checks)
    exit_price = number_field(values, "exit_price", ctx, checks)
    gross = number_field(values, "gross_pnl", ctx, checks)
    net = number_field(values, "net_pnl", ctx, checks)
    commission = number_field(values, "commission", ctx, checks)
    swap = number_field(values, "swap", ctx, checks)
    fees_raw = number_field(values, "fees", ctx, checks)
    # Fees and taxes are written as positive costs in most exports. Store them as negative.
    fees = -abs(fees_raw) if fees_raw is not None else None

    decimals = max(
        _decimals(values.get("entry_price", "")),
        _decimals(values.get("exit_price", "")),
    )
    multiplier = resolve_multiplier(symbol, values, ctx, checks) if symbol else None

    return Draft(
        source_rows=source_rows,
        trade_id=values.get("trade_id", "").strip() or None,
        account=values.get("account", "").strip() or ctx.default_account,
        symbol=symbol,
        asset_class=values.get("asset_class", "").strip() or None,
        side=side,
        entry_time=entry_time,
        exit_time=exit_time,
        has_offset=has_offset,
        qty=qty,
        multiplier=multiplier,
        entry_price=entry_price,
        exit_price=exit_price,
        price_decimals=decimals,
        fees=fees,
        commission=commission,
        swap=swap,
        gross_pnl=gross,
        net_pnl=net,
        currency=(values.get("currency", "").strip().upper() or ctx.default_currency),
        stop_loss=number_field(values, "stop_loss", ctx, checks),
        take_profit=number_field(values, "take_profit", ctx, checks),
        planned_risk=number_field(values, "planned_risk", ctx, checks),
        provided_r=number_field(values, "r_multiple", ctx, checks),
        mae=number_field(values, "mae", ctx, checks),
        mfe=number_field(values, "mfe", ctx, checks),
        setup=values.get("setup", "").strip() or None,
        timeframe=values.get("timeframe", "").strip() or None,
        session=values.get("session", "").strip().lower() or None,
        emotion=values.get("emotion", "").strip().lower() or None,
        tags=values.get("tags", "").strip() or None,
        notes=values.get("notes", ""),
        plan_followed=parse_bool(values.get("plan_followed", "")),
        confidence=values.get("confidence", "").strip() or None,
        screenshot_path=values.get("screenshot_path", "").strip() or None,
        time_precision=max(
            (time_precision(value) for value in (entry_raw, exit_raw) if value),
            key=lambda value: {"second": 0, "minute": 1, "hour": 2, "day": 3}[value],
            default="second",
        ),
        entry_notional=number_field(values, "notional", ctx, checks),
        exit_notional=number_field(values, "exit_notional", ctx, checks),
        leverage=number_field(values, "leverage", ctx, checks),
        order_type=values.get("order_type", "").strip() or None,
        status=values.get("status", "").strip() or None,
        action=values.get("action", "").strip() or None,
    )


def finalize(draft: Draft, checks: Checks, ctx: Context) -> Trade | list[Reason]:
    """Run the cross-field checks, compute P&L and R, and build the stored trade."""
    if checks.errors:
        return checks.errors
    assert draft.side is not None and draft.entry_time is not None and draft.qty is not None
    entry = draft.entry_time
    if draft.exit_time is None:
        return [Reason("missing_exit_time", "The row has no exit time.")]
    exit_time = draft.exit_time
    if exit_time < entry:
        return [Reason("negative_duration", "The exit time is before the entry time.")]

    multiplier = draft.multiplier if draft.multiplier is not None else 1.0
    costs = (draft.fees or 0.0) + (draft.commission or 0.0) + (draft.swap or 0.0)
    sign = 1.0 if draft.side == "long" else -1.0
    implied: float | None = None
    if draft.entry_price is not None and draft.exit_price is not None:
        implied = sign * (draft.exit_price - draft.entry_price) * draft.qty * multiplier

    reported_gross: float | None = None
    if draft.gross_pnl is not None:
        reported_gross = draft.gross_pnl
    elif draft.net_pnl is not None:
        reported_gross = draft.net_pnl - costs
    gross = reported_gross if reported_gross is not None else implied
    net = (
        draft.net_pnl if draft.net_pnl is not None else gross + costs if gross is not None else None
    )

    warnings = list(checks.warnings)
    if reported_gross is not None and draft.gross_pnl is not None and draft.net_pnl is not None:
        if abs(draft.net_pnl - (draft.gross_pnl + costs)) > NET_TOLERANCE:
            warnings.append(Reason("net_mismatch", "Net P&L differs from gross P&L plus costs."))
    if reported_gross is not None and implied is not None:
        tolerance = PRICE_TOLERANCE_FLOOR + 0.5 * draft.qty * multiplier * 10 ** (
            -draft.price_decimals
        )
        if abs(reported_gross - implied) > tolerance:
            warnings.append(
                Reason(
                    "pnl_mismatch",
                    f"Reported gross P&L {reported_gross:.2f} differs from the price-implied "
                    f"{implied:.2f}. Check the contract size and quote currency.",
                )
            )

    risk = draft.planned_risk
    if risk is None and draft.stop_loss is not None and draft.entry_price is not None:
        stop_risk = abs(draft.entry_price - draft.stop_loss) * draft.qty * multiplier
        risk = stop_risk if stop_risk > 0 else None
    r_value: float | None = None
    if risk is not None and risk > 0:
        r_value = net / risk if net is not None else None
        if (
            draft.provided_r is not None
            and r_value is not None
            and abs(draft.provided_r - r_value) > R_TOLERANCE
        ):
            warnings.append(
                Reason(
                    "r_mismatch",
                    f"Provided R {draft.provided_r} differs from net / risk {r_value:.4f}.",
                )
            )
    elif draft.provided_r is not None and net is not None:
        r_value = draft.provided_r
    if risk is None:
        warnings.append(Reason("missing_risk", "No planned risk or stop, so R is unavailable."))
    if not draft.has_offset:
        warnings.append(Reason("timezone_assumed", f"Naive timestamps were read in {ctx.tz_name}."))
    if draft.time_precision in {"hour", "day"}:
        warnings.append(
            Reason(
                "time_precision",
                f"The source timestamp is only precise to the {draft.time_precision}; "
                "holding time is approximate.",
            )
        )

    key_parts = [
        draft.account,
        draft.symbol,
        draft.side,
        entry.isoformat(),
        exit_time.isoformat(),
        f"{draft.qty:.8f}",
        f"{draft.entry_price}",
        f"{draft.exit_price}",
        f"{net:.2f}" if net is not None else "unknown",
    ]
    trade_key = hashlib.sha256("|".join(key_parts).encode("utf-8")).hexdigest()
    hour = entry.hour
    return Trade(
        trade_key=trade_key,
        trade_id=draft.trade_id or trade_key[:16],
        account=draft.account,
        symbol=draft.symbol,
        asset_class=draft.asset_class,
        side=draft.side,
        entry_time=entry,
        exit_time=exit_time,
        source_timezone=None if draft.has_offset else ctx.tz_name,
        qty=draft.qty,
        multiplier=multiplier,
        entry_price=draft.entry_price,
        exit_price=draft.exit_price,
        fees=draft.fees,
        commission=draft.commission,
        swap=draft.swap,
        gross_pnl=round(gross, 8) if gross is not None else None,
        net_pnl=round(net, 8) if net is not None else None,
        currency=draft.currency,
        net_pnl_base=None,
        base_currency=ctx.base_currency,
        stop_loss=draft.stop_loss,
        take_profit=draft.take_profit,
        planned_risk=round(risk, 8) if risk is not None else None,
        r_multiple=round(r_value, 6) if r_value is not None else None,
        mae=draft.mae,
        mfe=draft.mfe,
        setup=draft.setup,
        timeframe=draft.timeframe,
        session=draft.session or session_for_hour(hour),
        tags=draft.tags,
        notes=draft.notes,
        emotion=draft.emotion,
        plan_followed=draft.plan_followed,
        confidence=draft.confidence,
        screenshot_path=draft.screenshot_path,
        holding_seconds=(
            (exit_time - entry).total_seconds() if draft.time_precision != "day" else None
        ),
        weekday=entry.weekday(),
        hour_utc=hour,
        source_row=draft.source_rows[0],
        time_precision=draft.time_precision,
        entry_notional=draft.entry_notional,
        exit_notional=draft.exit_notional,
        leverage=draft.leverage,
        order_type=draft.order_type,
        status=draft.status,
        action=draft.action,
        warnings=warnings,
    )
