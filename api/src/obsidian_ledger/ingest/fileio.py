"""Read trade files of each supported kind without executing anything inside them."""

from __future__ import annotations

import csv
import json
from collections.abc import Iterator
from datetime import date, datetime, time
from pathlib import Path
from typing import Any, Final, Literal, cast

from python_calamine import CalamineWorkbook

from obsidian_ledger.ingest.errors import IngestError
from obsidian_ledger.ingest.sniff import HEAD_LINES, SNIFF_BYTES, sniff_encoding
from obsidian_ledger.security.files import (
    MAX_COLUMNS,
    MAX_ROWS,
    OLE_MAGIC,
    ZIP_MAGIC,
    check_archive,
    check_ole_workbook,
    reject_dde_text,
    reject_forbidden_signature,
    reject_markup,
    reject_polyglot,
)

Kind = Literal["text", "json", "xlsx", "xls"]

_check_archive = check_archive


SUPPORTED_EXTENSIONS: Final = {".csv", ".tsv", ".txt", ".xlsx", ".xls", ".json"}


def validate_extension_and_content(path: Path, filename: str) -> None:
    """Ensure the file extension is supported and matches the actual file content."""
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise IngestError("unsupported_extension", f"Unsupported file extension '{ext}'.")

    with path.open("rb") as handle:
        head = handle.read(512)

    if ext == ".xlsx":
        if not head.startswith(ZIP_MAGIC):
            raise IngestError("extension_mismatch", "File content does not match .xlsx extension.")
        _check_archive(path)
    elif ext == ".xls":
        if not head.startswith(OLE_MAGIC):
            raise IngestError("extension_mismatch", "File content does not match .xls extension.")
        check_ole_workbook(path)
    elif ext == ".json":
        if head.startswith(ZIP_MAGIC) or head.startswith(OLE_MAGIC):
            raise IngestError("extension_mismatch", "File content does not match .json extension.")
        encoding = sniff_encoding(head)
        try:
            decoded = head.decode(encoding, errors="replace").lstrip()
        except Exception as exc:
            raise IngestError(
                "extension_mismatch",
                "File content does not match .json extension.",
            ) from exc
        if not decoded or decoded[0] not in ("[", "{"):
            raise IngestError("extension_mismatch", "File content does not match .json extension.")
        reject_polyglot(path, head)
        reject_dde_text(path)
    elif ext in (".csv", ".tsv", ".txt"):
        if head.startswith(ZIP_MAGIC) or head.startswith(OLE_MAGIC):
            raise IngestError("extension_mismatch", "Archive file uploaded with text extension.")
        try:
            reject_forbidden_signature(head)
        except IngestError as exc:
            raise IngestError(
                "extension_mismatch", "Binary file detected with text extension."
            ) from exc
        reject_markup(head)
        if b"\x00" in head and not head.startswith((b"\xff\xfe", b"\xfe\xff")):
            raise IngestError("extension_mismatch", "Binary null bytes detected in text file.")
        encoding = sniff_encoding(head)
        try:
            decoded = head.decode(encoding, errors="replace").lstrip()
            if decoded and decoded[0] in ("[", "{"):
                raise IngestError("extension_mismatch", "JSON content uploaded with CSV extension.")
        except UnicodeDecodeError as exc:
            raise IngestError("extension_mismatch", "Text file decoding failed.") from exc
        reject_polyglot(path, head)
        reject_dde_text(path)


def detect_kind(path: Path) -> Kind:
    with path.open("rb") as handle:
        head = handle.read(8)
    if head.startswith(ZIP_MAGIC):
        _check_archive(path)
        return "xlsx"
    if head.startswith(OLE_MAGIC):
        return "xls"
    return "text"


def read_head(path: Path) -> tuple[str, str]:
    """Return (encoding, decoded head) from the first bytes of a text file."""
    with path.open("rb") as handle:
        raw = handle.read(SNIFF_BYTES)
    encoding = sniff_encoding(raw)
    return encoding, raw.decode(encoding, errors="replace")


def head_lines(text: str) -> list[str]:
    return text.splitlines()[:HEAD_LINES]


def iter_text_records(path: Path, encoding: str, delimiter: str) -> Iterator[tuple[int, list[str]]]:
    """Stream CSV records. Record numbers start at 1 and match the row number in the file."""
    with path.open("r", encoding=encoding, errors="replace", newline="") as handle:
        try:
            for number, record in enumerate(csv.reader(handle, delimiter=delimiter), start=1):
                if number > MAX_ROWS:
                    raise IngestError("too_many_rows", f"The file has more than {MAX_ROWS:,} rows.")
                if len(record) > MAX_COLUMNS:
                    raise IngestError(
                        "too_many_columns", f"A row has more than {MAX_COLUMNS:,} columns."
                    )
                yield number, record
        except csv.Error as exc:
            raise IngestError("bad_csv", "The file has a cell or row that is too large.") from exc


