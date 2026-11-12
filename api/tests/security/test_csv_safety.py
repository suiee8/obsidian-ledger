"""CSV formula-injection tests.

Every cell whose text starts with =, +, -, @, tab, or carriage return gets a leading single quote
when written to CSV. JSON numeric values stay numeric; risky numeric-looking CSV text is quoted.
"""

from __future__ import annotations

import csv
import io
import zipfile
from pathlib import Path

import polars as pl
import pytest
from fastapi.testclient import TestClient

from obsidian_ledger.coach.export import to_csv as report_to_csv
from obsidian_ledger.csvsafe import neutralize_cell, neutralize_csv, neutralize_frame
from obsidian_ledger.ingest.export import rejected_csv
from obsidian_ledger.ingest.trade import Reason, Rejected
from obsidian_ledger.main import create_app
from obsidian_ledger.settings import Settings

MT5_SAMPLE_CSV = Path(__file__).resolve().parents[3] / "samples" / "mt5_statement.csv"


@pytest.mark.parametrize("prefix", ["=", "+", "-", "@", "\t", "\r"])
def test_each_prefix_is_neutralized(prefix: str) -> None:
    cell = f"{prefix}cmd|'/c calc'!A0"
    neutralized = neutralize_cell(cell)
    assert neutralized.startswith("'"), f"Prefix {prefix!r} was not neutralized: {neutralized!r}"
    assert neutralized == f"'{cell}"


@pytest.mark.parametrize("prefix", ["=", "+", "-", "@", "\t", "\r"])
def test_leading_space_before_prefix_is_neutralized(prefix: str) -> None:
    cell = f'   {prefix}DDE("cmd";"calc")'
    neutralized = neutralize_cell(cell)
    assert neutralized == f"'{cell}", f"Leading space before {prefix!r} was not neutralized"


def test_bare_risky_characters_are_neutralized() -> None:
    for ch in ("=", "+", "-", "@", "\t", "\r"):
        assert neutralize_cell(ch) == f"'{ch}"


def test_risky_signed_numeric_strings_are_neutralized() -> None:
    risky_numbers = [
        "-0.70",
        " -0.70 ",
        "-42",
        "-1234.56",
        "+100",
        " +100 ",
        "+0.05",
    ]
    for num in risky_numbers:
        assert neutralize_cell(num) == "'" + num

    safe_numbers = [
        "123",
        " 123 ",
        "0",
        "0.0",
        "1,000.50",
        "1e-5",
    ]
    for num in safe_numbers:
        assert neutralize_cell(num) == num, f"Valid number {num!r} was unexpectedly altered"


def test_csv_serialization_neutralizes_negative_numeric_values() -> None:
    serialized = neutralize_csv("net_pnl\n-0.70\n")
    assert serialized == "net_pnl\n'-0.70\n"


def test_negative_number_with_text_is_neutralized() -> None:
    assert neutralize_cell("-0.70%").startswith("'")
    assert neutralize_cell("-calc").startswith("'")
    assert neutralize_cell(" -2+3*cmd ").startswith("'")


def test_safe_strings_remain_unchanged() -> None:
    safe_strings = [
        "AAPL",
        "EURUSD",
        "Long breakout",
        "Win",
        "Normal note without formula",
        "   hello world",
        "",
        "   ",
    ]
    for s in safe_strings:
        assert neutralize_cell(s) == s


def test_non_string_values_remain_unchanged() -> None:
    assert neutralize_cell(123) == 123
    assert neutralize_cell(-0.70) == -0.70
    assert neutralize_cell(None) is None
    assert neutralize_cell(True) is True


