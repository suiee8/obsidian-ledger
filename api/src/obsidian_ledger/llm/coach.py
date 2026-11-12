"""The language-model Coach: a summary of the computed report, and answers to questions.

The deterministic report is always the source. The model only rewords tool results. Its JSON is
schema-checked, and every number it writes is checked against the tool results of the same
request. A paragraph that fails is replaced with the engine's own text. If the model is missing,
slow, or keeps returning bad output, the caller gets a clear "unavailable" result and the app
shows the deterministic report as before.
"""

from __future__ import annotations

import json
import queue
import threading
import time
from collections.abc import Callable, Generator
from dataclasses import dataclass, field
from typing import Any, Final, Literal

import httpx

from obsidian_ledger.coach.models import CoachReport
from obsidian_ledger.coach.numbers import tokens
from obsidian_ledger.coach.service import CoachService
from obsidian_ledger.coach.tools import ToolBox
from obsidian_ledger.llm import prompts
from obsidian_ledger.llm.check import unmatched
from obsidian_ledger.llm.config import LLMConfig, load_config
from obsidian_ledger.llm.jsonish import obj
from obsidian_ledger.llm.provider import Provider, ProviderError, Reply
from obsidian_ledger.llm.providers import NONE, ProviderInfo, catalog
from obsidian_ledger.llm.schemas import Answer, InvalidOutput, Summary, parse
from obsidian_ledger.llm.secrets import SecretError, Secrets, hint
from obsidian_ledger.llm.tools_view import Chip, ModelTools, Privacy, ToolRun
from obsidian_ledger.metrics.data import Filters
from obsidian_ledger.metrics.engine import AnalysisEngine
from obsidian_ledger.metrics.routes import FiltersIn
from obsidian_ledger.store.db import Store

ANSWER_SECONDS: Final = 30.0
MAX_TOOL_CALLS: Final = 6
MAX_ROUNDS: Final = MAX_TOOL_CALLS + 3
MAX_CHIPS: Final = 8
WITHHELD: Final = (
    "This paragraph was withheld because it contained a number that is not in the tool results."
)
SECTION_TITLES: Final = {
    "verdict": "Verdict",
    "leaks": "Leaks",
    "strengths": "Strengths",
    "risk": "Risk",
    "next_step": "Next step",
}

Unavailable = Literal[
    "no_data",
    "no_provider",
    "no_key",
    "no_model",
    "no_consent",
    "unreachable",
    "model_missing",
    "timeout",
    "invalid_output",
    "bad_response",
    "bad_key",
    "no_credit",
    "rate_limited",
    "unsupported",
]


class Unusable(Exception):
    def __init__(self, reason: Unavailable, message: str) -> None:
        super().__init__(message)
        self.reason: Unavailable = reason
        self.message = message


class Stopped(Exception):
    """The user pressed Stop, or the client went away."""


@dataclass
class Deadline:
    seconds: float
    started: float = field(default_factory=time.perf_counter)

    def remaining(self) -> float:
        return self.seconds - (time.perf_counter() - self.started)

    def elapsed(self) -> float:
        return time.perf_counter() - self.started

    def check(self) -> float:
        left = self.remaining()
        if left <= 0:
            raise Unusable(
                "timeout", f"It did not finish within the {self.seconds:g}-second limit."
            )
        return left


def _filters_dict(filters: FiltersIn) -> dict[str, Any]:
    return filters.model_dump(mode="json")


def deterministic_sections(report: CoachReport) -> dict[str, str]:
    """The engine's own text for each summary section, used when a paragraph fails the check."""
    verdict = " ".join(report.verdict.lines[:2])
    leaks = (
        report.top_leaks[0].rule
        if report.top_leaks
        else "No leak cleared the false-discovery filter. That means none is proven, not that "
        "none exists."
    )
    strengths = (
        report.top_strengths[0].rule
        if report.top_strengths
        else "No strength cleared the false-discovery filter yet."
    )
    risk = (
        f"{report.risk_review[0].title}: {report.risk_review[0].figure.display}. "
        f"{report.risk_review[0].note}"
        if report.risk_review
        else "No risk figures are available for this selection."
    )
    next_step = (
        f"{report.action_plan[0].focus}. {report.action_plan[0].task}"
        if report.action_plan
        else "Import more trades, then run the report again."
    )
    return {
        "verdict": verdict,
        "leaks": leaks,
        "strengths": strengths,
        "risk": risk,
        "next_step": next_step,
    }


