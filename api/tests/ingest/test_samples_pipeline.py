"""End-to-end checks on the committed sample files. Expected values are hand-calculated."""

from pathlib import Path

import pytest

from obsidian_ledger.ingest.analysis import analyze
from obsidian_ledger.ingest.options import ImportOptions
from obsidian_ledger.ingest.run import RunOutcome, run_import

SAMPLES = Path(__file__).resolve().parents[3] / "samples"


def _run(name: str, **options: object) -> RunOutcome:
    opts = ImportOptions.model_validate(options)
    analysis = analyze(SAMPLES / name, opts)
    assert not analysis.blocking, [q.id for q in analysis.blocking]
    return run_import(analysis, opts)


def test_mt5_five_closed_positions_with_costs_and_stops() -> None:
    outcome = _run("mt5_statement.csv")
    assert outcome.rejected == []
    trades = {trade.symbol: trade for trade in outcome.trades}
    assert len(trades) == 5

    eurusd = trades["EURUSD"]
    # Profit 26.50, commission -0.70, swap -0.12, taxes 0.
    assert eurusd.gross_pnl == pytest.approx(26.50)
    assert eurusd.net_pnl == pytest.approx(25.68)
    # Stop distance 0.00200 x 0.10 lot x 100,000 = 20.00 planned risk.
    assert eurusd.planned_risk == pytest.approx(20.0)
    assert eurusd.r_multiple == pytest.approx(25.68 / 20.0)
    # 14:32:01 to 16:05:22 is 1 h 33 min 21 s.
    assert eurusd.holding_seconds == pytest.approx(5601.0)

    assert trades["XAUUSD"].gross_pnl == pytest.approx(-174.0)
    assert trades["XAUUSD"].net_pnl == pytest.approx(-175.90)
    assert trades["GBPUSD"].net_pnl == pytest.approx(67.05)
    assert trades["US500"].net_pnl == pytest.approx(78.25)


def test_mt5_usdjpy_flags_quote_currency_mismatch_and_keeps_reported_value() -> None:
    outcome = _run("mt5_statement.csv")
    usdjpy = next(trade for trade in outcome.trades if trade.symbol == "USDJPY")
    assert usdjpy.gross_pnl == pytest.approx(240.0)
    codes = [reason.code for reason in usdjpy.warnings]
    assert "pnl_mismatch" in codes
    for trade in outcome.trades:
        if trade.symbol != "USDJPY":
            assert "pnl_mismatch" not in [reason.code for reason in trade.warnings]


def test_tradingview_legs_pair_into_four_trades_with_default_symbol() -> None:
    outcome = _run("tradingview_trades.csv", default_symbol="BTCUSD")
    assert outcome.rejected == []
    nets = [trade.net_pnl for trade in outcome.trades]
    assert nets == pytest.approx([12.00, -9.50, 30.00, -6.00])
    assert [trade.side for trade in outcome.trades] == ["long", "short", "long", "long"]
    first = outcome.trades[0]
    assert first.setup == "ORB long"
    assert first.mfe == pytest.approx(1.80)
    assert first.mae == pytest.approx(0.40)
    assert first.holding_seconds == pytest.approx(5580.0)  # 14:32 to 16:05
    assert first.currency == "USD"


def test_tradingview_without_symbol_asks_one_blocking_question() -> None:
    analysis = analyze(SAMPLES / "tradingview_trades.csv", ImportOptions())
    assert [question.id for question in analysis.blocking] == ["default_symbol"]


def test_ibkr_fills_pair_fifo_and_split_commissions() -> None:
    outcome = _run("ibkr_executions.csv")
    assert outcome.rejected == []
    assert outcome.open_positions == []
    by_id = {trade.trade_id: trade for trade in outcome.trades}
    assert set(by_id) == {"90001-90002-1", "90003-90004-1", "90005-90006-1", "90007-90008-1"}

    aapl = by_id["90001-90002-1"]
    assert aapl.gross_pnl == pytest.approx(24.0)  # (190.40 - 189.20) x 20
    assert aapl.commission == pytest.approx(-2.0)
    assert aapl.net_pnl == pytest.approx(22.0)

    eur = by_id["90003-90004-1"]
    assert eur.gross_pnl == pytest.approx(265.0)  # (1.09480 - 1.09215) x 100,000
    assert eur.net_pnl == pytest.approx(261.0)
    assert eur.asset_class == "forex"

    mnq = by_id["90005-90006-1"]
    # Short 2 at 21450, bought back at 21480, multiplier 2: -30 x 2 x 2 = -120.
    assert mnq.side == "short"
    assert mnq.gross_pnl == pytest.approx(-120.0)
    assert mnq.net_pnl == pytest.approx(-124.80)

    msft = by_id["90007-90008-1"]
    assert msft.gross_pnl == pytest.approx(-35.25)
    assert msft.net_pnl == pytest.approx(-37.25)


def test_messy_journal_rejects_every_row_with_a_specific_reason() -> None:
    outcome = _run("messy_journal.csv")
    # The fixture has one timestamp column, so no row can be paired with an exit time.
    assert outcome.trades == []
    reasons = {row.source_row: {reason.code for reason in row.reasons} for row in outcome.rejected}
    assert reasons[5] == {"missing_exit_time"}
    assert reasons[7] == {"missing_symbol", "missing_exit_time", "zero_quantity"}
    assert reasons[8] == {"bad_time", "missing_exit_time"}
    assert reasons[12] == {"field_count"}
    assert "bad_number" in reasons[14] and "bad_side" in reasons[14]
    assert 11 not in reasons  # the blank line is skipped, not rejected


def test_synthetic_preview_matches_manifest_net_total() -> None:
    outcome = _run("synthetic_preview.csv")
    assert outcome.rejected == []
    assert len(outcome.trades) == 1000
    total = sum(trade.net_pnl for trade in outcome.trades)
    assert total == pytest.approx(5083.08, abs=0.05)  # samples/synthetic_preview.manifest.json
    wins = sum(1 for trade in outcome.trades if trade.net_pnl > 0)
    assert wins == 485
    for trade in outcome.trades:
        assert trade.r_multiple is not None
        assert "r_mismatch" not in [reason.code for reason in trade.warnings]
