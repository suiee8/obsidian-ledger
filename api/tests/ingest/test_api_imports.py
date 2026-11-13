"""HTTP flows: preview, commit, re-import, blocking questions, downloads, and upload guards."""

import csv
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
    return TestClient(create_app(settings), base_url="http://127.0.0.1")


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


def test_content_inference_maps_unknown_columns_and_user_can_override(
    client: TestClient,
) -> None:
    content = (
        b"Zzz,Qty,Dir,When,Px in,Px out,Done,Net\n"
        b"AAPL,10,long,2026-01-06 10:00,100,101,2026-01-06 11:00,10\n"
    )
    preview = _preview(client, "custom.csv", content)
    question_ids = {q["id"] for q in preview["questions"] if q["blocking"]}
    assert question_ids == {"default_symbol"}
    assert preview["shape"] == "round_trip"
    inferred = {column["header"]: column["field"] for column in preview["columns"]}
    assert inferred["When"] == "entry_time"
    assert inferred["Dir"] == "side"
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


def test_content_inference_recognizes_direction_in_unfamiliar_side_column(
    client: TestClient,
) -> None:
    content = (
        b"trade_id,symbol,Dir,entry_time,exit_time,qty,entry_price,exit_price,net_pnl\n"
        b"1,AAPL,long,2026-01-06T10:00:00Z,2026-01-06T11:00:00Z,10,100,101,10\n"
    )
    preview = _preview(client, "side.csv", content)
    inferred = {column["header"]: column["field"] for column in preview["columns"]}
    assert inferred["Dir"] == "side"
    assert not any(question["id"] == "side" for question in preview["questions"])


def test_missing_cost_components_make_fee_drag_unavailable_not_zero(client: TestClient) -> None:
    preview = _preview(
        client,
        "pnl_without_costs.csv",
        b"symbol,side,entry_time,exit_time,qty,net_pnl\n"
        b"AAPL,long,2026-01-06T10:00:00Z,2026-01-06T11:00:00Z,1,10\n",
    )
    result = _commit(client, preview["preview_id"])
    assert result.status_code == 200, result.text

    explore = client.get("/api/explore").json()
    assert explore["fee_drag"]["costs"] is None
    assert explore["fee_drag"]["gross"] is None
    assert explore["fee_drag"]["drag"] is None
    assert explore["fee_drag"]["by_symbol"] == []
    assert "Not available" in explore["fee_drag"]["rule"]


def test_user_confirmed_symbol_alias_is_applied_to_imported_trade(client: TestClient) -> None:
    preview = _preview(
        client,
        "truncated_symbol.csv",
        b"Symbol,Side,Entry Time,Exit Time,Quantity,Net P&L\n"
        b"FARTCOINU,long,2026-01-06T10:00:00Z,2026-01-06T11:00:00Z,1,10\n",
    )
    result = _commit(
        client,
        preview["preview_id"],
        symbol_aliases={"FARTCOINU": "FARTCOIN"},
    )
    assert result.status_code == 200, result.text
    trades = client.get("/api/trades").json()
    assert len(trades) == 1
    assert trades[0]["symbol"] == "FARTCOIN"


def test_mexc_content_import_keeps_nullable_values_and_all_order_events(client: TestClient) -> None:
    preview = _preview(client, "mexc_futures_order_history_normalized.csv")
    assert preview["header_record"] == 1
    assert preview["rows_profiled"] == 944
    assert preview["symbol_count"] == 142
    assert preview["duplicate_rows"] == 3
    assert preview["capabilities"]["has_pnl"] is False
    assert preview["capabilities"]["has_price"] is False
    assert {"hour_precision", "truncated_symbols", "duplicates"} <= set(preview["warnings"])
    assert {column["header"]: column["field"] for column in preview["columns"]}[
        "Filled Quantity"
    ] == "qty"
    assert {column["header"]: column["field"] for column in preview["columns"]}[
        "Order Value"
    ] == "notional"

    result = _commit(client, preview["preview_id"]).json()
    assert result["rows_total"] == 944
    assert result["rejected"] == 0
    assert result["duplicates_in_file"] == 3
    assert result["activity_events"] == 944
    assert result["quantity_conserved"] is True

    trades = client.get("/api/trades", params={"limit": 1000}).json()
    assert trades
    assert len({trade["trade_key"] for trade in trades}) == len(trades)
    assert all(trade["net_pnl"] is None for trade in trades)
    assert all(trade["entry_price"] is None and trade["exit_price"] is None for trade in trades)
    assert all(trade["fees"] is None for trade in trades)
    assert all(
        trade["holding_seconds"] is None or trade["holding_seconds"] >= 0 for trade in trades
    )
    availability = client.get("/api/availability").json()
    assert availability["available"] is False
    assert availability["has_pnl"] is False
    assert availability["has_prices"] is False
    assert availability["activity"]["source_events"] == 944
    assert availability["activity"]["symbols"] == 142
    assert availability["activity"]["hold_times_available"] is True
    metrics = client.get("/api/metrics").json()
    assert metrics["sample"]["trades"] == len(trades)
    assert metrics["core"]["net_pnl"] is None
    assert metrics["risk"]["drawdown"]["max_drawdown"] is None
    coach = client.post("/api/coach/report", json={}).json()
    assert coach["verdict"]["label"] == "cannot_be_assessed"
    assert coach["verdict"]["headline"] == "Cannot be assessed"
    assert coach["sample_trades"]["value"] == len(trades)


