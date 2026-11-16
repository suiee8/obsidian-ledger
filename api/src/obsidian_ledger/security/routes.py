"""Login status and session routes. In local mode there is nothing to log into."""

from __future__ import annotations

import math

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from obsidian_ledger.security.auth import (
    SESSION_COOKIE,
    LoginThrottle,
    SessionStore,
    verify_password,
)
from obsidian_ledger.security.events import SecurityLog

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginIn(BaseModel):
    password: str = Field(min_length=1, max_length=1024)


def _client(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _error(status: int, code: str, message: str, retry_after: float = 0.0) -> JSONResponse:
    headers = {"Retry-After": str(math.ceil(retry_after))} if retry_after else None
    return JSONResponse(
        status_code=status, content={"error": {"code": code, "message": message}}, headers=headers
    )


@router.get("/status")
def status(request: Request) -> dict[str, bool]:
    settings = request.app.state.settings
    sessions: SessionStore = request.app.state.sessions
    authenticated = (not settings.public) or sessions.validate(request.cookies.get(SESSION_COOKIE))
    return {
        "public": settings.public,
        "authenticated": authenticated,
        "read_only": settings.demo_readonly,
    }


@router.post("/login")
def login(body: LoginIn, request: Request) -> Response:
    settings = request.app.state.settings
    if not settings.public:
        return _error(404, "not_found", "Login is not enabled.")
    throttle: LoginThrottle = request.app.state.login_throttle
    log: SecurityLog = request.app.state.security_log
    client = _client(request)
    wait = throttle.retry_after(client)
    if wait > 0:
        log.record("rate_limited", client=client, path="/api/auth/login", reason="login_backoff")
        return _error(429, "login_locked", "Too many attempts. Try again later.", wait)
    if not verify_password(body.password, settings.password_hash):
        throttle.failure(client)
        log.record("auth_failure", client=client, path="/api/auth/login", reason="bad_password")
        return _error(401, "invalid_credentials", "Incorrect password.")
    throttle.success(client)
    sessions: SessionStore = request.app.state.sessions
    response = JSONResponse({"authenticated": True})
    response.set_cookie(
        SESSION_COOKIE,
        sessions.create(),
        httponly=True,
        secure=True,
        samesite="strict",
        path="/",
    )
    return response


@router.post("/logout")
def logout(request: Request) -> Response:
    sessions: SessionStore = request.app.state.sessions
    sessions.destroy(request.cookies.get(SESSION_COOKIE))
    response = JSONResponse({"authenticated": False})
    response.delete_cookie(SESSION_COOKIE, path="/", secure=True, httponly=True, samesite="strict")
    return response
