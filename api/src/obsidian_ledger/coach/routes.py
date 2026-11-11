"""HTTP routes for the Coach: report, progress stream, stored reports, export, and tools."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Path, Query, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from obsidian_ledger.coach import export
from obsidian_ledger.coach.models import CoachReport
from obsidian_ledger.coach.service import CoachService
from obsidian_ledger.coach.tools import ToolBox
from obsidian_ledger.metrics.data import Filters
from obsidian_ledger.metrics.routes import FiltersIn
from obsidian_ledger.store.db import Store
from obsidian_ledger.workspace.selection import SelectionStore

router = APIRouter(prefix="/api/coach", tags=["coach"])
REPORT_ID = r"^[a-f0-9]{32}$"


class ReportBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filters: FiltersIn = Field(default_factory=FiltersIn)
    force: bool = False


class FindingSelectionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filters: FiltersIn = Field(default_factory=FiltersIn)
    finding_id: str = Field(min_length=5, max_length=120)


class ToolBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    arguments: dict[str, Any] = Field(default_factory=dict[str, Any])


def _coach(request: Request) -> CoachService:
    service: CoachService = request.app.state.coach
    return service


def _tools(request: Request) -> ToolBox:
    box: ToolBox = request.app.state.tools
    return box


def _store(request: Request) -> Store:
    store: Store = request.app.state.store
    return store


@router.post("/report")
def create_report(request: Request, body: ReportBody) -> CoachReport:
    """The Coach report for these filters. A stored report is returned if the data is unchanged."""
    return _coach(request).report(body.filters.to_filters(), force=body.force)


@router.post("/findings/selection")
def select_finding_trades(request: Request, body: FindingSelectionBody) -> dict[str, Any]:
    """Turn one finding into the set of trades behind it, for the Trades table.

    Pass the filters the report was built with. The count equals the finding's `n`.
    """
    keys = _coach(request).finding_trade_keys(body.filters.to_filters(), body.finding_id)
    if keys is None:
        raise HTTPException(
            status_code=404, detail="That finding is not in this data. Run the report again."
        )
    selections: SelectionStore = request.app.state.selections
    selection = selections.add(keys)
    return {"selection_id": selection.selection_id, "count": len(keys)}


@router.get("/stream")
def stream_report(
    request: Request,
    force: bool = False,
    date_from: date | None = None,
    date_to: date | None = None,
    account: Annotated[list[str] | None, Query()] = None,
    symbol: Annotated[list[str] | None, Query()] = None,
    setup: Annotated[list[str] | None, Query()] = None,
    side: Annotated[list[str] | None, Query()] = None,
    tag: str | None = None,
) -> StreamingResponse:
    """Server-sent events: one event per timeline step, then `done` with the report id."""
    filters = Filters(
        date_from=date_from,
        date_to=date_to,
        accounts=tuple(account or []),
        symbols=tuple(symbol or []),
        setups=tuple(setup or []),
        sides=tuple(side or []),
        tag=tag,
    )
    service = _coach(request)

    def events() -> Iterator[str]:
        for event in service.stream(filters, force=force):
            yield f"event: {event['step'] if event['step'] in ('done', 'error') else 'step'}\n"
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/reports")
def list_reports(
    request: Request, limit: Annotated[int, Query(ge=1, le=100)] = 20
) -> list[dict[str, Any]]:
    return _store(request).list_coach_reports(limit)


@router.get("/reports/{report_id}")
def get_report(request: Request, report_id: Annotated[str, Path(pattern=REPORT_ID)]) -> CoachReport:
    report = _coach(request).stored(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="No report with that id.")
    return report


@router.get("/reports/{report_id}/export")
def export_report(
    request: Request,
    report_id: Annotated[str, Path(pattern=REPORT_ID)],
    format: Annotated[str, Query(pattern="^(md|html)$")] = "md",  # noqa: A002 - query name
) -> Response:
    report = _coach(request).stored(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="No report with that id.")
    if format == "html":
        return Response(export.to_html(report), media_type="text/html; charset=utf-8")
    return Response(
        export.to_markdown(report),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="coach-report-{report_id[:8]}.md"'},
    )


@router.get("/tools")
def list_tools(request: Request) -> list[dict[str, Any]]:
    return _tools(request).schemas()


@router.post("/tools/{name}")
def call_tool(request: Request, name: str, body: ToolBody) -> dict[str, Any]:
    try:
        return _tools(request).call(name, body.arguments)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc.args[0])) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
