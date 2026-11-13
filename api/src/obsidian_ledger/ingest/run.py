"""Run one import: read every record, validate it, and collect trades and rejected rows."""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict, deque
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Final, Literal

import polars as pl

from obsidian_ledger.ingest.adapters import IBKR_ASSET_CLASSES
from obsidian_ledger.ingest.analysis import Analysis
from obsidian_ledger.ingest.fifo import Fill, OpenRemainder, pair_fills
from obsidian_ledger.ingest.frames import empty_accepted, frame_from_trades, trades_from_frame
from obsidian_ledger.ingest.normalize import (
    Checks,
    Context,
    draft_from_values,
    finalize,
    number_field,
    parse_timestamp,
    resolve_multiplier,
    resolve_symbol,
)
from obsidian_ledger.ingest.options import ImportOptions
from obsidian_ledger.ingest.parse import parse_number, parse_side, parse_side_action, time_precision
from obsidian_ledger.ingest.trade import Draft, Reason, Rejected, Trade
from obsidian_ledger.ingest.vector import run_round_trip

_FORMULA_START: Final = re.compile(r"^[=+\-@\t\r]")


@dataclass
class RunOutcome:
    """Result of one import. Accepted trades live in `frame`, the form the store and quality use.

    `trades` builds Trade objects from the frame on first access. The legs and executions shapes
    still produce Trade objects directly, and those are kept as they are.
    """

    frame: pl.DataFrame = field(default_factory=empty_accepted)
    rejected: list[Rejected] = field(default_factory=list[Rejected])
    rows_total: int = 0
    blank_rows: int = 0
    open_positions: list[OpenRemainder] = field(default_factory=list[OpenRemainder])
    fx_missing: dict[str, int] = field(default_factory=dict[str, int])
    formula_rows: list[int] = field(default_factory=list[int])
    activity_events: list[dict[str, object]] = field(default_factory=list[dict[str, object]])
    data_warnings: tuple[str, ...] = ()
    orphan_closes: int = 0
    duplicates_in_file: int = 0
    quantity_conserved: bool = True
    _trades: list[Trade] | None = None

    @property
    def trades(self) -> list[Trade]:
        if self._trades is None:
            self._trades = trades_from_frame(self.frame)
        return self._trades

    def reject(self, row: int, reasons: list[Reason], cells: list[str]) -> None:
        self.rejected.append(Rejected(row, reasons, cells))


@dataclass(frozen=True)
class _OrderEvent:
    row: int
    order: int
    account: str
    symbol: str
    direction: Literal["long", "short"]
    action: str | None
    quantity: float | None
    notional: float | None
    price: float | None
    fees: float | None
    commission: float | None
    swap: float | None
    gross_pnl: float | None
    net_pnl: float | None
    time: datetime
    has_offset: bool
    precision: str
    currency: str
    asset_class: str | None
    leverage: float | None
    order_type: str | None
    status: str | None
    duplicate: bool


@dataclass
class _OrderLot:
    event: _OrderEvent
    remaining: float


def _is_formula_like(cell: str) -> bool:
    text = cell.strip()
    if not text:
        return False
    if not _FORMULA_START.match(text):
        return False
    if text[0] in "+-" and parse_number(text, "dot") is not None:
        return False
    return parse_number(text, "comma") is None


def _values(cells: list[str], field_index: Mapping[str, int]) -> dict[str, str]:
    return {
        name: cells[index].strip() if index < len(cells) else ""
        for name, index in field_index.items()
    }


def _field_count_ok(row: list[str], width: int) -> bool:
    if len(row) < width:
        return False
    return not any(cell.strip() for cell in row[width:])


def _apply_fx(outcome: RunOutcome, options: ImportOptions, base: str) -> None:
    for trade in outcome.trades:
        if trade.net_pnl is None:
            trade.net_pnl_base = None
            continue
        if trade.currency == base:
            trade.net_pnl_base = trade.net_pnl
        elif trade.currency in options.fx_rates:
            trade.net_pnl_base = trade.net_pnl * options.fx_rates[trade.currency]
        else:
            trade.net_pnl_base = None
            outcome.fx_missing[trade.currency] = outcome.fx_missing.get(trade.currency, 0) + 1


