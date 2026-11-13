"""Upload safety unit tests: size limits, zip bombs, path traversal, extension mismatch."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from obsidian_ledger.ingest.errors import IngestError
from obsidian_ledger.ingest.fileio import validate_extension_and_content
from obsidian_ledger.main import create_app
from obsidian_ledger.settings import Settings


def test_file_size_limit_rejection(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, max_upload_mb=1)
    app = create_app(settings)
    client = TestClient(app, base_url="http://127.0.0.1")

    response = client.post(
        "/api/imports/preview",
        params={"filename": "oversized.csv"},
        content=b"x" * (2 * 1024 * 1024),
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "too_large"


def test_zip_bomb_compression_ratio_rejected(tmp_path: Path) -> None:
    path = tmp_path / "bomb_ratio.xlsx"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("xl/workbook.xml", b"0" * (20 * 1024 * 1024))

    with pytest.raises(IngestError) as exc_info:
        validate_extension_and_content(path, path.name)
    assert exc_info.value.code == "archive_compression_ratio"


def test_zip_bomb_too_many_members_rejected(tmp_path: Path) -> None:
    path = tmp_path / "bomb_members.xlsx"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
        for i in range(5001):
            archive.writestr(f"file_{i}.txt", b"x")

    with pytest.raises(IngestError) as exc_info:
        validate_extension_and_content(path, path.name)
    assert exc_info.value.code == "archive_too_many_members"


def test_archive_path_traversal_rejected(tmp_path: Path) -> None:
    path = tmp_path / "traversal.xlsx"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("xl/workbook.xml", b"<workbook/>")
        archive.writestr("../evil.txt", b"malicious content")

    with pytest.raises(IngestError) as exc_info:
        validate_extension_and_content(path, path.name)
    assert exc_info.value.code == "archive_path_traversal"


def test_archive_absolute_path_traversal_rejected(tmp_path: Path) -> None:
    path = tmp_path / "abs_traversal.xlsx"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("xl/workbook.xml", b"<workbook/>")
        archive.writestr("/etc/passwd", b"root:x:0:0")

    with pytest.raises(IngestError) as exc_info:
        validate_extension_and_content(path, path.name)
    assert exc_info.value.code == "archive_path_traversal"


def test_archive_windows_path_traversal_rejected(tmp_path: Path) -> None:
    path = tmp_path / "win_traversal.xlsx"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("xl/workbook.xml", b"<workbook/>")
        archive.writestr("\\windows\\system32\\cmd.exe", b"malicious")

    with pytest.raises(IngestError) as exc_info:
        validate_extension_and_content(path, path.name)
    assert exc_info.value.code == "archive_path_traversal"


def test_unsupported_extension_rejected(tmp_path: Path) -> None:
    path = tmp_path / "script.py"
    path.write_text("print('hello')", encoding="utf-8")
    with pytest.raises(IngestError) as exc_info:
        validate_extension_and_content(path, "script.py")
    assert exc_info.value.code == "unsupported_extension"

    exe_path = tmp_path / "evil.exe"
    exe_path.write_bytes(b"MZ\x90\x00")
    with pytest.raises(IngestError) as exc_info:
        validate_extension_and_content(exe_path, "evil.exe")
    assert exc_info.value.code == "unsupported_extension"


def test_xlsx_extension_with_text_content_rejected(tmp_path: Path) -> None:
    path = tmp_path / "fake.xlsx"
    path.write_text("date,symbol,price\n2026-01-01,AAPL,150", encoding="utf-8")
    with pytest.raises(IngestError) as exc_info:
        validate_extension_and_content(path, "fake.xlsx")
    assert exc_info.value.code == "extension_mismatch"


def test_xls_extension_with_text_content_rejected(tmp_path: Path) -> None:
    path = tmp_path / "fake.xls"
    path.write_text("date,symbol,price\n2026-01-01,AAPL,150", encoding="utf-8")
    with pytest.raises(IngestError) as exc_info:
        validate_extension_and_content(path, "fake.xls")
    assert exc_info.value.code == "extension_mismatch"


def test_csv_extension_with_binary_content_rejected(tmp_path: Path) -> None:
    path = tmp_path / "binary.csv"
    path.write_bytes(b"\x7fELF\x02\x01\x01\x00" + b"\x00" * 100)
    with pytest.raises(IngestError) as exc_info:
        validate_extension_and_content(path, "binary.csv")
    assert exc_info.value.code == "extension_mismatch"

    pe_path = tmp_path / "pe.csv"
    pe_path.write_bytes(b"MZ\x90\x00\x03\x00\x00\x00")
    with pytest.raises(IngestError) as exc_info:
        validate_extension_and_content(pe_path, "pe.csv")
    assert exc_info.value.code == "extension_mismatch"


def test_csv_extension_with_json_content_rejected(tmp_path: Path) -> None:
    path = tmp_path / "trades_json.csv"
    path.write_text('[{"symbol": "AAPL", "pnl": 100.0}]', encoding="utf-8")
    with pytest.raises(IngestError) as exc_info:
        validate_extension_and_content(path, "trades_json.csv")
    assert exc_info.value.code == "extension_mismatch"


def test_json_extension_with_csv_content_rejected(tmp_path: Path) -> None:
    path = tmp_path / "trades_csv.json"
    path.write_text("date,symbol,price\n2026-01-01,AAPL,150", encoding="utf-8")
    with pytest.raises(IngestError) as exc_info:
        validate_extension_and_content(path, "trades_csv.json")
    assert exc_info.value.code == "extension_mismatch"


def test_upload_preview_api_rejects_mismatched_extension(tmp_path: Path) -> None:
    app = create_app(Settings(data_dir=tmp_path))
    client = TestClient(app, base_url="http://127.0.0.1")

    response = client.post(
        "/api/imports/preview",
        params={"filename": "fake.xlsx"},
        content=b"symbol,pnl\nAAPL,100",
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "extension_mismatch"
