"""What-if simulator for trading rules, replayed in time order without look-ahead.

Each trade gets its features once. Static rules (symbol, hour, setup) are boolean masks over
those features, applied in one vector step. Only the daily-state rules (trade count, losses,
daily loss cap) depend on earlier decisions, so only they need a sequential pass. That pass
visits just the trades that passed the static masks.
"""

from __future__ import annotations

import heapq
from dataclasses import asdict, dataclass
from typing import Any, Final

import numpy as np
import numpy.typing as npt
import polars as pl

from obsidian_ledger.metrics.risk import drawdown
from obsidian_ledger.metrics.stats import bootstrap_summary

Array = npt.NDArray[np.float64]
OVERFIT_WARNING: Final = (
    "These rules were chosen after looking at this same sample, so the improvement is "
    "likely to be overstated. Test them on trades they were not chosen from before relying on them."
)


@dataclass(frozen=True)
class Rules:
    daily_loss_cap: float | None = None  # stop taking trades after this much loss in a day
    max_trades_per_day: int | None = None
    stop_after_losses: int | None = None  # losses in one day before trading stops for that day
    exclude_symbols: tuple[str, ...] = ()
    exclude_hours: tuple[int, ...] = ()  # UTC entry hours to skip
    exclude_setups: tuple[str, ...] = ()
    cap_risk_per_trade: float | None = None  # scale a trade's P&L down when its risk exceeds this

    def is_empty(self) -> bool:
        return asdict(self) == asdict(Rules())

    def has_daily_state(self) -> bool:
        return (
            self.daily_loss_cap is not None
            or self.max_trades_per_day is not None
            or self.stop_after_losses is not None
        )


def _static_masks(rows: pl.DataFrame, rules: Rules) -> tuple[npt.NDArray[np.bool_], dict[str, int]]:
    """Mask of trades removed by static rules, plus the count per reason.

    A trade is counted under the first rule that removes it, in the order symbol, hour, setup.
    """
    count = rows.height
    symbol_out = rows.get_column("symbol").fill_null("unknown").is_in(list(rules.exclude_symbols))
    hour_out = rows.get_column("hour_utc").is_in(list(rules.exclude_hours))
    setup_out = rows.get_column("setup").fill_null("unknown").is_in(list(rules.exclude_setups))
    symbol_mask = symbol_out.to_numpy() if rules.exclude_symbols else np.zeros(count, bool)
    hour_mask = hour_out.to_numpy() if rules.exclude_hours else np.zeros(count, bool)
    setup_mask = setup_out.to_numpy() if rules.exclude_setups else np.zeros(count, bool)
    hour_first = hour_mask & ~symbol_mask
    setup_first = setup_mask & ~symbol_mask & ~hour_mask
    removed = symbol_mask | hour_mask | setup_mask
    reasons = {
        "symbol": int(symbol_mask.sum()),
        "hour": int(hour_first.sum()),
        "setup": int(setup_first.sum()),
    }
    return removed, reasons


def _daily_replay(
    rules: Rules,
    candidates: npt.NDArray[np.intp],
    entry_epoch: npt.NDArray[np.float64],
    exit_epoch: npt.NDArray[np.float64],
    day_code: npt.NDArray[np.intp],
    pnl_scaled: npt.NDArray[np.float64],
) -> tuple[npt.NDArray[np.bool_], dict[str, int]]:
    """Sequential pass over candidate trades, applying the rules that depend on the day so far.

    A trade's result is added to its entry day's loss tally only once it has exited, so the
    decision uses only information known at entry. Returns the taken mask and skipped counts.
    """
    taken = np.zeros(entry_epoch.size, dtype=bool)
    skipped = {"max_trades": 0, "losses": 0, "daily_loss": 0}
    day_taken: dict[int, int] = {}
    day_losses: dict[int, int] = {}
    day_realized: dict[int, float] = {}
    pending: list[tuple[float, int, int, float]] = []
    for index in candidates.tolist():
        now = entry_epoch[index]
        while pending and pending[0][0] <= now:
            _exit, _seq, code, value = heapq.heappop(pending)
            day_realized[code] = day_realized.get(code, 0.0) + value
            if value < 0:
                day_losses[code] = day_losses.get(code, 0) + 1
        code = int(day_code[index])
        if (
            rules.max_trades_per_day is not None
            and day_taken.get(code, 0) >= rules.max_trades_per_day
        ):
            skipped["max_trades"] += 1
            continue
        if (
            rules.stop_after_losses is not None
            and day_losses.get(code, 0) >= rules.stop_after_losses
        ):
            skipped["losses"] += 1
            continue
        if (
            rules.daily_loss_cap is not None
            and day_realized.get(code, 0.0) <= -rules.daily_loss_cap
        ):
            skipped["daily_loss"] += 1
            continue
        value = float(pnl_scaled[index])
        day_taken[code] = day_taken.get(code, 0) + 1
        taken[index] = True
        heapq.heappush(pending, (float(exit_epoch[index]), index, code, value))
    return taken, skipped


CURVE_POINTS: Final = 300


def _active_rules(rules: Rules) -> int:
    return sum(
        [
            rules.daily_loss_cap is not None,
            rules.max_trades_per_day is not None,
            rules.stop_after_losses is not None,
            bool(rules.exclude_symbols),
            bool(rules.exclude_hours),
            bool(rules.exclude_setups),
            rules.cap_risk_per_trade is not None,
        ]
    )


