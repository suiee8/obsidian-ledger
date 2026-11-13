import json
import zipfile
from pathlib import Path

import pytest

from obsidian_ledger.ingest.analysis import analyze
from obsidian_ledger.ingest.errors import IngestError
from obsidian_ledger.ingest.fileio import detect_kind, load_json_rows, unique_names
from obsidian_ledger.ingest.options import ImportOptions
from obsidian_ledger.ingest.sniff import detect_text_layout, sniff_encoding


def test_utf8_bom_and_plain_ascii_are_detected() -> None:
    assert sniff_encoding(b"\xef\xbb\xbfdate,symbol\n") == "utf-8-sig"
    assert sniff_encoding(b"date,symbol\n1,2\n") in {"ascii", "utf_8", "utf-8"}


def test_header_detection_skips_preamble_and_finds_semicolon_delimiter() -> None:
    lines = [
        "Journal dump — do not delete this preamble",
        "exported by hand",
        "",
        "date;symbol;side;qty;entry;exit;net_pnl;notes",
        "06.01.2026 09:15;RELIANCE;BUY;10;2.468,50;2.480,00;1.150,00;planned entry",
    ]
    layout = detect_text_layout(lines)
    assert layout.delimiter == ";"
    assert layout.header_index == 3


def test_unknown_headers_are_exposed_as_headerless_columns_for_manual_mapping() -> None:
    layout = detect_text_layout(["foo,bar", "1,2", "3,4"])
    assert layout.header_index == 0
    assert layout.headers == ("foo", "bar")


def test_duplicate_headers_get_numbered_names() -> None:
    assert unique_names(["Price", "Size", "Price"]) == ("Price", "Size", "Price (2)")


def test_zip_that_is_not_a_workbook_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "archive.xlsx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("readme.txt", "hello")
    with pytest.raises(IngestError) as caught:
        detect_kind(path)
    assert caught.value.code == "unsupported_archive"


def test_zip_bomb_is_refused_by_compression_ratio(tmp_path: Path) -> None:
    path = tmp_path / "bomb.xlsx"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("xl/workbook.xml", b"0" * (20 * 1024 * 1024))
    with pytest.raises(IngestError) as caught:
        detect_kind(path)
    assert caught.value.code == "archive_compression_ratio"


def test_json_list_of_objects_becomes_rows(tmp_path: Path) -> None:
    path = tmp_path / "trades.json"
    path.write_text(json.dumps([{"symbol": "AAPL", "qty": 10, "side": "buy"}]), encoding="utf-8")
    rows = load_json_rows(path, "utf-8")
    assert rows == [["symbol", "qty", "side"], ["AAPL", "10", "buy"]]


def test_google_sheets_values_export_becomes_rows(tmp_path: Path) -> None:
    path = tmp_path / "sheet.json"
    payload = {"range": "Sheet1!A1:B2", "values": [["symbol", "qty"], ["AAPL", "10"]]}
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert load_json_rows(path, "utf-8") == [["symbol", "qty"], ["AAPL", "10"]]


def test_json_with_unknown_layout_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"trades": 3}), encoding="utf-8")
    with pytest.raises(IngestError) as caught:
        load_json_rows(path, "utf-8")
    assert caught.value.code == "unsupported_json"


def test_xlsx_round_trip_reads_cached_values(tmp_path: Path) -> None:
    openpyxl = pytest.importorskip("openpyxl")
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.append(["symbol", "side", "qty", "entry_time", "entry_price", "exit_time", "exit_price"])
    sheet.append(["AAPL", "buy", 10, "2026-01-06 14:32:00", 100.5, "2026-01-06 15:00:00", 101.5])
    path = tmp_path / "trades.xlsx"
    workbook.save(path)
    analysis = analyze(path, ImportOptions())
    assert analysis.source.kind == "xlsx"
    assert analysis.shape == "round_trip"
    records = list(analysis.source.iter_records())
    assert records[0][1][0] == "AAPL"
