"""HTTP routes for the analysis engine."""

from __future__ import annotations

import csv
import io
from datetime import date
from typing import Annotated, Any, Literal

import orjson
from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from obsidian_ledger.csvsafe import neutralize_cell, neutralize_csv
from obsidian_ledger.metrics.data import Filters
from obsidian_ledger.metrics.engine import AnalysisEngine, Params
from obsidian_ledger.metrics.segments import DIMENSIONS
from obsidian_ledger.metrics.simulator import Rules
from obsidian_ledger.workspace.selection import SelectionStore

router = APIRouter(prefix="/api", tags=["analysis"])


class FiltersIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date_from: date | None = None
    date_to: date | None = None
    accounts: list[str] = Field(default_factory=list[str])
    symbols: list[str] = Field(default_factory=list[str])
    setups: list[str] = Field(default_factory=list[str])
    sides: list[str] = Field(default_factory=list[str])
    tag: str | None = None

    def to_filters(self) -> Filters:
        return Filters(
            date_from=self.date_from,
            date_to=self.date_to,
            accounts=tuple(self.accounts),
            symbols=tuple(self.symbols),
            setups=tuple(self.setups),
            sides=tuple(self.sides),
            tag=self.tag,
        )


class RulesIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    daily_loss_cap: float | None = Field(default=None, gt=0)
    max_trades_per_day: int | None = Field(default=None, ge=1)
    stop_after_losses: int | None = Field(default=None, ge=1)
    exclude_symbols: list[str] = Field(default_factory=list[str])
    exclude_hours: list[int] = Field(default_factory=list[int])
    exclude_setups: list[str] = Field(default_factory=list[str])
    cap_risk_per_trade: float | None = Field(default=None, gt=0)

    def to_rules(self) -> Rules:
        return Rules(
            daily_loss_cap=self.daily_loss_cap,
            max_trades_per_day=self.max_trades_per_day,
            stop_after_losses=self.stop_after_losses,
            exclude_symbols=tuple(self.exclude_symbols),
            exclude_hours=tuple(h for h in self.exclude_hours if 0 <= h <= 23),
            exclude_setups=tuple(self.exclude_setups),
            cap_risk_per_trade=self.cap_risk_per_trade,
        )


class SimulateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filters: FiltersIn = Field(default_factory=FiltersIn)
    rules: RulesIn
    resamples: int = Field(default=1000, ge=100, le=10000)
    seed: int = 42
    # False returns the point estimate at once and skips the bootstrap intervals.
    intervals: bool = True


