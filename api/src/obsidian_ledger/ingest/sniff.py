"""Find the delimiter and header row of a file, and the encoding of its bytes."""

from __future__ import annotations

import codecs
import csv
import io
import re
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
    """Detect known or unfamiliar headers, otherwise keep a headerless file importable."""
    best: Layout | None = None
    for delimiter in DELIMITERS:
        try:
            parsed = list(csv.reader(io.StringIO("\n".join(lines)), delimiter=delimiter))
        except csv.Error:
            continue
        layout = _best_header(parsed, delimiter)
        if layout is None:
            width_counts: dict[int, int] = {}
            for row in parsed[:HEAD_LINES]:
                if len(row) > 1 and any(cell.strip() for cell in row):
                    width_counts[len(row)] = width_counts.get(len(row), 0) + 1
            if not width_counts:
                continue
            width = max(width_counts, key=lambda count: width_counts[count])
            matching = [
                (index, row) for index, row in enumerate(parsed[:HEAD_LINES]) if len(row) == width
            ]
            if len(matching) < 2:
                continue
            first_index, first_row = matching[0]
            next_row = matching[1][1]
            first_looks_like_header = all(
                cell.strip()
                and len(cell.strip()) <= MAX_HEADER_CHARS
                and not re.fullmatch(r"[+-]?\d+(?:[.,]\d+)?", cell.strip())
                and not re.match(r"^\d{4}[-/.]\d{1,2}[-/.]\d{1,2}", cell.strip())
                for cell in first_row
            )
            next_has_data = any(
                re.fullmatch(r"[+-]?\d+(?:[.,]\d+)?", cell.strip())
                or re.match(r"^\d{4}[-/.]\d{1,2}[-/.]\d{1,2}", cell.strip())
                for cell in next_row
            )
            if first_looks_like_header and next_has_data:
                layout = Layout(
                    delimiter,
                    first_index,
                    tuple(cell.strip() for cell in first_row),
                    0,
                )
            else:
                layout = Layout(
                    delimiter,
                    -1,
                    tuple(f"Column {index + 1}" for index in range(width)),
                    0,
                )
        if best is None or (layout.hits, len(layout.headers)) > (best.hits, len(best.headers)):
            best = layout
    if best is None:
        raise IngestError(
            "no_header_row",
            "The file has no rows with a consistent tabular layout.",
        )
    return best


def detect_rows_layout(rows: list[list[str]]) -> Layout:
    """Find the header in rows already parsed from XLSX, XLS, or JSON."""
    layout = _best_header(rows[:HEAD_LINES], None)
    if layout is None:
        first: list[str] = []
        for row in rows:
            if any(cell.strip() for cell in row):
                first = row
                break
        if len(first) < 2:
            raise IngestError("no_header_row", "The file has no consistent tabular layout.")
        return Layout(None, -1, tuple(f"Column {index + 1}" for index in range(len(first))), 0)
    return layout
