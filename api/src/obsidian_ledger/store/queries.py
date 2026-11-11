"""SQL pieces for trade queries. Filter values always travel as bound parameters."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Final

from obsidian_ledger.metrics.data import Filters

# Columns a client may sort by. Anything else is rejected before it reaches SQL.
SORTABLE: Final[frozenset[str]] = frozenset(
    {
        "exit_time",
        "entry_time",
        "symbol",
        "side",
        "setup",
        "qty",
        "net_pnl_base",
        "r_multiple",
        "holding_seconds",
        "trade_id",
    }
)
# Fields a user may edit on a trade. Everything else is derived or imported.
EDITABLE: Final[frozenset[str]] = frozenset({"notes", "tags", "emotion", "confidence"})


def where_clause(filters: Filters, keys: Sequence[str] | None = None) -> tuple[str, list[Any]]:
    """WHERE clause and parameters for a Filters value. Trades without base P&L are excluded,
    matching the metrics. `keys` narrows the result to those trades (a brushed selection)."""
    clauses: list[str] = ["net_pnl_base IS NOT NULL"]
    params: list[Any] = []
    if filters.date_from is not None:
        clauses.append("CAST(exit_time AS DATE) >= ?")
        params.append(filters.date_from)
    if filters.date_to is not None:
        clauses.append("CAST(exit_time AS DATE) <= ?")
        params.append(filters.date_to)
    for column, values in (
        ("account", filters.accounts),
        ("symbol", filters.symbols),
        ("setup", filters.setups),
        ("side", filters.sides),
    ):
        if values:
            placeholders = ", ".join("?" for _ in values)
            clauses.append(f"{column} IN ({placeholders})")
            params.extend(values)
    if filters.tag:
        clauses.append(
            "(instr(lower(coalesce(tags, '')), ?) > 0 OR lower(coalesce(emotion, '')) = ?)"
        )
        params.extend([filters.tag.lower(), filters.tag.lower()])
    if keys is not None:
        clauses.append("list_contains(?, trade_key)")
        params.append(list(keys))
    return " WHERE " + " AND ".join(clauses), params


def order_clause(sort: str, descending: bool) -> str:
    if sort not in SORTABLE:
        raise ValueError(f"Cannot sort by '{sort}'.")
    direction = "DESC" if descending else "ASC"
    return f"ORDER BY {sort} {direction} NULLS LAST, trade_key"
