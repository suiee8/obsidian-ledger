"""Recompute any number in a Coach report from its source reference.

A source is a string such as `slice|seg~hour~14|diff_pnl` or `core|net_pnl`. `Resolver.resolve`
rebuilds the value from the trades, using Polars for the arithmetic, which is a different code path
from the NumPy code that produced the report. A test walks every Figure and checks that the two
agree.

Grammar (parts are separated by `|`):
    core|<metric>              a key of the core metrics (trades, net_pnl, expectancy_r, ...)
    core|ci_<unit>_<low|high>  the verdict interval, by re-running its seeded bootstrap
    risk|<metric>              max_drawdown, sqn, risk_cv, median_planned_risk, kelly
    behavior|<metric>          longest_loss_streak
    slice|<slice id>|<stat>    n, mean_pnl, total_pnl, diff_pnl, diff_r, impact,
                               and for measured patterns: mean_amount, total_amount;
                               ci_pnl_*, ci_r_*, ci_amount_* are interval bounds
    trade|<trade key>|pnl      one trade's net P&L
    meta|<name>                tests_run, no_risk_trades, excluded_no_fx, overtrading_limit
"""

from __future__ import annotations

import numpy as np
import polars as pl

from obsidian_ledger.coach.effects import bootstrap_intervals, mean_bootstrap
from obsidian_ledger.coach.findings import find_all
from obsidian_ledger.coach.params import CoachParams
from obsidian_ledger.coach.slices import MEASURED_PATTERNS, SliceBuilder
from obsidian_ledger.metrics.behavior import analyze_behavior
from obsidian_ledger.metrics.core import core_metrics
from obsidian_ledger.metrics.risk import drawdown, kelly_upper_bound, risk_per_trade, sqn


class UnresolvableSource(ValueError):
    """The source names something this resolver does not know."""