def test_neutralize_frame_handles_all_prefixes_and_numbers() -> None:
    raw_col = [
        "=SUM(A1:B10)",
        "+cmd",
        "-calc",
        "@SUM(1,2)",
        "\talert(1)",
        "\rformat",
        "   =1+1",
        "   @SUM",
        "   \ttab",
        "   \rcarriage",
        "-0.70",
        " -0.70 ",
        "+100",
        "123",
        "AAPL",
        None,
    ]
    numeric_col = [
        -0.70,
        100.0,
        -42.5,
        0.0,
        1.23,
        4.56,
        7.89,
        0.1,
        0.2,
        0.3,
        -5.0,
        -10.0,
        20.0,
        30.0,
        40.0,
        None,
    ]
    df = pl.DataFrame(
        {
            "notes": raw_col,
            "net_pnl": numeric_col,
        }
    )

    neutralized = neutralize_frame(df)

    # Text column was neutralized
    notes_out = neutralized["notes"].to_list()
    assert notes_out[0] == "'=SUM(A1:B10)"
    assert notes_out[1] == "'+cmd"
    assert notes_out[2] == "'-calc"
    assert notes_out[3] == "'@SUM(1,2)"
    assert notes_out[4] == "'\talert(1)"
    assert notes_out[5] == "'\rformat"
    assert notes_out[6] == "'   =1+1"
    assert notes_out[7] == "'   @SUM"
    assert notes_out[8] == "'   \ttab"
    assert notes_out[9] == "'   \rcarriage"
    assert notes_out[10] == "'-0.70"
    assert notes_out[11] == "' -0.70 "
    assert notes_out[12] == "'+100"
    assert notes_out[13] == "123"
    assert notes_out[14] == "AAPL"
    assert notes_out[15] is None

    # Numeric column remains unchanged
    assert neutralized["net_pnl"].to_list() == numeric_col


def test_rejected_csv_neutralizes_headers_and_cells() -> None:
    headers = ["=header1", "@header2", "normal_header"]
    rejected = [
        Rejected(
            source_row=2,
            cells=["=cmd", "-0.70", "\ttab_cell", "AAPL"],
            reasons=[Reason(code="+risk_code", message="@risk_message")],
        )
    ]
    csv_bytes = rejected_csv(headers, rejected)
    csv_text = csv_bytes.decode("utf-8")

    assert "'=header1" in csv_text
    assert "'@header2" in csv_text
    assert "'=cmd" in csv_text
    assert "'-0.70" in csv_text
    assert "'\ttab_cell" in csv_text
    assert "'+risk_code" in csv_text
    assert "'@risk_message" in csv_text


def test_coach_report_csv_export_neutralizes_cells(tmp_path: Path) -> None:
    app = create_app(Settings(data_dir=tmp_path))
    client = TestClient(app)

    # Ingest sample trades to produce a real coach report
    sample_file = MT5_SAMPLE_CSV.read_bytes()
    preview = client.post(
        "/api/imports/preview",
        params={"filename": "mt5_statement.csv"},
        content=sample_file,
    ).json()
    commit = client.post(f"/api/imports/{preview['preview_id']}/commit", json={})
    assert commit.status_code == 200

    report_resp = client.post("/api/coach/report", json={})
    assert report_resp.status_code == 200
    report_data = report_resp.json()
    report_id = report_data["report_id"]

    # Export as CSV through HTTP endpoint
    csv_resp = client.get(f"/api/coach/reports/{report_id}/export", params={"format": "csv"})
    assert csv_resp.status_code == 200
    assert csv_resp.headers["content-type"].startswith("text/csv")
    csv_text = csv_resp.text

    # Header and fields exist
    assert (
        "section,title,confidence,trades_count,mean_value,effect_value,rule,description" in csv_text
    )

    # Test that a formula injection in a report model is neutralized by report_to_csv
    coach_report = app.state.coach.stored(report_id)
    assert coach_report is not None
    if coach_report.top_leaks:
        malicious_leak = coach_report.top_leaks[0].model_copy(update={"title": "=cmd|'calc'!A0"})
        malicious_report = coach_report.model_copy(update={"top_leaks": [malicious_leak]})
        serialized = report_to_csv(malicious_report)
        assert "'=cmd|'calc'!A0" in serialized


