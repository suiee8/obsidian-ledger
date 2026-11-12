"""Typed views of decoded JSON, so code that reads tool results and replies stays type-checked."""

from __future__ import annotations

from typing import Any, cast


def obj(value: Any) -> dict[str, Any]:
    """The value if it is a JSON object, else an empty one."""
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def arr(value: Any) -> list[Any]:
    """The value if it is a JSON array, else an empty one."""
    return cast(list[Any], value) if isinstance(value, list) else []
