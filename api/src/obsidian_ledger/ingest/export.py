"""CSV export of rejected rows. Cells are neutralized so spreadsheets never run them as formulas."""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Sequence
from typing import Final

from obsidian_ledger.ingest.trade import Rejected

_NUMERIC: Final = re.compile(r"^[+-]?\d+([.,]\d+)?$")
_RISKY_START: Final = ("=", "+", "-", "@", "\t", "\r")


def neutralize_cell(value: str) -> str:
    """Prefix risky text with an apostrophe. Plain numbers such as -0.70 are left alone."""
    if value.startswith(_RISKY_START) and not _NUMERIC.match(value.strip()):
        return "'" + value
    return value


def rejected_csv(headers: Sequence[str], rejected: Sequence[Rejected]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["source_row", "reason_codes", "reasons", *headers])
    for item in rejected:
        codes = ";".join(reason.code for reason in item.reasons)
        messages = " | ".join(reason.message for reason in item.reasons)
        writer.writerow(
            [
                str(item.source_row),
                neutralize_cell(codes),
                neutralize_cell(messages),
                *(neutralize_cell(cell) for cell in item.cells),
            ]
        )
    return buffer.getvalue().encode("utf-8")
