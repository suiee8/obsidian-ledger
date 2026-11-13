"""Decide how a file will be read: columns, shape, formats, questions, and assumptions."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
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
from obsidian_ledger.ingest.canonical import (
    ALL_FIELDS,
    assign_fields,
    header_matches,
    normalize_header,
)
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
    parse_number,
    parse_side_action,
    parse_time,
)
from obsidian_ledger.ingest.sniff import detect_rows_layout, detect_text_layout

SAMPLE_RECORDS: Final = 2000
PROFILE_STRIDE: Final = 100
PREVIEW_RECORDS: Final = 5
TIME_FIELDS: Final = (
    "entry_time",
    "exit_time",
    "leg_time",
    "fill_time",
    "entry_clock",
    "exit_clock",
)
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
    "notional",
    "leverage",
    "mae",
    "mfe",
    "multiplier",
)
SHAPES: Final = ("round_trip", "legs", "executions", "orders")


@dataclass
class Source:
    path: Path
    kind: str
    encoding: str
    delimiter: str | None
    header_record: int  # 1-based record number of the header line
    headers: tuple[str, ...]
    memory_rows: list[list[str]] | None  # all rows for XLSX, XLS, and JSON
    line_ending: str = "unknown"
    ignored_records: set[int] = field(default_factory=set[int])

    def iter_records(self) -> Iterator[tuple[int, list[str]]]:
        """Yield (record number, cells) for every record below the header."""
        if self.memory_rows is not None:
            for number, row in enumerate(self.memory_rows, start=1):
                if number > self.header_record and number not in self.ignored_records:
                    yield number, row
            return
        if self.delimiter is None:
            raise IngestError("internal", "A text source needs a delimiter.", status=500)
        for number, row in iter_text_records(self.path, self.encoding, self.delimiter):
            if number > self.header_record and number not in self.ignored_records:
                yield number, row


@dataclass
class Column:
    index: int
    header: str
    field: str | None
    confidence: str | None  # high | medium | low
    source: str  # adapter | template | synonym | user | none
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class ColumnProfile:
    index: int
    header: str
    type_mix: dict[str, int]
    regex_shape: tuple[str, ...]
    cardinality: int
    minimum: float | None
    maximum: float | None
    monotonicity: str
    max_length: int
    samples: tuple[str, ...]


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
    profiles: list[ColumnProfile] = field(default_factory=list[ColumnProfile])
    capabilities: dict[str, bool] = field(default_factory=dict[str, bool])
    warnings: tuple[str, ...] = ()
    rows_profiled: int = 0
    duplicate_rows: int = 0
    row_order: str = "unknown"
    totals_rows: int = 0

    @property
    def blocking(self) -> list[Question]:
        return [question for question in self.questions if question.blocking]


def _infer_shape(fields: set[str], side_values: list[str] | None = None) -> str | None:
    if "entry_time" in fields and "exit_time" in fields:
        return "round_trip"
    explicit_actions = any(parse_side_action(value)[0] is not None for value in (side_values or []))
    if (
        not explicit_actions
        and "entry_time" in fields
        and fields & {"exit_price", "gross_pnl", "net_pnl"}
    ):
        return "round_trip"
    has_time = bool(fields & {"fill_time", "entry_time"})
    has_price = bool(fields & {"fill_price", "entry_price"})
    if "fill_time" in fields and {"side", "qty"} <= fields and has_price:
        return "executions"
    if "side" in fields and has_time and fields & {"qty", "notional"}:
        return "orders"
    return None


def _open_source(path: Path) -> Source:
    kind = detect_kind(path)
    encoding = ""
    head = ""
    line_ending = "unknown"
    if kind == "text":
        encoding, head = read_head(path)
        line_ending = (
            "CRLF"
            if "\r\n" in head
            else "CR"
            if "\r" in head
            else "LF"
            if "\n" in head
            else "unknown"
        )
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
            line_ending=line_ending,
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


def _is_totals_row(cells: list[str]) -> bool:
    labels = {"total", "totals", "grand total", "summary"}
    return any(normalize_header(cell) in labels for cell in cells[:2] if cell.strip())


def _sample_records(
    source: Source,
) -> tuple[list[tuple[int, list[str]]], int, int, int]:
    records: list[tuple[int, list[str]]] = []
    seen: set[bytes] = set()
    duplicates = 0
    total = 0
    totals = 0
    for number, cells in source.iter_records():
        if _is_totals_row(cells):
            source.ignored_records.add(number)
            totals += 1
            continue
        if any(cell.strip() for cell in cells):
            total += 1
            signature = hashlib.sha256("\x1f".join(cells).encode("utf-8")).digest()
            if signature in seen:
                duplicates += 1
            else:
                seen.add(signature)
            if total <= SAMPLE_RECORDS or (total - SAMPLE_RECORDS) % PROFILE_STRIDE == 0:
                records.append((number, cells))
    return records, total, duplicates, totals


_NUMBER_SHAPE = re.compile(r"^[+-]?\d+(?:[.,]\d+)?$")
_DATE_SHAPE = re.compile(
    r"^(?:\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|\d{1,2}[-/.]\d{1,2}[-/.]\d{4})(?:[ T].*)?$"
)


def _looks_like_time(value: str) -> bool:
    text = value.strip()
    if _DATE_SHAPE.match(text) or re.fullmatch(r"\d{10}|\d{13}", text):
        return True
    return bool(re.search(r"(?:\s|T)\d{1,2}:?$", text))


def _profile_columns(
    headers: list[str], records: list[tuple[int, list[str]]]
) -> list[ColumnProfile]:
    profiles: list[ColumnProfile] = []
    for index, header in enumerate(headers):
        values = [cells[index].strip() for _, cells in records if index < len(cells)]
        nonempty = [value for value in values if value]
        types: Counter[str] = Counter()
        shapes: Counter[str] = Counter()
        numeric: list[float] = []
        time_values: list[float] = []
        for value in nonempty:
            if _looks_like_time(value):
                types["time"] += 1
                shapes["datetime" if ":" in value else "date-or-epoch"] += 1
                parsed = parse_time(value, "slash_dayfirst") or parse_time(
                    value, "slash_monthfirst"
                )
                if parsed is not None:
                    time_values.append(parsed[0].timestamp())
                continue
            number = parse_number(value, "dot")
            if number is None:
                number = parse_number(value, "comma")
            if number is not None:
                types["number"] += 1
                shapes["integer" if number.is_integer() else "decimal"] += 1
                numeric.append(number)
            else:
                types["text"] += 1
                shapes["text"] += 1
        if len(nonempty) < len(values):
            types["empty"] = len(values) - len(nonempty)
        sequence = time_values if len(time_values) >= max(2, len(nonempty) * 0.7) else numeric
        monotonicity = "unknown"
        if len(sequence) >= 2:
            if all(left <= right for left, right in zip(sequence, sequence[1:], strict=False)):
                monotonicity = "ascending"
            elif all(left >= right for left, right in zip(sequence, sequence[1:], strict=False)):
                monotonicity = "descending"
            else:
                monotonicity = "mixed"
        samples = tuple(dict.fromkeys(nonempty))[:3]
        profiles.append(
            ColumnProfile(
                index=index,
                header=header,
                type_mix=dict(types),
                regex_shape=tuple(name for name, _ in shapes.most_common(3)),
                cardinality=len(set(nonempty)),
                minimum=min(numeric) if numeric else None,
                maximum=max(numeric) if numeric else None,
                monotonicity=monotonicity,
                max_length=max((len(value) for value in nonempty), default=0),
                samples=samples,
            )
        )
    return profiles


def _content_role(profile: ColumnProfile, values: list[str]) -> tuple[str, float, str] | None:
    nonempty = [value.strip() for value in values if value.strip()]
    if not nonempty:
        return None
    timed = sum(_looks_like_time(value) for value in nonempty)
    if timed / len(nonempty) >= 0.7:
        return "entry_time", 0.96, "timestamp-shaped values"
    side_pairs = [parse_side_action(value) for value in nonempty]
    directional = sum(direction is not None for _, direction in side_pairs)
    if directional / len(nonempty) >= 0.8 and len(set(nonempty)) <= 16:
        return "side", 0.98, "recognized side/action vocabulary"
    numeric = [parse_number(value, "dot") for value in nonempty]
    if all(value is None for value in numeric):
        numeric = [parse_number(value, "comma") for value in nonempty]
    if numeric and sum(value is not None for value in numeric) / len(nonempty) >= 0.9:
        # Header evidence is used by the caller to distinguish prices, quantities, P&L, and value.
        unique_ratio = profile.cardinality / len(nonempty)
        if (
            all(value is not None and value.is_integer() for value in numeric)
            and profile.cardinality > 1
            and unique_ratio < 0.3
            and max(abs(value or 0) for value in numeric) < 10**9
        ):
            return "qty", 0.76, "mostly repeated integer quantities"
    text_values = [value for value in nonempty if not _NUMBER_SHAPE.fullmatch(value)]
    alphabetic = sum(any(char.isalpha() for char in value) for value in text_values)
    if (
        len(text_values) / len(nonempty) >= 0.9
        and alphabetic / max(1, len(text_values)) >= 0.8
        and profile.cardinality >= min(5, max(2, len(nonempty) // 20))
    ):
        return "symbol", 0.78, "high-cardinality instrument-like text"
    return None


def _time_value(cells: list[str], field_index: dict[str, int], prefix: str = "entry") -> str:
    base = _value_of(cells, field_index, f"{prefix}_time")
    clock = _value_of(cells, field_index, f"{prefix}_clock")
    if base and clock and not re.search(r"\d{1,2}:\d{2}", base):
        return f"{base.strip()} {clock.strip()}"
    return base or clock


def _row_order(
    records: list[tuple[int, list[str]]], field_index: dict[str, int], slash_family: str | None
) -> str:
    values = [
        parse_time(_time_value(cells, field_index), slash_family)
        for _, cells in records
        if _time_value(cells, field_index)
    ]
    times = [value[0] for value in values if value is not None]
    if len(times) < 2:
        return "unknown"
    if all(left <= right for left, right in zip(times, times[1:], strict=False)):
        return "ascending"
    if all(left >= right for left, right in zip(times, times[1:], strict=False)):
        return "descending"
    return "mixed"


def _date_values(records: list[tuple[int, list[str]]], field_index: dict[str, int]) -> list[str]:
    return [
        value
        for _, cells in records
        for value in (
            _time_value(cells, field_index),
            _time_value(cells, field_index, "exit"),
            _value_of(cells, field_index, "leg_time"),
            _value_of(cells, field_index, "fill_time"),
        )
        if value
    ]


def analyze(
    path: Path,
    options: ImportOptions,
    *,
    default_timezone: str = "UTC",
    template_lookup: TemplateLookup | None = None,
) -> Analysis:
    """Profile source rows once, then decide mappings, layout, and import assumptions."""
    source = _open_source(path)
    unique = unique_names(list(source.headers))
    source.headers = unique
    headers = list(unique)
    records, rows_profiled, duplicate_rows, totals_rows = _sample_records(source)
    profiles = _profile_columns(headers, records)
    content_signature = "\n".join(
        f"{profile.type_mix}|{profile.regex_shape}|"
        f"{min(profile.cardinality, 20)}|{profile.max_length}"
        for profile in profiles
    )
    fingerprint = hashlib.sha256(
        (
            "\n".join(sorted(normalize_header(header) for header in headers))
            + "\n"
            + content_signature
        ).encode("utf-8")
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
        columns[index].reasons = (f"header matched {match.field}",)
        taken_columns.add(index)
        taken_fields.add(match.field)

    for column in columns:
        if column.field is not None:
            continue
        normalized = normalize_header(column.header)
        if normalized in {"entry time", "open time"} and "entry_time" in taken_fields:
            column.field = "entry_clock"
        elif normalized in {"exit time", "close time"} and "exit_time" in taken_fields:
            column.field = "exit_clock"
        else:
            continue
        column.confidence = "medium"
        column.source = "synonym"
        column.reasons = ("separate clock column paired with a date column",)
        taken_columns.add(column.index)
        taken_fields.add(column.field)

    content_scores: dict[int, float] = {}
    ambiguous_content_columns: set[int] = set()
    for profile in profiles:
        values = [cells[profile.index] for _, cells in records if profile.index < len(cells)]
        suggestion = _content_role(profile, values)
        if suggestion is None:
            continue
        role, score, reason = suggestion
        column = columns[profile.index]
        if role == "entry_time":
            if column.field in {"entry_time", "exit_time", "leg_time", "fill_time"}:
                continue
            time_matches = header_matches(column.header)
            if "exit_time" in time_matches:
                role = "exit_time"
            elif any(
                candidate.field in {"entry_time", "fill_time"}
                for candidate in columns
                if candidate.index != column.index
            ):
                role = "exit_time"
        if column.source == "adapter":
            continue
        existing_match = header_matches(column.header).get(role)
        if column.field is None or (
            score >= 0.9
            and column.field != role
            and (existing_match is None or existing_match.score < 3.0)
        ):
            conflict = next(
                (other for other in columns if other.index != column.index and other.field == role),
                None,
            )
            if conflict is not None:
                if conflict.source == "content":
                    previous_score = content_scores.get(conflict.index, 0.0)
                    if abs(previous_score - score) < 0.15:
                        ambiguous_content_columns.update({conflict.index, column.index})
                        conflict.field = None
                        conflict.confidence = None
                        conflict.source = "none"
                        conflict.reasons = ()
                        continue
                    if previous_score > score:
                        ambiguous_content_columns.add(column.index)
                        continue
                    conflict.field = None
                    conflict.confidence = None
                    conflict.source = "none"
                    conflict.reasons = ()
                elif conflict.source != "adapter":
                    ambiguous_content_columns.add(column.index)
                    continue
                else:
                    continue
            column.field = role
            column.confidence = "high" if score >= 0.9 else "medium"
            column.source = "content"
            column.reasons = (reason,)
            content_scores[column.index] = score
            taken_columns.add(column.index)
            taken_fields.add(role)

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
        columns[index].reasons = ("user override",)

    questions: list[Question] = []
    assumptions: list[Assumption] = []
    field_index: dict[str, int] = {}
    for column in columns:
        if column.field is not None and column.field not in field_index:
            field_index[column.field] = column.index
    fields = set(field_index)
    ambiguous_headers = {
        headers[index]
        for index in ambiguous_content_columns
        if headers[index] not in options.mapping
    }
    for column in columns:
        if column.field is not None or column.header in options.mapping:
            continue
        if header_matches(column.header):
            continue
        profile = profiles[column.index]
        if profile.type_mix.get("number", 0) > 0 and profile.cardinality > 1:
            ambiguous_headers.add(column.header)
    if ambiguous_headers:
        questions.append(
            Question(
                "mapping_ambiguity",
                "Several columns can contain prices, quantities, P&L, or identifiers. "
                "Assign a role or explicitly ignore each ambiguous column.",
                tuple(header for header in headers if header in ambiguous_headers),
                blocking=True,
            )
        )

    side_values = [
        _value_of(cells, field_index, "side")
        for _, cells in records
        if _value_of(cells, field_index, "side")
    ]
    shape: str | None = adapter.shape if adapter is not None else _infer_shape(fields, side_values)
    if options.shape is not None:
        shape = options.shape

    if shape is None:
        questions.append(
            Question(
                "shape",
                "The file layout is unfamiliar. Choose its row structure; unknown formats "
                "can be mapped manually.",
                SHAPES,
                blocking=True,
            )
        )

    time_values = _date_values(records, field_index)
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

    preview_records = records[:PREVIEW_RECORDS]
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

    capabilities = {
        "has_time": bool(fields & {"entry_time", "exit_time", "fill_time", "leg_time"}),
        "has_direction": bool(fields & {"side", "leg"}),
        "has_quantity": "qty" in fields,
        "has_notional": "notional" in fields,
        "has_price": bool(fields & {"entry_price", "exit_price", "fill_price", "leg_price"}),
        "has_fees": bool(fields & {"fees", "commission", "swap"}),
        "has_pnl": bool(fields & {"gross_pnl", "net_pnl"}),
        "has_stop": "stop_loss" in fields,
    }

    if shape == "orders" and "side" in fields:
        side_values = [
            _value_of(cells, field_index, "side")
            for _, cells in records
            if _value_of(cells, field_index, "side")
        ]
        if (
            side_values
            and options.side_mode is None
            and all(parse_side_action(value)[0] is None for value in side_values)
        ):
            questions.append(
                Question(
                    "side_mode",
                    "These buy/sell values do not say whether each row opens or closes. "
                    "Treat them as a netted position history?",
                    ("netting",),
                    blocking=True,
                )
            )

    missing_minimum: list[str] = []
    if not capabilities["has_time"]:
        missing_minimum.append("time")
    if not capabilities["has_direction"]:
        missing_minimum.append("direction or action")
    if not (capabilities["has_quantity"] or capabilities["has_notional"]):
        missing_minimum.append("quantity or notional")
    if missing_minimum:
        questions.append(
            Question(
                "mapping",
                "Map columns for " + ", ".join(missing_minimum) + " to import this file.",
                tuple(header for header in headers),
                blocking=True,
            )
        )

    warning_codes: list[str] = []
    if any(re.search(r"(?:\s|T)\d{1,2}:$", value) for value in time_values):
        warning_codes.append("hour_precision")
    if duplicate_rows:
        warning_codes.append("duplicates")
    if totals_rows:
        warning_codes.append("totals_row")
    if "leverage" in field_index and any(
        parse_number(_value_of(cells, field_index, "leverage"), "dot") == 0 for _, cells in records
    ):
        warning_codes.append("zero_leverage")
    if any("filled quantity" in normalize_header(header) for header in headers) and any(
        "order quantity" in normalize_header(header) for header in headers
    ):
        warning_codes.append("partial_fills")
    for profile in profiles:
        if profile.header == headers[field_index["symbol"]] if "symbol" in field_index else False:
            lengths = Counter(
                value.strip()
                for _, cells in records
                if profile.index < len(cells) and (value := cells[profile.index].strip())
            )
            max_length = profile.max_length
            max_width_values = sum(
                count for value, count in lengths.items() if len(value) == max_length
            )
            if (
                max_length >= 8
                and profile.cardinality >= 5
                and max_width_values / max(1, rows_profiled) >= 0.02
            ):
                warning_codes.append("truncated_symbols")
                break

    row_order = _row_order(records, field_index, date.slash_family)

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
        symbol_aliases=dict(options.symbol_aliases),
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
        profiles=profiles,
        capabilities=capabilities,
        warnings=tuple(warning_codes),
        rows_profiled=rows_profiled,
        duplicate_rows=duplicate_rows,
        row_order=row_order,
        totals_rows=totals_rows,
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
