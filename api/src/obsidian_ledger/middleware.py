"""Small ASGI guards shared by the local API."""

from __future__ import annotations

import asyncio
import json
import time
from collections import defaultdict, deque

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from obsidian_ledger.security.auth import SESSION_COOKIE, SessionStore
from obsidian_ledger.security.events import SecurityLog

CLIENT_HEADER = b"x-ledger-client"
CLIENT_HEADER_VALUE = b"web"
ALLOWED_METHODS = frozenset({"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"})
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
# POST routes that only compute or read. Read-only mode lets these through.
READ_ONLY_POST = (
    "/api/simulate",
    "/api/selections",
    "/api/coach/report",
    "/api/coach/findings/selection",
    "/api/coach/ask",
    "/api/coach/ai/summary",
)
PUBLIC_PATHS = frozenset({"/health", "/health/ready", "/api/auth/status", "/api/auth/login"})


class RequestBodyTooLarge(Exception):
    """Raised when a streamed request exceeds the configured body limit."""

    def __init__(self, message: str, code: str = "body_too_large") -> None:
        super().__init__(message)
        self.code = code


def _error_body(code: str, message: str) -> bytes:
    return json.dumps({"error": {"code": code, "message": message}}).encode("utf-8")


def _client(scope: Scope) -> str:
    client = scope.get("client")
    return str(client[0]) if client else "unknown"


def _security_log(scope: Scope) -> SecurityLog | None:
    app = scope.get("app")
    log = getattr(getattr(app, "state", None), "security_log", None)
    return log if isinstance(log, SecurityLog) else None


def _note(scope: Scope, event: str, reason: str) -> None:
    log = _security_log(scope)
    if log is not None:
        log.record(
            event,
            client=_client(scope),
            method=str(scope.get("method", "")),
            path=str(scope.get("path", "")),
            reason=reason,
        )


async def _reject(send: Send, status: int, code: str, message: str) -> None:
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


def _header(scope: Scope, name: bytes) -> str | None:
    for key, value in scope.get("headers", []):
        if key.lower() == name:
            return bytes(value).decode("latin-1")
    return None


class GuardMiddleware:
    """Host allow-list, Origin allow-list, method allow-list, and the required client header."""

    def __init__(self, app: ASGIApp, *, allowed_hosts: list[str], allowed_origins: list[str]) -> None:
        self.app = app
        self.hosts = frozenset(allowed_hosts)
        self.origins = frozenset(allowed_origins)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        method = str(scope.get("method", "GET")).upper()
        host = (_header(scope, b"host") or "").rsplit(":", 1)[0].lower().strip("[]")
        if host not in self.hosts:
            _note(scope, "rejected_host", "host_not_allowed")
            await _reject(send, 400, "invalid_host", "Request refused.")
            return
        origin = _header(scope, b"origin")
        if origin is not None and origin not in self.origins:
            _note(scope, "rejected_origin", "origin_not_allowed")
            await _reject(send, 403, "forbidden_origin", "Request refused.")
            return
        if method not in ALLOWED_METHODS:
            _note(scope, "rejected_method", "method_not_allowed")
            await _reject(send, 405, "method_not_allowed", "Method not allowed.")
            return
        if method not in SAFE_METHODS and _header(scope, CLIENT_HEADER) != "web":
            _note(scope, "rejected_request", "missing_client_header")
            await _reject(send, 403, "missing_client_header", "Request refused.")
            return
        await self.app(scope, receive, send)


class AccessControlMiddleware:
    """Public-mode login gate and read-only demo gate, both enforced at the API layer."""

    def __init__(
        self, app: ASGIApp, *, public: bool, read_only: bool, sessions: SessionStore
    ) -> None:
        self.app = app
        self.public = public
        self.read_only = read_only
        self.sessions = sessions

    @staticmethod
    def _cookie(scope: Scope) -> str | None:
        raw = _header(scope, b"cookie") or ""
        for part in raw.split(";"):
            name, _, value = part.strip().partition("=")
            if name == SESSION_COOKIE:
                return value
        return None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        method = str(scope.get("method", "GET")).upper()
        path = str(scope.get("path", ""))
        if method != "OPTIONS":
            if self.public and path not in PUBLIC_PATHS and not self.sessions.validate(
                self._cookie(scope)
            ):
                _note(scope, "auth_failure", "login_required")
                await _reject(send, 401, "auth_required", "Sign in to continue.")
                return
            if (
                self.read_only
                and method not in SAFE_METHODS
                and not (
                    method == "POST"
                    and (path in READ_ONLY_POST or path.startswith("/api/coach/tools/"))
                )
                and path != "/api/auth/login"
                and path != "/api/auth/logout"
            ):
                _note(scope, "rejected_write", "read_only_mode")
                await _reject(send, 403, "read_only", "This demo is read-only.")
                return
        await self.app(scope, receive, send)


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
            (b"cross-origin-opener-policy", b"same-origin"),
            (b"cross-origin-resource-policy", b"same-origin"),
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
            _note(scope, "rate_limited", "requests_per_minute")
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
                _note(scope, "busy", "heavy_job_limit")
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