def _run_legs(analysis: Analysis, ctx: Context, outcome: RunOutcome) -> None:
    width = len(analysis.source.headers)
    groups: dict[str, dict[str, tuple[int, list[str], dict[str, str]]]] = {}
    order: list[str] = []
    for number, row in analysis.source.iter_records():
        if not any(cell.strip() for cell in row):
            outcome.blank_rows += 1
            continue
        outcome.rows_total += 1
        if not _field_count_ok(row, width):
            outcome.reject(
                number,
                [Reason("field_count", f"Row has {len(row)} cells; the header has {width}.")],
                row,
            )
            continue
        cells = row[:width]
        values = _values(cells, analysis.field_index)
        leg_text = values.get("leg", "").lower()
        kind = "entry" if "entry" in leg_text else "exit" if "exit" in leg_text else None
        trade_no = values.get("trade_id", "")
        if kind is None:
            outcome.reject(
                number,
                [
                    Reason(
                        "unknown_leg", f"Leg '{values.get('leg', '')}' is neither entry nor exit."
                    )
                ],
                cells,
            )
            continue
        if not trade_no:
            outcome.reject(
                number,
                [
                    Reason(
                        "missing_trade_id", "The leg has no trade number, so it cannot be paired."
                    )
                ],
                cells,
            )
            continue
        group = groups.get(trade_no)
        if group is None:
            group = {}
            groups[trade_no] = group
            order.append(trade_no)
        if kind in group:
            outcome.reject(
                number,
                [Reason("duplicate_leg", f"Trade {trade_no} already has an {kind} leg.")],
                cells,
            )
            continue
        group[kind] = (number, cells, values)

    for trade_no in order:
        group = groups[trade_no]
        if "entry" not in group or "exit" not in group:
            missing = "exit" if "entry" in group else "entry"
            for number, cells, _values_map in group.values():
                outcome.reject(
                    number,
                    [Reason(f"missing_{missing}_leg", f"Trade {trade_no} has no {missing} leg.")],
                    cells,
                )
            continue
        entry_no, entry_cells, entry = group["entry"]
        exit_no, exit_cells, exit_leg = group["exit"]
        merged = dict(entry)
        merged.update(
            {
                "side": entry.get("leg", ""),
                "entry_time": entry.get("leg_time", ""),
                "exit_time": exit_leg.get("leg_time", ""),
                "entry_price": entry.get("leg_price", ""),
                "exit_price": exit_leg.get("leg_price", ""),
                "net_pnl": exit_leg.get("net_pnl", ""),
                "mfe": exit_leg.get("mfe", ""),
                "mae": exit_leg.get("mae", ""),
                "trade_id": trade_no,
            }
        )
        checks = Checks()
        if any(_is_formula_like(cell) for cell in entry_cells + exit_cells):
            checks.warnings.append(
                Reason(
                    "formula_like_cell",
                    "A cell starts like a formula. It was stored as text and not evaluated.",
                )
            )
            outcome.formula_rows.append(entry_no)
        draft = draft_from_values(merged, (entry_no, exit_no), ctx, checks, round_trip=True)
        result = finalize(draft, checks, ctx)
        if isinstance(result, list):
            outcome.reject(entry_no, result, entry_cells)
            outcome.reject(exit_no, result, exit_cells)
            continue
        outcome.trades.append(result)


