"""Property tests: invariants that must hold for any trade sequence Hypothesis generates."""

from typing import Any

import numpy as np
from hypothesis import given, settings
from hypothesis import strategies as st

from obsidian_ledger.metrics.core import core_metrics
from obsidian_ledger.metrics.discipline import discipline_score
from obsidian_ledger.metrics.risk import drawdown
from obsidian_ledger.metrics.stats import benjamini_hochberg

# Subnormal values are excluded. Scaling 5e-324 by 0.5 gives exactly zero, which flips its
# win or loss class and says nothing about the metrics themselves.
money = st.floats(
    min_value=-10_000,
    max_value=10_000,
    allow_nan=False,
    allow_infinity=False,
    allow_subnormal=False,
)
outcomes = st.lists(money, min_size=1, max_size=60)
p_values = st.lists(st.floats(min_value=0.0, max_value=1.0), min_size=1, max_size=40)
SETTINGS = settings(max_examples=150, deadline=None)


def _metrics(values: list[float]) -> dict[str, Any]:
    pnl = np.array(values, dtype=np.float64)
    return core_metrics(pnl, np.zeros_like(pnl), np.full_like(pnl, np.nan))


@SETTINGS
@given(outcomes)
def test_win_rate_is_a_proportion(values: list[float]) -> None:
    rate = _metrics(values)["win_rate"]
    if rate is not None:
        assert isinstance(rate, float)
        assert 0.0 <= rate <= 1.0


@SETTINGS
@given(outcomes)
def test_profit_factor_is_nonnegative_when_defined(values: list[float]) -> None:
    factor = _metrics(values)["profit_factor"]
    if factor is not None:
        assert isinstance(factor, float)
        assert factor >= 0.0


@SETTINGS
@given(outcomes, st.floats(min_value=0.01, max_value=100.0))
def test_scaling_all_pnl_scales_money_and_keeps_rates(values: list[float], k: float) -> None:
    base = _metrics(values)
    scaled = _metrics([v * k for v in values])
    assert np.isclose(scaled["expectancy"], base["expectancy"] * k, rtol=1e-9, atol=1e-6)
    assert scaled["win_rate"] == base["win_rate"]


@SETTINGS
@given(outcomes, st.randoms(use_true_random=False))
def test_totals_do_not_depend_on_trade_order(values: list[float], rng: object) -> None:
    shuffled = list(values)
    rng.shuffle(shuffled)  # type: ignore[attr-defined]
    assert np.isclose(_metrics(values)["net_pnl"], _metrics(shuffled)["net_pnl"], atol=1e-6)


@SETTINGS
@given(outcomes, st.floats(min_value=1.0, max_value=1_000_000.0))
def test_drawdown_is_never_positive(values: list[float], start: float) -> None:
    dd = drawdown(np.array(values), start)
    assert dd["max_drawdown"] <= 0.0
    pct = dd["max_drawdown_pct"]
    if pct is not None:
        assert pct <= 0.0


@SETTINGS
@given(p_values)
def test_benjamini_hochberg_inflates_but_stays_in_range(p: list[float]) -> None:
    q = benjamini_hochberg(list(p))
    for raw, adjusted in zip(p, q, strict=True):
        assert adjusted is not None
        assert raw - 1e-12 <= adjusted <= 1.0
    ordered = sorted(zip(p, [v for v in q if v is not None], strict=True))
    adjusted_in_order = [adj for _raw, adj in ordered]
    assert all(
        a <= b + 1e-12 for a, b in zip(adjusted_in_order, adjusted_in_order[1:], strict=False)
    )


@SETTINGS
@given(
    st.floats(min_value=0.0, max_value=1.0),
    st.floats(min_value=0.0, max_value=5.0),
    st.one_of(st.none(), st.floats(min_value=0.0, max_value=2.0)),
    st.one_of(st.none(), st.floats(min_value=0.0, max_value=1.0)),
)
def test_discipline_score_stays_between_zero_and_one_hundred(
    adherence: float,
    overtrade_share: float,
    risk_cv: float | None,
    stop_rate: float | None,
) -> None:
    behavior = {
        "plan": {"adherence_rate": adherence},
        "revenge": {"rate_after_loss": 0.0},
        "overtrading": {"days": 10, "overtraded_days": min(10, round(overtrade_share * 10))},
    }
    result = discipline_score(behavior, risk_cv, stop_rate)
    score = result["score"]
    assert score is not None
    assert 0.0 <= score <= 100.0
    assert 1 <= result["components_used"] <= 5