class AxisBound(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: Literal["t", "pnl", "r", "mae", "mfe", "hold"]
    low: float | None = None
    high: float | None = None


class SelectionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filters: FiltersIn = Field(default_factory=FiltersIn)
    bounds: list[AxisBound] = Field(min_length=1, max_length=2)


def _engine(request: Request) -> AnalysisEngine:
    engine: AnalysisEngine = request.app.state.analysis
    return engine


@router.get("/metrics")
def metrics(
    request: Request,
    date_from: date | None = None,
    date_to: date | None = None,
    account: Annotated[list[str] | None, Query()] = None,
    symbol: Annotated[list[str] | None, Query()] = None,
    setup: Annotated[list[str] | None, Query()] = None,
    side: Annotated[list[str] | None, Query()] = None,
    tag: str | None = None,
    bootstrap: Annotated[int, Query(ge=100, le=10000)] = 1000,
    paths: Annotated[int, Query(ge=500, le=20000)] = 5000,
) -> dict[str, Any]:
    filters = Filters(
        date_from=date_from,
        date_to=date_to,
        accounts=tuple(account or []),
        symbols=tuple(symbol or []),
        setups=tuple(setup or []),
        sides=tuple(side or []),
        tag=tag,
    )
    params = Params(bootstrap_resamples=bootstrap, mc_paths=paths)
    return _engine(request).report(filters, params)


@router.get("/segments")
def segments(
    request: Request,
    by: str,
    min_n: Annotated[int, Query(ge=1, le=10000)] = 30,
    date_from: date | None = None,
    date_to: date | None = None,
    account: Annotated[list[str] | None, Query()] = None,
    symbol: Annotated[list[str] | None, Query()] = None,
    setup: Annotated[list[str] | None, Query()] = None,
    side: Annotated[list[str] | None, Query()] = None,
    tag: str | None = None,
) -> dict[str, Any]:
    if by not in DIMENSIONS:
        raise HTTPException(status_code=422, detail=f"by must be one of {', '.join(DIMENSIONS)}.")
    filters = Filters(
        date_from=date_from,
        date_to=date_to,
        accounts=tuple(account or []),
        symbols=tuple(symbol or []),
        setups=tuple(setup or []),
        sides=tuple(side or []),
        tag=tag,
    )
    return _engine(request).segments(filters, by, min_n)


@router.get("/segments/export")
def export_segments(
    request: Request,
    by: str,
    min_n: Annotated[int, Query(ge=1, le=10000)] = 30,
    date_from: date | None = None,
    date_to: date | None = None,
    account: Annotated[list[str] | None, Query()] = None,
    symbol: Annotated[list[str] | None, Query()] = None,
    setup: Annotated[list[str] | None, Query()] = None,
    side: Annotated[list[str] | None, Query()] = None,
    tag: str | None = None,
) -> Response:
    """Export segments as CSV with formula cells neutralized."""
    if by not in DIMENSIONS:
        raise HTTPException(status_code=422, detail=f"by must be one of {', '.join(DIMENSIONS)}.")
    filters = Filters(
        date_from=date_from,
        date_to=date_to,
        accounts=tuple(account or []),
        symbols=tuple(symbol or []),
        setups=tuple(setup or []),
        sides=tuple(side or []),
        tag=tag,
    )
    result = _engine(request).segments(filters, by, min_n)
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(
        [
            neutralize_cell("dimension"),
            neutralize_cell("key"),
            neutralize_cell("trades"),
            neutralize_cell("win_rate"),
            neutralize_cell("net_pnl"),
            neutralize_cell("profit_factor"),
            neutralize_cell("expectancy"),
        ]
    )
    for item in result.get("slices", []):
        writer.writerow(
            [
                neutralize_cell(by),
                neutralize_cell(str(item.get("value", ""))),
                neutralize_cell(str(item.get("n", 0))),
                neutralize_cell(str(item.get("win_rate", 0.0))),
                neutralize_cell(str(item.get("net_pnl", 0.0))),
                neutralize_cell(str(item.get("profit_factor", 0.0))),
                neutralize_cell(str(item.get("expectancy", 0.0))),
            ]
        )
    return Response(
        neutralize_csv(buffer.getvalue()),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="segments-{by}.csv"'},
    )


@router.post("/simulate")
def simulate_rules(request: Request, body: SimulateBody) -> dict[str, Any]:
    return _engine(request).simulate(
        body.filters.to_filters(),
        body.rules.to_rules(),
        body.resamples,
        body.seed,
        body.intervals,
    )


def _query_filters(
    date_from: date | None,
    date_to: date | None,
    account: list[str] | None,
    symbol: list[str] | None,
    setup: list[str] | None,
    side: list[str] | None,
    tag: str | None,
) -> Filters:
    return Filters(
        date_from=date_from,
        date_to=date_to,
        accounts=tuple(account or []),
        symbols=tuple(symbol or []),
        setups=tuple(setup or []),
        sides=tuple(side or []),
        tag=tag,
    )


@router.get("/explore", response_model=None)
def explore(
    request: Request,
    date_from: date | None = None,
    date_to: date | None = None,
    account: Annotated[list[str] | None, Query()] = None,
    symbol: Annotated[list[str] | None, Query()] = None,
    setup: Annotated[list[str] | None, Query()] = None,
    side: Annotated[list[str] | None, Query()] = None,
    tag: str | None = None,
) -> Response:
    """Per-trade points (columnar), MAE/MFE, streaks, and fee drag for the Analytics screen."""
    filters = _query_filters(date_from, date_to, account, symbol, setup, side, tag)
    payload = _engine(request).explore(filters)
    raw = orjson.dumps(payload, option=orjson.OPT_SERIALIZE_NUMPY)
    return Response(raw, media_type="application/json")


@router.get("/behavior/timeline")
def behavior_timeline(
    request: Request,
    date_from: date | None = None,
    date_to: date | None = None,
    account: Annotated[list[str] | None, Query()] = None,
    symbol: Annotated[list[str] | None, Query()] = None,
    setup: Annotated[list[str] | None, Query()] = None,
    side: Annotated[list[str] | None, Query()] = None,
    tag: str | None = None,
) -> dict[str, Any]:
    """Daily revenge, tilt, and overtrading counts, and performance after a loss."""
    filters = _query_filters(date_from, date_to, account, symbol, setup, side, tag)
    return _engine(request).behavior_timeline(filters, Params())


@router.post("/selections")
def create_selection(request: Request, body: SelectionBody) -> dict[str, Any]:
    """Turn a brushed range on a chart into a set of trades the Trades table can show."""
    bounds = [(bound.field, bound.low, bound.high) for bound in body.bounds]
    keys = _engine(request).select_trades(body.filters.to_filters(), bounds)
    selections: SelectionStore = request.app.state.selections
    selection = selections.add(keys)
    return {"selection_id": selection.selection_id, "count": len(keys)}


@router.get("/dashboard", response_model=None)
def dashboard(
    request: Request,
    date_from: date | None = None,
    date_to: date | None = None,
    account: Annotated[list[str] | None, Query()] = None,
    symbol: Annotated[list[str] | None, Query()] = None,
    setup: Annotated[list[str] | None, Query()] = None,
    side: Annotated[list[str] | None, Query()] = None,
    tag: str | None = None,
) -> Response:
    filters = Filters(
        date_from=date_from,
        date_to=date_to,
        accounts=tuple(account or []),
        symbols=tuple(symbol or []),
        setups=tuple(setup or []),
        sides=tuple(side or []),
        tag=tag,
    )
    engine = _engine(request)
    headers = {
        "ETag": engine.dashboard_etag(filters),
        "Cache-Control": "no-cache",
        "Vary": "Accept-Encoding",
    }
    if request.headers.get("if-none-match") == headers["ETag"]:
        return Response(status_code=304, headers=headers)
    _etag, raw, packed = engine.dashboard_bytes(filters)
    if "gzip" in request.headers.get("accept-encoding", ""):
        return Response(
            packed,
            media_type="application/json",
            headers={**headers, "Content-Encoding": "gzip"},
        )
    return Response(raw, media_type="application/json", headers=headers)
