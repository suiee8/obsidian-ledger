"""Bootstrap, Monte Carlo, and simulator behavior with fixtures whose answers are known."""

from datetime import UTC, datetime

import numpy as np
import polars as pl

from obsidian_ledger.metrics.behavior import analyze_behavior
from obsidian_ledger.metrics.discipline import discipline_score
from obsidian_ledger.metrics.segments import segment_table
from obsidian_ledger.metrics.simulator import Rules, simulate
from obsidian_ledger.metrics.stats import bootstrap_summary, monte_carlo


def _ts(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 1, 6, hour, minute, tzinfo=UTC).replace(tzinfo=None)


def test_bootstrap_on_constant_trades_has_zero_width_intervals() -> None:
    result = bootstrap_summary(np.full(20, 5.0), resamples=200, seed=1)
    assert result["expectancy"]["point"] == 5.0
    assert result["expectancy"]["ci95"] == [5.0, 5.0]
    assert result["win_rate"]["ci95"] == [1.0, 1.0]
    # Without losses in any resample, profit factor has no value.
    assert result["profit_factor"]["ci95"] is None


def test_bootstrap_is_reproducible_for_a_seed() -> None:
    pnl = np.array([100.0, -50.0, 200.0, -100.0, 0.0, 50.0])
    first = bootstrap_summary(pnl, resamples=300, seed=7)
    second = bootstrap_summary(pnl, resamples=300, seed=7)
    assert first["expectancy"]["ci95"] == second["expectancy"]["ci95"]


def test_monte_carlo_certain_outcomes() -> None:
    losing = np.full(20, -10.0)
    result = monte_carlo(
        losing, paths=200, seed=3, start_equity=None, drawdown_threshold=50.0, target=0.0
    )
    # Every path falls 200 from its start, so a 50 drawdown is certain and no path ends at 0.
    assert result["probability_drawdown_at_least_threshold"] == 1.0
    assert result["probability_reaching_target"] == 0.0
    assert result["probability_ruin"] is None


def test_monte_carlo_ruin_with_starting_equity() -> None:
    losing = np.full(20, -10.0)
    result = monte_carlo(
        losing, paths=100, seed=3, start_equity=100.0, drawdown_threshold=50.0, target=110.0
    )
    # Ruin means equity below 50 (half of 100). Every path loses 200, so ruin is certain.
    assert result["probability_ruin"] == 1.0


def test_monte_carlo_winning_outcomes_never_draw_down() -> None:
    winning = np.full(20, 10.0)
    result = monte_carlo(
        winning, paths=100, seed=3, start_equity=None, drawdown_threshold=1.0, target=0.0
    )
    assert result["probability_drawdown_at_least_threshold"] == 0.0
    assert result["probability_reaching_target"] == 1.0


def test_monte_carlo_fan_is_ordered() -> None:
    rng = np.random.default_rng(0)
    result = monte_carlo(
        rng.normal(5, 20, 80),
        paths=300,
        seed=9,
        start_equity=None,
        drawdown_threshold=100.0,
        target=0.0,
    )
    for row in result["fan"]:
        assert row["p5"] <= row["p25"] <= row["p50"] <= row["p75"] <= row["p95"]