class Resolver:
    def __init__(
        self,
        trades: pl.DataFrame,
        params: CoachParams,
        *,
        starting_equity: float | None = None,
        excluded_no_fx: int = 0,
        currency: str = "",
    ) -> None:
        self.trades = trades
        self.params = params
        self.starting_equity = starting_equity
        self.excluded_no_fx = excluded_no_fx
        self.currency = currency
        self.builder = SliceBuilder(trades, params, currency)

    def resolve(self, source: str) -> float | None:
        parts = source.split("|")
        head = parts[0]
        if head == "core" and len(parts) == 2:
            return self._core(parts[1])
        if head == "risk" and len(parts) == 2:
            return self._risk(parts[1])
        if head == "behavior" and len(parts) == 2:
            return self._behavior(parts[1])
        if head == "slice" and len(parts) == 3:
            return self._slice(parts[1], parts[2])
        if head == "trade" and len(parts) == 3 and parts[2] == "pnl":
            return self._trade(parts[1])
        if head == "meta" and len(parts) == 2:
            return self._meta(parts[1])
        raise UnresolvableSource(source)

    # ----- core / risk / behavior -----

    def _core(self, name: str) -> float | None:
        if name.startswith("ci_"):
            return self._core_interval(name)
        frame = self.trades
        pnl = frame["pnl"].to_numpy().astype(np.float64)
        costs = frame["costs"].to_numpy().astype(np.float64)
        r = frame["r_multiple"].to_numpy().astype(np.float64)
        value = core_metrics(pnl, costs, r).get(name)
        return float(value) if value is not None else None

    def _core_interval(self, name: str) -> float | None:
        """Verdict interval: the seeded bootstrap of the mean over R (when enough trades have
        a planned risk) or over currency P&L."""
        unit, _, side = name.removeprefix("ci_").rpartition("_")
        values = self.builder.pnl
        if unit == "r":
            values = self.builder.r[np.isfinite(self.builder.r)]
        elif unit != "currency":
            raise UnresolvableSource(name)
        bounds = mean_bootstrap(values, self.params.resamples, self.params.seed)
        return _pick(bounds, side, name)

    def _risk(self, name: str) -> float | None:
        frame = self.trades.sort(["exit_time", "trade_key"])
        if name == "max_drawdown":
            return float(drawdown(frame["pnl"].to_numpy(), self.starting_equity)["max_drawdown"])
        r = frame["r_multiple"].to_numpy().astype(np.float64)
        planned = frame["planned_risk"].to_numpy().astype(np.float64)
        if name == "sqn":
            value = sqn(r)
            return float(value) if value is not None else None
        if name == "risk_cv":
            value = risk_per_trade(planned)["coefficient_of_variation"]
            return float(value) if value is not None else None
        if name == "median_planned_risk":
            known = planned[np.isfinite(planned) & (planned > 0)]
            return float(np.median(known)) if known.size else None
        if name == "kelly":
            core = core_metrics(
                frame["pnl"].to_numpy().astype(np.float64),
                frame["costs"].to_numpy().astype(np.float64),
                r,
            )
            value = kelly_upper_bound(core.get("win_rate"), core.get("payoff_ratio"))
            return float(value) if value is not None else None
        raise UnresolvableSource(name)

    def _behavior(self, name: str) -> float | None:
        result = analyze_behavior(self.trades, 10, 10.0, 0.5)
        value = result.get(name)
        return float(value) if value is not None else None

    # ----- slices -----

    def _slice(self, slice_id: str, stat: str) -> float | None:
        if stat.startswith("ci_"):
            return self._slice_interval(slice_id, stat)
        if slice_id.removeprefix("beh~") in MEASURED_PATTERNS:
            return self._measured(slice_id.removeprefix("beh~"), stat)
        defn = self.builder.get(slice_id)
        if defn is None:
            raise UnresolvableSource(slice_id)
        frame = self.builder.frame
        inside = frame.filter(pl.Series(defn.mask))
        outside = frame.filter(pl.Series(defn.rest))
        if stat == "n":
            return float(inside.height)
        if stat == "mean_pnl":
            return _mean(inside["pnl"])
        if stat == "total_pnl":
            return float(inside["pnl"].sum())
        mean_in, mean_out = _mean(inside["pnl"]), _mean(outside["pnl"])
        if stat == "diff_pnl":
            return None if mean_in is None or mean_out is None else mean_in - mean_out
        if stat == "diff_r":
            r_in, r_out = (
                _mean(inside["r_multiple"].drop_nulls()),
                _mean(outside["r_multiple"].drop_nulls()),
            )
            return None if r_in is None or r_out is None else r_in - r_out
        if stat == "impact":
            if mean_in is None or mean_out is None:
                return None
            diff = mean_in - mean_out
            return float(inside.height) * (-diff if diff < 0 else diff)
        raise UnresolvableSource(stat)

    def _slice_interval(self, slice_id: str, stat: str) -> float | None:
        """Re-run the seeded bootstrap for this one slice. Draws depend only on the seed and the
        number of trades, so the result does not depend on which other slices the report had."""
        kind, _, side = stat.removeprefix("ci_").rpartition("_")
        builder = self.builder
        if kind == "amount":
            found = builder.amounts(slice_id.removeprefix("beh~"))
            if found is None:
                raise UnresolvableSource(slice_id)
            mask, amount = found
            bounds = mean_bootstrap(amount[mask], self.params.resamples, self.params.seed)
            # The report shows the shortfall as a negative number, so the bounds swap and flip.
            flipped = None if bounds is None else (-bounds[1], -bounds[0])
            return _pick(flipped, side, stat)
        defn = builder.get(slice_id)
        if defn is None:
            raise UnresolvableSource(slice_id)
        interval = bootstrap_intervals(
            builder.pnl,
            builder.r,
            [(defn.mask, defn.rest)],
            self.params.resamples,
            self.params.seed,
        )[0]
        if kind == "pnl":
            return _pick((interval.pnl_low, interval.pnl_high), side, stat)
        if kind == "r":
            return _pick((interval.r_low, interval.r_high), side, stat)
        raise UnresolvableSource(stat)

    def _measured(self, name: str, stat: str) -> float | None:
        found = self.builder.amounts(name)
        if found is None:
            raise UnresolvableSource(name)
        mask, amount = found
        frame = self.builder.frame
        inside = frame.filter(pl.Series(mask))
        values = pl.Series(amount[mask])
        if stat == "n":
            return float(inside.height)
        if stat == "mean_pnl":
            return _mean(inside["pnl"])
        if stat == "total_pnl":
            return float(inside["pnl"].sum())
        if stat == "mean_amount":
            mean = _mean(values)
            return None if mean is None else -mean  # shown as a shortfall, so negative
        if stat == "total_amount":
            return float(values.sum())
        raise UnresolvableSource(stat)

    # ----- trades and meta -----

    def _trade(self, trade_key: str) -> float | None:
        row = self.trades.filter(pl.col("trade_key") == trade_key)
        return float(row["pnl"][0]) if row.height else None

    def _meta(self, name: str) -> float | None:
        if name == "tests_run":
            return float(find_all(self.builder, self.currency).tests_run)
        if name == "no_risk_trades":
            risk = self.trades["planned_risk"]
            return float((risk.is_null() | (risk.fill_null(1.0) <= 0)).sum())
        if name == "overtrading_limit":
            # Twice the median trades per day, if that is above the configured limit.
            per_day = self.trades.group_by("entry_day").len()["len"].to_numpy()
            doubled = int(np.ceil(2 * float(np.median(per_day)))) if per_day.size else 0
            return float(max(self.params.overtrading_threshold, doubled))
        if name == "excluded_no_fx":
            return float(self.excluded_no_fx)
        raise UnresolvableSource(name)


def _pick(
    bounds: tuple[float, float] | tuple[float | None, float | None] | None, side: str, name: str
) -> float | None:
    if side not in ("low", "high"):
        raise UnresolvableSource(name)
    if bounds is None:
        return None
    value = bounds[0] if side == "low" else bounds[1]
    return None if value is None else float(value)


def _mean(values: pl.Series) -> float | None:
    mean = values.mean()
    return float(mean) if isinstance(mean, int | float) else None
