"""HTTP routes for the optional cloud model: status, settings, key, test, summary, and questions."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from obsidian_ledger.llm.coach import LLMCoach
from obsidian_ledger.llm.config import MAX_SECONDS, MODEL_NAME, LLMConfig, save_config
from obsidian_ledger.llm.providers import NONE
from obsidian_ledger.llm.secrets import SecretError
from obsidian_ledger.metrics.routes import FiltersIn

router = APIRouter(prefix="/api", tags=["llm"])
KEY_PATTERN = r"^[\x21-\x7e]{8,300}$"  # printable, no spaces: what API keys look like


class ConfigIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str | None = Field(default=None, max_length=40)
    model: str | None = Field(default=None, pattern=MODEL_NAME)
    answer_seconds: int | None = Field(default=None, ge=10, le=MAX_SECONDS)
    # True: you agree that aggregate results may be sent to the chosen provider.
    consent: bool | None = None


class KeyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = Field(max_length=40)
    api_key: str = Field(pattern=KEY_PATTERN)


class TestIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str | None = Field(default=None, max_length=40)
    model: str | None = Field(default=None, pattern=MODEL_NAME)
    # A key to try before saving it. It is used once and not stored.
    api_key: str | None = Field(default=None, pattern=KEY_PATTERN)


class SummaryIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filters: FiltersIn = Field(default_factory=FiltersIn)


class AskIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filters: FiltersIn = Field(default_factory=FiltersIn)
    question: str = Field(min_length=1, max_length=500)


def _llm(request: Request) -> LLMCoach:
    coach: LLMCoach = request.app.state.llm
    return coach


def _known(llm: LLMCoach, provider: str) -> str:
    if provider != NONE and llm.info(provider) is None:
        raise HTTPException(status_code=422, detail=f"Unknown provider '{provider}'.")
    return provider


@router.get("/llm/status")
def llm_status(request: Request) -> dict[str, Any]:
    """The chosen provider and model, whether a key is saved, and whether the AI layer is ready.
    Answers from saved settings only; it sends nothing over the network."""
    return _llm(request).status()


@router.put("/llm/config")
def llm_config(request: Request, body: ConfigIn) -> dict[str, Any]:
    llm = _llm(request)
    current = llm.config()
    provider = _known(llm, body.provider) if body.provider is not None else current.provider
    changed = provider != current.provider
    model = body.model if "model" in body.model_fields_set else (None if changed else current.model)
    consented = [item for item in current.consented if item in llm.providers]
    if body.consent is True and provider != NONE and provider not in consented:
        consented.append(provider)
    if body.consent is False and provider in consented:
        consented.remove(provider)
    config = LLMConfig(
        provider=provider,
        model=model,
        answer_seconds=body.answer_seconds or current.answer_seconds,
        consented=consented,
    )
    save_config(llm.store, config)
    return llm.status(config)


@router.put("/llm/key")
def save_key(request: Request, body: KeyIn) -> dict[str, Any]:
    """Save an API key to the system keychain. The key is never sent back."""
    llm = _llm(request)
    provider = _known(llm, body.provider)
    if provider == NONE:
        raise HTTPException(status_code=422, detail="Choose a provider first.")
    try:
        llm.secrets.set(provider, body.api_key.strip())
    except SecretError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return llm.status()


@router.delete("/llm/key/{provider}")
def delete_key(request: Request, provider: str) -> dict[str, Any]:
    llm = _llm(request)
    _known(llm, provider)
    try:
        llm.secrets.delete(provider)
    except SecretError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return llm.status()


@router.post("/llm/test")
def llm_test(request: Request, body: TestIn) -> dict[str, Any]:
    """Check a key and list models. Sends one short test message and no journal data."""
    llm = _llm(request)
    current = llm.config()
    provider = _known(llm, body.provider) if body.provider is not None else current.provider
    model = body.model if "model" in body.model_fields_set else current.model
    config = LLMConfig(provider=provider, model=model, answer_seconds=current.answer_seconds)
    return llm.test(config, body.api_key)


@router.post("/coach/ai/summary")
def ai_summary(request: Request, body: SummaryIn) -> dict[str, Any]:
    return _llm(request).summary(body.filters)


def _sse(events: Iterator[dict[str, Any]]) -> Iterator[str]:
    for event in events:
        kind = event.get("type", "message")
        if kind == "ping":
            yield ": ping\n\n"  # a comment line keeps the connection alive and shows liveness
            continue
        yield f"event: {kind}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"


@router.post("/coach/ask")
def ask(request: Request, body: AskIn) -> StreamingResponse:
    """Answer a question over server-sent events: status, tool, paragraph, then done or error."""
    question = " ".join(body.question.split())
    if not question:
        raise HTTPException(status_code=422, detail="Ask a question first.")
    events = _llm(request).ask(body.filters, question)
    return StreamingResponse(
        _sse(events),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