def _fill_from(
    number: int,
    cells: list[str],
    analysis: Analysis,
    ctx: Context,
    checks: Checks,
) -> Fill | None:
    values = _values(cells, analysis.field_index)
    side = parse_side(values.get("side", ""))
    if side is None:
        checks.errors.append(
            Reason("bad_side", f"Side '{values.get('side', '')}' is not buy or sell.")
        )
    quantity = number_field(values, "qty", ctx, checks)
    if quantity is not None and quantity == 0:
        checks.errors.append(Reason("zero_quantity", "Fill quantity is zero."))
    price_name = "fill_price" if "fill_price" in analysis.field_index else "entry_price"
    time_name = "fill_time" if "fill_time" in analysis.field_index else "entry_time"
    price_values = dict(values)
    price_values["entry_price"] = values.get(price_name, "")
    price = number_field(price_values, "entry_price", ctx, checks)
    time_raw = values.get(time_name, "")
    parsed = parse_timestamp(time_raw, ctx) if time_raw else None
    if parsed is None:
        checks.errors.append(
            Reason("bad_time", f"Fill time '{time_raw}' is not a recognised date.")
        )
    symbol = resolve_symbol(values.get("symbol", ""), ctx) or (ctx.default_symbol or "")
    if not symbol:
        checks.errors.append(Reason("missing_symbol", "The fill has no symbol."))
    commission = number_field(values, "commission", ctx, checks) or 0.0
    multiplier = resolve_multiplier(symbol, values, ctx, checks) if symbol else None
    if checks.errors or side is None or quantity is None or price is None or parsed is None:
        return None
    asset_raw = values.get("asset_class", "")
    asset_class = (
        IBKR_ASSET_CLASSES.get(asset_raw.upper(), asset_raw.lower() or None)
        if ctx.adapter == "ibkr"
        else (asset_raw.lower() or None)
    )
    time_value, has_offset = parsed
    return Fill(
        row=number,
        account=values.get("account", "") or ctx.default_account,
        symbol=symbol,
        asset_class=asset_class,
        currency=(values.get("currency", "").upper() or ctx.default_currency),
        side=side,
        qty=abs(quantity),
        price=price,
        time=time_value,
        commission=commission,
        multiplier=multiplier if multiplier is not None else 1.0,
        order_id=values.get("order_id", "") or None,
        has_offset=has_offset,
    )


def _run_executions(analysis: Analysis, ctx: Context, outcome: RunOutcome) -> None:
    width = len(analysis.source.headers)
    fills: list[Fill] = []
    cells_by_row: dict[int, list[str]] = {}
    seen_rows: set[bytes] = set()
    duplicate_rows: set[int] = set()
    for number, row in analysis.source.iter_records():
        if not any(cell.strip() for cell in row):
            outcome.blank_rows += 1
            continue
        outcome.rows_total += 1
        if not _field_count_ok(row, width):
            outcome.reject(
                number,
                [Reason("field_count", f"Row has {len(row)} cells; the header has {width}.")],
                row,
            )
            continue
        cells = row[:width]
        checks = Checks()
        fill = _fill_from(number, cells, analysis, ctx, checks)
        if fill is None:
            outcome.reject(number, checks.errors, cells)
            continue
        signature = hashlib.sha256("\x1f".join(cells).encode("utf-8")).digest()
        if signature in seen_rows:
            duplicate_rows.add(number)
            outcome.duplicates_in_file += 1
        seen_rows.add(signature)
        cells_by_row[number] = cells
        fills.append(fill)

    legs, remainders = pair_fills(fills)
    outcome.open_positions = remainders
    seen_keys: set[str] = set()
    for leg in legs:
        open_fill, close_fill = leg.open_fill, leg.close_fill
        draft = Draft(
            source_rows=(open_fill.row, close_fill.row),
            trade_id=(
                f"{open_fill.order_id or open_fill.row}-"
                f"{close_fill.order_id or close_fill.row}-{leg.sequence}"
            ),
            account=open_fill.account,
            symbol=open_fill.symbol,
            asset_class=open_fill.asset_class,
            side=open_fill.side,
            entry_time=open_fill.time,
            exit_time=close_fill.time,
            has_offset=open_fill.has_offset and close_fill.has_offset,
            qty=leg.qty,
            multiplier=open_fill.multiplier,
            entry_price=open_fill.price,
            exit_price=close_fill.price,
            price_decimals=0,
            fees=0.0,
            commission=leg.commission,
            swap=0.0,
            gross_pnl=None,
            net_pnl=None,
            currency=open_fill.currency,
        )
        checks = Checks()
        if open_fill.row in duplicate_rows or close_fill.row in duplicate_rows:
            checks.warnings.append(
                Reason(
                    "duplicate_kept", "An exact duplicate source row was kept as a separate fill."
                )
            )
        result = finalize(draft, checks, ctx)
        if isinstance(result, list):
            outcome.reject(open_fill.row, result, cells_by_row.get(open_fill.row, []))
            outcome.reject(close_fill.row, result, cells_by_row.get(close_fill.row, []))
            continue
        if result.trade_key in seen_keys:
            result.trade_key = hashlib.sha256(
                f"{result.trade_key}|rows:{open_fill.row}:{close_fill.row}".encode()
            ).hexdigest()
        seen_keys.add(result.trade_key)
        outcome.trades.append(result)


