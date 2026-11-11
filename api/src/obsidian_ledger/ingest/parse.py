"""Parsers for numbers, timestamps, and trade direction words."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Final, Literal

DecimalStyle = Literal["dot", "comma"]

SLASH_DAYFIRST: Final = "slash_dayfirst"
SLASH_MONTHFIRST: Final = "slash_monthfirst"


@dataclass(frozen=True)
class DateCandidate:
    key: str
    pattern: str
    # Only the two slash families are ambiguous. Every other pattern is unambiguous.
    family: str | None


# Order matters only when two patterns could read the same text. Patterns with
# a family are tried only when the file's slash family matches.
DATE_CANDIDATES: Final[tuple[DateCandidate, ...]] = (
    DateCandidate("iso_offset", "%Y-%m-%dT%H:%M:%S%z", None),
    DateCandidate("iso", "%Y-%m-%dT%H:%M:%S", None),
    DateCandidate("iso_space", "%Y-%m-%d %H:%M:%S", None),
    DateCandidate("iso_space_minutes", "%Y-%m-%d %H:%M", None),
    DateCandidate("mt5", "%Y.%m.%d %H:%M:%S", None),
    DateCandidate("mt5_minutes", "%Y.%m.%d %H:%M", None),
    DateCandidate("ibkr_compact", "%Y%m%d;%H%M%S", None),
    DateCandidate("dotted_dayfirst", "%d.%m.%Y %H:%M:%S", None),
    DateCandidate("dotted_dayfirst_minutes", "%d.%m.%Y %H:%M", None),
    DateCandidate("slash_dayfirst", "%d/%m/%Y %H:%M:%S", SLASH_DAYFIRST),
    DateCandidate("slash_dayfirst_minutes", "%d/%m/%Y %H:%M", SLASH_DAYFIRST),
    DateCandidate("slash_monthfirst", "%m/%d/%Y %H:%M:%S", SLASH_MONTHFIRST),
    DateCandidate("slash_monthfirst_minutes", "%m/%d/%Y %H:%M", SLASH_MONTHFIRST),
)

_NUMBER_VALUE: Final = re.compile(r"^[+-]?\d+(\.\d+)?$")
_COMMA_STYLE: Final = re.compile(r"^[+-]?(\d{1,3}(\.\d{3})+,\d+|\d+,\d{1,2}|\d+,\d{5,})$")
_DOT_STYLE: Final = re.compile(r"^[+-]?(\d{1,3}(,\d{3})+\.\d+|\d+\.\d+)$")
_CURRENCY_SIGNS: Final = re.compile(r"[$€£¥]")


def parse_number(text: str, style: DecimalStyle) -> float | None:
    """Parse a number written with the file's decimal style. Returns None if it is not numeric."""
    cleaned = text.strip().replace("\u00a0", "").replace(" ", "")
    if not cleaned:
        return None
    negative = cleaned.startswith("(") and cleaned.endswith(")")
    if negative:
        cleaned = cleaned[1:-1]
    cleaned = _CURRENCY_SIGNS.sub("", cleaned)
    if style == "comma":
        cleaned = cleaned.replace(".", "").replace(",", ".")
    else:
        cleaned = cleaned.replace(",", "")
    if not _NUMBER_VALUE.match(cleaned):
        return None
    value = float(cleaned)
    return -value if negative else value


def count_number_style(values: Iterable[str]) -> tuple[DecimalStyle, int, int]:
    """Vote on the decimal style. Returns (style, comma_votes, dot_votes).

    Values such as "1,085" fit both styles and are not counted.
    """
    comma = 0
    dot = 0
    for raw in values:
        text = raw.strip().replace(" ", "")
        if _COMMA_STYLE.match(text):
            comma += 1
        elif _DOT_STYLE.match(text):
            dot += 1
    return ("comma" if comma > dot else "dot"), comma, dot


def parse_side(text: str) -> Literal["long", "short"] | None:
    """Read direction words such as "buy", "Entry long", or "SELL"."""
    words = set(re.findall(r"[a-z]+", text.lower()))
    if words & {"long", "buy"}:
        return "long"
    if words & {"short", "sell"}:
        return "short"
    return None


def parse_time(text: str, slash_family: str | None) -> tuple[datetime, bool] | None:
    """Parse one timestamp. Returns (value, has_offset), or None if no candidate fits."""
    for candidate in DATE_CANDIDATES:
        if candidate.family is not None and candidate.family != slash_family:
            continue
        try:
            value = datetime.strptime(text.strip(), candidate.pattern)
        except ValueError:
            continue
        return value, value.tzinfo is not None
    return None


@dataclass(frozen=True)
class DateChoice:
    """Result of testing every date pattern against sample values from one file."""

    total: int
    counts: dict[str, int]
    slash_family: str | None
    ambiguous: bool

    def summary(self) -> str:
        used = [(key, n) for key, n in self.counts.items() if n > 0]
        if not used:
            return f"no sample matched a known date format ({self.total} samples)"
        parts = ", ".join(f"{key} {n}" for key, n in sorted(used, key=lambda item: -item[1]))
        return f"{parts} of {self.total} samples"


def choose_date_format(samples: list[str]) -> DateChoice:
    """Detect which patterns the samples use and whether slash dates are ambiguous."""
    cleaned = [value.strip() for value in samples if value.strip()]
    counts: dict[str, int] = {}
    for candidate in DATE_CANDIDATES:
        hits = 0
        for value in cleaned:
            try:
                datetime.strptime(value, candidate.pattern)
            except ValueError:
                continue
            hits += 1
        counts[candidate.key] = hits
    total = len(cleaned)
    full_families = {
        candidate.family
        for candidate in DATE_CANDIDATES
        if candidate.family is not None and total > 0 and counts[candidate.key] == total
    }
    if len(full_families) >= 2:
        return DateChoice(total, counts, None, ambiguous=True)
    if len(full_families) == 1:
        return DateChoice(total, counts, next(iter(full_families)), ambiguous=False)
    # No family parses every sample. Use the family that parses the most samples.
    slash_scores = {
        family: max(
            counts[candidate.key] for candidate in DATE_CANDIDATES if candidate.family == family
        )
        for family in (SLASH_DAYFIRST, SLASH_MONTHFIRST)
    }
    best_family = max(slash_scores, key=lambda family: slash_scores[family])
    slash_family = best_family if slash_scores[best_family] > 0 else None
    return DateChoice(total, counts, slash_family, ambiguous=False)
