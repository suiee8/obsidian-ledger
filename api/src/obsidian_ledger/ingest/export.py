"""CSV export of rejected rows. Every cell, including the file's own header names, is neutralized so
spreadsheets never run them as formulas (see obsidian_ledger.csvsafe)."""

from __future__ import annotations

import csv
import io
from collections.abc import Sequence

from obsidian_ledger.csvsafe import neutralize_cell, neutralize_csv
from obsidian_ledger.ingest.trade import Rejected

__all__ = ["neutralize_cell", "rejected_csv"]


def rejected_csv(headers: Sequence[str], rejected: Sequence[Rejected]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(
        ["source_row", "reason_codes", "reasons", *(neutralize_cell(name) for name in headers)]
    )
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
    return neutralize_csv(buffer.getvalue()).encode("utf-8")