def overfit_assessment(rules: Rules, count: int, kept: int) -> dict[str, Any]:
    """Reasons these particular rules are likely to look better here than they would later."""
    active = _active_rules(rules)
    reasons: list[str] = []
    if active and count < 100:
        reasons.append(f"Only {count} trades. Small samples make almost any rule look good.")
    if active >= 3:
        reasons.append(
            f"{active} rules are combined, which gives the sample more ways to be fitted."
        )
    if active and count and kept / count < 0.5:
        reasons.append("The rules remove more than half of your trades.")
    if rules.exclude_symbols or rules.exclude_hours or rules.exclude_setups:
        reasons.append(
            "Excluded symbols, hours, or setups were picked from the same trades they are "
            "tested on."
        )
    return {"level": "high" if reasons else "standard", "active_rules": active, "reasons": reasons}


def _curve(baseline: npt.NDArray[np.float64], simulated: npt.NDArray[np.float64]) -> dict[str, Any]:
    """Cumulative P&L in exit order for both paths, thinned to about CURVE_POINTS points."""
    count = baseline.size
    index = np.unique(np.linspace(0, count - 1, min(count, CURVE_POINTS)).astype(np.intp))
    return {
        "trades": count,
        "x": (index + 1).tolist(),
        "baseline": np.round(np.cumsum(baseline)[index], 2).tolist(),
        "simulated": np.round(np.cumsum(simulated)[index], 2).tolist(),
    }


def simulate(
    frame: pl.DataFrame, rules: Rules, resamples: int, seed: int, intervals: bool = True
) -> dict[str, Any]:
    """Replay trades in entry order under the rules and compare with the unchanged sample.

    With `intervals` off the point estimate is returned at once and the bootstrap is skipped.
    """
    rows = frame.sort(["entry_time", "trade_key"])
    count = rows.height
    if count == 0:
        return {"trades": 0, "rules": asdict(rules), "warning": OVERFIT_WARNING}

    pnl = rows.get_column("pnl").to_numpy().astype(np.float64)
    risk = rows.get_column("planned_risk").to_numpy().astype(np.float64)
    entry_epoch = rows.get_column("entry_time").dt.epoch("s").to_numpy().astype(np.float64)
    exit_epoch = rows.get_column("exit_time").dt.epoch("s").to_numpy().astype(np.float64)
    day_code = rows.get_column("entry_day").rank("dense").to_numpy().astype(np.intp) - 1

    removed, skipped = _static_masks(rows, rules)
    # A trade's P&L is scaled down when its risk exceeds the cap. Scaling is a per-trade factor.
    scale = np.ones(count, dtype=np.float64)
    if rules.cap_risk_per_trade is not None:
        over = np.isfinite(risk) & (risk > rules.cap_risk_per_trade)
        scale[over] = rules.cap_risk_per_trade / risk[over]
    else:
        over = np.zeros(count, dtype=bool)
    pnl_scaled = pnl * scale

    candidates = np.flatnonzero(~removed)
    if rules.has_daily_state() and candidates.size:
        taken, daily_skipped = _daily_replay(
            rules, candidates, entry_epoch, exit_epoch, day_code, pnl_scaled
        )
        skipped.update(daily_skipped)
    else:
        taken = ~removed
    risk_capped = int((taken & over).sum())

    simulated = np.where(taken, pnl_scaled, 0.0)
    exits = rows.get_column("exit_time").to_numpy()
    order = np.argsort(exits, kind="stable")
    baseline_path = drawdown(pnl[order], None)
    kept_order = order[taken[order]]
    simulated_path = drawdown(simulated[kept_order], None)
    delta = simulated - pnl
    base_mean = float(pnl.mean())
    sim_kept = simulated[taken]
    sim_mean = float(sim_kept.mean()) if sim_kept.size else None
    if intervals:
        interval = bootstrap_summary(delta, resamples, seed)["expectancy"]
        point, ci95 = interval["point"], interval["ci95"]
    else:
        point, ci95 = float(delta.mean()), None
    net_ci95 = [ci95[0] * count, ci95[1] * count] if ci95 else None
    return {
        "trades": count,
        "kept_trades": int(taken.sum()),
        "removed_trades": int(count - taken.sum()),
        "skipped_by_reason": {reason: n for reason, n in skipped.items() if n},
        "risk_capped_trades": risk_capped,
        "rules": asdict(rules),
        "baseline": {
            "net_pnl": float(pnl.sum()),
            "expectancy": base_mean,
            "max_drawdown": baseline_path["max_drawdown"],
        },
        "simulated": {
            "net_pnl": float(simulated.sum()),
            "expectancy": sim_mean,
            "max_drawdown": simulated_path["max_drawdown"],
        },
        "change": {
            "net_pnl": float(simulated.sum() - pnl.sum()),
            "expectancy_per_trade": point,
            "expectancy_per_trade_ci95": ci95,
            "net_pnl_ci95": net_ci95,
            "method": (
                "Paired bootstrap of the per-trade change, with skipped trades counted as zero."
            ),
        },
        "warning": OVERFIT_WARNING,
        "overfit": overfit_assessment(rules, count, int(taken.sum())),
        "intervals": "ready" if intervals else "pending",
        "curves": _curve(pnl[order], simulated[order]),
        "no_rules_set": rules.is_empty(),
    }
