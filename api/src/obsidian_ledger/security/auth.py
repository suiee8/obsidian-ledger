"""Single-user password login for public mode. scrypt from the standard library, no new dependency."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import time
from collections.abc import Callable

SESSION_COOKIE = "ledger_session"
SCRYPT_N = 2**15
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_MAXMEM = 128 * 1024 * 1024


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        maxmem=SCRYPT_MAXMEM,
        dklen=32,
    )
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str | None) -> bool:
    """Constant-time check. Any malformed stored value simply fails."""
    try:
        scheme, n, r, p, salt, expected = (stored or "").split("$")
        if scheme != "scrypt":
            return False
        digest = hashlib.scrypt(
            password.encode("utf-8"),
            salt=_unb64(salt),
            n=int(n),
            r=int(r),
            p=int(p),
            maxmem=SCRYPT_MAXMEM,
            dklen=32,
        )
        return hmac.compare_digest(digest, _unb64(expected))
    except (ValueError, TypeError):
        return False


class SessionStore:
    """In-memory sessions with an idle timeout. A restart signs everyone out."""

    def __init__(self, idle_seconds: float, clock: Callable[[], float] = time.monotonic) -> None:
        self.idle_seconds = idle_seconds
        self.clock = clock
        self._sessions: dict[str, float] = {}

    def create(self) -> str:
        token = secrets.token_urlsafe(32)
        self._sessions[token] = self.clock()
        return token

    def validate(self, token: str | None) -> bool:
        """True and refreshes the idle timer when the session is live."""
        if not token:
            return False
        seen = self._sessions.get(token)
        if seen is None:
            return False
        now = self.clock()
        if now - seen > self.idle_seconds:
            del self._sessions[token]
            return False
        self._sessions[token] = now
        return True

    def destroy(self, token: str | None) -> None:
        if token:
            self._sessions.pop(token, None)


class LoginThrottle:
    """Backoff per client: free for two failures, then 2, 4, 8 ... seconds up to 15 minutes."""

    MAX_DELAY = 900.0

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self.clock = clock
        self._state: dict[str, tuple[int, float]] = {}

    def retry_after(self, client: str) -> float:
        _, blocked_until = self._state.get(client, (0, 0.0))
        return max(0.0, blocked_until - self.clock())

    def failure(self, client: str) -> None:
        count, _ = self._state.get(client, (0, 0.0))
        count += 1
        delay = min(2.0 ** (count - 2), self.MAX_DELAY) if count >= 3 else 0.0
        self._state[client] = (count, self.clock() + delay)

    def success(self, client: str) -> None:
        self._state.pop(client, None)
