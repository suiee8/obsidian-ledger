"""Check that every number a model wrote came from a tool result in the same request.

The allowed numbers are collected from exactly the JSON the model was sent. Two kinds of source
count:

1. Engine text: numbers inside strings the app wrote, such as a figure's display ("-62.10 USD")
   or a rule. A number in the answer matches if it is written the same way ("62.10").
2. Raw values: a JSON number such as 0.4567 or 1358. A number in the answer matches if it equals
   the value written to the precision used, and either has at least the value's own detail
   (two decimals, or one for a percent) or the value is a whole number. "45.7%" matches 0.4567;
   "46%" does not, and neither does "90%" unless some result holds exactly 0.9 or shows "90%".
   A percent is only ever matched by a ratio or by a text that also showed it as a percent, so a
   count of 90 trades never supports "90%".

Free text the user or a broker wrote (notes, tags, emotions, symbols, setups, accounts, trade ids)
is never a source, because it is the channel a prompt injection would use. Short identifiers from
results (a symbol such as US500, a trade id such as T000042) may be named in an answer: they are
removed before the check, so their digits never count as figures. An identifier must contain a
letter and no spaces, so text such as "90% win rate" is never treated as a name.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Final

from obsidian_ledger.coach.numbers import NumberToken, tokens

IDENTIFIER: Final = re.compile(r"^(?=.*[A-Za-z])[A-Za-z0-9._/\-]{1,40}$")
NAME_KEYS: Final = frozenset({"symbol", "setup", "account", "trade_id", "group"})

USER_TEXT: Final = frozenset(
    {
        "notes",
        "tags",
        "emotion",
        "symbol",
        "setup",
        "account",
        "trade_id",
        "trade_key",
        "group",
        "screenshot_path",
        "timeframe",
        "source_timezone",
        "confidence",
        "untrusted_text",
    }
)


@dataclass
class Allowed:
    texts: set[str] = field(default_factory=set[str])
    percent_texts: set[str] = field(default_factory=set[str])
    values: list[float] = field(default_factory=list[float])
    names: set[str] = field(default_factory=set[str])

    def add_payload(self, payload: Any, key: str = "") -> None:
        if isinstance(payload, bool) or payload is None:
            return
        if key in USER_TEXT and not isinstance(payload, str):
            return  # a note wrapped as {"untrusted_text": ...}: nothing inside it is a source
        if isinstance(payload, int | float):
            if math.isfinite(payload):
                self.values.append(float(payload))
            return
        if isinstance(payload, str):
            if key in NAME_KEYS and IDENTIFIER.match(payload.strip()):
                self.names.add(payload.strip())
            if key not in USER_TEXT:
                self.add_text(payload)
            return
        if isinstance(payload, dict):
            for child_key, child in payload.items():  # pyright: ignore[reportUnknownVariableType]
                self.add_payload(child, str(child_key))  # pyright: ignore[reportUnknownArgumentType]
            return
        if isinstance(payload, list | tuple):
            for child in payload:  # pyright: ignore[reportUnknownVariableType]
                self.add_payload(child, key)

    def add_text(self, text: str) -> None:
        for token in tokens(text):
            (self.percent_texts if token.percent else self.texts).add(token.text)

    def matches(self, token: NumberToken) -> bool:
        if token.text in (self.percent_texts if token.percent else self.texts):
            return True
        for value in self.values:
            if token.percent:
                if abs(value) > 1:
                    continue
                choices = ((abs(value) * 100, 1),)
            else:
                choices = ((abs(value), 2),)
            for candidate, minimum in choices:
                if f"{candidate:.{token.decimals}f}" != token.text:
                    continue
                whole = math.isclose(candidate, round(candidate), abs_tol=1e-9)
                if token.decimals >= minimum or whole:
                    return True
        return False


def unmatched(text: str, allowed: Allowed) -> list[str]:
    """Numbers in the text that no tool result supports."""
    masked = text
    for name in sorted(allowed.names, key=len, reverse=True):
        masked = re.sub(rf"(?<![A-Za-z0-9]){re.escape(name)}(?![A-Za-z0-9])", " ", masked)
    return [token.text for token in tokens(masked) if not allowed.matches(token)]
