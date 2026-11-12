"""Settings, column templates, export of all data, and wiping everything."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Path, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.background import BackgroundTask

from obsidian_ledger.metrics.engine import AnalysisEngine
from obsidian_ledger.store.db import Store
from obsidian_ledger.store.export import write_export
from obsidian_ledger.workspace.selection import SelectionStore

router = APIRouter(prefix="/api", tags=["settings"])

# The exact text a person types to confirm a wipe. The server checks it too.
WIPE_PHRASE = "delete all my data"
STARTING_EQUITY_KEY = "starting_equity"
PRIVACY_KEY = "privacy"
LLM_NOTE = (
    "The Coach report is always computed on this computer with fixed rules. An AI provider you "
    "choose (GLM or Kimi) can add a plain-language summary and answer questions. It only "
    "rewords computed results, and every number it writes is checked."
)


class PrivacyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    aggregates_only: bool = True
    include_notes: bool = False
    include_trade_rows: bool = False


class SettingsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    starting_equity: float | None = Field(default=None, gt=0, le=1e12)
    privacy: PrivacyIn | None = None


class TemplateRename(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)


class WipeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirm: str


def _store(request: Request) -> Store:
    store: Store = request.app.state.store
    return store


def _privacy(store: Store) -> dict[str, bool]:
    saved = store.get_preferences().get(PRIVACY_KEY, {})
    merged = PrivacyIn.model_validate({**PrivacyIn().model_dump(), **saved})
    if merged.aggregates_only:  # the master switch wins
        merged = PrivacyIn(aggregates_only=True)
    return merged.model_dump()


def _settings_out(store: Store) -> dict[str, Any]:
    raw = store.get_setting(STARTING_EQUITY_KEY)
    return {
        "starting_equity": float(raw) if raw is not None else None,
        "privacy": _privacy(store),
        "llm": {"provider": "cloud", "note": LLM_NOTE},
        "data": {
            "trades": store.count_trades(),
            "imports": len(store.list_imports()),
            "templates": len(store.list_templates()),
        },
        "wipe_phrase": WIPE_PHRASE,
    }


@router.get("/settings")
def get_settings(request: Request) -> dict[str, Any]:
    return _settings_out(_store(request))


@router.put("/settings")
def put_settings(request: Request, body: SettingsIn) -> dict[str, Any]:
    store = _store(request)
    if "starting_equity" in body.model_fields_set:
        if body.starting_equity is None:
            store.delete_setting(STARTING_EQUITY_KEY)
        else:
            store.set_setting(STARTING_EQUITY_KEY, repr(float(body.starting_equity)))
    if body.privacy is not None:
        privacy = body.privacy
        if privacy.aggregates_only:
            privacy = PrivacyIn(aggregates_only=True)
        store.set_preference(PRIVACY_KEY, privacy.model_dump())
    return _settings_out(store)


@router.patch("/templates/{fingerprint}")
def rename_template(
    request: Request,
    fingerprint: Annotated[str, Path(min_length=1, max_length=128)],
    body: TemplateRename,
) -> dict[str, Any]:
    store = _store(request)
    if not store.rename_template(fingerprint, body.name.strip()):
        raise HTTPException(status_code=404, detail="No such column template.")
    return {"fingerprint": fingerprint, "name": body.name.strip()}


@router.delete("/templates/{fingerprint}", status_code=204)
def delete_template(
    request: Request, fingerprint: Annotated[str, Path(min_length=1, max_length=128)]
) -> None:
    if not _store(request).delete_template(fingerprint):
        raise HTTPException(status_code=404, detail="No such column template.")


@router.get("/export")
def export_all(request: Request) -> FileResponse:
    """A zip with every trade, import, view, template, report, setting, and original file."""
    store = _store(request)
    path = store.staging_dir / f"export-{uuid.uuid4().hex}.zip"
    write_export(store, path)
    stamp = datetime.now(UTC).strftime("%Y%m%d")
    return FileResponse(
        path,
        media_type="application/zip",
        filename=f"obsidian-ledger-export-{stamp}.zip",
        background=BackgroundTask(lambda: path.unlink(missing_ok=True)),
    )


@router.post("/wipe")
def wipe_everything(request: Request, body: WipeBody) -> dict[str, Any]:
    """Delete all data. Needs the exact confirmation phrase, which the screen asks you to type."""
    if body.confirm != WIPE_PHRASE:
        raise HTTPException(
            status_code=422, detail=f'To wipe everything, send the phrase "{WIPE_PHRASE}".'
        )
    removed = _store(request).wipe()
    engine: AnalysisEngine = request.app.state.analysis
    engine.reset()
    selections: SelectionStore = request.app.state.selections
    selections.clear()
    # Saved AI provider keys live in the system keychain, outside the data folder. Remove them too.
    llm: Any = request.app.state.llm
    keys = 0
    for provider in llm.providers:
        try:
            if llm.secrets.get(provider):
                llm.secrets.delete(provider)
                keys += 1
        except Exception:  # noqa: BLE001 - a keychain problem must not undo the wipe
            continue
    removed["api_keys"] = keys
    return {"wiped": True, "removed": removed}
