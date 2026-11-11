"""Number formatting and Figure construction.

The text in rules and summaries is built from the same Figure `display` strings, so a sentence can
never show a number that differs from the figure behind it.
"""

from __future__ import annotations

import math

from obsidian_ledger.coach.models import Figure, Unit


def money(value: float | None, currency: str) -> str:
    if value is None or not math.isfinite(value):
        return "n/a"
    sign = "-" if value < 0 else "+"
    return f"{sign}{abs(value):,.2f} {currency}"


def plain_money(value: float | None, currency: str) -> str:
    if value is None or not math.isfinite(value):
        return "n/a"
    return f"{abs(value):,.2f} {currency}"


def r_text(value: float | None) -> str:
    if value is None or not math.isfinite(value):
        return "n/a"
    sign = "-" if value < 0 else "+"
    return f"{sign}{abs(value):.2f} R"


def duration(seconds: float | None) -> str:
    if seconds is None or not math.isfinite(seconds):
        return "n/a"
    if seconds < 90:
        return f"{seconds:.0f} s"
    if seconds < 5400:
        return f"{seconds / 60:.0f} min"
    return f"{seconds / 3600:.1f} h"


def figure(
    value: float | int | None,
    unit: Unit,
    source: str,
    label: str,
    currency: str = "",
    *,
    bootstrap: bool = False,
) -> Figure:
    """Build a Figure with its display text. Non-finite values become None."""
    clean: float | None
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        clean = None
    else:
        clean = float(value)
    if clean is None:
        text = "n/a"
    elif unit == "currency":
        text = money(clean, currency)
    elif unit == "R":
        text = r_text(clean)
    elif unit == "count":
        text = f"{int(round(clean)):,}"
    elif unit == "seconds":
        text = duration(clean)
    elif unit == "ratio":
        text = f"{clean * 100:.1f}%"
    elif unit == "number":
        text = f"{clean:.2f}"
    elif unit == "score":
        text = f"{clean:.0f}"
    else:
        text = f"{clean:g}"
    return Figure(
        value=clean,
        unit=unit,
        display=text,
        source=source,
        label=label,
        kind="bootstrap" if bootstrap else "exact",
    )