def test_numeric_json_values_stay_numeric_in_api(tmp_path: Path) -> None:
    app = create_app(Settings(data_dir=tmp_path))
    client = TestClient(app)

    # Ingest MT5 statement with known trades and negative commission/profits
    sample_file = MT5_SAMPLE_CSV.read_bytes()
    preview = client.post(
        "/api/imports/preview",
        params={"filename": "mt5_statement.csv"},
        content=sample_file,
    ).json()
    assert "preview_id" in preview
    commit = client.post(
        f"/api/imports/{preview['preview_id']}/commit",
        json={},
    )
    assert commit.status_code == 200

    # Query dashboard - all numbers are numeric types in JSON
    dash_resp = client.get("/api/dashboard")
    assert dash_resp.status_code == 200
    dash_data = dash_resp.json()

    # Numbers in JSON remain floats/ints, not strings or quoted
    assert isinstance(dash_data["report"]["sample"]["trades"], int)
    assert dash_data["report"]["sample"]["trades"] > 0
    assert isinstance(dash_data["report"]["core"]["net_pnl"], float)
    assert isinstance(dash_data["report"]["core"]["profit_factor"], (float, int, type(None)))

    # Test trades page endpoint
    trades_resp = client.get("/api/trades/page")
    assert trades_resp.status_code == 200
    trades_data = trades_resp.json()
    assert trades_data["total"] > 0
    row = trades_data["rows"][0]
    assert isinstance(row["net_pnl"], float)
    assert isinstance(row["commission"], float)
    assert row["commission"] < 0  # e.g. -0.70 negative number stays numeric float in JSON
    assert isinstance(row["qty"], (int, float))

    trade_export = client.get("/api/trades/export")
    assert trade_export.status_code == 200
    trade_export_rows = list(csv.DictReader(io.StringIO(trade_export.text)))
    assert any(row["commission"].startswith("'-") for row in trade_export_rows)

    # Test segments endpoint
    seg_resp = client.get("/api/segments", params={"by": "symbol"})
    assert seg_resp.status_code == 200
    seg_data = seg_resp.json()
    assert "slices" in seg_data
    assert isinstance(seg_data["slices"], list)
    if seg_data["slices"]:
        seg = seg_data["slices"][0]
        assert isinstance(seg["n"], int)
        assert isinstance(seg["net_pnl"], (float, int))

    segment_export = client.get(
        "/api/segments/export",
        params={"by": "symbol", "min_n": 1},
    )
    assert segment_export.status_code == 200
    segment_rows = list(csv.DictReader(io.StringIO(segment_export.text)))
    assert any(row["net_pnl"].startswith("'-") for row in segment_rows)

    zip_export = client.get("/api/export")
    assert zip_export.status_code == 200
    with zipfile.ZipFile(io.BytesIO(zip_export.content)) as archive:
        zip_trade_rows = list(
            csv.DictReader(io.StringIO(archive.read("trades.csv").decode("utf-8")))
        )
    assert any(row["commission"].startswith("'-") for row in zip_trade_rows)

    # Query metrics and dashboard - all numbers are numeric types in JSON
    dash_resp = client.get("/api/dashboard")
    assert dash_resp.status_code == 200
    dash_data = dash_resp.json()

    # Numbers in JSON remain floats/ints, not strings or quoted
    assert isinstance(dash_data["report"]["sample"]["trades"], int)
    assert isinstance(dash_data["report"]["core"]["net_pnl"], float)

    # Test trades page endpoint
    trades_resp = client.get("/api/trades/page")
    assert trades_resp.status_code == 200
    trades_data = trades_resp.json()
    assert trades_data["total"] == 5
    assert dash_data["report"]["core"]["net_pnl"] == pytest.approx(
        sum(trade["net_pnl"] for trade in trades_data["rows"])
    )
    row = trades_data["rows"][0]
    assert isinstance(row["net_pnl"], float)
    assert any(trade["commission"] == -0.70 for trade in trades_data["rows"])
    assert isinstance(row["qty"], (int, float))

    # Test segments endpoint
    seg_resp = client.get("/api/segments", params={"by": "symbol"})
    assert seg_resp.status_code == 200
    seg_data = seg_resp.json()
    assert "slices" in seg_data
    assert isinstance(seg_data["slices"], list)
