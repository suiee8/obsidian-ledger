from __future__ import annotations

from typing import Any


class IngestError(Exception):
    """A file-level failure that stops the import, with a stable machine-readable code."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status: int = 422,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.details = details or {}
