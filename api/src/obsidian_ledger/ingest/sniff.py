"""Find the delimiter and header row of a file, and the encoding of its bytes."""

from __future__ import annotations

import codecs
import csv
from dataclasses import dataclass
from typing import Final

from charset_normalizer import from_bytes

from obsidian_ledger.ingest.canonical import header_matches
from obsidian_ledger.ingest.errors import IngestError

DELIMITERS: Final[tuple[str, ...]] = (",", ";", "\t", "|")
HEAD_LINES: Final = 80
SNIFF_BYTES: Final = 64 * 1024
MIN_HEADER_HITS: Final = 2
# Column names are short. Longer cells are data, so they are never scored as headers.
MAX_HEADER_CHARS: Final = 40


@dataclass(frozen=True)
class Layout:
    delimiter: str | None
    header_index: int  # zero-based position among the parsed records
    headers: tuple[str, ...]
    hits: int


def sniff_encoding(head: bytes) -> str:
    if head.startswith(codecs.BOM_UTF8):
        return "utf-8-sig"
    if head.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return "utf-16"
    try:
        # Valid UTF-8 is the common case, so skip the slower statistical detector.
        head.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        pass
    best = from_bytes(head).best()
    if best is not None and best.encoding:
        return best.encoding
    return "utf-8"


def _first_record(line: str, delimiter: str) -> list[str]:
    records = list(csv.reader([line], delimiter=delimiter))
    return records[0] if records else []


def _best_header(rows: list[list[str]], delimiter: str | None) -> Layout | None:
    best: Layout | None = None
    for index, row in enumerate(rows):
        if len(row) < 2:
            continue
        hits = sum(
            1
            for cell in row
            if 0 < len(cell.strip()) <= MAX_HEADER_CHARS
            and any(m.score >= 2.0 for m in header_matches(cell).values())
        )
        if hits < MIN_HEADER_HITS:
            continue
        if best is None or hits > best.hits:
            best = Layout(delimiter, index, tuple(cell.strip() for cell in row), hits)
    return best


def detect_text_layout(lines: list[str]) -> Layout:
    """Try each delimiter on the first lines and keep the header with the most known columns."""
    best: Layout | None = None
    for delimiter in DELIMITERS:
        parsed = [_first_record(line, delimiter) for line in lines]
        layout = _best_header(parsed, delimiter)
        if layout is None:
            continue
        if best is None or (layout.hits, len(layout.headers)) > (best.hits, len(best.headers)):
            best = layout
    if best is None:
        raise IngestError(
            "no_header_row",
            f"No header row with at least {MIN_HEADER_HITS} recognised column names was found "
            f"in the first {HEAD_LINES} lines.",
        )
    return best


def detect_rows_layout(rows: list[list[str]]) -> Layout:
    """Find the header in rows already parsed from XLSX, XLS, or JSON."""
    layout = _best_header(rows[:HEAD_LINES], None)
    if layout is None:
        raise IngestError(
            "no_header_row",
            "No header row with at least two recognised column names was found in the first rows.",
        )
    return layout
