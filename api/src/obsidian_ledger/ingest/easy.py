"""Opt-in defaults and safety gates for the one-step import."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from obsidian_ledger.ingest.analysis import Analysis, Assumption
from obsidian_ledger.ingest.canonical import header_matches
from obsidian_ledger.ingest.errors import IngestError
from obsidian_ledger.ingest.options import ImportOptions
from obsidian_ledger.ingest.run import RunOutcome


@dataclass(frozen=True)
class EasyImportConfig:
    confidence: float = 0.8
    tie: float = 0.1
    auto_valid: float = 0.95
    minimum_valid: float = 0.5


CONFIG = EasyImportConfig()
_REQUIRED = (
    ("symbol",),
    ("entry_time", "exit_time", "leg_time", "fill_time"),
    ("side", "action"),
    ("qty", "notional"),
)
_SYMBOL = re.compile(
    r"(?<![A-Za-z0-9])([A-Z]{1,12}(?:USDT|USDC|USD|EUR)|[A-Z]{1,8}[-/][A-Z]{2,5})(?![A-Za-z0-9])"
)


def filename_symbol(filename: str) -> str:
    stem = Path(filename).stem
    match = _SYMBOL.search(stem.upper())
    if match:
        return match.group(1)
    candidate = re.sub(
        r"(?:[_ -](?:trades|fills|orders|executions|export))+$", "", stem, flags=re.I
    )
    if re.fullmatch(r"[A-Z]{1,6}(?:\.[A-Z])?", candidate) and candidate not in {
        "TRADE",
        "TRADES",
        "EXPORT",
        "HISTORY",
        "FILLS",
        "ORDERS",
        "CSV",
    }:
        return candidate
    return "UNKNOWN"


def defaults(analysis: Analysis, options: ImportOptions, filename: str) -> ImportOptions:
    updates: dict[str, str] = {}
    if any(question.id == "default_symbol" for question in analysis.blocking):
        updates["default_symbol"] = filename_symbol(filename)
    if any(question.id == "side_mode" for question in analysis.blocking):
        updates["side_mode"] = "netting"
    return options.model_copy(update=updates)


def confidence_fields(analysis: Analysis) -> list[str]:
    """Return the required fields that need somebody to confirm a column."""
    headers = [(column, header_matches(column.header)) for column in analysis.columns]
    groups: list[str] = []
    for fields in _REQUIRED:
        if fields == ("symbol",) and analysis.context.default_symbol:
            continue
        choices = [column for column in analysis.columns if column.field in fields]
        for column in choices:
            if column.source in {"adapter", "template", "user"}:
                break
            if column.field is None or (column.match_score or 0) < CONFIG.confidence:
                continue
            alternatives = (
                (
                    1.0
                    if candidate.header.strip().lower() == column.field
                    else matches[column.field].score / 3
                )
                for candidate, matches in headers
                if candidate.index != column.index
                and candidate.source not in {"adapter", "template", "user"}
                and (candidate.field is None or candidate.field == column.field)
                and column.field in matches
            )
            if any(
                score >= (column.match_score or 0) - CONFIG.tie - 1e-9 for score in alternatives
            ):
                continue
            break
        else:
            groups.append(choices[0].field or fields[0] if choices else fields[0])
    return groups


def record_assumptions(analysis: Analysis, options: ImportOptions) -> None:
    if options.default_symbol:
        analysis.assumptions.append(
            Assumption(
                "default_symbol", options.default_symbol, "Used where the file has no symbol.", True
            )
        )
    if options.side_mode:
        analysis.assumptions.append(
            Assumption(
                "buy_sell", "netting", "Plain buys and sells are netted per instrument.", True
            )
        )
    if options.starting_equity is None:
        analysis.assumptions.append(
            Assumption(
                "starting_equity",
                "none supplied",
                "The import leaves the journal setting as it is.",
                True,
            )
        )
    if analysis.duplicate_rows:
        analysis.assumptions.append(
            Assumption(
                "duplicate_rows",
                str(analysis.duplicate_rows),
                "Identical rows within the file are kept.",
                False,
            )
        )


def check_rows(outcome: RunOutcome, automatic: bool) -> None:
    total = outcome.rows_total
    rejected = len({row.source_row for row in outcome.rejected})
    ratio = (total - rejected) / total if total > 0 else 0
    if ratio < CONFIG.minimum_valid:
        raise IngestError("too_few_valid_rows", "Less than half of this file could be read.")
    if automatic and ratio < CONFIG.auto_valid:
        raise IngestError(
            "confirm_valid_rows",
            "Some rows could not be read. Continue with the rows we can use?",
            details={"valid_rows": total - rejected, "total_rows": total},
        )
