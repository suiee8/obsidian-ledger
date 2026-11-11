"""Metrics checked against values calculated by hand.

Fixture: six closed trades in exit order, net P&L 100, -50, 200, -100, 0, 50.
"""

import math

import numpy as np
import pytest

from obsidian_ledger.metrics.core import core_metrics
from obsidian_ledger.metrics.risk import drawdown, kelly_upper_bound, risk_per_trade, sqn
from obsidian_ledger.metrics.stats import benjamini_hochberg, mean_interval

PNL = np.array([100.0, -50.0, 200.0, -100.0, 0.0, 50.0])
NO_COST = np.zeros(6)
NO_R = np.full(6, np.nan)


def test_core_metrics_match_hand_calculation() -> None:
    m = core_metrics(PNL, NO_COST, NO_R)
    assert m["trades"] == 6
    assert (m["wins"], m["losses"], m["flat"]) == (3, 2, 1)
    assert m["net_pnl"] == pytest.approx(200.0)
    # Win rate is wins over non-flat trades: 3 / 5.
    assert m["win_rate"] == pytest.approx(0.6)
    # Average win (100 + 200 + 50) / 3 and average loss (50 + 100) / 2.
    assert m["avg_win"] == pytest.approx(350 / 3)
    assert m["avg_loss"] == pytest.approx(75.0)
    assert m["payoff_ratio"] == pytest.approx((350 / 3) / 75)
    # Gross wins 350, gross losses 150.
    assert m["profit_factor"] == pytest.approx(350 / 150)
    assert m["expectancy"] == pytest.approx(200 / 6)
    # Sorted: -100, -50, 0, 50, 100, 200. Median is (0 + 50) / 2.
    assert m["median_trade"] == pytest.approx(25.0)
    assert m["largest_win"] == 200.0
    assert m["largest_loss"] == -100.0


def test_fee_drag_is_costs_over_absolute_gross() -> None:
    costs = np.full(6, -1.0)  # 6 total in costs, so gross is net + 6 = 206
    m = core_metrics(PNL, costs, NO_R)
    assert m["gross_pnl"] == pytest.approx(206.0)
    assert m["fee_drag"] == pytest.approx(6 / 206)


def test_drawdown_hand_calculation_with_starting_equity() -> None:
    # Equity path: 1000, 1100, 1050, 1250, 1150, 1150, 1200.
    # Running peak reaches 1250 after trade 3. Trough is 1150 after trade 4: depth -100.
    # Equity never returns to 1250, so the drawdown is not recovered.
    dd = drawdown(PNL, 1000.0)
    assert dd["max_drawdown"] == pytest.approx(-100.0)
    assert dd["max_drawdown_pct"] == pytest.approx(-100 / 1250)
    assert dd["drawdown_trades"] == 1
    assert dd["recovered"] is False
    assert dd["recovery_trades"] is None


def test_drawdown_without_starting_equity_has_no_percentage() -> None:
    dd = drawdown(PNL, None)
    assert dd["max_drawdown"] == pytest.approx(-100.0)
    assert dd["max_drawdown_pct"] is None


def test_drawdown_recovery_is_counted_in_trades() -> None:
    # Path from zero: 0, -10, -20, +5, +15, +25. Peak 0, trough -20 after trade 2.
    # Path returns to 0 after trade 5, so recovery takes 3 trades.
    dd = drawdown(np.array([-10.0, -10.0, 5.0, 10.0, 10.0]), None)
    assert dd["max_drawdown"] == pytest.approx(-20.0)
    assert dd["recovered"] is True
    assert dd["recovery_trades"] == 3


def test_sqn_hand_calculation() -> None:
    # R = [1, -1, 2]: mean 2/3, sample variance 7/3, so SQN = sqrt(3) * (2/3) / sqrt(7/3).
    assert sqn(np.array([1.0, -1.0, 2.0])) == pytest.approx(0.7559, abs=1e-3)


def test_kelly_upper_bound_hand_calculation() -> None:
    # W = 0.6, payoff = (350/3) / 75 = 1.5556, so f = 0.6 - 0.4 / 1.5556.
    assert kelly_upper_bound(0.6, (350 / 3) / 75) == pytest.approx(0.6 - 0.4 / ((350 / 3) / 75))
    assert kelly_upper_bound(0.6, None) is None


def test_risk_per_trade_coefficient_of_variation() -> None:
    result = risk_per_trade(np.array([10.0, 20.0, 30.0]))
    assert result["mean"] == pytest.approx(20.0)
    assert result["coefficient_of_variation"] == pytest.approx(10.0 / 20.0)


def test_mean_interval_matches_student_t() -> None:
    # Values 1, 2, 3: mean 2, sample sd 1, t(0.975, 2) = 4.3027.
    # Half-width 4.3027 / sqrt(3) = 2.4843.
    result = mean_interval(np.array([1.0, 2.0, 3.0]))
    assert result["mean"] == pytest.approx(2.0)
    low, high = result["ci95"]
    assert low == pytest.approx(2.0 - 2.4843, abs=1e-3)
    assert high == pytest.approx(2.0 + 2.4843, abs=1e-3)


def test_benjamini_hochberg_hand_calculation() -> None:
    # Sorted p: 0.01, 0.03, 0.04, 0.20. Ranked p * m / rank: 0.04, 0.06, 0.0533, 0.20.
    # Enforce monotonicity from the largest down: 0.04, 0.0533, 0.0533, 0.20.
    q = benjamini_hochberg([0.01, 0.04, 0.03, 0.20])
    assert q[0] == pytest.approx(0.04)
    assert q[1] == pytest.approx(0.16 / 3)
    assert q[2] == pytest.approx(0.16 / 3)
    assert q[3] == pytest.approx(0.20)


def test_benjamini_hochberg_skips_untestable_slices() -> None:
    assert benjamini_hochberg([None, 0.01, None]) == [None, pytest.approx(0.01), None]


def test_sqn_is_undefined_for_constant_outcomes() -> None:
    assert sqn(np.array([1.0, 1.0, 1.0])) is None


def test_daily_ratios_need_a_starting_equity() -> None:
    from obsidian_ledger.metrics.risk import daily_ratios

    result = daily_ratios(np.array([10.0, -5.0, 20.0]), None, None)
    assert result["available"] is False
    assert "starting equity" in result["reason"]


def test_daily_sharpe_follows_its_definition() -> None:
    from obsidian_ledger.metrics.risk import daily_ratios

    days = np.array([10.0, -5.0, 20.0])
    result = daily_ratios(days, 1000.0, None)
    equity_before = np.array([1000.0, 1010.0, 1005.0])
    returns = days / equity_before
    expected = returns.mean() / returns.std(ddof=1) * math.sqrt(252)
    assert result["available"] is True
    assert result["sharpe"] == pytest.approx(expected)
