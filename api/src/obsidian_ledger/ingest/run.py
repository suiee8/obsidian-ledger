"""Run one import: read every record, validate it, and collect trades and rejected rows."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Final

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
)
from obsidian_ledger.ingest.options import ImportOptions
from obsidian_ledger.ingest.parse import parse_number, parse_side
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
    _trades: list[Trade] | None = None

    @property
    def trades(self) -> list[Trade]:
        if self._trades is None:
            self._trades = trades_from_frame(self.frame)
        return self._trades

    def reject(self, row: int, reasons: list[Reason], cells: list[str]) -> None:
        self.rejected.append(Rejected(row, reasons, cells))


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
    symbol = values.get("symbol", "") or (ctx.default_symbol or "")
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
    seen: dict[tuple[str, str, str, str], int] = {}
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
        key = (fill.order_id or "", fill.time.isoformat(), f"{fill.qty}", f"{fill.price}")
        if key in seen:
            outcome.reject(
                number, [Reason("duplicate_fill", f"Same fill as row {seen[key]}.")], cells
            )
            continue
        seen[key] = number
        cells_by_row[number] = cells
        fills.append(fill)

    legs, remainders = pair_fills(fills)
    outcome.open_positions = remainders
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
        result = finalize(draft, Checks(), ctx)
        if isinstance(result, list):
            outcome.reject(open_fill.row, result, cells_by_row.get(open_fill.row, []))
            outcome.reject(close_fill.row, result, cells_by_row.get(close_fill.row, []))
            continue
        outcome.trades.append(result)


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
        )
    outcome = RunOutcome()
    if analysis.shape == "legs":
        _run_legs(analysis, ctx, outcome)
    elif analysis.shape == "executions":
        _run_executions(analysis, ctx, outcome)
    else:
        raise ValueError("run_import needs a resolved shape")
    _apply_fx(outcome, options, ctx.base_currency)
    outcome.frame = frame_from_trades(outcome.trades)
    return outcome
