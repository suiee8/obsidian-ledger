"""Typed wrappers around the SciPy functions the statistics use.

SciPy does not ship type stubs for these functions, so the untyped calls live in this one
module. The rest of the code sees plain floats.
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt
from scipy import special as _special  # pyright: ignore
from scipy import stats as _stats  # pyright: ignore


def t_quantile(probability: float, degrees_of_freedom: int) -> float:
    """Inverse CDF of Student's t distribution."""
    return float(_stats.t.ppf(probability, degrees_of_freedom))  # pyright: ignore


def welch_two_sided_p(
    sample: npt.NDArray[np.float64],
    other: npt.NDArray[np.float64],
) -> float:
    """Two-sided p-value from Welch's t-test, which does not assume equal variances.

    Computed from the closed form (Welch-Satterthwaite degrees of freedom) so it skips the
    argument handling in scipy.stats.ttest_ind, which costs about 5 ms per call. Tests compare
    it with ttest_ind. Returns nan when either sample has no variance.
    """
    n1 = sample.size
    n2 = other.size
    v1 = float(sample.var(ddof=1)) / n1
    v2 = float(other.var(ddof=1)) / n2
    spread = v1 + v2
    if spread <= 0.0:
        return float("nan")
    t = (float(sample.mean()) - float(other.mean())) / spread**0.5
    dof = spread**2 / (v1**2 / (n1 - 1) + v2**2 / (n2 - 1))
    return float(2.0 * _special.stdtr(dof, -abs(t)))  # pyright: ignore
