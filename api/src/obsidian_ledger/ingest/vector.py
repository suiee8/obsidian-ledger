"""Round-trip imports validated as Polars expressions, one rule per column, not one loop per row.

What stays row-wise, and why:
- Tokenizing: the stdlib csv reader (or the XLSX and JSON readers) yields each row once. Blank-row
  and field-count checks run there, because they decide which rows enter the frame at all.
- Trade keys: SHA-256 has no Polars equivalent. Keys must match the keys already stored in users'
  databases, so each key is hashed once in Python.
- Rejected rows: their reason codes and messages come from the per-row validation in normalize.py,
  so each message is exactly the one the rejection report has always shown. Only failing rows take
  this path.

Everything else (parsing, cross-field checks, derived columns, warnings, duplicates, FX) is computed
for all rows at once and must give the same values as the per-row code.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final

import polars as pl

from obsidian_ledger.ingest.adapters import default_contract_size
from obsidian_ledger.ingest.analysis import Analysis
from obsidian_ledger.ingest.frames import ACCEPTED_SCHEMA, WARNING_COLUMN
from obsidian_ledger.ingest.normalize import (
    NET_TOLERANCE,
    PRICE_TOLERANCE_FLOOR,
    R_TOLERANCE,
    Checks,
    Context,
    draft_from_values,
    finalize,
)
from obsidian_ledger.ingest.parse import (
    DATE_CANDIDATES,
    DecimalStyle,
    parse_side_action,
    time_precision,
)
from obsidian_ledger.ingest.trade import Reason, Rejected, Trade

_NUMBER_SHAPE: Final = r"^[+-]?\d+(\.\d+)?$"
_CURRENCY_SIGNS: Final = r"[$€£¥]"
_FORMULA_START: Final = r"^[=+\-@\t\r]"
_DECIMAL_SUFFIX: Final = r"[.,](\d+)$"
_LONG_WORDS: Final = r"(^|[^a-z])long([^a-z]|$)"
_SHORT_WORDS: Final = r"(^|[^a-z])short([^a-z]|$)"
_BUY_WORDS: Final = r"(^|[^a-z])(buy|b)([^a-z]|$)"
_SELL_WORDS: Final = r"(^|[^a-z])(sell|s)([^a-z]|$)"
_PLAN_TRUE: Final = ("true", "yes", "y", "1")
_PLAN_FALSE: Final = ("false", "no", "n", "0")
# Numeric fields that report bad_number when present but not numeric. The qty field is handled
# with the quantity rules, so it is included here only for parsing.
_NUMERIC_FIELDS: Final = (
    "qty",
    "entry_price",
    "exit_price",
    "gross_pnl",
    "net_pnl",
    "commission",
    "swap",
    "fees",
    "stop_loss",
    "take_profit",
    "planned_risk",
    "r_multiple",
    "mae",
    "mfe",
    "notional",
    "exit_notional",
    "leverage",
)
_TEXT_FIELDS: Final = (
    "trade_id",
    "account",
    "asset_class",
    "currency",
    "setup",
    "timeframe",
    "session",
    "tags",
    "notes",
    "emotion",
    "screenshot_path",
    "confidence",
    "order_type",
    "status",
    "action",
)


@dataclass
class VectorRows:
    accepted: pl.DataFrame
    rejected: list[Rejected]
    formula_rows: list[int]
    blank_rows: int
    rows_total: int


def number_expr(text: pl.Expr, style: DecimalStyle) -> tuple[pl.Expr, pl.Expr]:
    """Vector form of parse.parse_number for stripped text. Returns (value, invalid).

    Empty text gives a null value and is not invalid. Non-numeric text is invalid.
    """
    cleaned = text.str.replace_all("\u00a0", "").str.replace_all(" ", "")
    negative = cleaned.str.starts_with("(") & cleaned.str.ends_with(")")
    unwrapped = (
        pl.when(negative).then(cleaned.str.slice(1, cleaned.str.len_chars() - 2)).otherwise(cleaned)
    )
    body = unwrapped.str.replace_all(_CURRENCY_SIGNS, "")
    if style == "comma":
        body = body.str.replace_all(r"\.", "").str.replace_all(",", ".")
    else:
        body = body.str.replace_all(",", "")
    shaped = body.str.contains(_NUMBER_SHAPE)
    magnitude = pl.when(shaped).then(body.cast(pl.Float64, strict=False))
    value = pl.when(negative).then(-magnitude).otherwise(magnitude)
    empty = text.str.len_chars() == 0
    return pl.when(empty).then(None).otherwise(value), ~empty & ~shaped


def _side(text: pl.Expr) -> pl.Expr:
    lowered = text.str.to_lowercase()
    return (
        pl.when(lowered.str.contains(_LONG_WORDS))
        .then(pl.lit("long"))
        .when(lowered.str.contains(_SHORT_WORDS))
        .then(pl.lit("short"))
        .when(lowered.str.contains(_BUY_WORDS))
        .then(pl.lit("long"))
        .when(lowered.str.contains(_SELL_WORDS))
        .then(pl.lit("short"))
        .otherwise(None)
    )


def _timestamp(text: pl.Expr, tz_name: str, family: str | None) -> tuple[pl.Expr, pl.Expr]:
    """Vector form of normalize.parse_timestamp. Returns (naive UTC datetime, has_offset).

    Candidates are tried in parse.DATE_CANDIDATES order and the first match wins. A trailing Z is
    read as +0000 because Polars does not accept Z inside %z. Naive times are read in the file's
    timezone. A time that does not exist there (a DST gap) gives null and is reported as a bad time.
    """
    prepared = text.str.strip_chars().str.replace(r"Z$", "+0000")
    results: list[pl.Expr] = []
    has_offset: pl.Expr | None = None
    for candidate in DATE_CANDIDATES:
        if candidate.key in {"iso_space_hour", "iso_space_hour_plain"}:
            continue
        if candidate.family is not None and candidate.family != family:
            continue
        parsed = prepared.str.to_datetime(format=candidate.pattern, strict=False, time_unit="us")
        if candidate.key == "iso_offset":
            utc = parsed.dt.convert_time_zone("UTC").dt.replace_time_zone(None)
            has_offset = parsed.is_not_null()
        else:
            utc = (
                parsed.dt.replace_time_zone(tz_name, ambiguous="earliest", non_existent="null")
                .dt.convert_time_zone("UTC")
                .dt.replace_time_zone(None)
            )
        results.append(utc)
    assert has_offset is not None, "the offset pattern is always a candidate"
    numeric = prepared.cast(pl.Float64, strict=False)
    digits = prepared.str.len_chars()
    epoch_value = prepared.cast(pl.Int64, strict=False)
    epoch_us = (
        pl.when(digits == 10)
        .then(epoch_value * 1_000_000)
        .when(digits == 13)
        .then(epoch_value * 1_000)
        .otherwise(None)
        .cast(pl.Datetime("us"))
    )
    excel_us = (
        pl.when((numeric >= 1) & (numeric <= 100000) & ~digits.is_in([10, 13]))
        .then(
            pl.lit(datetime(1899, 12, 30))
            + pl.duration(microseconds=(numeric * 86_400_000_000).cast(pl.Int64))
        )
        .otherwise(None)
    )
    return pl.coalesce([*results, epoch_us, excel_us]), has_offset | epoch_us.is_not_null()


def _formula_like(cell: pl.Expr) -> pl.Expr:
    """Vector form of run._is_formula_like for one cell."""
    text = cell.str.strip_chars()
    starts = text.str.contains(_FORMULA_START)
    signed = text.str.starts_with("+") | text.str.starts_with("-")
    dot_number = number_expr(text, "dot")[0].is_not_null()
    comma_number = number_expr(text, "comma")[0].is_not_null()
    return (text.str.len_chars() > 0) & starts & ~(signed & dot_number) & ~comma_number


def _decimals(text: pl.Expr) -> pl.Expr:
    digits = text.str.strip_chars().str.extract(_DECIMAL_SUFFIX, 1)
    return digits.str.len_chars().fill_null(0).cast(pl.Float64)


def _session_for_hour(hour: pl.Expr) -> pl.Expr:
    return (
        pl.when(hour < 7)
        .then(pl.lit("asia"))
        .when(hour < 13)
        .then(pl.lit("london"))
        .otherwise(pl.lit("new_york"))
    )


def _lookup(key: pl.Expr, table: Mapping[str, float]) -> pl.Expr:
    """Map a string column to floats. Keys missing from the table give null."""
    if not table:
        return pl.lit(None, dtype=pl.Float64)
    return key.replace_strict(dict(table), default=None, return_dtype=pl.Float64)


def _warning_codes(flags: Mapping[str, pl.Expr]) -> pl.Expr:
    parts = [
        pl.when(flag.fill_null(False)).then(pl.lit(code)).otherwise(None)
        for code, flag in flags.items()
    ]
    return pl.concat_list(parts).list.drop_nulls()


def _trade_keys(frame: pl.DataFrame) -> list[str]:
    """SHA-256 identity per trade, byte-identical to normalize.finalize's key.

    The key uses the parsed prices, as the per-row code does, not multiplier-scaled values.
    """
    keys: list[str] = []
    rows = frame.select(
        [
            "account",
            "symbol",
            "side",
            "entry_time",
            "exit_time",
            "qty",
            "n_entry_price",
            "n_exit_price",
            "net",
        ]
    ).iter_rows()
    for account, symbol, side, entry, exit_time, qty, entry_price, exit_price, net in rows:
        assert isinstance(entry, datetime) and isinstance(exit_time, datetime)
        parts = [
            account,
            symbol,
            side,
            entry.replace(tzinfo=UTC).isoformat(),
            exit_time.replace(tzinfo=UTC).isoformat(),
            f"{qty:.8f}",
            f"{entry_price}",
            f"{exit_price}",
            f"{net:.2f}" if net is not None else "unknown",
        ]
        keys.append(hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest())
    return keys


def _row_rejection(analysis: Analysis, ctx: Context, number: int, cells: list[str]) -> Rejected:
    """Exact reasons for a row the vector rules reject, from the per-row validation."""
    values = {
        name: cells[index].strip() if index < len(cells) else ""
        for name, index in analysis.field_index.items()
    }
    checks = Checks()
    draft = draft_from_values(values, (number,), ctx, checks, round_trip=True)
    result = finalize(draft, checks, ctx)
    if isinstance(result, Trade):
        raise RuntimeError(
            f"row {number}: vector validation rejected a row the per-row rules accept"
        )
    return Rejected(number, result, cells)


def run_round_trip(
    analysis: Analysis, ctx: Context, fx_rates: Mapping[str, float]
) -> tuple[VectorRows, dict[str, int]]:
    """Validate every round-trip row. Returns the accepted frame, the rejects, and FX gaps."""
    width = len(analysis.source.headers)
    rejected: list[Rejected] = []
    numbers: list[int] = []
    cells: list[list[str]] = []
    blank_rows = 0
    rows_total = 0
    for number, row in analysis.source.iter_records():
        if not any(cell.strip() for cell in row):
            blank_rows += 1
            continue
        rows_total += 1
        if len(row) < width or any(cell.strip() for cell in row[width:]):
            rejected.append(
                Rejected(
                    number,
                    [Reason("field_count", f"Row has {len(row)} cells; the header has {width}.")],
                    row,
                )
            )
            continue
        numbers.append(number)
        parsed_row = row[:width]
        symbol_index = analysis.field_index.get("symbol")
        if symbol_index is not None and symbol_index < len(parsed_row):
            source_symbol = parsed_row[symbol_index].strip()
            parsed_row[symbol_index] = ctx.symbol_aliases.get(source_symbol, source_symbol)
        cells.append(parsed_row)

    if not numbers:
        empty = VectorRows(
            pl.DataFrame(schema=ACCEPTED_SCHEMA), rejected, [], blank_rows, rows_total
        )
        return empty, {}

    names = [f"c{index}" for index in range(width)]
    field_index = analysis.field_index

    def row_time(row: list[str], prefix: str) -> str:
        base_name = f"{prefix}_time"
        clock_name = f"{prefix}_clock"
        base = row[field_index[base_name]].strip() if base_name in field_index else ""
        clock = row[field_index[clock_name]].strip() if clock_name in field_index else ""
        if base and clock and not re.search(r"\d{1,2}:\d{2}", base):
            return f"{base} {clock}"
        return base or clock

    raw = pl.DataFrame(cells, schema=names, orient="row").with_columns(
        pl.Series("source_row", numbers, dtype=pl.Int32),
        pl.Series(
            "time_precision",
            [
                max(
                    (time_precision(row_time(row, prefix)) for prefix in ("entry", "exit")),
                    key=lambda value: {"second": 0, "minute": 1, "hour": 2, "day": 3}[value],
                    default="second",
                )
                for row in cells
            ],
            dtype=pl.String,
        ),
        pl.Series(
            "inferred_action",
            [
                parse_side_action(
                    row[field_index["side"]]
                    if "side" in field_index and field_index["side"] < len(row)
                    else ""
                )[0]
                for row in cells
            ],
            dtype=pl.String,
        ),
    )

    def text(field: str) -> pl.Expr:
        if field in field_index:
            base = pl.col(f"c{field_index[field]}").str.strip_chars()
            clock_field = "entry_clock" if field == "entry_time" else "exit_clock"
            if field in {"entry_time", "exit_time"} and clock_field in field_index:
                clock = pl.col(f"c{field_index[clock_field]}").str.strip_chars()
                base_has_minutes = base.str.contains(r"\d{1,2}:\d{2}")
                return (
                    pl.when(base_has_minutes | (clock == ""))
                    .then(base)
                    .otherwise(pl.concat_str([base, clock], separator=" ").str.strip_chars())
                )
            return base
        return pl.lit("", dtype=pl.String)

    # Step 1: parse each field from its text.
    parsed_numbers: list[pl.Expr] = []
    for field in _NUMERIC_FIELDS:
        value, bad = number_expr(text(field), ctx.decimal)
        parsed_numbers += [value.alias(f"n_{field}"), bad.alias(f"bad_{field}")]
    entry_utc, has_offset = _timestamp(text("entry_time"), ctx.tz_name, ctx.slash_family)
    exit_utc, _ = _timestamp(text("exit_time"), ctx.tz_name, ctx.slash_family)
    symbol_raw = text("symbol")
    mult_value, mult_bad = number_expr(text("multiplier"), ctx.decimal)
    formula = pl.any_horizontal([_formula_like(pl.col(name)) for name in names])
    step1 = raw.lazy().with_columns(
        *parsed_numbers,
        symbol=pl.when(symbol_raw != "")
        .then(symbol_raw)
        .otherwise(pl.lit(ctx.default_symbol or "")),
        side=_side(text("side")),
        entry_time=entry_utc,
        exit_time=exit_utc,
        has_offset=has_offset,
        entry_missing=text("entry_time") == "",
        exit_missing=text("exit_time") == "",
        qty_missing=text("qty") == "",
        mult_text=text("multiplier"),
        mult_value=mult_value,
        mult_bad=mult_bad,
        formula=formula,
        **{f"t_{field}": text(field) for field in _TEXT_FIELDS},
        entry_decimals=_decimals(text("entry_price")),
        exit_decimals=_decimals(text("exit_price")),
        plan_text=text("plan_followed").str.to_lowercase(),
        entry_time_text=text("entry_time"),
        exit_time_text=text("exit_time"),
    )

    # Step 2: resolve the multiplier and the cross-field values, as finalize does.
    symbol_index = field_index.get("symbol")
    symbols = list(
        dict.fromkeys(
            (row[symbol_index].strip() if symbol_index is not None else "")
            or (ctx.default_symbol or "")
            for row in cells
        )
    )
    symbols = [symbol for symbol in symbols if symbol]
    contract_sizes = {symbol: float(size) for symbol, size in ctx.contract_sizes.items()}
    adapter_sizes: dict[str, float] = {}
    for symbol in symbols:
        if symbol not in contract_sizes:
            size = default_contract_size(ctx.adapter, symbol)
            if size is not None:
                adapter_sizes[symbol] = float(size)
    symbol_col = pl.col("symbol")
    in_contract = symbol_col.is_in(list(contract_sizes)) if contract_sizes else pl.lit(False)
    multiplier = (
        pl.when(in_contract)
        .then(_lookup(symbol_col, contract_sizes))
        .when(pl.col("mult_text") != "")
        .then(pl.col("mult_value"))
        .otherwise(_lookup(symbol_col, adapter_sizes))
    )
    step2 = step1.with_columns(
        multiplier=multiplier,
        multiplier_bad=(symbol_col != "")
        & ~in_contract
        & (pl.col("mult_text") != "")
        & pl.col("mult_bad"),
    )
    step2 = step2.with_columns(
        mult=pl.col("multiplier").fill_null(1.0),
        qty=pl.col("n_qty").abs(),
    )
    step2 = step2.with_columns(
        draft_error=(
            (pl.col("symbol") == "")
            | pl.col("side").is_null()
            | pl.col("entry_missing")
            | (~pl.col("entry_missing") & pl.col("entry_time").is_null())
            | pl.col("exit_missing")
            | (~pl.col("exit_missing") & pl.col("exit_time").is_null())
            | pl.col("qty_missing")
            | (pl.col("n_qty") == 0)
            | pl.col("multiplier_bad")
            | pl.any_horizontal([pl.col(f"bad_{field}") for field in _NUMERIC_FIELDS])
        ),
        fees=pl.when(pl.col("n_fees").is_not_null()).then(-pl.col("n_fees").abs()).otherwise(None),
        commission_f=pl.col("n_commission"),
        swap_f=pl.col("n_swap"),
    )
    step2 = step2.with_columns(
        costs=(
            pl.col("fees").fill_null(0.0)
            + pl.col("commission_f").fill_null(0.0)
            + pl.col("swap_f").fill_null(0.0)
        ),
    )
    sign = pl.when(pl.col("side") == "long").then(1.0).otherwise(-1.0)
    step2 = step2.with_columns(
        implied=pl.when(
            pl.col("n_entry_price").is_not_null() & pl.col("n_exit_price").is_not_null()
        ).then(
            sign
            * (pl.col("n_exit_price") - pl.col("n_entry_price"))
            * pl.col("qty")
            * pl.col("mult")
        ),
        reported_gross=pl.when(pl.col("n_gross_pnl").is_not_null())
        .then(pl.col("n_gross_pnl"))
        .when(pl.col("n_net_pnl").is_not_null())
        .then(pl.col("n_net_pnl") - pl.col("costs")),
    )
    step2 = step2.with_columns(
        gross=pl.coalesce([pl.col("reported_gross"), pl.col("implied")]),
    )
    step2 = step2.with_columns(
        net=pl.when(pl.col("n_net_pnl").is_not_null())
        .then(pl.col("n_net_pnl"))
        .otherwise(pl.col("gross") + pl.col("costs")),
        # A null comparison only happens when entry or exit is missing, and those rows already fail
        # the draft check, so treating null as "no finalize error" is safe.
        finalize_error=(pl.col("exit_time") < pl.col("entry_time")).fill_null(False),
        draft_error=pl.col("draft_error").fill_null(True),
        account=pl.when(pl.col("t_account") != "")
        .then(pl.col("t_account"))
        .otherwise(pl.lit(ctx.default_account)),
    )

    # Step 3: warnings and risk. Tolerances match normalize.finalize.
    step3 = step2.with_columns(
        price_decimals=pl.max_horizontal(pl.col("entry_decimals"), pl.col("exit_decimals")),
        stop_risk=pl.when(
            pl.col("n_stop_loss").is_not_null() & pl.col("n_entry_price").is_not_null()
        ).then(
            (pl.col("n_entry_price") - pl.col("n_stop_loss")).abs() * pl.col("qty") * pl.col("mult")
        ),
    )
    step3 = step3.with_columns(
        risk=pl.when(pl.col("n_planned_risk").is_not_null())
        .then(pl.col("n_planned_risk"))
        .when(pl.col("stop_risk") > 0)
        .then(pl.col("stop_risk")),
    )
    step3 = step3.with_columns(
        r_value=pl.when(pl.col("risk") > 0)
        .then(pl.col("net") / pl.col("risk"))
        .otherwise(pl.col("n_r_multiple")),
    )
    pnl_tolerance = PRICE_TOLERANCE_FLOOR + 0.5 * pl.col("qty") * pl.col("mult") * (
        10.0 ** (-pl.col("price_decimals"))
    )
    step3 = step3.with_columns(
        warning_codes=_warning_codes(
            {
                "formula_like_cell": pl.col("formula"),
                "time_precision": pl.col("time_precision").is_in(["hour", "day"]),
                "net_mismatch": pl.col("n_gross_pnl").is_not_null()
                & pl.col("n_net_pnl").is_not_null()
                & (
                    (pl.col("n_net_pnl") - (pl.col("n_gross_pnl") + pl.col("costs"))).abs()
                    > NET_TOLERANCE
                ),
                "pnl_mismatch": pl.col("reported_gross").is_not_null()
                & pl.col("implied").is_not_null()
                & ((pl.col("reported_gross") - pl.col("implied")).abs() > pnl_tolerance),
                "r_mismatch": (pl.col("risk") > 0)
                & pl.col("n_r_multiple").is_not_null()
                & ((pl.col("n_r_multiple") - pl.col("net") / pl.col("risk")).abs() > R_TOLERANCE),
                "missing_risk": pl.col("risk").is_null(),
                "timezone_assumed": ~pl.col("has_offset"),
            }
        ),
    )

    # Step 4: keep rows with no errors. Keys and duplicates are computed on those rows only.
    all_rows = step3.with_columns(
        keep=~pl.col("draft_error") & ~pl.col("finalize_error"),
    ).collect()
    formula_rows = all_rows.filter(pl.col("formula")).get_column("source_row").to_list()
    row_cells = dict(zip(numbers, cells, strict=True))
    error_rows = all_rows.filter(~pl.col("keep")).get_column("source_row").to_list()
    for number in error_rows:
        rejected.append(_row_rejection(analysis, ctx, number, row_cells[number]))

    candidates = all_rows.filter(pl.col("keep"))
    keys = _trade_keys(candidates)
    key_counts = Counter(keys)
    occurrences: Counter[str] = Counter()
    distinct_keys: list[str] = []
    duplicate_warning: list[bool] = []
    for key in keys:
        occurrences[key] += 1
        occurrence = occurrences[key]
        duplicate_warning.append(key_counts[key] > 1)
        distinct_keys.append(
            key
            if occurrence == 1
            else hashlib.sha256(f"{key}|occurrence:{occurrence}".encode()).hexdigest()
        )
    warning_lists = candidates.get_column(WARNING_COLUMN).to_list()
    for index, is_duplicate in enumerate(duplicate_warning):
        if is_duplicate:
            warning_lists[index] = [*warning_lists[index], "duplicate_kept"]
    accepted = candidates.with_columns(
        pl.Series("trade_key", distinct_keys, dtype=pl.String),
        pl.Series(WARNING_COLUMN, warning_lists, dtype=pl.List(pl.String)),
    )
    accepted = accepted.with_columns(
        trade_id=pl.when(pl.col("t_trade_id") != "")
        .then(pl.col("t_trade_id"))
        .otherwise(pl.col("trade_key").str.slice(0, 16)),
        currency=pl.when(pl.col("t_currency") != "")
        .then(pl.col("t_currency").str.to_uppercase())
        .otherwise(pl.lit(ctx.default_currency)),
        session=pl.when(pl.col("t_session") != "")
        .then(pl.col("t_session").str.to_lowercase())
        .otherwise(_session_for_hour(pl.col("entry_time").dt.hour())),
        asset_class=pl.when(pl.col("t_asset_class") != "").then(pl.col("t_asset_class")),
        setup=pl.when(pl.col("t_setup") != "").then(pl.col("t_setup")),
        timeframe=pl.when(pl.col("t_timeframe") != "").then(pl.col("t_timeframe")),
        tags=pl.when(pl.col("t_tags") != "").then(pl.col("t_tags")),
        emotion=pl.when(pl.col("t_emotion") != "").then(pl.col("t_emotion").str.to_lowercase()),
        screenshot_path=pl.when(pl.col("t_screenshot_path") != "").then(
            pl.col("t_screenshot_path")
        ),
        confidence=pl.when(pl.col("t_confidence") != "").then(pl.col("t_confidence")),
        plan_followed=pl.when(pl.col("plan_text").is_in(list(_PLAN_TRUE)))
        .then(pl.lit(True))
        .when(pl.col("plan_text").is_in(list(_PLAN_FALSE)))
        .then(pl.lit(False))
        .otherwise(None),
    )
    accepted, fx_missing = _apply_fx(accepted, ctx, fx_rates)
    stored = accepted.select(
        pl.col("trade_key"),
        pl.col("trade_id"),
        pl.col("account"),
        pl.col("symbol"),
        pl.col("asset_class"),
        pl.col("side"),
        pl.col("entry_time"),
        pl.col("exit_time"),
        pl.when(pl.col("has_offset"))
        .then(None)
        .otherwise(pl.lit(ctx.tz_name))
        .alias("source_timezone"),
        pl.col("qty"),
        pl.col("mult").alias("multiplier"),
        pl.col("n_entry_price").alias("entry_price"),
        pl.col("n_exit_price").alias("exit_price"),
        pl.col("fees"),
        pl.col("commission_f").alias("commission"),
        pl.col("swap_f").alias("swap"),
        pl.col("gross").round(8).alias("gross_pnl"),
        pl.col("net").round(8).alias("net_pnl"),
        pl.col("currency"),
        pl.col("net_pnl_base"),
        pl.lit(ctx.base_currency).alias("base_currency"),
        pl.col("n_stop_loss").alias("stop_loss"),
        pl.col("n_take_profit").alias("take_profit"),
        pl.when(pl.col("risk").is_not_null()).then(pl.col("risk").round(8)).alias("planned_risk"),
        pl.when(pl.col("r_value").is_not_null())
        .then(pl.col("r_value").round(6))
        .alias("r_multiple"),
        pl.col("n_mae").alias("mae"),
        pl.col("n_mfe").alias("mfe"),
        pl.col("setup"),
        pl.col("timeframe"),
        pl.col("session"),
        pl.col("tags"),
        pl.col("t_notes").alias("notes"),
        pl.col("emotion"),
        pl.col("plan_followed"),
        (pl.col("exit_time") - pl.col("entry_time"))
        .dt.total_seconds()
        .cast(pl.Float64)
        .alias("holding_seconds"),
        (pl.col("entry_time").dt.weekday() - 1).cast(pl.Int32).alias("weekday"),
        pl.col("entry_time").dt.hour().cast(pl.Int32).alias("hour_utc"),
        pl.col("source_row"),
        pl.col("screenshot_path"),
        pl.col("confidence"),
        pl.col("time_precision"),
        pl.col("n_notional").alias("entry_notional"),
        pl.col("n_exit_notional").alias("exit_notional"),
        pl.col("n_leverage").alias("leverage"),
        pl.col("t_order_type").alias("order_type"),
        pl.col("t_status").alias("status"),
        pl.when(pl.col("t_action") != "")
        .then(pl.col("t_action"))
        .otherwise(pl.col("inferred_action"))
        .alias("action"),
        pl.col(WARNING_COLUMN),
    )
    stored = stored.cast(ACCEPTED_SCHEMA)
    rejected.sort(key=lambda item: item.source_row)
    return (
        VectorRows(stored, rejected, sorted(formula_rows), blank_rows, rows_total),
        fx_missing,
    )


def _apply_fx(
    accepted: pl.DataFrame, ctx: Context, fx_rates: Mapping[str, float]
) -> tuple[pl.DataFrame, dict[str, int]]:
    """Net P&L in base currency. A currency with no FX rate leaves it null."""
    currency = pl.col("currency")
    rate = (
        pl.when(currency == ctx.base_currency)
        .then(pl.lit(1.0))
        .otherwise(_lookup(currency, fx_rates))
    )
    frame = accepted.with_columns(
        net_pnl_base=pl.when(pl.col("net").is_null())
        .then(None)
        .when(currency == ctx.base_currency)
        .then(pl.col("net"))
        .otherwise(pl.col("net") * rate)
    )
    missing = (
        frame.filter(pl.col("net").is_not_null() & pl.col("net_pnl_base").is_null())
        .group_by("currency")
        .len()
    )
    fx_missing = {str(row[0]): int(row[1]) for row in missing.iter_rows()}
    return frame, fx_missing
