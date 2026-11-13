"""Turn row-level results into the data-quality report that the user reads."""

from __future__ import annotations

import statistics
from collections import defaultdict
from typing import Final

import polars as pl

from obsidian_ledger.ingest.frames import WARNING_COLUMN
from obsidian_ledger.ingest.run import RunOutcome
from obsidian_ledger.ingest.trade import Issue, Severity

MAX_EXAMPLES: Final = 10
OUTLIER_SCORE: Final = 5.0
MIN_OUTLIER_SAMPLE: Final = 20

# code -> (severity, title, suggested fix). Codes are stable so clients can match them.
CATALOG: Final[dict[str, tuple[Severity, str, str]]] = {
    "field_count": (
        "error",
        "Row has the wrong number of cells",
        "Check for an unquoted delimiter or a shifted row in the source file.",
    ),
    "bad_time": (
        "error",
        "Unreadable date or time",
        "Check the date format, or answer the day-first or month-first question.",
    ),
    "missing_entry_time": (
        "error",
        "Missing entry time",
        "Add the entry timestamp to these rows in the source file.",
    ),
    "missing_exit_time": (
        "error",
        "Missing exit time",
        "Add an exit or close timestamp. Without it, holding time cannot be computed.",
    ),
    "negative_duration": (
        "error",
        "Exit before entry",
        "The close is stamped before the open. Check the timestamps or the timezone.",
    ),
    "missing_symbol": ("error", "Missing symbol", "Map a symbol column or enter a default symbol."),
    "bad_side": ("error", "Unknown side", "Use buy, sell, long, or short in the side column."),
    "zero_quantity": ("error", "Zero quantity", "Remove or correct rows with zero size."),
    "bad_quantity": ("error", "Missing or unreadable quantity", "Fill in the quantity column."),
    "bad_number": ("error", "Value is not a number", "Check the decimal style or fix the cell."),
    "no_pnl_or_prices": (
        "error",
        "No P&L and no prices",
        "Provide net P&L, or entry and exit prices.",
    ),
    "duplicate_in_file": (
        "error",
        "Duplicate trade in the file",
        "The same trade appears more than once. Keep one copy.",
    ),
    "duplicate_fill": (
        "error",
        "Duplicate execution",
        "The same fill appears more than once. Keep one copy.",
    ),
    "duplicate_kept": (
        "info",
        "Exact duplicate rows kept",
        "Rows may represent separate fills. They were kept and assigned distinct trade keys.",
    ),
    "duplicates": (
        "info",
        "Exact duplicate rows kept",
        "Rows may represent separate fills. They were kept and assigned distinct trade keys.",
    ),
    "hour_precision": (
        "warning",
        "Hour-only timestamps",
        "Import more precise times for exact holding durations; current durations are approximate.",
    ),
    "truncated_symbols": (
        "warning",
        "Possible truncated symbols",
        "Values are preserved as-is. Review the symbol column or add an alias; "
        "no correction was guessed.",
    ),
    "zero_leverage": (
        "warning",
        "Zero leverage values",
        "Check whether zero means no leverage data or an invalid source value.",
    ),
    "partial_fills": (
        "info",
        "Order and filled quantities differ",
        "Filled quantities are used for matching; inspect partial fills before importing.",
    ),
    "totals_row": (
        "info",
        "Trailing totals row skipped",
        "The summary row was excluded from trade activity.",
    ),
    "orphan_close": (
        "info",
        "Close without a matching open",
        "Check whether the source is missing the opening order or was exported with a "
        "different range.",
    ),
    "quantity_conservation": (
        "error",
        "Quantity conservation failed",
        "Review partial fills and unmatched quantities before relying on the paired trades.",
    ),
    "unknown_leg": ("error", "Leg is neither entry nor exit", "Check the Type column values."),
    "duplicate_leg": (
        "error",
        "Two legs of the same kind",
        "Each trade needs exactly one entry leg and one exit leg.",
    ),
    "missing_trade_id": (
        "error",
        "Leg has no trade number",
        "Add the trade number so legs can be paired.",
    ),
    "missing_entry_leg": (
        "error",
        "Exit leg without an entry leg",
        "The matching entry row is missing.",
    ),
    "missing_exit_leg": (
        "error",
        "Entry leg without an exit leg",
        "The matching exit row is missing.",
    ),
    "pnl_mismatch": (
        "warning",
        "Reported P&L differs from prices",
        "Check the contract size and quote currency. The reported P&L was kept.",
    ),
    "net_mismatch": (
        "warning",
        "Net P&L differs from gross plus costs",
        "Check the fee and swap columns against the net value.",
    ),
    "r_mismatch": (
        "warning",
        "Provided R differs from net over risk",
        "The provided R was kept in the source. Check the planned risk.",
    ),
    "formula_like_cell": (
        "warning",
        "Cell looks like a formula",
        "The value was stored as text and not evaluated. Review the source cell.",
    ),
    "missing_risk": (
        "info",
        "No planned risk or stop",
        "Add a stop-loss or planned-risk column to get R multiples.",
    ),
    "timezone_assumed": (
        "info",
        "Timestamps without a timezone",
        "Confirm the timezone in the import options if the broker used local time.",
    ),
    "open_position": (
        "info",
        "Position still open in the file",
        "These fills did not close in the file, so they are not counted.",
    ),
    "fx_missing": (
        "warning",
        "No FX rate for a currency",
        "Enter a rate for the currency in the import options to convert P&L.",
    ),
    "outlier": (
        "warning",
        "Unusually large P&L",
        "Check these trades for entry errors. They are kept and flagged.",
    ),
    "mixed_currency": (
        "info",
        "Trades in more than one currency",
        "Enter FX rates in the import options so P&L converts to the base currency.",
    ),
}