def _frame(rows: list[tuple[float, float, datetime, datetime, str]]) -> pl.DataFrame:
    """Rows of (pnl, qty, entry, exit, symbol) with the columns the metrics read."""
    return pl.DataFrame(
        {
            "trade_key": [f"k{i}" for i in range(len(rows))],
            "pnl": [r[0] for r in rows],
            "qty": [r[1] for r in rows],
            "entry_time": [r[2] for r in rows],
            "exit_time": [r[3] for r in rows],
            "symbol": [r[4] for r in rows],
            "entry_day": [r[2].date() for r in rows],
            "exit_day": [r[3].date() for r in rows],
            "holding_seconds": [(r[3] - r[2]).total_seconds() for r in rows],
            "hour_utc": [r[2].hour for r in rows],
            "weekday": [r[2].weekday() for r in rows],
            "setup": [None for _ in rows],
            "side": ["long" for _ in rows],
            "session": ["london" for _ in rows],
            "emotion": [None for _ in rows],
            "account": ["default" for _ in rows],
            "tags": [None for _ in rows],
            "planned_risk": [None for _ in rows],
            "r_multiple": [None for _ in rows],
            "mae": [None for _ in rows],
            "mfe": [None for _ in rows],
            "plan_followed": [None for _ in rows],
            "stop_loss": [None for _ in rows],
        },
        schema_overrides={
            "entry_time": pl.Datetime("us"),
            "exit_time": pl.Datetime("us"),
            "entry_day": pl.Date,
            "exit_day": pl.Date,
            "planned_risk": pl.Float64,
            "r_multiple": pl.Float64,
            "mae": pl.Float64,
            "mfe": pl.Float64,
            "plan_followed": pl.Boolean,
            "stop_loss": pl.Float64,
            "setup": pl.String,
            "emotion": pl.String,
            "tags": pl.String,
        },
    )


def test_simulator_daily_loss_cap_uses_only_known_results() -> None:
    # t1 loses 100 (exits 10:10). t2 enters 10:20 (t1 is known), loses 100, exits 10:30.
    # t3 enters 11:00. t2 is now known: the day has lost 200, which breaks the 150 cap.
    frame = _frame(
        [
            (-100.0, 1.0, _ts(10, 0), _ts(10, 10), "AAPL"),
            (-100.0, 1.0, _ts(10, 20), _ts(10, 30), "AAPL"),
            (50.0, 1.0, _ts(11, 0), _ts(11, 10), "AAPL"),
        ]
    )
    result = simulate(frame, Rules(daily_loss_cap=150.0), resamples=100, seed=1)
    assert result["kept_trades"] == 2
    assert result["removed_trades"] == 1
    assert result["skipped_by_reason"] == {"daily_loss": 1}
    assert result["baseline"]["net_pnl"] == -150.0
    assert result["simulated"]["net_pnl"] == -200.0


def test_simulator_does_not_use_a_loss_before_it_closes() -> None:
    # t1 enters 10:00 and loses 200 at 12:00. t2 enters 10:30, before t1 closes, so the
    # 150 cap cannot yet apply: t2 must be taken. Using t1's loss early would skip it.
    frame = _frame(
        [
            (-200.0, 1.0, _ts(10, 0), _ts(12, 0), "AAPL"),
            (-10.0, 1.0, _ts(10, 30), _ts(10, 40), "AAPL"),
        ]
    )
    result = simulate(frame, Rules(daily_loss_cap=150.0), resamples=100, seed=1)
    assert result["kept_trades"] == 2
    assert result["skipped_by_reason"] == {}


def test_simulator_max_trades_per_day() -> None:
    frame = _frame(
        [
            (-100.0, 1.0, _ts(10, 0), _ts(10, 10), "AAPL"),
            (50.0, 1.0, _ts(11, 0), _ts(11, 10), "AAPL"),
        ]
    )
    result = simulate(frame, Rules(max_trades_per_day=1), resamples=100, seed=1)
    assert result["kept_trades"] == 1
    assert result["simulated"]["net_pnl"] == -100.0


def test_simulator_symbol_exclusion() -> None:
    frame = _frame(
        [
            (-40.0, 1.0, _ts(10, 0), _ts(10, 10), "BTC"),
            (30.0, 1.0, _ts(11, 0), _ts(11, 10), "AAPL"),
        ]
    )
    result = simulate(frame, Rules(exclude_symbols=("BTC",)), resamples=100, seed=1)
    assert result["simulated"]["net_pnl"] == 30.0
    assert result["no_rules_set"] is False


