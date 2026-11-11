"""Canonical trade fields and scoring of file headers against them."""

from __future__ import annotations

import difflib
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Final, Literal

Confidence = Literal["high", "medium", "low"]
FUZZY_CUTOFF: Final = 0.82

FIELD_SYNONYMS: Final[dict[str, tuple[str, ...]]] = {
    "trade_id": ("trade id", "trade number", "trade no", "ticket", "position id", "deal id"),
    "account": ("account", "account id", "clientaccountid", "login"),
    "symbol": ("symbol", "item", "instrument", "ticker", "pair", "market", "contract"),
    "asset_class": ("asset class", "assetclass", "asset type"),
    "side": ("side", "type", "direction", "action", "buy sell", "buysell"),
    "entry_time": (
        "entry time",
        "open time",
        "open date",
        "entry date",
        "date",
        "date and time",
        "datetime",
        "entry datetime",
        "open datetime",
        "opened",
    ),
    "exit_time": (
        "exit time",
        "close time",
        "close date",
        "exit date",
        "exit datetime",
        "close datetime",
        "closed",
    ),
    "qty": (
        "qty",
        "quantity",
        "size",
        "position size",
        "position size qty",
        "volume",
        "lots",
        "amount",
    ),
    "entry_price": (
        "entry price",
        "open price",
        "entry",
        "open",
        "price",
        "trade price",
        "tradeprice",
    ),
    "exit_price": ("exit price", "close price", "exit", "close"),
    "fees": ("fees", "fee", "taxes", "tax"),
    "commission": ("commission", "commissions", "ib commission", "ibcommission"),
    "swap": ("swap", "funding", "financing", "rollover"),
    "gross_pnl": ("gross pnl", "gross p l", "gross profit", "gross", "profit"),
    "net_pnl": ("net pnl", "net p l", "net profit", "net", "pnl", "p l", "realized pnl"),
    "stop_loss": ("stop loss", "stop", "sl", "s l", "stop price"),
    "take_profit": ("take profit", "target", "tp", "t p"),
    "planned_risk": ("planned risk", "risk", "risk amount"),
    "r_multiple": ("r multiple", "rmultiple"),
    "currency": ("currency", "currencyprimary", "currency code", "ccy"),
    "setup": ("setup", "signal", "strategy", "pattern", "playbook"),
    "timeframe": ("timeframe", "time frame", "chart timeframe"),
    "session": ("session",),
    "emotion": ("emotion", "emotional state", "mood"),
    "plan_followed": ("plan followed", "followed plan", "plan adherence"),
    "confidence": ("confidence", "conviction", "trader confidence"),
    "screenshot_path": ("screenshot", "screenshot path", "screenshot url", "chart image", "chart"),
    "mae": ("mae", "adverse excursion"),
    "mfe": ("mfe", "favorable excursion", "favourable excursion"),
    "notes": ("notes", "note", "comment", "comments", "memo", "description", "journal"),
    "tags": ("tags", "tag", "labels"),
    "multiplier": ("multiplier", "contract multiplier", "contract size"),
    "order_id": ("order id", "orderid"),
}

# Fields that only broker adapters produce. They describe one leg or fill of a file.
ADAPTER_FIELDS: Final[tuple[str, ...]] = ("leg", "leg_time", "leg_price", "fill_time", "fill_price")
CANONICAL_FIELDS: Final[tuple[str, ...]] = tuple(FIELD_SYNONYMS)
ALL_FIELDS: Final[frozenset[str]] = frozenset(CANONICAL_FIELDS + ADAPTER_FIELDS)

_TOKEN_SPLIT: Final = re.compile(r"[^a-z0-9]+")


def normalize_header(text: str) -> str:
    """Lowercase and split on every non-alphanumeric character. "P&L" becomes "p l"."""
    return " ".join(part for part in _TOKEN_SPLIT.split(text.lower()) if part)


_NORMAL_SYNONYMS: Final[tuple[tuple[str, str], ...]] = tuple(
    (field, normalize_header(synonym))
    for field, synonyms in FIELD_SYNONYMS.items()
    for synonym in synonyms
)


@dataclass(frozen=True)
class HeaderMatch:
    field: str
    score: float
    confidence: Confidence


def _confidence(score: float) -> Confidence:
    if score >= 3.0:
        return "high"
    if score >= 2.0:
        return "medium"
    return "low"


def _score(name: str, tokens: frozenset[str], synonym: str) -> float:
    if name == synonym:
        return 3.0
    parts = synonym.split()
    if parts and set(parts) <= tokens:
        # Every word of the synonym appears in the header. Longer synonyms score higher.
        return 2.0 + min(len(parts), 9) / 10
    # quick_ratio is an upper bound on ratio. If it is already below the cut-off, the full match
    # cannot pass it either, so the expensive SequenceMatcher call is skipped without changing
    # any result.
    total = len(name) + len(synonym)
    # Shared characters cannot exceed the shorter string, so this length bound is also an upper
    # bound on the ratio. Most pairs fail it without any character counting.
    if total and 2 * min(len(name), len(synonym)) < FUZZY_CUTOFF * total:
        return 0.0
    if _quick_ratio(name, synonym) < FUZZY_CUTOFF:
        return 0.0
    ratio = difflib.SequenceMatcher(None, name, synonym).ratio()
    if ratio >= FUZZY_CUTOFF:
        return 1.0 + ratio / 10
    return 0.0


@lru_cache(maxsize=1024)
def _char_counts(text: str) -> Counter[str]:
    return Counter(text)


def _quick_ratio(name: str, synonym: str) -> float:
    """Same value as difflib's quick_ratio: twice the shared characters over the total length."""
    total = len(name) + len(synonym)
    if total == 0:
        return 1.0
    shared = sum((_char_counts(name) & _char_counts(synonym)).values())
    return 2.0 * shared / total


@lru_cache(maxsize=4096)
def header_matches(header: str) -> dict[str, HeaderMatch]:
    """Best score for each canonical field that the header could represent.

    The result is cached and must not be modified by callers.
    """
    name = normalize_header(header)
    if not name:
        return {}
    tokens = frozenset(name.split())
    best: dict[str, HeaderMatch] = {}
    for field, synonym in _NORMAL_SYNONYMS:
        score = _score(name, tokens, synonym)
        if score <= 0.0:
            continue
        current = best.get(field)
        if current is None or score > current.score:
            best[field] = HeaderMatch(field=field, score=score, confidence=_confidence(score))
    return best


def assign_fields(
    headers: Sequence[str],
    taken_columns: set[int],
    taken_fields: set[str],
) -> dict[int, HeaderMatch]:
    """Give each free column at most one field, best scores first, never reusing a field."""
    candidates: list[tuple[float, int, str, HeaderMatch]] = []
    for index, header in enumerate(headers):
        if index in taken_columns:
            continue
        for field, match in header_matches(header).items():
            if field not in taken_fields:
                candidates.append((match.score, index, field, match))
    candidates.sort(key=lambda item: (-item[0], item[1], item[2]))
    chosen: dict[int, HeaderMatch] = {}
    used_fields = set(taken_fields)
    for _score_value, index, field, match in candidates:
        if index in chosen or field in used_fields:
            continue
        chosen[index] = match
        used_fields.add(field)
    return chosen