def _issue(code: str, count: int, rows: list[int]) -> Issue:
    severity, title, fix = CATALOG[code]
    return Issue(
        code=code,
        severity=severity,
        title=title,
        count=count,
        example_rows=tuple(rows[:MAX_EXAMPLES]),
        suggested_fix=fix,
    )


def _robust_outliers(values: list[float]) -> list[int]:
    """Indexes whose modified z-score (median and MAD based) exceeds the threshold."""
    if len(values) < MIN_OUTLIER_SAMPLE:
        return []
    median = statistics.median(values)
    deviations = [abs(value - median) for value in values]
    mad = statistics.median(deviations)
    if mad == 0:
        return []
    return [
        index
        for index, value in enumerate(values)
        if abs(0.6745 * (value - median) / mad) > OUTLIER_SCORE
    ]


def build_issues(outcome: RunOutcome) -> list[Issue]:
    issues: list[Issue] = []

    rejected_rows: dict[str, list[int]] = defaultdict(list)
    for rejected in outcome.rejected:
        for reason in rejected.reasons:
            rows = rejected_rows[reason.code]
            if not rows or rows[-1] != rejected.source_row:
                rows.append(rejected.source_row)

    frame = outcome.frame
    warned_rows: dict[str, list[int]] = defaultdict(list)
    by_code = (
        frame.select(["source_row", WARNING_COLUMN])
        .explode(WARNING_COLUMN)
        .drop_nulls(WARNING_COLUMN)
        .group_by(WARNING_COLUMN, maintain_order=True)
        .agg(pl.col("source_row").unique(maintain_order=True))
    )
    for code, rows in by_code.iter_rows():
        warned_rows[code] = list(rows)

    for code, rows in rejected_rows.items():
        if code in CATALOG:
            issues.append(_issue(code, len(rows), rows))
    for code, rows in warned_rows.items():
        if code in CATALOG and code not in rejected_rows:
            issues.append(_issue(code, len(rows), rows))
    for code in outcome.data_warnings:
        if code in CATALOG and code not in {issue.code for issue in issues}:
            count = outcome.duplicates_in_file if code == "duplicates" else 1
            issues.append(_issue(code, count, []))

    if outcome.open_positions:
        count = len(outcome.open_positions)
        issues.append(
            Issue(
                code="open_position",
                severity="info",
                title=CATALOG["open_position"][1],
                count=count,
                example_rows=(),
                suggested_fix=CATALOG["open_position"][2],
            )
        )
    if outcome.orphan_closes:
        issues.append(_issue("orphan_close", outcome.orphan_closes, []))
    if not outcome.quantity_conserved:
        issues.append(_issue("quantity_conservation", 1, []))

    if outcome.fx_missing:
        currencies = ", ".join(sorted(outcome.fx_missing))
        issues.append(
            Issue(
                code="fx_missing",
                severity="warning",
                title=f"No FX rate for {currencies}",
                count=sum(outcome.fx_missing.values()),
                example_rows=(),
                suggested_fix=CATALOG["fx_missing"][2],
            )
        )

    currencies = sorted(frame.get_column("currency").unique().to_list())
    if len(currencies) > 1:
        issues.append(
            Issue(
                code="mixed_currency",
                severity="info",
                title=f"Trades in {', '.join(currencies)}",
                count=frame.height,
                example_rows=(),
                suggested_fix=CATALOG["mixed_currency"][2],
            )
        )

    pnl_frame = frame.filter(pl.col("net_pnl").is_not_null())
    pnl_values = pnl_frame.get_column("net_pnl").to_list()
    outlier_indexes = _robust_outliers(pnl_values)
    if outlier_indexes:
        source_rows = pnl_frame.get_column("source_row").to_list()
        rows = [source_rows[index] for index in outlier_indexes]
        issues.append(_issue("outlier", len(rows), rows))

    return issues
