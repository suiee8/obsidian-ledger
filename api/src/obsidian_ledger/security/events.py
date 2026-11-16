"""Security event log. Records what was rejected, never trade data, notes, or keys."""

from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

MAX_LOG_BYTES = 2 * 1024 * 1024
LOG_BACKUPS = 3
_UNSAFE = re.compile(r"[^A-Za-z0-9._:/\-]")


def _clean(value: object, limit: int = 80) -> str:
    return _UNSAFE.sub("?", str(value))[:limit]


class SecurityLog:
    """One file per data folder: `.ledger-data/logs/security.log`."""

    def __init__(self, data_dir: Path) -> None:
        log_dir = data_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        # A private Logger (not registered by name) so several apps in one process never share it.
        self._logger = logging.Logger("obsidian_ledger.security", logging.INFO)
        self._handler = RotatingFileHandler(
            log_dir / "security.log",
            maxBytes=MAX_LOG_BYTES,
            backupCount=LOG_BACKUPS,
            encoding="utf-8",
        )
        self._handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
        self._logger.addHandler(self._handler)

    def record(
        self,
        event: str,
        *,
        client: str | None = None,
        method: str | None = None,
        path: str | None = None,
        reason: str | None = None,
    ) -> None:
        """Only these fields exist. The path keeps two segments so ids and keys never appear."""
        short_path = "/".join((path or "").split("/")[:3])
        parts = [f"event={_clean(event)}"]
        for name, value in (
            ("client", client),
            ("method", method),
            ("path", short_path or None),
            ("reason", reason),
        ):
            if value:
                parts.append(f"{name}={_clean(value)}")
        self._logger.info(" ".join(parts))

    def close(self) -> None:
        self._handler.close()
        self._logger.removeHandler(self._handler)