def test_simulator_without_rules_matches_baseline() -> None:
    frame = _frame(
        [
            (-40.0, 1.0, _ts(10, 0), _ts(10, 10), "BTC"),
            (30.0, 1.0, _ts(11, 0), _ts(11, 10), "AAPL"),
        ]
    )
    result = simulate(frame, Rules(), resamples=100, seed=1)
    assert result["simulated"]["net_pnl"] == result["baseline"]["net_pnl"]
    assert result["no_rules_set"] is True


def test_behavior_flags_quick_re_entry_after_a_loss() -> None:
    # A loses 100 and exits 10:30. B enters 10:35 (five minutes later), so it is a revenge entry.
    frame = _frame(
        [
            (-100.0, 10.0, _ts(10, 0), _ts(10, 30), "AAPL"),
            (50.0, 10.0, _ts(10, 35), _ts(11, 0), "AAPL"),
        ]
    )
    behavior = analyze_behavior(
        frame, overtrading_threshold=10, revenge_gap_minutes=10, size_jump=0.5
    )
    assert behavior["revenge"]["flagged_trades"] == 1
    assert behavior["revenge"]["after_loss_trades"] == 1
    assert behavior["revenge"]["rate_after_loss"] == 1.0
    assert behavior["revenge"]["net_pnl_of_flagged"] == 50.0
    assert behavior["longest_loss_streak"] == 1


def test_behavior_does_not_flag_a_calm_entry_after_a_win() -> None:
    frame = _frame(
        [
            (100.0, 10.0, _ts(10, 0), _ts(10, 30), "AAPL"),
            (-50.0, 10.0, _ts(10, 35), _ts(11, 0), "AAPL"),
        ]
    )
    behavior = analyze_behavior(
        frame, overtrading_threshold=10, revenge_gap_minutes=10, size_jump=0.5
    )
    assert behavior["revenge"]["flagged_trades"] == 0
    assert behavior["after_win"]["trades"] == 1


def test_discipline_score_hand_calculation() -> None:
    behavior = {
        "plan": {"adherence_rate": 0.8},
        "revenge": {"rate_after_loss": 0.25},
        "overtrading": {"days": 10, "overtraded_days": 1},
    }
    result = discipline_score(behavior, risk_cv=0.5, stop_usage_rate=0.5)
    # 0.30 x 80 + 0.25 x 50 + 0.20 x 75 + 0.15 x 90 + 0.10 x 50 = 70.
    assert result["score"] == 70.0
    assert result["components_used"] == 5


def test_discipline_score_rescales_when_components_are_missing() -> None:
    result = discipline_score({"plan": {"adherence_rate": 0.8}}, risk_cv=None, stop_usage_rate=None)
    assert result["score"] == 80.0
    assert result["components_used"] == 1


def test_segments_separate_an_edge_from_a_leak() -> None:
    rng = np.random.default_rng(5)
    rows: list[tuple[float, float, datetime, datetime, str]] = []
    for index in range(40):
        rows.append(
            (10.0 + rng.uniform(-2, 2), 1.0, _ts(10, index % 50), _ts(10, index % 50), "AAPL")
        )
        rows.append(
            (-10.0 + rng.uniform(-2, 2), 1.0, _ts(10, index % 50), _ts(10, index % 50), "MSFT")
        )
    table = segment_table(_frame(rows), "symbol", min_n=30)
    verdicts = {slice_["value"]: slice_["verdict"] for slice_ in table["slices"]}
    assert verdicts == {"AAPL": "edge", "MSFT": "leak"}


def test_small_segments_are_marked_low_confidence() -> None:
    rows = [(10.0, 1.0, _ts(10), _ts(10), "AAPL") for _ in range(5)]
    rows += [(-10.0, 1.0, _ts(10), _ts(10), "MSFT") for _ in range(40)]
    table = segment_table(_frame(rows), "symbol", min_n=30)
    small = next(s for s in table["slices"] if s["value"] == "AAPL")
    assert small["low_confidence"] is True
    assert small["verdict"] == "low confidence"
