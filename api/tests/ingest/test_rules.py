"""Validation rules, each checked with a small file written for the test."""

from pathlib import Path

import pytest

from obsidian_ledger.ingest.analysis import analyze
from obsidian_ledger.ingest.export import neutralize_cell, rejected_csv
from obsidian_ledger.ingest.options import ImportOptions
from obsidian_ledger.ingest.run import RunOutcome, run_import

HEADER = (
    "trade_id,symbol,side,entry_time,exit_time,qty,entry_price,exit_price,"
    "fees,net_pnl,planned_risk,r_multiple"
)


def _csv(tmp_path: Path, *rows: str, header: str = HEADER) -> Path:
    path = tmp_path / "journal.csv"
    path.write_text("\n".join([header, *rows]) + "\n", encoding="utf-8")
    return path


def _run(path: Path, **options: object) -> RunOutcome:
    opts = ImportOptions.model_validate(options)
    analysis = analyze(path, opts)
    assert not analysis.blocking, [q.id for q in analysis.blocking]
    return run_import(analysis, opts)


def _codes(outcome: RunOutcome, row: int) -> set[str]:
    for rejected in outcome.rejected:
        if rejected.source_row == row:
            return {reason.code for reason in rejected.reasons}
    return set()


def test_exit_before_entry_is_rejected_as_negative_duration(tmp_path: Path) -> None:
    path = _csv(
        tmp_path, "1,TCS,long,2026-01-05T15:00:00Z,2026-01-05T14:00:00Z,5,4100,4050,-1,250,,"
    )
    outcome = _run(path)
    assert outcome.trades == []
    assert _codes(outcome, 2) == {"negative_duration"}


def test_fees_are_stored_as_costs_even_when_the_file_writes_them_positive(tmp_path: Path) -> None:
    path = _csv(
        tmp_path, "1,BTCUSD,long,2026-01-06T10:00:00Z,2026-01-06T11:00:00Z,1,100,101,1.00,99,,"
    )
    outcome = _run(path)
    trade = outcome.trades[0]
    assert trade.fees == pytest.approx(-1.0)
    # Net 99 is after the 1.00 fee, so gross must be 100.
    assert trade.gross_pnl == pytest.approx(100.0)


def test_net_only_rows_are_accepted_without_prices(tmp_path: Path) -> None:
    path = _csv(tmp_path, "1,ETHUSD,short,2026-01-06T10:00:00Z,2026-01-06T11:00:00Z,2,,,,-40,,")
    outcome = _run(path)
    assert outcome.rejected == []
    assert outcome.trades[0].net_pnl == pytest.approx(-40.0)


def test_row_with_no_pnl_and_no_prices_keeps_financial_values_unknown(tmp_path: Path) -> None:
    path = _csv(tmp_path, "1,ETHUSD,long,2026-01-06T10:00:00Z,2026-01-06T11:00:00Z,2,,,,,,")
    outcome = _run(path)
    assert outcome.rejected == []
    assert len(outcome.trades) == 1
    assert outcome.trades[0].net_pnl is None
    assert outcome.trades[0].gross_pnl is None
    assert outcome.trades[0].entry_price is None
    assert outcome.trades[0].exit_price is None


def test_identical_rows_are_kept_and_flagged_as_possible_duplicate_fills(tmp_path: Path) -> None:
    row = "1,AAPL,long,2026-01-06T10:00:00Z,2026-01-06T11:00:00Z,10,100,101,,10,,"
    outcome = _run(_csv(tmp_path, row, row))
    assert len(outcome.trades) == 2
    assert len({trade.trade_key for trade in outcome.trades}) == 2
    assert any(reason.code == "duplicate_kept" for reason in outcome.trades[1].warnings)


def test_zero_quantity_and_bad_side_report_every_reason(tmp_path: Path) -> None:
    path = _csv(tmp_path, "1,AAPL,hold,2026-01-06T10:00:00Z,2026-01-06T11:00:00Z,0,100,101,,10,,")
    assert _codes(_run(path), 2) == {"bad_side", "zero_quantity"}


def test_field_count_mismatch_is_rejected_not_guessed(tmp_path: Path) -> None:
    path = _csv(tmp_path, "1,AAPL,long,2026-01-06T10:00:00Z,2026-01-06T11:00:00Z,10,100")
    assert _codes(_run(path), 2) == {"field_count"}