class LLMCoach:
    def __init__(
        self,
        store: Store,
        engine: AnalysisEngine,
        coach: CoachService,
        toolbox: ToolBox,
        secrets: Secrets,
        *,
        test_provider_url: str | None = None,
        transport: httpx.BaseTransport | None = None,
        answer_seconds: float | None = None,
    ) -> None:
        self.store = store
        self.engine = engine
        self.coach = coach
        self.toolbox = toolbox
        self.secrets = secrets
        self.providers = catalog(test_provider_url)
        self.transport = transport
        # None means "use the limit saved in Settings". Tests set a number to force a limit.
        self.answer_seconds = answer_seconds
        self._summaries: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    # ----- configuration -----

    def config(self) -> LLMConfig:
        config = load_config(self.store)
        if config.provider != NONE and config.provider not in self.providers:
            return LLMConfig(answer_seconds=config.answer_seconds)
        return config

    def info(self, provider_id: str) -> ProviderInfo | None:
        return self.providers.get(provider_id)

    def key(self, provider_id: str) -> str | None:
        try:
            return self.secrets.get(provider_id)
        except SecretError:
            return None

    def provider(self, config: LLMConfig, api_key: str | None = None) -> Provider:
        info = self.providers[config.provider]
        key = api_key if api_key is not None else self.key(config.provider)
        return Provider(info, key, config.model, self.transport)

    def privacy(self) -> Privacy:
        saved = self.store.get_preferences().get("privacy", {})
        return Privacy.from_settings(obj(saved))

    def status(self, config: LLMConfig | None = None) -> dict[str, Any]:
        """What is set up. Makes no network request: nothing leaves the computer to show this."""
        chosen = config or self.config()
        info = self.info(chosen.provider)
        key = self.key(chosen.provider) if info else None
        out: dict[str, Any] = {
            "provider": chosen.provider,
            "provider_name": info.name if info else None,
            "host": info.public()["host"] if info else None,
            "model": chosen.model,
            "models": list(info.models) if info else [],
            "free_models": list(info.free_models) if info else [],
            "key_saved": key is not None,
            "key_hint": hint(key),
            "consented": chosen.provider in chosen.consented,
            "answer_seconds": chosen.answer_seconds,
            "providers": [p.public() for p in self.providers.values()],
            "ready": False,
            "reason": None,
            "message": None,
        }
        if info is None:
            out.update(reason="no_provider", message="Choose an AI provider in Settings.")
        elif key is None:
            out.update(reason="no_key", message=f"Save an API key for {info.name} in Settings.")
        elif not chosen.model:
            out.update(reason="no_model", message="Choose a model in Settings.")
        elif chosen.provider not in chosen.consented:
            out.update(
                reason="no_consent",
                message=f"Confirm in Settings that results may be sent to {info.name}.",
            )
        else:
            out.update(ready=True)
        return out

    def test(self, config: LLMConfig, api_key: str | None = None) -> dict[str, Any]:
        """Check the key and list models. Sends one short test message and no journal data."""
        info = self.info(config.provider)
        if info is None:
            return {"ok": False, "reason": "no_provider", "message": "Choose a provider first."}
        key = api_key or self.key(config.provider)
        if not key:
            return {
                "ok": False,
                "reason": "no_key",
                "message": f"Enter an API key for {info.name}.",
            }
        started = time.perf_counter()
        provider = Provider(info, key, config.model, self.transport)
        try:
            models = provider.models()
            if not config.model:
                return {
                    "ok": False,
                    "reason": "no_model",
                    "message": "Key accepted. Choose a model.",
                    "models": models,
                }
            provider.check_key()
        except ProviderError as exc:
            return {"ok": False, "reason": exc.reason, "message": exc.message, "models": []}
        return {
            "ok": True,
            "reason": None,
            "message": f"{info.name} answered with {config.model}.",
            "models": models,
            "milliseconds": round((time.perf_counter() - started) * 1000),
        }

    # ----- shared pieces -----

    def _prepare(self, filters_in: FiltersIn) -> tuple[Filters, LLMConfig]:
        """Refuse before any request when there is no data, no provider, no key, no model, or no
        consent."""
        filters = filters_in.to_filters()
        _version, prepared = self.engine.trades_for(filters)
        if prepared.frame.height == 0:
            raise Unusable("no_data", "There are no trades to explain. Import a journal first.")
        config = self.config()
        status = self.status(config)
        if not status["ready"]:
            raise Unusable(status["reason"], status["message"])
        return filters, config

    @staticmethod
    def _complete(
        provider: Provider,
        messages: list[dict[str, Any]],
        deadline: Deadline,
        **options: Any,
    ) -> Reply:
        left = deadline.check()
        try:
            return provider.chat(messages, timeout=left, **options)
        except ProviderError as exc:
            if exc.reason == "timeout":
                raise Unusable(
                    "timeout", f"It did not finish within the {deadline.seconds:g}-second limit."
                ) from exc
            raise Unusable(exc.reason, exc.message) from exc

    @staticmethod
    def _tool_messages(
        runs: list[tuple[str, ToolRun]], content: str | None
    ) -> list[dict[str, Any]]:
        assistant = {
            "role": "assistant",
            "content": content or "",
            "tool_calls": [
                {
                    "id": call_id,
                    "type": "function",
                    "function": {"name": run.name, "arguments": json.dumps(run.arguments)},
                }
                for call_id, run in runs
            ],
        }
        results = [
            {
                "role": "tool",
                "tool_call_id": call_id,
                "name": run.name,
                "content": json.dumps(run.payload, ensure_ascii=False),
            }
            for call_id, run in runs
        ]
        return [assistant, *results]

    # ----- summary -----

    def _deadline(self, config: LLMConfig) -> Deadline:
        seconds = self.answer_seconds if self.answer_seconds is not None else config.answer_seconds
        return Deadline(float(seconds))

    def summary(self, filters_in: FiltersIn) -> dict[str, Any]:
        """The AI summary of the report for these filters, or why it is unavailable."""
        try:
            filters, config = self._prepare(filters_in)
        except Unusable as exc:
            return {"status": "unavailable", "reason": exc.reason, "message": exc.message}
        deadline = self._deadline(config)
        report = self.coach.report(filters)
        privacy = self.privacy()
        key = json.dumps(
            [report.report_id, config.provider, config.model, privacy.__dict__], sort_keys=True
        )
        with self._lock:
            cached = self._summaries.get(key)
        if cached is not None:
            return cached
        try:
            result = self._summarize(report, filters_in, config, privacy, deadline)
        except Unusable as exc:
            return {
                "status": "unavailable",
                "reason": exc.reason,
                "message": exc.message,
                "model": config.model,
                "report_id": report.report_id,
            }
        with self._lock:
            self._summaries[key] = result
        return result

    def _summarize(
        self,
        report: CoachReport,
        filters_in: FiltersIn,
        config: LLMConfig,
        privacy: Privacy,
        deadline: Deadline,
    ) -> dict[str, Any]:
        tools = ModelTools(self.toolbox, privacy, _filters_dict(filters_in), report.base_currency)
        # The server makes the calls, so the model gets the same three results every time.
        runs = [
            (f"call_{index}", tools.call(name, {}))
            for index, name in enumerate(("get_metrics", "find_leaks", "find_strengths"), 1)
        ]
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": prompts.SUMMARY_TASK},
            {"role": "user", "content": "Summarize my computed Coach report."},
            *self._tool_messages(runs, None),
        ]
        provider = self.provider(config)
        parsed = self._parse_with_retry(provider, messages, deadline, Summary)
        fallback = deterministic_sections(report)
        paragraphs: list[dict[str, Any]] = []
        for paragraph in parsed.paragraphs:
            missing = unmatched(paragraph.text, tools.allowed)
            replaced = bool(missing)
            paragraphs.append(
                {
                    "section": paragraph.section,
                    "title": SECTION_TITLES[paragraph.section],
                    "text": fallback[paragraph.section] if replaced else paragraph.text,
                    "replaced": replaced,
                    "unmatched": missing,
                }
            )
        headline_missing = unmatched(parsed.headline, tools.allowed)
        return {
            "status": "ok",
            "model": config.model,
            "report_id": report.report_id,
            "headline": report.verdict.headline if headline_missing else parsed.headline,
            "headline_replaced": bool(headline_missing),
            "paragraphs": paragraphs,
            "tools_used": [run.public() for _, run in runs],
            "seconds": round(deadline.elapsed(), 2),
        }

    def _parse_with_retry(
        self,
        provider: Provider,
        messages: list[dict[str, Any]],
        deadline: Deadline,
        schema: type[Summary] | type[Answer],
        **options: Any,
    ) -> Any:
        reply = self._complete(provider, messages, deadline, json_mode=True, **options)
        try:
            return parse(reply.content, schema)
        except InvalidOutput as first:
            retry = [
                *messages,
                {"role": "assistant", "content": reply.content or ""},
                {"role": "user", "content": prompts.RETRY.format(problem=str(first))},
            ]
            again = self._complete(provider, retry, deadline, json_mode=True)
            try:
                return parse(again.content, schema)
            except InvalidOutput as second:
                raise Unusable(
                    "invalid_output",
                    f"The model's reply could not be used after one retry ({second}).",
                ) from second

    # ----- questions -----

    def ask(
        self,
        filters_in: FiltersIn,
        question: str,
        stop: threading.Event | None = None,
    ) -> Generator[dict[str, Any]]:
        """Answer one question. Yields events: status, tool, paragraph, done, or error."""
        cancel = stop or threading.Event()
        events: queue.Queue[dict[str, Any] | None] = queue.Queue()

        def emit(event: dict[str, Any]) -> None:
            events.put(event)

        def work() -> None:
            try:
                self._answer(filters_in, question, emit, cancel)
            except Stopped:
                emit({"type": "error", "reason": "stopped", "message": "Stopped."})
            except Unusable as exc:
                emit({"type": "error", "reason": exc.reason, "message": exc.message})
            except Exception as exc:  # noqa: BLE001 - shown to the user, never crashes the stream
                emit(
                    {
                        "type": "error",
                        "reason": "bad_response",
                        "message": f"The answer failed: {exc}",
                    }
                )
            finally:
                events.put(None)

        worker = threading.Thread(target=work, daemon=True)
        worker.start()
        try:
            while True:
                try:
                    event = events.get(timeout=1.0)
                except queue.Empty:
                    yield {"type": "ping"}
                    continue
                if event is None:
                    return
                yield event
        finally:
            cancel.set()  # the client stopped reading: no further model or tool calls

    def _answer(
        self,
        filters_in: FiltersIn,
        question: str,
        emit: Callable[[dict[str, Any]], None],
        cancel: threading.Event,
    ) -> None:
        filters, config = self._prepare(filters_in)
        deadline = self._deadline(config)
        report = self.coach.report(filters)
        privacy = self.privacy()
        tools = ModelTools(self.toolbox, privacy, _filters_dict(filters_in), report.base_currency)
        provider = self.provider(config)
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": prompts.ANSWER_TASK},
            {"role": "user", "content": f"Question: {question}"},
        ]
        emit({"type": "status", "phase": "thinking", "message": "Reading your question"})
        calls_used = 0
        answer: Answer | None = None
        for _round in range(MAX_ROUNDS):
            if cancel.is_set():
                raise Stopped
            offer_tools = calls_used < MAX_TOOL_CALLS
            reply = self._complete(
                provider,
                messages,
                deadline,
                tools=tools.definitions() if offer_tools else None,
                json_mode=not offer_tools,
            )
            if cancel.is_set():
                raise Stopped
            if reply.tool_calls:
                batch: list[tuple[str, ToolRun]] = []
                for call in reply.tool_calls:
                    if calls_used >= MAX_TOOL_CALLS:
                        run = tools.reject(
                            call.name,
                            {},
                            f"The limit of {MAX_TOOL_CALLS} tool calls for one answer is reached.",
                        )
                    else:
                        calls_used += 1
                        emit({"type": "status", "phase": "tool", "message": f"Calling {call.name}"})
                        run = tools.call(call.name, call.arguments)
                    emit({"type": "tool", **run.public()})
                    batch.append((call.id, run))
                messages.extend(self._tool_messages(batch, reply.content))
                if calls_used >= MAX_TOOL_CALLS:
                    messages.append({"role": "user", "content": prompts.TOOL_LIMIT})
                continue
            emit({"type": "status", "phase": "writing", "message": "Checking the answer"})
            try:
                answer = parse(reply.content, Answer)
            except InvalidOutput as first:
                messages.extend(
                    [
                        {"role": "assistant", "content": reply.content or ""},
                        {"role": "user", "content": prompts.RETRY.format(problem=str(first))},
                    ]
                )
                again = self._complete(provider, messages, deadline, json_mode=True)
                try:
                    answer = parse(again.content, Answer)
                except InvalidOutput as second:
                    raise Unusable(
                        "invalid_output",
                        f"The model's reply could not be used after one retry ({second}).",
                    ) from second
            break
        if answer is None:
            raise Unusable("invalid_output", "The model kept calling tools and never answered.")
        if not any(run.ok for run in tools.runs):
            raise Unusable(
                "invalid_output",
                "The model answered without reading any results, so its answer was not shown.",
            )
        self._emit_paragraphs(answer, tools, emit)
        emit(
            {
                "type": "done",
                "model": config.model,
                "tools_used": [run.public() for run in tools.runs],
                "tool_calls": calls_used,
                "seconds": round(deadline.elapsed(), 2),
            }
        )

    @staticmethod
    def _emit_paragraphs(
        answer: Answer, tools: ModelTools, emit: Callable[[dict[str, Any]], None]
    ) -> None:
        evidence = tools.evidence
        visible_trades: set[str] = set()
        for run in tools.runs:
            visible_trades |= run.trade_ids
        for index, paragraph in enumerate(answer.paragraphs):
            findings = [fid for fid in paragraph.finding_ids if fid in evidence.by_finding]
            trades = [tid for tid in paragraph.trade_ids if tid in visible_trades]
            missing = unmatched(paragraph.text, tools.allowed)
            replaced = bool(missing)
            if replaced:
                rules = [
                    evidence.finding_rules[fid] for fid in findings if fid in evidence.finding_rules
                ]
                text = " ".join(rules) if rules else WITHHELD
            else:
                text = paragraph.text
            chips: list[Chip] = []
            for fid in findings:
                chips.extend(evidence.by_finding[fid][:4])
            chips.extend(evidence.by_trade_id[tid] for tid in trades if tid in evidence.by_trade_id)
            unique: dict[str, Chip] = {}
            for chip in chips:
                unique.setdefault(chip.trade_key, chip)
            sources = [
                run.index
                for run in tools.runs
                if run.ok
                and (
                    any(fid in run.finding_ids for fid in findings)
                    or any(tid in run.trade_ids for tid in trades)
                    or (not replaced and _supports(run, paragraph.text))
                )
            ]
            emit(
                {
                    "type": "paragraph",
                    "index": index,
                    "text": text,
                    "replaced": replaced,
                    "unmatched": missing,
                    "finding_ids": findings,
                    "chips": [chip.as_dict() for chip in list(unique.values())[:MAX_CHIPS]],
                    "sources": sources,
                }
            )


def _supports(run: ToolRun, text: str) -> bool:
    return any(run.allowed.matches(token) for token in tokens(text))