def _cell_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else repr(value)
    if isinstance(value, datetime | date | time):
        return value.isoformat(sep=" ") if isinstance(value, datetime) else value.isoformat()
    return str(value)


def load_workbook_rows(path: Path) -> list[list[str]]:
    """Read cached cell values from the first sheet. Formulas are never evaluated."""
    try:
        # python-calamine ships a partially typed signature. Its return type is known.
        workbook = CalamineWorkbook.from_path(str(path))  # pyright: ignore[reportUnknownMemberType]
    except Exception as exc:  # calamine raises several error classes for corrupt files
        raise IngestError("bad_workbook", "The spreadsheet could not be opened.") from exc
    if not workbook.sheet_names:
        raise IngestError("empty_workbook", "The workbook has no sheets.")
    values = cast(list[list[object]], workbook.get_sheet_by_index(0).to_python())
    _check_grid(values)
    return [[_cell_text(cell) for cell in row] for row in values]


def _check_grid(values: list[Any]) -> None:
    if len(values) > MAX_ROWS:
        raise IngestError("too_many_rows", f"The file has more than {MAX_ROWS:,} rows.")
    if any(isinstance(row, list) and len(cast(list[Any], row)) > MAX_COLUMNS for row in values):
        raise IngestError("too_many_columns", f"A row has more than {MAX_COLUMNS:,} columns.")


UNSAFE_KEYS: Final = frozenset({"__proto__", "constructor", "prototype"})


def _json_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, int | float):
        return str(value)
    return json.dumps(value, ensure_ascii=False)


def _rows_from_lists(values: list[Any]) -> list[list[str]]:
    _check_grid(values)
    rows: list[list[str]] = []
    for row in values:
        if isinstance(row, list):
            rows.append([_json_text(cell) for cell in cast(list[Any], row)])
        else:
            rows.append([])
    return rows


def _rows_from_objects(items: list[dict[str, Any]]) -> list[list[str]]:
    if len(items) > MAX_ROWS:
        raise IngestError("too_many_rows", f"The file has more than {MAX_ROWS:,} rows.")
    headers: dict[str, None] = {}
    for item in items:
        for key in item:
            name = str(key)
            headers.setdefault(name + "_" if name in UNSAFE_KEYS else name, None)
    names = list(headers)
    if len(names) > MAX_COLUMNS:
        raise IngestError("too_many_columns", f"The file has more than {MAX_COLUMNS:,} columns.")
    rows: list[list[str]] = [names]
    for item in items:
        rows.append(
            [
                _json_text(item.get(name[:-1] if name[:-1] in UNSAFE_KEYS else name))
                for name in names
            ]
        )
    return rows


def load_json_rows(path: Path, encoding: str) -> list[list[str]]:
    """Accept a list of objects, a list of lists, or a Google Sheets `values` export."""
    text = path.read_bytes().decode(encoding, errors="replace")
    try:
        payload: Any = json.loads(text)
    except json.JSONDecodeError as exc:
        raise IngestError("bad_json", f"Invalid JSON at line {exc.lineno}: {exc.msg}.") from exc
    except RecursionError as exc:
        raise IngestError("json_too_deep", "The JSON is nested too deeply.") from exc
    if isinstance(payload, dict):
        values = cast(dict[str, Any], payload).get("values")
        if isinstance(values, list):
            return _rows_from_lists(cast(list[Any], values))
        raise IngestError("unsupported_json", "JSON objects must contain a 'values' array.")
    if isinstance(payload, list) and payload:
        items = cast(list[Any], payload)
        if all(isinstance(item, dict) for item in items):
            return _rows_from_objects(cast(list[dict[str, Any]], items))
        if all(isinstance(item, list) for item in items):
            return _rows_from_lists(items)
    raise IngestError("unsupported_json", "Unsupported JSON layout. Use a list of objects or rows.")


def unique_names(names: list[str]) -> tuple[str, ...]:
    """Make header names unique. Duplicate "Price" headers become "Price" and "Price (2)"."""
    seen: dict[str, int] = {}
    result: list[str] = []
    for name in names:
        count = seen.get(name, 0) + 1
        seen[name] = count
        result.append(name if count == 1 else f"{name} ({count})")
    return tuple(result)
