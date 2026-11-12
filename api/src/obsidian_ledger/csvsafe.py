"""CSV formula-injection guard for every CSV the app writes.

A spreadsheet runs a cell as a formula when its text starts with =, +, -, @, a tab, or a carriage
return. Journal notes, symbols and headers come from files other people wrote, so each such cell
gets a leading apostrophe, which spreadsheets show as text. JSON numbers remain numeric; serialized
CSV cells with a risky prefix are treated as text.

The rule is the same for the Python helper and the Polars expression below. Tests in
tests/security/test_csv_safety.py check both.
"""

from __future__ import annotations

import csv
import io
from typing import Any, Final

import polars as pl

RISKY_START: Final = ("=", "+", "-", "@", "\t", "\r")
RISKY_START_RE: Final = r"^[ ]*[=+\-@\t\r]"


def neutralize_cell(value: Any) -> Any:
    """Prefix risky text cells, including numeric-looking signed strings."""
    if not isinstance(value, str):
        return value
    if value.lstrip(" ").startswith(RISKY_START):
        return "'" + value
    return value


def neutralize_frame(frame: pl.DataFrame) -> pl.DataFrame:
    """Neutralize text columns before CSV serialization; leave typed numeric data unchanged."""
    text_columns = [name for name, dtype in frame.schema.items() if dtype.is_(pl.String)]
    if not text_columns:
        return frame
    exprs: list[pl.Expr] = []
    for name in text_columns:
        cell = pl.col(name)
        risky = cell.str.contains(RISKY_START_RE).fill_null(False)
        exprs.append(pl.when(risky).then(pl.lit("'") + cell).otherwise(cell).alias(name))
    return frame.with_columns(exprs)


def neutralize_csv(value: str) -> str:
    """Neutralize every serialized CSV cell, including numeric values written by dataframes."""
    reader = csv.reader(io.StringIO(value))
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerows([[neutralize_cell(cell) for cell in row] for row in reader])
    return buffer.getvalue()
