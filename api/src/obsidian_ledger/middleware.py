"""Small ASGI guards shared by the local API."""

from __future__ import annotations

import asyncio
import json
import time
from collections import defaultdict, deque

from starlette.types import ASGIApp, Message, Receive, Scope, Send


class RequestBodyTooLarge(Exception):
    """Raised when a streamed request exceeds the configured body limit."""

    def __init__(self, message: str, code: str = "body_too_large") -> None:
        super().__init__(message)
        self.code = code


def _error_body(code: str, message: str) -> bytes:
    return json.dumps({"error": {"code": code, "message": message}}).encode("utf-8")


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.headers = [
            (
                b"content-security-policy",
                b"default-src 'none'; base-uri 'none'; frame-ancestors 'none'",
            ),
            (b"x-content-type-options", b"nosniff"),
            (b"x-frame-options", b"DENY"),
            (b"referrer-policy", b"no-referrer"),
            (
                b"permissions-policy",
                b"accelerometer=(), camera=(), geolocation=(), gyroscope=(), "
                b"microphone=(), payment=(), usb=()",
            ),
        ]

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_security_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                present = {key.lower() for key, _ in message.get("headers", [])}
                message = {
                    **message,
                    "headers": [
                        *message.get("headers", []),
                        *(header for header in self.headers if header[0] not in present),
                    ],
                }
            await send(message)

        await self.app(scope, receive, send_with_security_headers)


UPLOAD_PATHS = frozenset({"/api/imports/preview"})
JSON_BODY_LIMIT_BYTES = 1024 * 1024


class RequestBodyLimitMiddleware:
    """Cap every request body: the upload limit on file endpoints, a small cap on all others."""

    def __init__(
        self,
        app: ASGIApp,
        max_body_bytes: int,
        json_body_bytes: int = JSON_BODY_LIMIT_BYTES,
    ) -> None:
        self.app = app
        self.upload_body_bytes = max_body_bytes
        self.json_body_bytes = min(json_body_bytes, max_body_bytes)
        self.message = "Request body exceeds the allowed size."

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        is_upload = scope.get("path") in UPLOAD_PATHS
        limit = self.upload_body_bytes if is_upload else self.json_body_bytes
        content_length = next(
            (value for key, value in scope.get("headers", []) if key.lower() == b"content-length"),
            None,
        )
        error_code = (
            "too_large" if scope.get("path") == "/api/imports/preview" else "body_too_large"
        )
        if content_length is not None:
            try:
                declared_size = int(content_length)
            except ValueError:
                await self._send_error(
                    send, 400, "invalid_content_length", "Invalid Content-Length."
                )
                return
            if declared_size < 0:
                await self._send_error(
                    send, 400, "invalid_content_length", "Invalid Content-Length."
                )
                return
            if declared_size > limit:
                await self._send_error(send, 413, error_code, self.message)
                return

        received = 0
        exceeded = False
        replaced = False

        async def limited_receive() -> Message:
            nonlocal received, exceeded
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    exceeded = True
                    raise RequestBodyTooLarge(self.message, error_code)
            return message

        async def guarded_send(message: Message) -> None:
            # FastAPI turns an error raised while reading a body into a 400. Once the limit is
            # crossed, the client must see 413 instead, whatever the framework answered.
            nonlocal replaced
            if exceeded:
                if not replaced:
                    replaced = True
                    await self._send_error(send, 413, error_code, self.message)
                return
            await send(message)

        await self.app(scope, limited_receive, guarded_send)

    @staticmethod
    async def _send_error(send: Send, status: int, code: str, message: str) -> None:
        body = _error_body(code, message)
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("ascii")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})


class RequestPolicyMiddleware:
    """Bound expensive work, request duration, and request frequency per local client."""

    HEAVY_PATHS = {
        "/api/coach/report",
        "/api/imports/preview",
        "/api/simulate",
    }

    def __init__(
        self,
        app: ASGIApp,
        *,
        heavy_limit: int,
        requests_per_minute: int,
        timeout_seconds: float,
    ) -> None:
        self.app = app
        self.heavy = asyncio.Semaphore(heavy_limit)
        self.requests_per_minute = requests_per_minute
        self.timeout_seconds = timeout_seconds
        self.requests: dict[str, deque[float]] = defaultdict(deque)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = str(scope.get("path", ""))
        method = str(scope.get("method", "GET"))
        if path in {"/health", "/health/ready"}:
            await self.app(scope, receive, send)
            return

        now = time.monotonic()
        client = scope.get("client")
        key = str(client[0]) if client else "unknown"
        recent = self.requests[key]
        while recent and now - recent[0] >= 60:
            recent.popleft()
        if len(recent) >= self.requests_per_minute:
            await self._send_error(
                send, 429, "rate_limited", "Too many requests; try again shortly."
            )
            return
        recent.append(now)

        is_heavy = method == "POST" and (
            path in self.HEAVY_PATHS
            or (path.startswith("/api/imports/") and path.endswith("/commit"))
        )
        acquired = False
        if is_heavy:
            try:
                await asyncio.wait_for(self.heavy.acquire(), timeout=0.01)
                acquired = True
            except TimeoutError:
                await self._send_error(
                    send, 503, "busy", "The API is handling its maximum number of heavy jobs."
                )
                return

        response_started = False

        async def track_start(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            if path == "/api/coach/stream":
                await self.app(scope, receive, track_start)
            else:
                await asyncio.wait_for(
                    self.app(scope, receive, track_start),
                    timeout=self.timeout_seconds,
                )
        except TimeoutError:
            if not response_started:
                await self._send_error(
                    send, 504, "request_timeout", "The request exceeded the API time limit."
                )
        finally:
            if acquired:
                self.heavy.release()

    @staticmethod
    async def _send_error(send: Send, status: int, code: str, message: str) -> None:
        body = _error_body(code, message)
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("ascii")),
                    *([(b"retry-after", b"60")] if status == 429 else []),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