def _event_time(values: Mapping[str, str], ctx: Context) -> tuple[datetime, bool, str] | None:
    raw = values.get("entry_time", "") or values.get("fill_time", "")
    clock = values.get("entry_clock", "")
    if clock and not re.search(r"\d{1,2}:\d{2}", raw):
        raw = f"{raw} {clock}".strip()
    parsed = parse_timestamp(raw, ctx) if raw else None
    return (parsed[0], parsed[1], time_precision(raw)) if parsed is not None else None


def _consume_order(
    event: _OrderEvent,
    queue: deque[_OrderLot],
    outcome: RunOutcome,
    ctx: Context,
    sequence: dict[tuple[str, ...], int],
    seen_keys: dict[str, int],
    key: tuple[str, ...],
    *,
    netting: bool,
) -> float:
    remaining = event.quantity or 0.0
    while remaining > 1e-9 and queue:
        lot = queue[0]
        if netting and lot.event.direction == event.direction:
            break
        matched = min(lot.remaining, remaining)
        sequence[key] = sequence.get(key, 0) + 1
        opening, closing = lot.event, event
        checks = Checks()
        if opening.duplicate or closing.duplicate:
            checks.warnings.append(
                Reason(
                    "duplicate_kept", "An exact duplicate source row was kept as a separate fill."
                )
            )
        precision_rank = {"second": 0, "minute": 1, "hour": 2, "day": 3}
        precision = max((opening.precision, closing.precision), key=precision_rank.__getitem__)
        open_fraction = matched / (opening.quantity or matched)
        close_fraction = matched / (closing.quantity or matched)
        entry_price = opening.price
        exit_price = closing.price
        draft = Draft(
            source_rows=(opening.row, closing.row),
            trade_id=f"order-{opening.row}-{closing.row}-{sequence[key]}",
            account=opening.account,
            symbol=opening.symbol,
            asset_class=opening.asset_class or closing.asset_class,
            side=opening.direction,  # type: ignore[arg-type]
            entry_time=opening.time,
            exit_time=closing.time,
            has_offset=opening.has_offset and closing.has_offset,
            qty=matched,
            multiplier=1.0,
            entry_price=entry_price,
            exit_price=exit_price,
            price_decimals=0,
            fees=(
                (opening.fees or 0.0) * open_fraction + (closing.fees or 0.0) * close_fraction
                if opening.fees is not None and closing.fees is not None
                else None
            ),
            commission=(
                (opening.commission or 0.0) * open_fraction
                + (closing.commission or 0.0) * close_fraction
                if opening.commission is not None and closing.commission is not None
                else None
            ),
            swap=(
                (opening.swap or 0.0) * open_fraction + (closing.swap or 0.0) * close_fraction
                if opening.swap is not None and closing.swap is not None
                else None
            ),
            gross_pnl=(
                closing.gross_pnl * close_fraction if closing.gross_pnl is not None else None
            ),
            net_pnl=closing.net_pnl * close_fraction if closing.net_pnl is not None else None,
            currency=opening.currency,
            time_precision=precision,
            entry_notional=opening.notional,
            exit_notional=closing.notional,
            leverage=closing.leverage if closing.leverage is not None else opening.leverage,
            order_type=closing.order_type or opening.order_type,
            status=closing.status,
            action="close",
        )
        result = finalize(draft, checks, ctx)
        if isinstance(result, list):
            outcome.reject(opening.row, result, [])
            outcome.reject(closing.row, result, [])
        else:
            base_key = result.trade_key
            occurrence = seen_keys.get(base_key, 0)
            if occurrence:
                result.trade_key = hashlib.sha256(
                    f"{base_key}|occurrence:{occurrence}".encode()
                ).hexdigest()
            seen_keys[base_key] = occurrence + 1
            outcome.trades.append(result)
        lot.remaining -= matched
        remaining -= matched
        if lot.remaining <= 1e-9:
            queue.popleft()
    return remaining


