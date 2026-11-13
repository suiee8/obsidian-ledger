"""Assemble the analysis report, the segment tables, and simulator results.

Results are cached by dataset version and parameters, so a change to the trades or to the
starting equity invalidates them.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import threading
from collections import Counter, OrderedDict
from dataclasses import asdict, dataclass
from typing import Any, Final, cast

import numpy as np
import orjson
import polars as pl

from obsidian_ledger.metrics import explore, timelines
from obsidian_ledger.metrics.behavior import analyze_behavior
from obsidian_ledger.metrics.core import core_metrics, period_extremes
from obsidian_ledger.metrics.data import LOW_CONFIDENCE_N, Filters, Prepared, prepare
from obsidian_ledger.metrics.discipline import FORMULA, WEIGHTS, discipline_score
from obsidian_ledger.metrics.risk import (
    daily_ratios,
    drawdown,
    kelly_upper_bound,
    risk_per_trade,
    sqn,
)
from obsidian_ledger.metrics.segments import segment_table
from obsidian_ledger.metrics.simulator import Rules
from obsidian_ledger.metrics.simulator import simulate as run_simulation
from obsidian_ledger.metrics.stats import bootstrap_summary, monte_carlo
from obsidian_ledger.metrics.views import (
    daily_series,
    edge_radar,
    equity_series,
    r_histogram,
    top_findings,
    weekday_hour_heatmap,
)
from obsidian_ledger.store.db import Store

STARTING_EQUITY_KEY: Final = "starting_equity"
CACHE_SIZE: Final = 64
WIRE_CACHE_SIZE: Final = 16
GZIP_LEVEL: Final = 3  # level 3 is within a few percent of level 6 on JSON, at a third of the time
KELLY_WARNING: Final = (
    "Kelly is shown as an upper bound on the fraction of equity to risk. It assumes the "
    "measured edge is real and stable. Do not size positions from it."
)


@dataclass(frozen=True)
class Params:
    bootstrap_resamples: int = 1000
    mc_paths: int = 5000
    seed: int = 42
    overtrading_threshold: int = 10
    revenge_gap_minutes: float = 10.0
    size_jump: float = 0.5
    drawdown_pct: float = 0.20
    target_pct: float = 0.10


class AnalysisEngine:
    def __init__(self, store: Store) -> None:
        self.store = store
        self._cache: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._raw: tuple[str, pl.DataFrame] | None = None
        self._wire: OrderedDict[str, tuple[bytes, bytes]] = OrderedDict()
        self._lock = threading.Lock()

    def _raw_frame(self) -> tuple[str, pl.DataFrame]:
        version = self.store.dataset_version()
        if self._raw is None or self._raw[0] != version:
            self._raw = (version, self.store.load_frame())
        return self._raw

    def starting_equity(self) -> float | None:
        """The starting equity the user set, if any."""
        return self._starting_equity()

    def trades_for(self, filters: Filters) -> tuple[str, Prepared]:
        """(dataset version, filtered trades with derived columns). The frame is cached."""
        return self._prepared(filters)

    def availability(self, filters: Filters) -> dict[str, Any]:
        """Return P&L availability and non-P&L activity for the current selection."""
        version, prepared = self._prepared(filters)
        if prepared.frame.height or not prepared.unpriced.height:
            return {
                "available": True,
                "has_pnl": prepared.frame.height > 0,
                "has_prices": True,
                "message": None,
                "activity": None,
                "dataset_version": version,
            }
        report = self._unavailable_report(version, prepared.unpriced, self._starting_equity())
        return {
            "available": False,
            **report["availability"],
            "activity": report["activity"],
            "dataset_version": version,
        }

    def _starting_equity(self) -> float | None:
        raw = self.store.get_setting(STARTING_EQUITY_KEY)
        return float(raw) if raw is not None else None

    def _cached(self, key: str, compute: Any) -> dict[str, Any]:
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
        result = compute()
        with self._lock:
            self._cache[key] = result
            self._cache.move_to_end(key)
            while len(self._cache) > CACHE_SIZE:
                self._cache.popitem(last=False)
        return result

    def _prepared(self, filters: Filters) -> tuple[str, Prepared]:
        version, raw = self._raw_frame()
        return version, prepare(raw, filters)

    def report(self, filters: Filters, params: Params) -> dict[str, Any]:
        version = self.store.dataset_version()
        key = json.dumps({"v": version, "f": filters.key(), "p": asdict(params)}, sort_keys=True)
        return self._cached(key, lambda: self._build_report(filters, params))

    def _build_report(self, filters: Filters, params: Params) -> dict[str, Any]:
        version, prepared = self._prepared(filters)
        starting = self._starting_equity()
        frame = prepared.frame
        if frame.height == 0 and prepared.unpriced.height:
            return self._unavailable_report(version, prepared.unpriced, starting)
        if frame.height == 0:
            return _empty_report(version, prepared.excluded_no_fx, starting)

        pnl = frame["pnl"].to_numpy()
        costs = frame["costs"].to_numpy()
        r = frame["r_multiple"].to_numpy().astype(np.float64)
        core = core_metrics(pnl, costs, r)
        dd = drawdown(pnl, starting)
        daily = (
            frame.group_by("exit_day").agg(pl.col("pnl").sum()).sort("exit_day")["pnl"].to_numpy()
        )
        ratios = daily_ratios(daily, starting, dd["max_drawdown_pct"])
        risk_values = frame["planned_risk"].to_numpy().astype(np.float64)
        behavior = analyze_behavior(
            frame,
            params.overtrading_threshold,
            params.revenge_gap_minutes,
            params.size_jump,
        )
        risk_stats = risk_per_trade(risk_values)
        stop_known = frame["stop_loss"].is_not_null().to_numpy()
        stop_rate = float(stop_known.mean()) if stop_known.size else None
        discipline = discipline_score(behavior, risk_stats["coefficient_of_variation"], stop_rate)

        avg_loss = core.get("avg_loss")
        drawdown_threshold = (
            params.drawdown_pct * starting if starting else 10.0 * (avg_loss or 0.0)
        )
        target = params.target_pct * starting if starting else 0.0
        monte = monte_carlo(
            pnl,
            params.mc_paths,
            params.seed,
            starting,
            drawdown_threshold,
            target,
        )
        bootstrap = bootstrap_summary(pnl, params.bootstrap_resamples, params.seed)

        caveats = _caveats(frame, prepared.excluded_no_fx, starting, core["trades"])
        return {
            "dataset_version": version,
            "filters": {
                "date_from": filters.date_from.isoformat() if filters.date_from else None,
                "date_to": filters.date_to.isoformat() if filters.date_to else None,
                "accounts": list(filters.accounts),
                "symbols": list(filters.symbols),
                "setups": list(filters.setups),
                "sides": list(filters.sides),
                "tag": filters.tag,
            },
            "sample": {
                "trades": core["trades"],
                "excluded_no_fx": prepared.excluded_no_fx,
                "low_confidence": core["trades"] < LOW_CONFIDENCE_N,
                "low_confidence_threshold": LOW_CONFIDENCE_N,
                "starting_equity": starting,
            },
            "core": core,
            "period_extremes": period_extremes(frame),
            "risk": {
                "drawdown": dd,
                "daily_ratios": ratios,
                "sqn": sqn(r),
                "kelly_upper_bound": kelly_upper_bound(
                    core.get("win_rate"), core.get("payoff_ratio")
                ),
                "kelly_warning": KELLY_WARNING,
                "risk_per_trade": risk_stats,
                "expectancy_r": core.get("expectancy_r"),
            },
            "statistics": {"bootstrap": bootstrap, "monte_carlo": monte},
            "behavior": behavior,
            "discipline": discipline,
            "caveats": caveats,
        }

    def _unavailable_report(
        self, version: str, trades: pl.DataFrame, starting: float | None
    ) -> dict[str, Any]:
        """Report activity that remains valid when source rows contain no P&L."""
        report = _empty_report(version, 0, starting)
        count = trades.height
        report["sample"].update(trades=count, low_confidence=count < LOW_CONFIDENCE_N)
        report["core"].update(trades=count, wins=None, losses=None, flat=None)
        report["risk"]["drawdown"] = {
            "max_drawdown": None,
            "max_drawdown_pct": None,
            "recovered": None,
        }
        report["risk"]["daily_ratios"] = {
            "available": False,
            "reason": (
                "Not available: this file has no P&L. Import realized P&L to enable "
                "performance metrics."
            ),
        }

        latest = self.store.latest_import()
        capabilities = cast(dict[str, bool], latest.get("capabilities", {})) if latest else {}
        has_prices = bool(capabilities.get("has_price", False))
        report["availability"] = {
            "has_pnl": False,
            "has_prices": has_prices,
            "message": (
                "Not available: this file has no P&L or prices. "
                "Import realized P&L and entry/exit prices to enable performance metrics."
                if not has_prices
                else (
                    "Not available: this file has no P&L. Import realized P&L to enable "
                    "performance metrics."
                )
            ),
        }

        import_id = str(latest["import_id"]) if latest and latest.get("import_id") else None
        events = self.store.load_activity_frame(import_id)
        symbols: Counter[str] = Counter()
        days: Counter[str] = Counter()
        hours: Counter[int] = Counter()
        directions: Counter[str] = Counter()
        order_types: Counter[str] = Counter()
        leverage_values: list[float] = []
        trades_per_day: Counter[str] = Counter()
        if "entry_time" in trades.columns:
            for entry_time in trades.get_column("entry_time").drop_nulls().to_list():
                trades_per_day[entry_time.date().isoformat()] += 1
        for event in events.iter_rows(named=True):
            symbol = event.get("symbol")
            if symbol:
                symbols[str(symbol)] += 1
            timestamp = event.get("event_time")
            if timestamp is not None:
                days[timestamp.date().isoformat()] += 1
                hours[timestamp.hour] += 1
            direction = event.get("direction")
            if direction:
                directions[str(direction)] += 1
            order_type = event.get("order_type")
            if order_type:
                order_types[str(order_type)] += 1
            leverage = event.get("leverage")
            if leverage is not None:
                leverage_values.append(float(leverage))

        precision = (
            trades.get_column("time_precision").unique().to_list()
            if "time_precision" in trades.columns
            else []
        )
        hold_values = trades.get_column("holding_seconds").drop_nulls().to_list()
        report["activity"] = {
            "trades": count,
            "source_events": events.height,
            "symbols": len(symbols),
            "by_symbol": [
                {"symbol": name, "events": total} for name, total in symbols.most_common()
            ],
            "by_day": [{"day": day, "events": total} for day, total in sorted(days.items())],
            "by_hour": [{"hour": hour, "events": total} for hour, total in sorted(hours.items())],
            "directions": dict(directions),
            "order_types": dict(order_types),
            "leverage_values": len(leverage_values),
            "average_leverage": (
                sum(leverage_values) / len(leverage_values) if leverage_values else None
            ),
            "hold_times_available": bool(hold_values),
            "average_holding_seconds": (
                sum(hold_values) / len(hold_values) if hold_values else None
            ),
            "time_precision": precision,
            "overtraded_days": sum(total > 10 for total in trades_per_day.values()),
        }
        report["caveats"] = [
            report["availability"]["message"],
            "Trade counts, activity, and holding time are available; P&L-based metrics are not.",
        ]
        return report

    def dashboard(self, filters: Filters) -> dict[str, Any]:
        """Everything the Dashboard draws, in one cached response.

        The headline report uses a small bootstrap and Monte Carlo size so the page opens quickly.
        The full report is available from /api/metrics.
        """
        version = self.store.dataset_version()
        key = json.dumps({"v": version, "f": filters.key(), "dash": True}, sort_keys=True)

        def compute() -> dict[str, Any]:
            report = self.report(filters, Params(bootstrap_resamples=200, mc_paths=500))
            _version, prepared = self._prepared(filters)
            frame = prepared.frame
            return {
                "dataset_version": version,
                "report": report,
                "equity": equity_series(frame, self._starting_equity()),
                "daily": daily_series(frame),
                "r_histogram": r_histogram(frame),
                "heatmap": weekday_hour_heatmap(frame),
                "radar": edge_radar(frame, LOW_CONFIDENCE_N),
                "findings": top_findings(frame, LOW_CONFIDENCE_N),
            }

        return self._cached(key, compute)

    def explore(self, filters: Filters) -> dict[str, Any]:
        """Per-trade points, MAE/MFE, streaks, and fee drag for the Analytics screen."""
        version = self.store.dataset_version()
        key = json.dumps({"v": version, "f": filters.key(), "explore": True}, sort_keys=True)

        def compute() -> dict[str, Any]:
            _version, prepared = self._prepared(filters)
            frame = prepared.frame
            return {
                "dataset_version": version,
                "points": explore.points(frame),
                "mae_mfe": explore.mae_mfe(frame),
                "streaks": explore.streaks(frame),
                "fee_drag": explore.fee_drag(frame),
            }

        return self._cached(key, compute)

    def behavior_timeline(self, filters: Filters, params: Params) -> dict[str, Any]:
        version = self.store.dataset_version()
        key = json.dumps({"v": version, "f": filters.key(), "tl": asdict(params)}, sort_keys=True)

        def compute() -> dict[str, Any]:
            _version, prepared = self._prepared(filters)
            result = timelines.behavior_timeline(
                prepared.frame,
                overtrading_threshold=params.overtrading_threshold,
                revenge_gap_minutes=params.revenge_gap_minutes,
                size_jump=params.size_jump,
            )
            result["dataset_version"] = version
            return result

        return self._cached(key, compute)

    def select_trades(
        self, filters: Filters, bounds: list[tuple[str, float | None, float | None]]
    ) -> list[str]:
        """Trade keys inside every brush bound, for the Trades table."""
        _version, prepared = self._prepared(filters)
        return explore.select_keys(prepared.frame, bounds)

    def reset(self) -> None:
        """Forget everything, including the loaded trade frame. Used after a wipe."""
        with self._lock:
            self._cache.clear()
            self._wire.clear()
            self._raw = None

    def clear_results(self) -> None:
        """Drop computed results but keep the loaded trade frame. A new filter starts here."""
        with self._lock:
            self._cache.clear()
            self._wire.clear()

    def dashboard_bytes(self, filters: Filters) -> tuple[str, bytes, bytes]:
        """(etag, json, gzipped json) for the dashboard, cached by dataset version and filters.

        The payload is serialized once with orjson and compressed once at a low level, so a
        repeat request is a dictionary lookup and a socket write. NaN becomes null.
        """
        etag = self.dashboard_etag(filters)
        with self._lock:
            hit = self._wire.get(etag)
            if hit is not None:
                self._wire.move_to_end(etag)
                return etag, hit[0], hit[1]
        payload = self.dashboard(filters)
        raw = orjson.dumps(payload, option=orjson.OPT_SERIALIZE_NUMPY | orjson.OPT_NON_STR_KEYS)
        packed = gzip.compress(raw, compresslevel=GZIP_LEVEL)
        with self._lock:
            self._wire[etag] = (raw, packed)
            self._wire.move_to_end(etag)
            while len(self._wire) > WIRE_CACHE_SIZE:
                self._wire.popitem(last=False)
        return etag, raw, packed

    def dashboard_etag(self, filters: Filters) -> str:
        """Changes whenever trades, the starting equity, or the filters change.

        Settings changes bump the dataset version, so a matching ETag means the cached payload
        is still current and the dashboard does not need to be computed.
        """
        basis = f"{self.store.dataset_version()}|{filters.key()}"
        return '"' + hashlib.sha256(basis.encode("utf-8")).hexdigest()[:32] + '"'

    def segments(self, filters: Filters, dimension: str, min_n: int) -> dict[str, Any]:
        version = self.store.dataset_version()
        key = json.dumps(
            {"v": version, "f": filters.key(), "seg": dimension, "min": min_n}, sort_keys=True
        )

        def compute() -> dict[str, Any]:
            _version, prepared = self._prepared(filters)
            return segment_table(prepared.frame, dimension, min_n)

        return self._cached(key, compute)

    def simulate(
        self,
        filters: Filters,
        rules: Rules,
        resamples: int,
        seed: int,
        intervals: bool = True,
    ) -> dict[str, Any]:
        """Cached by dataset version, filters, rules, and resampling parameters."""
        version = self.store.dataset_version()
        key = json.dumps(
            {
                "v": version,
                "f": filters.key(),
                "sim": asdict(rules),
                "n": resamples,
                "seed": seed,
                "iv": intervals,
            },
            sort_keys=True,
        )

        def compute() -> dict[str, Any]:
            prepared = self._prepared(filters)[1]
            result = run_simulation(prepared.frame, rules, resamples, seed, intervals)
            result["dataset_version"] = version
            result["sample"] = {"excluded_no_fx": prepared.excluded_no_fx}
            return result

        return self._cached(key, compute)


def _empty_report(version: str, excluded: int, starting: float | None) -> dict[str, Any]:
    """The report for a selection with no trades. It has every section a populated report has,
    with null or zero values, so clients can read one shape whatever the filters are."""
    return {
        "dataset_version": version,
        "sample": {
            "trades": 0,
            "excluded_no_fx": excluded,
            "low_confidence": True,
            "low_confidence_threshold": LOW_CONFIDENCE_N,
            "starting_equity": starting,
        },
        "core": {
            "trades": 0,
            "wins": 0,
            "losses": 0,
            "flat": 0,
            "net_pnl": None,
            "win_rate": None,
            "profit_factor": None,
            "expectancy": None,
            "expectancy_r": None,
            "payoff_ratio": None,
            "fee_drag": None,
            "largest_win": None,
            "largest_loss": None,
        },
        "risk": {
            "drawdown": {"max_drawdown": 0.0, "max_drawdown_pct": None, "recovered": True},
            "daily_ratios": {"available": False, "reason": "No trades in this selection."},
            "sqn": None,
            "kelly_upper_bound": None,
            "kelly_warning": KELLY_WARNING,
            "risk_per_trade": None,
            "expectancy_r": None,
        },
        "discipline": {
            "score": None,
            "components_used": 0,
            "components_total": len(WEIGHTS),
            "formula": FORMULA,
            "components": {},
            "weights": dict(WEIGHTS),
        },
        "caveats": ["No trades match these filters."],
    }


def _caveats(frame: pl.DataFrame, excluded: int, starting: float | None, trades: int) -> list[str]:
    notes: list[str] = []
    if trades < LOW_CONFIDENCE_N:
        notes.append(
            f"Only {trades} trades in this selection. Results are low confidence below "
            f"{LOW_CONFIDENCE_N} trades."
        )
    if excluded:
        notes.append(
            f"{excluded} trades were left out because no FX rate converts them to base currency."
        )
    if starting is None:
        notes.append(
            "No starting equity is set, so Sharpe, Sortino, Calmar, and drawdown "
            "percentages are unavailable."
        )
    unknown_plan = frame["plan_followed"].is_null().sum()
    if unknown_plan:
        notes.append(
            f"{unknown_plan} trades have no plan-followed value, so adherence uses the rest."
        )
    no_risk = frame["planned_risk"].is_null().sum()
    if no_risk:
        notes.append(
            f"{no_risk} trades have no planned risk, so their R multiples are unavailable."
        )
    no_excursion = frame["mfe"].is_null().sum()
    if no_excursion:
        notes.append(f"{no_excursion} trades have no MFE, so exit efficiency uses the rest.")
    return notes
