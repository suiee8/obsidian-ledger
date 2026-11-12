"""A small client for an OpenAI-compatible chat API, reached with an API key over HTTPS.

Only two endpoints are used: list models and chat completions with tools. Every failure becomes a
ProviderError with a reason the UI can explain. The API key is sent only in the Authorization
header and never appears in an error message.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal

import httpx

from obsidian_ledger.llm.jsonish import arr, obj
from obsidian_ledger.llm.providers import ProviderInfo

Reason = Literal[
    "unreachable",
    "timeout",
    "model_missing",
    "bad_response",
    "bad_key",
    "no_credit",
    "rate_limited",
    "unsupported",
]


class ProviderError(Exception):
    def __init__(self, reason: Reason, message: str) -> None:
        super().__init__(message)
        self.reason: Reason = reason
        self.message = message


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: str | dict[str, Any]


@dataclass(frozen=True)
class Reply:
    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list[ToolCall])


def _detail(response: httpx.Response) -> str:
    """The provider's own error text, if it sent one, cut short."""
    try:
        body = obj(response.json())
    except ValueError:
        return ""
    error: Any = body.get("error")
    text = obj(error).get("message") if isinstance(error, dict) else error or body.get("message")
    return str(text)[:200] if text else ""


class Provider:
    def __init__(
        self,
        info: ProviderInfo,
        api_key: str | None,
        model: str | None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.info = info
        self.api_key = api_key
        self.model = model
        self.transport = transport

    def _client(self, timeout: float) -> httpx.Client:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        if self.info.id == "openrouter":
            headers["X-Title"] = "Obsidian Ledger"
        return httpx.Client(
            base_url=self.info.base_url,
            headers=headers,
            timeout=httpx.Timeout(timeout, connect=min(timeout, 10.0)),
            transport=self.transport,
            trust_env=False,  # never route journal data through a system proxy
        )

    def _request(
        self, method: str, path: str, timeout: float, body: dict[str, Any] | None = None
    ) -> Any:
        name = self.info.name
        try:
            with self._client(max(timeout, 0.05)) as client:
                response = client.request(method, path, json=body)
        except httpx.ConnectError as exc:
            raise ProviderError(
                "unreachable", f"Could not reach {name}. Check the internet connection."
            ) from exc
        except httpx.TimeoutException as exc:
            raise ProviderError("timeout", f"{name} did not answer in time.") from exc
        except httpx.HTTPError as exc:
            raise ProviderError("unreachable", f"The request to {name} failed.") from exc
        status, detail = response.status_code, _detail(response)
        said = f" {name} said: {detail}" if detail else ""
        if status in (401, 403):
            raise ProviderError("bad_key", f"{name} did not accept the API key.{said}")
        if status == 402 or "insufficient" in detail.lower() or "balance" in detail.lower():
            raise ProviderError("no_credit", f"The {name} account has no credit left.{said}")
        if status == 429:
            raise ProviderError(
                "rate_limited", f"{name} is limiting requests. Try again soon.{said}"
            )
        if status == 404 and self.model and "model" in detail.lower():
            raise ProviderError("model_missing", f"{name} does not offer '{self.model}'.{said}")
        if status == 400 and ("tool" in detail.lower() or "function" in detail.lower()):
            raise ProviderError("unsupported", f"'{self.model}' cannot use tools.{said}")
        if status >= 400:
            raise ProviderError("bad_response", f"{name} answered with status {status}.{said}")
        try:
            return response.json()
        except ValueError as exc:
            raise ProviderError("bad_response", f"{name} sent a reply that is not JSON.") from exc

    def models(self, timeout: float = 8.0) -> list[str]:
        """Models the provider offers. Without a list endpoint, the provider's known models."""
        if not self.info.list_models:
            if not self.api_key:
                raise ProviderError("bad_key", f"No API key is saved for {self.info.name}.")
            return list(self.info.models)
        data = self._request("GET", "/models", timeout)
        names = [str(obj(item)["id"]) for item in arr(obj(data).get("data")) if obj(item).get("id")]
        if not names:
            raise ProviderError("bad_response", f"The model list from {self.info.name} was empty.")
        return sorted(set(names))

    def check_key(self, timeout: float = 15.0) -> None:
        """A one-word request, so a wrong key is found now and not on the first question. Sends no
        journal data."""
        self.chat(
            [{"role": "user", "content": "Reply with the word OK."}], timeout=timeout, max_tokens=5
        )

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        timeout: float,
        tools: list[dict[str, Any]] | None = None,
        json_mode: bool = False,
        max_tokens: int = 450,  # a summary or answer is about 250 tokens
    ) -> Reply:
        if not self.model:
            raise ProviderError("model_missing", "No model is selected.")
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
            "stream": False,
            "max_tokens": max_tokens,
            **self.info.extra_body,
        }
        if tools:
            body["tools"] = tools
        if json_mode and self.info.json_mode:
            body["response_format"] = {"type": "json_object"}
        data = self._request("POST", "/chat/completions", timeout, body)
        choices = arr(obj(data).get("choices"))
        message = obj(obj(choices[0]).get("message")) if choices else {}
        if not message:
            raise ProviderError("bad_response", f"The reply from {self.info.name} had no message.")
        calls: list[ToolCall] = []
        for index, raw in enumerate(arr(message.get("tool_calls"))):
            call = obj(raw)
            function = obj(call.get("function"))
            if not function.get("name"):
                continue
            raw_arguments: Any = function.get("arguments") or {}
            arguments: str | dict[str, Any] = (
                raw_arguments
                if isinstance(raw_arguments, str)
                else obj(raw_arguments)
                if isinstance(raw_arguments, dict)
                else json.dumps(raw_arguments)
            )
            calls.append(
                ToolCall(str(call.get("id") or f"call_{index}"), str(function["name"]), arguments)
            )
        content = message.get("content")
        return Reply(content if isinstance(content, str) else None, calls)
