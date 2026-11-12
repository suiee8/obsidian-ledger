"""Trade table, trade detail, inline edits, filter menus, and saved views."""

from __future__ import annotations

import math
from datetime import date, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Path, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from obsidian_ledger.csvsafe import neutralize_csv, neutralize_frame
from obsidian_ledger.metrics.data import Filters
from obsidian_ledger.store.db import Store
from obsidian_ledger.store.queries import EDITABLE, order_clause, where_clause
from obsidian_ledger.workspace.selection import SelectionStore

router = APIRouter(prefix="/api", tags=["workspace"])
TRADE_KEY = r"^[a-f0-9]{64}$"
MAX_PAGE = 500
SELECTION_ID = r"^[a-f0-9]{32}$"


class TradePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    notes: str | None = Field(default=None, max_length=5000)
    tags: str | None = Field(default=None, max_length=300)
    emotion: str | None = Field(default=None, max_length=40)
    confidence: str | None = Field(default=None, max_length=40)


class ViewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=60)
    config: dict[str, Any] = Field(default_factory=dict[str, Any])


def _store(request: Request) -> Store:
    store: Store = request.app.state.store
    return store


def _selection_keys(request: Request, selection_id: str | None) -> tuple[str, ...] | None:
    """The trade keys of a brushed selection, or None when the table is not narrowed."""
    if selection_id is None:
        return None
    selections: SelectionStore = request.app.state.selections
    found = selections.get(selection_id)
    if found is None:
        raise HTTPException(status_code=404, detail="That selection has expired. Brush again.")
    return found.keys


def _jsonable(row: dict[str, Any]) -> dict[str, Any]:
    """Make a stored row JSON-safe: UTC timestamps end in Z, NaN becomes null."""
    out: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, datetime):
            out[key] = value.isoformat() + "Z" if value.tzinfo is None else value.isoformat()
        elif isinstance(value, date):
            out[key] = value.isoformat()
        elif isinstance(value, float) and not math.isfinite(value):
            out[key] = None
        else:
            out[key] = value
    return out


def _filters(
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


@router.get("/trades/page")
def trade_page(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
    sort: str = "exit_time",
    direction: Annotated[Literal["asc", "desc"], Query(alias="dir")] = "desc",
    date_from: date | None = None,
    date_to: date | None = None,
    account: Annotated[list[str] | None, Query()] = None,
    symbol: Annotated[list[str] | None, Query()] = None,
    setup: Annotated[list[str] | None, Query()] = None,
    side: Annotated[list[str] | None, Query()] = None,
    tag: str | None = None,
    selection: Annotated[str | None, Query(pattern=SELECTION_ID)] = None,
) -> dict[str, Any]:
    filters = _filters(date_from, date_to, account, symbol, setup, side, tag)
    where, params = where_clause(filters, _selection_keys(request, selection))
    try:
        order = order_clause(sort, direction == "desc")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    total, rows = _store(request).query_page(where, params, order, limit, offset)
    return {"total": total, "offset": offset, "rows": [_jsonable(row) for row in rows]}


@router.get("/trades/export")
def export_trades(request: Request) -> Response:
    """Export all trades as CSV with formula cells neutralized."""
    trades = _store(request).load_frame()
    safe_csv = neutralize_csv(neutralize_frame(trades).write_csv())
    return Response(
        safe_csv,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="trades.csv"'},
    )


@router.get("/trades/{trade_key}/position")
def trade_position(
    request: Request,
    trade_key: Annotated[str, Path(pattern=TRADE_KEY)],
    sort: str = "exit_time",
    direction: Annotated[Literal["asc", "desc"], Query(alias="dir")] = "desc",
    date_from: date | None = None,
    date_to: date | None = None,
    account: Annotated[list[str] | None, Query()] = None,
    symbol: Annotated[list[str] | None, Query()] = None,
    setup: Annotated[list[str] | None, Query()] = None,
    side: Annotated[list[str] | None, Query()] = None,
    tag: str | None = None,
    selection: Annotated[str | None, Query(pattern=SELECTION_ID)] = None,
) -> dict[str, Any]:
    """Where a trade sits in the table for these filters and sort, so the UI can scroll to it."""
    filters = _filters(date_from, date_to, account, symbol, setup, side, tag)
    where, params = where_clause(filters, _selection_keys(request, selection))
    try:
        order = order_clause(sort, direction == "desc")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    found = _store(request).position_of(trade_key, where, params, order)
    if found is None:
        return {"index": None, "total": _store(request).query_page(where, params, order, 1, 0)[0]}
    return {"index": found[0], "total": found[1]}


@router.get("/trades/{trade_key}")
def trade_detail(
    request: Request,
    trade_key: Annotated[str, Path(pattern=TRADE_KEY)],
) -> dict[str, Any]:
    row = _store(request).get_trade(trade_key)
    if row is None:
        raise HTTPException(status_code=404, detail="No trade with that key.")
    return _jsonable(row)


@router.patch("/trades/{trade_key}")
def edit_trade(
    request: Request,
    trade_key: Annotated[str, Path(pattern=TRADE_KEY)],
    body: TradePatch,
) -> dict[str, Any]:
    store = _store(request)
    fields = {name: getattr(body, name) for name in body.model_fields_set if name in EDITABLE}
    if not store.update_trade(trade_key, fields):
        raise HTTPException(status_code=404, detail="No trade with that key.")
    row = store.get_trade(trade_key)
    if row is None:
        raise HTTPException(status_code=404, detail="No trade with that key.")
    return _jsonable(row)


@router.get("/filter-options")
def filter_options(request: Request) -> dict[str, list[str]]:
    store = _store(request)
    return {
        "accounts": store.distinct_values("account"),
        "symbols": store.distinct_values("symbol"),
        "setups": store.distinct_values("setup"),
        "sides": store.distinct_values("side"),
        "tags": store.distinct_values("tags"),
        "emotions": store.distinct_values("emotion"),
    }


@router.get("/views")
def list_views(request: Request) -> list[dict[str, Any]]:
    return _store(request).list_views()


@router.post("/views", status_code=201)
def save_view(request: Request, body: ViewIn) -> dict[str, Any]:
    _store(request).save_view(body.name, body.config)
    return {"name": body.name, "config": body.config}


@router.delete("/views/{name}", status_code=204)
def delete_view(request: Request, name: Annotated[str, Path(min_length=1, max_length=60)]) -> None:
    if not _store(request).delete_view(name):
        raise HTTPException(status_code=404, detail="No saved view with that name.")