def test_r_multiple_is_recomputed_and_provided_mismatch_is_flagged(tmp_path: Path) -> None:
    path = _csv(
        tmp_path, "1,AAPL,long,2026-01-06T10:00:00Z,2026-01-06T11:00:00Z,10,100,101,,10,20,5.0"
    )
    outcome = _run(path)
    trade = outcome.trades[0]
    assert trade.r_multiple == pytest.approx(0.5)
    assert "r_mismatch" in [reason.code for reason in trade.warnings]


def test_missing_stop_and_risk_leave_r_empty_with_an_info_code(tmp_path: Path) -> None:
    path = _csv(tmp_path, "1,AAPL,long,2026-01-06T10:00:00Z,2026-01-06T11:00:00Z,10,100,101,,10,,")
    trade = _run(path).trades[0]
    assert trade.r_multiple is None
    assert "missing_risk" in [reason.code for reason in trade.warnings]


def test_formula_cells_are_flagged_and_stored_as_text(tmp_path: Path) -> None:
    path = _csv(
        tmp_path,
        '1,=HYPERLINK("x"),long,2026-01-06T10:00:00Z,2026-01-06T11:00:00Z,10,100,101,,10,,',
    )
    outcome = _run(path)
    trade = outcome.trades[0]
    assert trade.symbol == '=HYPERLINK("x")'
    assert "formula_like_cell" in [reason.code for reason in trade.warnings]


def test_rejected_export_neutralizes_formula_cells() -> None:
    assert neutralize_cell("=CMD|'/c calc'") == "'=CMD|'/c calc'"
    assert neutralize_cell("-0.70") == "'-0.70"
    assert neutralize_cell("@SUM(A1)") == "'@SUM(A1)"


def test_rejected_csv_contains_reasons_and_safe_cells(tmp_path: Path) -> None:
    path = _csv(tmp_path, "1,=CMD,long,2026-01-06T10:00:00Z,,10,100,,,,,")
    outcome = _run(path)
    text = rejected_csv(
        [
            "trade_id",
            "symbol",
            "side",
            "entry_time",
            "exit_time",
            "qty",
            "entry_price",
            "exit_price",
            "fees",
            "net_pnl",
            "planned_risk",
            "r_multiple",
        ],
        outcome.rejected,
    ).decode("utf-8")
    assert "missing_exit_time" in text
    assert "'=CMD" in text
    assert "\n2," in text


def test_confidence_and_screenshot_fields_are_mapped_and_stored(tmp_path: Path) -> None:
    header = HEADER + ",Confidence,Screenshot"
    row = "1,AAPL,long,2026-01-06T10:00:00Z,2026-01-06T11:00:00Z,10,100,101,,10,,,4,charts/aapl.png"
    outcome = _run(_csv(tmp_path, row, header=header))
    trade = outcome.trades[0]
    assert trade.confidence == "4"
    assert trade.screenshot_path == "charts/aapl.png"


def test_mixed_currencies_raise_an_info_issue(tmp_path: Path) -> None:
    from obsidian_ledger.ingest.quality import build_issues

    header = HEADER + ",currency"
    rows = [
        "1,AAPL,long,2026-01-06T10:00:00Z,2026-01-06T11:00:00Z,10,100,101,,10,,,USD",
        "2,ASML,long,2026-01-07T10:00:00Z,2026-01-07T11:00:00Z,10,100,101,,10,,,EUR",
    ]
    issues = build_issues(_run(_csv(tmp_path, *rows, header=header)))
    assert "mixed_currency" in {issue.code for issue in issues}


def test_unknown_timezone_is_refused_with_a_clear_error(tmp_path: Path) -> None:
    path = _csv(tmp_path, "1,AAPL,long,2026-01-06T10:00:00Z,2026-01-06T11:00:00Z,10,100,101,,10,,")
    from obsidian_ledger.ingest.errors import IngestError

    with pytest.raises(ValueError):
        ImportOptions.model_validate({"timezone": "Mars/Olympus"})
    with pytest.raises(IngestError) as caught:
        analyze(path, ImportOptions(), default_timezone="Mars/Olympus")
    assert caught.value.code == "bad_timezone"


def test_naive_timestamps_use_the_configured_timezone(tmp_path: Path) -> None:
    path = _csv(tmp_path, "1,AAPL,long,2026-07-06 10:00,2026-07-06 11:00,10,100,101,,10,,")
    outcome = _run(path, timezone="Europe/London")
    trade = outcome.trades[0]
    # London is UTC+1 in July, so 10:00 local is 09:00 UTC.
    assert trade.entry_time.hour == 9
    assert trade.source_timezone == "Europe/London"
    assert trade.session == "london"
