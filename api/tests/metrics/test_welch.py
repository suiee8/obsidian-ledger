"""The closed-form Welch p-value must agree with scipy.stats.ttest_ind."""

import numpy as np
import pytest
from scipy import stats  # pyright: ignore

from obsidian_ledger.metrics._scipy import welch_two_sided_p


@pytest.mark.parametrize("seed", range(25))
def test_matches_scipy_ttest_ind(seed: int) -> None:
    rng = np.random.default_rng(seed)
    sample = rng.normal(rng.uniform(-2, 2), rng.uniform(0.5, 4), size=int(rng.integers(2, 400)))
    other = rng.normal(rng.uniform(-2, 2), rng.uniform(0.5, 4), size=int(rng.integers(2, 4000)))
    expected = float(stats.ttest_ind(sample, other, equal_var=False).pvalue)  # pyright: ignore
    assert welch_two_sided_p(sample, other) == pytest.approx(expected, rel=1e-9, abs=1e-12)


def test_no_variance_gives_nan() -> None:
    assert np.isnan(welch_two_sided_p(np.ones(5), np.ones(7)))
