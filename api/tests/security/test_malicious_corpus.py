"""Malicious-file corpus. Each file is refused or gets a structured error, never a 500."""

from __future__ import annotations

import io
import random
import shutil
import zipfile
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from obsidian_ledger.main import create_app
from obsidian_ledger.settings import Settings

SAFE_CSV = b"Symbol,Side,Qty\nAAPL,long,1\n"


@pytest.fixture(scope="module")
def client(tmp_path_factory: pytest.TempPathFactory) -> TestClient:
    settings = Settings.model_validate(
        {"data_dir": str(tmp_path_factory.mktemp("corpus") / "data"), "max_upload_mb": 50}
    )
    return TestClient(create_app(settings), base_url="http://127.0.0.1")


def _zip(members: dict[str, bytes], compression: int = zipfile.ZIP_DEFLATED) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=compression) as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def _upload(client: TestClient, name: str, content: bytes) -> Any:
    response = client.post(
        "/api/imports/preview",
        params={"filename": name},
        content=content,
        headers={"content-type": "application/octet-stream"},
    )
    assert response.status_code < 500, (name, response.status_code, response.text[:300])
    text = response.text
    assert "Traceback" not in text
    assert "/vercel/" not in text and "site-packages" not in text
    if response.status_code >= 400:
        assert "code" in response.json()["error"]
    return response


def _refused(client: TestClient, name: str, content: bytes, code: str | None = None) -> None:
    response = _upload(client, name, content)
    assert response.status_code in {400, 413, 415, 422}, response.text
    if code is not None:
        assert response.json()["error"]["code"] == code


def test_zip_bomb_is_refused(client: TestClient) -> None:
    bomb = _zip({"xl/workbook.xml": b"<workbook/>", "xl/worksheets/sheet1.xml": b"0" * 120_000_000})
    _refused(client, "bomb.xlsx", bomb, "archive_compression_ratio")


def test_zip_slip_path_is_refused(client: TestClient) -> None:
    _refused(
        client,
        "slip.xlsx",
        _zip({"xl/workbook.xml": b"<workbook/>", "../../evil.sh": b"x"}),
        "archive_path_traversal",
    )


def test_zip_with_too_many_entries_is_refused(client: TestClient) -> None:
    members = {"xl/workbook.xml": b"<workbook/>"}
    members.update({f"xl/pad/{i}.xml": b"<a/>" for i in range(5200)})
    _refused(client, "many.xlsx", _zip(members))


def test_macro_enabled_workbook_is_refused(client: TestClient) -> None:
    _refused(
        client,
        "macro.xlsx",
        _zip({"xl/workbook.xml": b"<workbook/>", "xl/vbaProject.bin": b"\xd0\xcf\x11\xe0"}),
    )


def test_workbook_with_external_links_is_refused(client: TestClient) -> None:
    _refused(
        client,
        "linked.xlsx",
        _zip(
            {
                "xl/workbook.xml": b"<workbook/>",
                "xl/externalLinks/externalLink1.xml": b"<externalLink/>",
            }
        ),
    )


@pytest.mark.parametrize("name", ["fake.xlsx", "fake.xls", "fake.csv", "fake.json", "fake.txt"])
def test_wrong_magic_bytes_are_refused(client: TestClient, name: str) -> None:
    _refused(client, name, b"MZ\x90\x00\x03\x00\x00\x00" + b"\x00" * 64)
    _refused(client, name, b"\x7fELF\x02\x01\x01\x00" + b"\x00" * 64)


def test_unsupported_types_are_refused_by_content_and_extension(client: TestClient) -> None:
    _refused(client, "doc.pdf", b"%PDF-1.7\n" + SAFE_CSV)
    _refused(client, "page.html", b"<html><script>alert(1)</script></html>")
    _refused(client, "archive.zip", _zip({"a.csv": SAFE_CSV}))


def test_polyglot_files_are_refused(client: TestClient) -> None:
    _refused(client, "poly.csv", b"%PDF-1.7\n" + SAFE_CSV)
    _refused(client, "poly2.csv", b"<script>alert(1)</script>\n" + SAFE_CSV)
    _refused(client, "poly3.csv", b"PK\x03\x04" + SAFE_CSV)
    _refused(client, "poly4.xlsx", SAFE_CSV + _zip({"xl/workbook.xml": b"<workbook/>"}))


def test_dde_formula_is_refused(client: TestClient) -> None:
    _refused(client, "dde.csv", b"Symbol,Note\nAAPL,=cmd|' /C calc'!A0\n", "dde_formula")


def test_oversized_rows_and_columns_do_not_crash(client: TestClient) -> None:
    wide = (
        ",".join(f"c{i}" for i in range(5000)) + "\n" + ",".join("1" for _ in range(5000))
    ).encode()
    _upload(client, "wide.csv", wide)
    _upload(client, "longcell.csv", b"Symbol,Note\nAAPL," + b"A" * 5_000_000 + b"\n")


def test_deeply_nested_json_does_not_crash(client: TestClient) -> None:
    _upload(client, "deep.json", b"[" * 200_000 + b"]" * 200_000)
    _upload(client, "deep2.json", b'{"a":' * 50_000 + b"1" + b"}" * 50_000)


def test_json_with_prototype_keys_is_inert(client: TestClient) -> None:
    payload = (
        b'[{"__proto__": {"polluted": true}, "constructor": {"prototype": {"x": 1}}, '
        b'"symbol": "AAPL", "side": "long", "qty": 1}]'
    )
    _upload(client, "proto.json", payload)
    assert client.get("/health").status_code == 200


@pytest.mark.skipif(
    shutil.which("clamdscan") is None and shutil.which("clamscan") is None,
    reason="EICAR needs an installed scanner (ClamAV).",
)
def test_eicar_is_refused_when_a_scanner_is_present(tmp_path: Path) -> None:
    settings = Settings.model_validate({"data_dir": str(tmp_path / "data"), "scanner": "clamd"})
    scanning = TestClient(create_app(settings), base_url="http://127.0.0.1")
    eicar = rb"X5O!P%@AP[4\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
    _refused(scanning, "eicar.csv", b"Symbol,Note\nAAPL," + eicar + b"\n")


def test_random_bytes_never_raise_an_unhandled_exception(client: TestClient) -> None:
    rng = random.Random(1234)
    names = ["a.csv", "a.tsv", "a.txt", "a.json", "a.xlsx", "a.xls"]
    for index in range(36):
        blob = rng.randbytes(rng.randint(0, 4096))
        _upload(client, names[index % len(names)], blob)


def test_mutated_valid_files_never_raise_an_unhandled_exception(client: TestClient) -> None:
    rng = random.Random(99)
    base = bytearray(b"Symbol,Side,Qty,Entry Time\nAAPL,long,1,2026-01-01 10:00\n" * 20)
    for _ in range(20):
        mutated = bytearray(base)
        for _ in range(rng.randint(1, 30)):
            mutated[rng.randrange(len(mutated))] = rng.randrange(256)
        _upload(client, "mutated.csv", bytes(mutated))
    assert client.get("/health").status_code == 200
