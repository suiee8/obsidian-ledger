"""Atomic replacement helpers for user data written by the API."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4


@contextmanager
def atomic_path(destination: Path) -> Generator[Path, None, None]:
    """Yield a sibling temporary path and replace the destination only on success."""
    temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
    try:
        yield temporary
        temporary.replace(destination)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
