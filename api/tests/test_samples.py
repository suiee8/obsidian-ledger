from datetime import datetime
from pathlib import Path

from ledger_samples import COLUMNS, generate_rows

ROOT = Path(__file__).resolve().parents[2]


def test_generator_is_deterministic() -> None:
    first = generate_rows(50, seed=42)
    second = generate_rows(50, seed=42)
    assert first == second
    assert first[0]["trade_id"] == "T000001"
    assert set(first[0]) == set(COLUMNS)


def test_rows_stay_internally_consistent() -> None:
    rows = generate_rows(300, seed=42)
    previous = ""
    for row in rows:
        assert row["currency"] == "USD"
        assert row["side"] in {"long", "short"}
        assert row["setup"] in {"breakout", "mean_revert", "fomo"}
        entry = datetime.fromisoformat(row["entry_time"].replace("Z", "+00:00"))
        exit_time = datetime.fromisoformat(row["exit_time"].replace("Z", "+00:00"))
        assert exit_time > entry
        assert entry.weekday() < 5
        assert exit_time.weekday() < 5
        assert previous < row["entry_time"]
        previous = row["entry_time"]
        risk = float(row["planned_risk"])
        net = float(row["net_pnl"])
        multiple = float(row["r_multiple"])
        assert risk > 0
        assert abs(multiple * risk - net) < 0.02
        assert (net > 0) == (multiple > 0)


def test_fomo_and_revenge_break_the_plan_more_often() -> None:
    rows = generate_rows(8_000, seed=42)

    def broken(emotion: str) -> float:
        subset = [row for row in rows if row["emotion"] == emotion]
        assert subset
        return sum(row["plan_followed"] == "false" for row in subset) / len(subset)

    assert broken("calm") < 0.12
    assert broken("fomo") > 0.55
    assert broken("revenge") > 0.60
    assert all(row["emotion"] == "fomo" for row in rows if row["setup"] == "fomo")


def test_broker_fixtures_exist() -> None:
    samples = ROOT / "samples"
    mt5 = (samples / "mt5_statement.csv").read_text(encoding="utf-8")
    header = mt5.splitlines()[0]
    assert header.count("Price") == 2
    tv = (samples / "tradingview_trades.csv").read_text(encoding="utf-8")
    assert "Entry long" in tv and "Exit long" in tv
    ibkr = (samples / "ibkr_executions.csv").read_text(encoding="utf-8")
    assert "YYYYMMDD" not in ibkr
    assert "20260106;143205" in ibkr
    text = (samples / "messy_journal.csv").read_text(encoding="utf-8")
    assert "date;symbol;side;qty;entry;exit;net_pnl;notes" in text
    assert text.count("planned entry") == 2
    assert "Ignore previous instructions" in text
    assert "=CMD|'/c calc'" in text
    preview = (samples / "synthetic_preview.csv").read_text(encoding="utf-8")
    preview_lines = preview.splitlines()
    assert len(preview_lines) == 1_001
    assert preview_lines[0].split(",") == list(COLUMNS)


def test_analytical_stack_imports() -> None:
    import duckdb
    import polars as pl

    assert duckdb.__version__
    assert pl.__version__