def _run_orders(
    analysis: Analysis, ctx: Context, outcome: RunOutcome, options: ImportOptions
) -> None:
    width = len(analysis.source.headers)
    events: list[_OrderEvent] = []
    seen_rows: set[bytes] = set()
    for order, (number, row) in enumerate(analysis.source.iter_records()):
        if not any(cell.strip() for cell in row):
            outcome.blank_rows += 1
            continue
        outcome.rows_total += 1
        if not _field_count_ok(row, width):
            outcome.reject(
                number,
                [Reason("field_count", f"Row has {len(row)} cells; the header has {width}.")],
                row,
            )
            continue
        cells = row[:width]
        values = _values(cells, analysis.field_index)
        checks = Checks()
        symbol = resolve_symbol(values.get("symbol", ""), ctx) or (ctx.default_symbol or "")
        if not symbol:
            checks.errors.append(Reason("missing_symbol", "The order has no instrument."))
        raw_side = values.get("side", "")
        action, direction = parse_side_action(raw_side)
        explicit_action = values.get("action", "").strip().lower()
        if explicit_action in {"open", "opening", "entry"}:
            action = "open"
        elif explicit_action in {"close", "closing", "exit"}:
            action = "close"
        if direction is None:
            checks.errors.append(Reason("bad_side", f"Direction '{raw_side}' is not recognised."))
        parsed_time = _event_time(values, ctx)
        if parsed_time is None:
            checks.errors.append(
                Reason(
                    "bad_time", f"Event time '{values.get('entry_time', '')}' is not recognised."
                )
            )
        quantity = number_field(values, "qty", ctx, checks)
        if quantity is not None and quantity <= 0:
            checks.errors.append(
                Reason("zero_quantity", "Order quantity must be greater than zero.")
            )
        notional = number_field(values, "notional", ctx, checks)
        price_values = dict(values)
        price_values["entry_price"] = values.get("fill_price", "") or values.get("entry_price", "")
        price = number_field(price_values, "entry_price", ctx, checks)
        leverage = number_field(values, "leverage", ctx, checks)
        fees_value = number_field(values, "fees", ctx, checks)
        fees = -abs(fees_value) if fees_value is not None else None
        commission = number_field(values, "commission", ctx, checks)
        swap = number_field(values, "swap", ctx, checks)
        gross_pnl = number_field(values, "gross_pnl", ctx, checks)
        net_pnl = number_field(values, "net_pnl", ctx, checks)
        if checks.errors or direction not in ("long", "short") or parsed_time is None:
            outcome.reject(number, checks.errors, cells)
            continue
        signature = hashlib.sha256("\x1f".join(cells).encode("utf-8")).digest()
        duplicate = signature in seen_rows
        if duplicate:
            outcome.duplicates_in_file += 1
        seen_rows.add(signature)
        time_value, has_offset, precision = parsed_time
        event = _OrderEvent(
            row=number,
            order=order,
            account=values.get("account", "") or ctx.default_account,
            symbol=symbol,
            direction=direction,
            action=action,
            quantity=abs(quantity) if quantity is not None else None,
            notional=notional,
            price=price,
            fees=fees,
            commission=commission,
            swap=swap,
            gross_pnl=gross_pnl,
            net_pnl=net_pnl,
            time=time_value,
            has_offset=has_offset,
            precision=precision,
            currency=(values.get("currency", "").upper() or ctx.default_currency),
            asset_class=values.get("asset_class", "").lower() or None,
            leverage=leverage,
            order_type=values.get("order_type", "").strip() or None,
            status=values.get("status", "").strip() or None,
            duplicate=duplicate,
        )
        events.append(event)
        outcome.activity_events.append(
            {
                "account": event.account,
                "symbol": event.symbol,
                "direction": event.direction,
                "action": event.action,
                "quantity": event.quantity,
                "notional": event.notional,
                "event_time": event.time.astimezone(UTC).replace(tzinfo=None),
                "time_precision": event.precision,
                "leverage": event.leverage,
                "order_type": event.order_type,
                "status": event.status,
                "source_row": event.row,
                "duplicate": event.duplicate,
            }
        )

    net_queues: dict[tuple[str, str], deque[_OrderLot]] = defaultdict(deque)
    explicit_queues: dict[tuple[str, str, str], deque[_OrderLot]] = defaultdict(deque)
    sequence: dict[tuple[str, ...], int] = {}
    seen_keys: dict[str, int] = {}
    open_quantities: defaultdict[tuple[str, str, str], float] = defaultdict(float)
    close_quantities: defaultdict[tuple[str, str, str], float] = defaultdict(float)
    orphan_quantities: defaultdict[tuple[str, str, str], float] = defaultdict(float)

    for event in sorted(events, key=lambda item: (item.time, item.order)):
        if event.quantity is None:
            continue
        if event.action == "open":
            key = (event.account, event.symbol, event.direction)
            explicit_queues[key].append(_OrderLot(event, event.quantity))
            open_quantities[key] += event.quantity
        elif event.action == "close":
            key = (event.account, event.symbol, event.direction)
            close_quantities[key] += event.quantity
            remaining = _consume_order(
                event,
                explicit_queues[key],
                outcome,
                ctx,
                sequence,
                seen_keys,
                key,
                netting=False,
            )
            if remaining > 1e-9:
                orphan_quantities[key] += remaining
                outcome.orphan_closes += 1
        elif options.side_mode == "netting":
            key = (event.account, event.symbol)
            queue = net_queues[key]
            if not queue or queue[0].event.direction == event.direction:
                queue.append(_OrderLot(event, event.quantity))
                open_quantities[(event.account, event.symbol, event.direction)] += event.quantity
            else:
                close_direction = queue[0].event.direction
                remaining = _consume_order(
                    event, queue, outcome, ctx, sequence, seen_keys, key, netting=True
                )
                close_quantities[(event.account, event.symbol, close_direction)] += (
                    event.quantity - remaining
                )
                if remaining > 1e-9:
                    queue.append(_OrderLot(event, remaining))
                    open_quantities[(event.account, event.symbol, event.direction)] += remaining

    remainder_lots = [
        lot
        for queue in [*explicit_queues.values(), *net_queues.values()]
        for lot in queue
        if lot.remaining > 1e-9
    ]
    grouped_remainders: defaultdict[tuple[str, str, Literal["long", "short"]], float] = defaultdict(
        float
    )
    for lot in remainder_lots:
        grouped_remainders[(lot.event.account, lot.event.symbol, lot.event.direction)] += (
            lot.remaining
        )
    outcome.open_positions = [
        OpenRemainder(account, symbol, direction, quantity)
        for (account, symbol, direction), quantity in grouped_remainders.items()
    ]
    keys = set(open_quantities) | set(close_quantities) | set(orphan_quantities)
    outcome.quantity_conserved = all(
        abs(
            open_quantities[key]
            - close_quantities[key]
            - sum(
                lot.remaining
                for lot in remainder_lots
                if (lot.event.account, lot.event.symbol, lot.event.direction) == key
            )
            + orphan_quantities[key]
        )
        < 1e-9
        for key in keys
    )


def run_import(analysis: Analysis, options: ImportOptions) -> RunOutcome:
    """Process every record for the analysed shape. Caller must check blocking questions first."""
    ctx = analysis.context
    if analysis.shape == "round_trip":
        rows, fx_missing = run_round_trip(analysis, ctx, options.fx_rates)
        return RunOutcome(
            frame=rows.accepted,
            rejected=rows.rejected,
            rows_total=rows.rows_total,
            blank_rows=rows.blank_rows,
            fx_missing=fx_missing,
            formula_rows=rows.formula_rows,
            duplicates_in_file=analysis.duplicate_rows,
            data_warnings=analysis.warnings,
        )
    outcome = RunOutcome(data_warnings=analysis.warnings)
    if analysis.shape == "legs":
        _run_legs(analysis, ctx, outcome)
    elif analysis.shape == "executions":
        _run_executions(analysis, ctx, outcome)
    elif analysis.shape == "orders":
        _run_orders(analysis, ctx, outcome, options)
    else:
        raise ValueError("run_import needs a resolved shape")
    _apply_fx(outcome, options, ctx.base_currency)
    outcome.frame = frame_from_trades(outcome.trades)
    return outcome