@pytest.mark.parametrize(
    "filename",
    [
        "binance_futures_eu.csv",
        "bybit_closed_pnl.csv",
        "zerodha_separate_date_time.csv",
        "mt4_open_close_times.csv",
        "preamble_totals.xlsx",
        "epoch_millisecond_times.csv",
        "date_only_trades.csv",
        "spanish_closed_trades.csv",
    ],
)
def test_synthetic_import_formats_are_readable(filename: str, client: TestClient) -> None:
    preview = _preview(client, filename)
    assert preview["shape"] in {"orders", "round_trip"}
    assert not [question for question in preview["questions"] if question["blocking"]]
    result = _commit(client, preview["preview_id"]).json()
    expected_rows = 4 if filename == "binance_futures_eu.csv" else 2
    assert result["rows_total"] == expected_rows
    assert result["accepted"] == 2
    assert result["rejected"] == 0


def test_headerless_file_requires_and_accepts_explicit_mapping(client: TestClient) -> None:
    preview = _preview(client, "headerless_trades.csv")
    blocking = {question["id"] for question in preview["questions"] if question["blocking"]}
    assert {"mapping_ambiguity", "mapping"} <= blocking
    result = _commit(
        client,
        preview["preview_id"],
        mapping={
            "Column 1": "symbol",
            "Column 2": "side",
            "Column 3": "qty",
            "Column 4": "entry_time",
            "Column 5": "exit_time",
            "Column 6": "entry_price",
            "Column 7": "exit_price",
            "Column 8": "net_pnl",
            "Column 9": None,
        },
    )
    assert result.status_code == 200, result.text
    assert result.json()["accepted"] == 2
    assert result.json()["rejected"] == 0


@pytest.mark.parametrize(
    "filename",
    [
        "mexc_futures_order_history_normalized.csv",
        "binance_futures_eu.csv",
        "bybit_closed_pnl.csv",
        "zerodha_separate_date_time.csv",
        "mt4_open_close_times.csv",
        "preamble_totals.xlsx",
        "epoch_millisecond_times.csv",
        "date_only_trades.csv",
        "headerless_trades.csv",
        "spanish_closed_trades.csv",
    ],
)
def test_renamed_columns_are_equal_or_raise_mapping_questions(
    filename: str, client: TestClient
) -> None:
    source = SAMPLES / filename
    original = _preview(client, filename)
    if [question for question in original["questions"] if question["blocking"]]:
        assert filename == "headerless_trades.csv"
        return
    original_result = _commit(client, original["preview_id"])
    assert original_result.status_code == 200, original_result.text
    original_rows = client.get("/api/trades", params={"limit": 1000}).json()
    canonical_fields = (
        "symbol",
        "side",
        "qty",
        "entry_time",
        "exit_time",
        "entry_price",
        "exit_price",
        "gross_pnl",
        "net_pnl",
        "fees",
    )
    original_canonical = sorted(
        tuple(row[field] for field in canonical_fields) for row in original_rows
    )

    if source.suffix == ".xlsx":
        from openpyxl import Workbook, load_workbook

        workbook = load_workbook(source)
        sheet = workbook.active
        assert sheet is not None
        header_row = next(
            row for row in range(1, sheet.max_row + 1) if sheet.cell(row, 1).value == "Symbol"
        )
        columns = list(range(1, sheet.max_column + 1))
        order = list(reversed(columns))
        reordered = [
            [sheet.cell(row, column).value for column in order]
            for row in range(1, sheet.max_row + 1)
        ]
        renamed_workbook = Workbook()
        renamed_sheet = renamed_workbook.active
        assert renamed_sheet is not None
        for row_index, values in enumerate(reordered, start=1):
            renamed_sheet.append(
                [f"col{column_index}" for column_index in range(1, len(values) + 1)]
                if row_index == header_row
                else values
            )
        output = io.BytesIO()
        renamed_workbook.save(output)
        renamed = output.getvalue()
    else:
        delimiter = original["delimiter"]
        rows = list(
            csv.reader(io.StringIO(source.read_text(encoding="utf-8-sig")), delimiter=delimiter)
        )
        order = list(reversed(range(len(rows[0]))))
        renamed_rows = [
            [f"col{index + 1}" for index in range(len(order))],
            *[[row[index] for index in order] for row in rows[1:]],
        ]
        output = io.StringIO()
        csv.writer(output, delimiter=delimiter, lineterminator="\n").writerows(renamed_rows)
        renamed = output.getvalue().encode("utf-8")

    renamed_preview = _preview(client, filename, renamed)
    blockers = [question for question in renamed_preview["questions"] if question["blocking"]]
    if blockers:
        assert any(
            question["id"] in {"mapping", "mapping_ambiguity", "shape", "side_mode"}
            for question in blockers
        )
        return
    result = _commit(client, renamed_preview["preview_id"])
    assert result.status_code == 200, result.text
    renamed_rows = client.get("/api/trades", params={"limit": 1000}).json()
    renamed_canonical = sorted(
        tuple(row[field] for field in canonical_fields)
        for row in renamed_rows
        if row["import_id"] == result.json()["import_id"]
    )
    assert renamed_canonical == original_canonical


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
