"""HTTP flows: preview, commit, re-import, blocking questions, downloads, and upload guards."""

import io
import zipfile
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from obsidian_ledger.main import create_app
from obsidian_ledger.settings import Settings

SAMPLES = Path(__file__).resolve().parents[3] / "samples"


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    settings = Settings.model_validate({"data_dir": str(tmp_path / "data"), "max_upload_mb": 1})
    return TestClient(create_app(settings))


def _preview(client: TestClient, name: str, content: bytes | None = None) -> dict[str, Any]:
    body = content if content is not None else (SAMPLES / name).read_bytes()
    response = client.post(
        "/api/imports/preview",
        params={"filename": name},
        content=body,
        headers={"content-type": "application/octet-stream"},
    )
    assert response.status_code == 200, response.text
    return dict(response.json())


def _commit(client: TestClient, preview_id: str, **options: Any) -> Any:
    return client.post(f"/api/imports/{preview_id}/commit", json=options)


def test_preview_reports_layout_mapping_and_no_questions_for_ibkr(client: TestClient) -> None:
    preview = _preview(client, "ibkr_executions.csv")
    assert preview["adapter"] == "ibkr"
    assert preview["shape"] == "executions"
    assert preview["questions"] == []
    assert preview["encoding"] in {"ascii", "utf_8", "utf-8"}
    mapped = {column["header"]: column["field"] for column in preview["columns"] if column["field"]}
    assert mapped["Buy/Sell"] == "side"
    assert len(preview["sample_rows"]) == 5


def test_commit_then_reimport_is_idempotent(client: TestClient) -> None:
    preview = _preview(client, "ibkr_executions.csv")
    first = _commit(client, preview["preview_id"], template_name="IBKR export")
    assert first.status_code == 200, first.text
    body = first.json()
    assert (body["accepted"], body["inserted"], body["already_present"]) == (4, 4, 0)

    second = _commit(client, _preview(client, "ibkr_executions.csv")["preview_id"])
    assert second.json()["inserted"] == 0
    assert second.json()["already_present"] == 4

    trades = client.get("/api/trades").json()
    assert len(trades) == 4
    assert trades[0]["trade_id"].startswith("90001-90002")
    assert trades[0]["currency"] == "USD"


def test_tradingview_asks_for_symbol_before_import(client: TestClient) -> None:
    preview = _preview(client, "tradingview_trades.csv")
    assert [q["id"] for q in preview["questions"] if q["blocking"]] == ["default_symbol"]
    refused = _commit(client, preview["preview_id"])
    assert refused.status_code == 422
    assert refused.json()["error"]["code"] == "needs_answers"

    preview = _preview(client, "tradingview_trades.csv")
    accepted = _commit(client, preview["preview_id"], default_symbol="BTCUSD")
    assert accepted.status_code == 200
    assert accepted.json()["accepted"] == 4


def test_messy_file_imports_nothing_and_rejected_csv_is_safe(client: TestClient) -> None:
    preview = _preview(client, "messy_journal.csv")
    body = _commit(client, preview["preview_id"]).json()
    assert body["accepted"] == 0
    assert body["rejected"] == 9
    codes = {issue["code"] for issue in body["issues"]}
    assert "missing_exit_time" in codes

    download = client.get(body["rejected_csv_path"])
    assert download.status_code == 200
    assert download.headers["content-type"].startswith("text/csv")
    text = download.text
    assert "source_row,reason_codes,reasons," in text.splitlines()[0]
    assert "'=CMD|" in text  # formula cell neutralized
    assert "Ignore previous instructions" in text  # stored as data, not acted on


