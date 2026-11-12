"""Find the numbers written in a sentence.

Shared by the check that every number in the deterministic report has a sourced figure, and by
the check that every number in a language-model answer came from a tool result.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Signs are not part of a token: "-62.10 USD" and "62.10" name the same figure.
NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


@dataclass(frozen=True)
class NumberToken:
    text: str
    value: float
    decimals: int
    percent: bool


def _clean(token: str) -> str:
    return token.rstrip(",").replace(",", "")


def tokens(text: str) -> list[NumberToken]:
    """Every number in the text, with how many decimals it was written with and whether a percent
    sign follows it."""
    found: list[NumberToken] = []
    for match in NUMBER.finditer(text):
        raw = _clean(match.group(0))
        if not raw:
            continue
        rest = text[match.end() :].lstrip()
        decimals = len(raw.split(".", 1)[1]) if "." in raw else 0
        found.append(NumberToken(raw, float(raw), decimals, rest.startswith("%")))
    return found


def numbers(text: str) -> set[float]:
    return {token.value for token in tokens(text)}
