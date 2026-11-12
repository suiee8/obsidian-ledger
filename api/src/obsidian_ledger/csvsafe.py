"""CSV formula-injection guard for every CSV the app writes.

A spreadsheet runs a cell as a formula when its text starts with =, +, -, @, a tab, or a carriage
return. Journal notes, symbols and headers come from files other people wrote, so each such cell
gets a leading apostrophe, which spreadsheets show as text. Numbers are left alone, so a loss of
-0.70 stays a number.

The rule is the same for the Python helper and the Polars expression below. Tests in
tests/security/test_csv_safety.py check both.
"""

from __future__ import annotations

import re
from typing import Any, Final

import polars as pl

RISKY_START: Final = ("=", "+", "-", "@", "\t", "\r")
# A plain number, optionally with a sign, a decimal part, an exponent, or thousands separators.
NUMBER: Final = r"^[+-]?(\d+|\d{1,3}(,\d{3})+)(\.\d+)?([eE][+-]?\d+)?$"
_NUMBER_RE: Final = re.compile(NUMBER)

# Polars regex patterns for frame neutralization:
# Matches cells that start with optional leading spaces followed by =, @, tab, or CR
RISKY_ANY_RE: Final = r"^[ ]*[=@\t\r]"
# Matches cells that start with optional leading spaces followed by + or -
RISKY_SIGN_RE: Final = r"^[ ]*[+-]"
# Matches a valid number cell with optional surrounding spaces
NUMBER_CELL_RE: Final = r"^[ ]*[+-]?(\d+|\d{1,3}(,\d{3})+)(\.\d+)?([eE][+-]?\d+)?[ ]*$"


def neutralize_cell(value: Any) -> Any:
    """Prefix a risky text cell with a single quote. Plain numbers and non-strings are unchanged."""
    if not isinstance(value, str):
        return value
    # Strip only space characters from the beginning so tabs and CRs are preserved as risky prefixes
    leading_spaces_stripped = value.lstrip(" ")
    if not leading_spaces_stripped:
        return value
    if leading_spaces_stripped.startswith(("=", "@", "\t", "\r")):
        return "'" + value
    if leading_spaces_stripped.startswith(("+", "-")):
        if not _NUMBER_RE.match(leading_spaces_stripped.strip(" \t\r\n")):
            return "'" + value
    return value


def neutralize_frame(frame: pl.DataFrame) -> pl.DataFrame:
    """Neutralize every text column. Numeric, boolean and date columns are not touched."""
    text_columns = [
        name
        for name, dtype in frame.schema.items()
        if dtype in (pl.Utf8, pl.String)
    ]
    if not text_columns:
        return frame
    exprs: list[pl.Expr] = []
    for name in text_columns:
        cell = pl.col(name)
        risky = (
            cell.str.contains(RISKY_ANY_RE)
            | (cell.str.contains(RISKY_SIGN_RE) & ~cell.str.contains(NUMBER_CELL_RE))
        ).fill_null(False)
        exprs.append(
            pl.when(risky).then(pl.lit("'") + cell).otherwise(cell).alias(name)
        )
    return frame.with_columns(exprs)