def test_user_mapping_overrides_the_guess(client: TestClient) -> None:
    content = (
        b"Zzz,Qty,Dir,When,Px in,Px out,Done,Net\n"
        b"AAPL,10,long,2026-01-06 10:00,100,101,2026-01-06 11:00,10\n"
    )
    preview = _preview(client, "custom.csv", content)
    question_ids = {q["id"] for q in preview["questions"] if q["blocking"]}
    # Nothing is recognised as a time column, so the shape is unknown until the mapping is given.
    assert {"default_symbol", "shape"} <= question_ids
    refused = _commit(client, preview["preview_id"])
    assert refused.status_code == 422
    body = _commit(
        client,
        preview["preview_id"],
        mapping={
            "Zzz": "symbol",
            "Qty": "qty",
            "Dir": "side",
            "When": "entry_time",
            "Px in": "entry_price",
            "Px out": "exit_price",
            "Done": "exit_time",
            "Net": "net_pnl",
        },
    ).json()
    assert body["accepted"] == 1


def test_unrecognised_side_column_asks_which_column_holds_direction(client: TestClient) -> None:
    content = (
        b"trade_id,symbol,Dir,entry_time,exit_time,qty,entry_price,exit_price,net_pnl\n"
        b"1,AAPL,long,2026-01-06T10:00:00Z,2026-01-06T11:00:00Z,10,100,101,10\n"
    )
    preview = _preview(client, "side.csv", content)
    side = [q for q in preview["questions"] if q["id"] == "side"]
    assert len(side) == 1 and side[0]["blocking"] is True
    assert "Dir" in side[0]["options"]


def test_saved_template_is_applied_to_the_same_headers_next_time(client: TestClient) -> None:
    content = (
        b"Zzz,Qty,Dir,When,Px in,Px out,Done,Net\n"
        b"AAPL,10,long,2026-01-06 10:00,100,101,2026-01-06 11:00,10\n"
    )
    mapping = {
        "Zzz": "symbol",
        "Qty": "qty",
        "Dir": "side",
        "When": "entry_time",
        "Px in": "entry_price",
        "Px out": "exit_price",
        "Done": "exit_time",
        "Net": "net_pnl",
    }
    first = _preview(client, "custom.csv", content)
    assert (
        _commit(
            client, first["preview_id"], mapping=mapping, template_name="Custom broker"
        ).status_code
        == 200
    )

    second = _preview(client, "custom.csv", content)
    sources = {column["header"]: column["source"] for column in second["columns"]}
    assert sources["Zzz"] == "template"
    fields = {column["header"]: column["field"] for column in second["columns"]}
    assert fields["Net"] == "net_pnl"
    assert [q for q in second["questions"] if q["blocking"]] == []
    templates = client.get("/api/templates").json()
    assert [template["name"] for template in templates] == ["Custom broker"]


def test_oversized_upload_is_refused_with_413(client: TestClient) -> None:
    response = client.post(
        "/api/imports/preview",
        params={"filename": "big.csv"},
        content=b"x" * (2 * 1024 * 1024),
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "too_large"


def test_zip_bomb_is_refused(client: TestClient) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("xl/workbook.xml", b"0" * (20 * 1024 * 1024))
    response = client.post(
        "/api/imports/preview", params={"filename": "bomb.xlsx"}, content=buffer.getvalue()
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "archive_compression_ratio"


def test_empty_upload_is_refused(client: TestClient) -> None:
    response = client.post("/api/imports/preview", params={"filename": "empty.csv"}, content=b"")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "empty_file"


def test_bad_ids_are_rejected_before_touching_disk(client: TestClient) -> None:
    assert client.post("/api/imports/../../etc/commit", json={}).status_code in {404, 422}
    assert client.get("/api/imports/not-a-real-id").status_code == 422
    assert client.get("/api/imports/0123456789abcdef0123456789abcdef").status_code == 404


def test_unknown_option_fields_are_refused(client: TestClient) -> None:
    preview = _preview(client, "ibkr_executions.csv")
    response = _commit(client, preview["preview_id"], surprise=True)
    assert response.status_code == 422


def test_preview_expires_after_commit(client: TestClient) -> None:
    preview = _preview(client, "ibkr_executions.csv")
    assert _commit(client, preview["preview_id"]).status_code == 200
    assert _commit(client, preview["preview_id"]).status_code == 404
