"""Decide how a file will be read: columns, shape, formats, questions, and assumptions."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from obsidian_ledger.ingest.adapters import (
    AdapterSpec,
    default_contract_size,
    detect_adapter,
    map_columns,
    tradingview_currency,
)
from obsidian_ledger.ingest.canonical import ALL_FIELDS, assign_fields, normalize_header
from obsidian_ledger.ingest.errors import IngestError
from obsidian_ledger.ingest.fileio import (
    detect_kind,
    head_lines,
    iter_text_records,
    load_json_rows,
    load_workbook_rows,
    read_head,
    unique_names,
)
from obsidian_ledger.ingest.normalize import Context
from obsidian_ledger.ingest.options import ImportOptions
from obsidian_ledger.ingest.parse import (
    SLASH_DAYFIRST,
    SLASH_MONTHFIRST,
    DateChoice,
    DecimalStyle,
    choose_date_format,
    count_number_style,
)
from obsidian_ledger.ingest.sniff import detect_rows_layout, detect_text_layout

SAMPLE_RECORDS: Final = 300
PREVIEW_RECORDS: Final = 5
TIME_FIELDS: Final = ("entry_time", "exit_time", "leg_time", "fill_time")
NUMERIC_FIELDS: Final = (
    "qty",
    "entry_price",
    "exit_price",
    "leg_price",
    "fill_price",
    "gross_pnl",
    "net_pnl",
    "fees",
    "commission",
    "swap",
    "stop_loss",
    "take_profit",
    "planned_risk",
    "mae",
    "mfe",
    "multiplier",
)
SHAPES: Final = ("round_trip", "legs", "executions")


@dataclass
class Source:
    path: Path
    kind: str
    encoding: str
    delimiter: str | None
    header_record: int  # 1-based record number of the header line
    headers: tuple[str, ...]
    memory_rows: list[list[str]] | None  # all rows for XLSX, XLS, and JSON

    def iter_records(self) -> Iterator[tuple[int, list[str]]]:
        """Yield (record number, cells) for every record below the header."""
        if self.memory_rows is not None:
            for number, row in enumerate(self.memory_rows, start=1):
                if number > self.header_record:
                    yield number, row
            return
        if self.delimiter is None:
            raise IngestError("internal", "A text source needs a delimiter.", status=500)
        for number, row in iter_text_records(self.path, self.encoding, self.delimiter):
            if number > self.header_record:
                yield number, row


@dataclass
class Column:
    index: int
    header: str
    field: str | None
    confidence: str | None  # high | medium | low
    source: str  # adapter | template | synonym | user | none


@dataclass(frozen=True)
class Question:
    id: str
    text: str
    options: tuple[str, ...]
    blocking: bool


@dataclass(frozen=True)
class Assumption:
    key: str
    value: str
    detail: str
    adjustable: bool


@dataclass
class Analysis:
    source: Source
    fingerprint: str
    adapter: str | None
    shape: str | None
    columns: list[Column]
    field_index: dict[str, int]
    date: DateChoice
    context: Context
    questions: list[Question]
    assumptions: list[Assumption]
    preview_rows: list[dict[str, str]]
    symbols_sampled: tuple[str, ...] = ()

    @property
    def blocking(self) -> list[Question]:
        return [question for question in self.questions if question.blocking]


def _infer_shape(fields: set[str]) -> str | None:
    if "entry_time" in fields and fields & {"exit_time", "exit_price", "gross_pnl", "net_pnl"}:
        return "round_trip"
    has_time = bool(fields & {"fill_time", "entry_time"})
    has_price = bool(fields & {"fill_price", "entry_price"})
    if {"side", "qty"} <= fields and has_time and has_price:
        return "executions"
    return None


def _open_source(path: Path) -> Source:
    kind = detect_kind(path)
    encoding = ""
    head = ""
    if kind == "text":
        encoding, head = read_head(path)
        if head.lstrip()[:1] in ("[", "{"):
            kind = "json"
    if kind == "text":
        layout = detect_text_layout(head_lines(head))
        return Source(
            path=path,
            kind="text",
            encoding=encoding,
            delimiter=layout.delimiter,
            header_record=layout.header_index + 1,
            headers=layout.headers,
            memory_rows=None,
        )
    rows = load_json_rows(path, encoding or "utf-8") if kind == "json" else load_workbook_rows(path)
    layout = detect_rows_layout(rows)
    return Source(
        path=path,
        kind=kind,
        encoding=encoding,
        delimiter=None,
        header_record=layout.header_index + 1,
        headers=layout.headers,
        memory_rows=rows,
    )


TemplateLookup = Callable[[str], Mapping[str, str | None] | None]


def _numeric_samples(
    records: list[tuple[int, list[str]]], field_index: dict[str, int]
) -> list[str]:
    values: list[str] = []
    for _number, cells in records:
        for name in NUMERIC_FIELDS:
            index = field_index.get(name)
            if index is not None and index < len(cells) and cells[index].strip():
                values.append(cells[index])
    return values


def _value_of(cells: list[str], field_index: dict[str, int], name: str) -> str:
    index = field_index.get(name)
    if index is None or index >= len(cells):
        return ""
    return cells[index].strip()


def _sample_records(source: Source, limit: int) -> list[tuple[int, list[str]]]:
    records: list[tuple[int, list[str]]] = []
    for number, cells in source.iter_records():
        if any(cell.strip() for cell in cells):
            records.append((number, cells))
            if len(records) >= limit:
                break
    return records


def analyze(
    path: Path,
    options: ImportOptions,
    *,
    default_timezone: str = "UTC",
    template_lookup: TemplateLookup | None = None,
) -> Analysis:
    """Read the header and a sample of rows, then decide everything the import will assume."""
    source = _open_source(path)
    unique = unique_names(list(source.headers))
    source.headers = unique
    headers = list(unique)
    fingerprint = hashlib.sha256(
        "\n".join(normalize_header(header) for header in headers).encode("utf-8")
    ).hexdigest()

    adapter: AdapterSpec | None = detect_adapter(headers)
    columns = [Column(index, header, None, None, "none") for index, header in enumerate(headers)]
    taken_columns: set[int] = set()
    taken_fields: set[str] = set()

    if adapter is not None:
        for index, name in map_columns(adapter, headers).items():
            columns[index].field = name
            columns[index].confidence = "high"
            columns[index].source = "adapter"
            taken_columns.add(index)
            taken_fields.add(name)

    template = template_lookup(fingerprint) if template_lookup is not None else None
    if template is not None:
        for index, header in enumerate(headers):
            if index in taken_columns or header not in template:
                continue
            name = template[header]
            columns[index].field = name
            columns[index].confidence = "high" if name else None
            columns[index].source = "template"
            taken_columns.add(index)
            if name:
                taken_fields.add(name)

    for index, match in assign_fields(headers, taken_columns, taken_fields).items():
        columns[index].field = match.field
        columns[index].confidence = match.confidence
        columns[index].source = "synonym"
        taken_columns.add(index)

    for header_name, name in options.mapping.items():
        matches = [index for index, header in enumerate(headers) if header == header_name]
        if not matches:
            raise IngestError("unknown_column", f"The file has no column named '{header_name}'.")
        if name is not None and name not in ALL_FIELDS:
            raise IngestError("unknown_field", f"'{name}' is not a canonical field.")
        index = matches[0]
        if name is not None:
            for other in columns:
                if other.index != index and other.field == name:
                    other.field = None
                    other.confidence = None
                    other.source = "none"
        columns[index].field = name
        columns[index].confidence = "high" if name else None
        columns[index].source = "user"

    field_index: dict[str, int] = {}
    for column in columns:
        if column.field is not None and column.field not in field_index:
            field_index[column.field] = column.index
    fields = set(field_index)

    shape: str | None = adapter.shape if adapter is not None else _infer_shape(fields)
    if options.shape is not None:
        shape = options.shape

    questions: list[Question] = []
    assumptions: list[Assumption] = []

    if shape is None:
        questions.append(
            Question(
                "shape",
                "The file does not look like round trips or raw executions. Which is it?",
                SHAPES,
                blocking=True,
            )
        )

    records = _sample_records(source, SAMPLE_RECORDS)
    time_values = [
        cells[field_index[name]].strip()
        for _number, cells in records
        for name in TIME_FIELDS
        if name in field_index
        and field_index[name] < len(cells)
        and cells[field_index[name]].strip()
    ]
    date = choose_date_format(time_values)
    if options.date_format is not None:
        slash_family = SLASH_DAYFIRST if options.date_format == "dayfirst" else SLASH_MONTHFIRST
        assumptions.append(
            Assumption("date_order", options.date_format, "Chosen by you.", adjustable=True)
        )
    elif date.ambiguous:
        slash_family = None
        questions.append(
            Question(
                "date_format",
                "Some dates such as 01/06/2026 read two ways. "
                "Are slash dates day-first or month-first?",
                ("dayfirst", "monthfirst"),
                blocking=True,
            )
        )
    else:
        slash_family = date.slash_family
        assumptions.append(
            Assumption(
                "date_formats",
                date.summary(),
                "Patterns that matched the sampled timestamps. Other rows use the same list.",
                adjustable=False,
            )
        )

    numeric = _numeric_samples(records, field_index)
    if options.decimal is not None:
        decimal: DecimalStyle = options.decimal
        assumptions.append(Assumption("decimal", decimal, "Chosen by you.", adjustable=True))
    else:
        decimal, comma_votes, dot_votes = count_number_style(numeric)
        style_text = "1.234,56 (comma decimal)" if decimal == "comma" else "1,234.56 (dot decimal)"
        assumptions.append(
            Assumption(
                "decimal",
                style_text,
                f"{comma_votes} comma-style and {dot_votes} dot-style numbers in the sample.",
                adjustable=True,
            )
        )

    timezone_name = options.timezone or default_timezone
    try:
        tz = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise IngestError("bad_timezone", f"Unknown timezone '{timezone_name}'.") from exc
    assumptions.append(
        Assumption(
            "timezone",
            timezone_name,
            "Timestamps without an offset are read in this timezone. "
            "Change it if the broker used local time.",
            adjustable=True,
        )
    )

    tv_currency = (
        tradingview_currency(headers)
        if adapter is not None and adapter.name == "tradingview"
        else None
    )
    default_currency = options.default_currency or tv_currency or options.base_currency
    if "currency" not in fields:
        detail = (
            "Read from the TradingView price header."
            if tv_currency and not options.default_currency
            else "The file has no currency column, so the base currency is used."
        )
        assumptions.append(Assumption("currency", default_currency, detail, adjustable=True))
    if "account" not in fields:
        assumptions.append(
            Assumption(
                "account",
                options.default_account or "default",
                "The file has no account column.",
                adjustable=True,
            )
        )

    if shape in ("round_trip", "executions") and "side" not in fields:
        unmapped = tuple(column.header for column in columns if column.field is None)
        questions.append(
            Question(
                "side",
                "No column holds buy or sell. Which column does?",
                unmapped,
                blocking=True,
            )
        )

    if "symbol" not in fields and options.default_symbol is None:
        questions.append(
            Question(
                "default_symbol",
                "The file has no symbol column. Enter the symbol these rows trade.",
                (),
                blocking=True,
            )
        )

    preview_records = _sample_records(source, PREVIEW_RECORDS)
    preview_rows = [
        {header: cells[index] if index < len(cells) else "" for index, header in enumerate(headers)}
        for _number, cells in preview_records
    ]

    symbols: list[str] = []
    for _number, cells in records:
        symbol = _value_of(cells, field_index, "symbol")
        if symbol and symbol not in symbols:
            symbols.append(symbol)
    if not symbols and options.default_symbol:
        symbols.append(options.default_symbol)

    if "multiplier" not in fields and symbols:
        described: list[str] = []
        for symbol in symbols:
            if symbol in options.contract_sizes:
                described.append(f"{symbol} {options.contract_sizes[symbol]:g} (you set it)")
                continue
            default = default_contract_size(adapter.name if adapter else None, symbol)
            if default is not None:
                described.append(f"{symbol} {default:g} (default for this broker)")
            else:
                described.append(f"{symbol} 1 (no multiplier column or default)")
        assumptions.append(
            Assumption(
                "contract_size",
                "; ".join(described),
                "Multiplies price moves into P&L. Set a size per symbol if these are wrong.",
                adjustable=True,
            )
        )

    context = Context(
        tz=tz,
        tz_name=timezone_name,
        slash_family=slash_family,
        decimal=decimal,
        default_symbol=options.default_symbol,
        default_account=options.default_account or "default",
        default_currency=default_currency,
        adapter=adapter.name if adapter else None,
        base_currency=options.base_currency,
        contract_sizes=dict(options.contract_sizes),
    )
    return Analysis(
        source=source,
        fingerprint=fingerprint,
        adapter=adapter.name if adapter else None,
        shape=shape,
        columns=columns,
        field_index=field_index,
        date=date,
        context=context,
        questions=questions,
        assumptions=assumptions,
        preview_rows=preview_rows,
        symbols_sampled=tuple(symbols),
    )


def analysis_json(analysis: Analysis) -> str:
    """Compact JSON of the decisions, for logs and the import record."""
    payload = {
        "adapter": analysis.adapter,
        "shape": analysis.shape,
        "fingerprint": analysis.fingerprint,
        "assumptions": [a.key + ": " + a.value for a in analysis.assumptions],
    }
    return json.dumps(payload, ensure_ascii=False)
