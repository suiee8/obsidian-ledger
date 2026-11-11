"""Short-lived sets of trade keys, made by brushing a chart, that the Trades table can show.

Held in memory only. A selection lives until the server restarts or newer ones push it out.
"""

from __future__ import annotations

import threading
import uuid
from collections import OrderedDict
from dataclasses import dataclass

MAX_SELECTIONS = 16


@dataclass(frozen=True)
class Selection:
    selection_id: str
    keys: tuple[str, ...]


class SelectionStore:
    def __init__(self, limit: int = MAX_SELECTIONS) -> None:
        self._limit = limit
        self._items: OrderedDict[str, Selection] = OrderedDict()
        self._lock = threading.Lock()

    def add(self, keys: list[str]) -> Selection:
        selection = Selection(uuid.uuid4().hex, tuple(keys))
        with self._lock:
            self._items[selection.selection_id] = selection
            while len(self._items) > self._limit:
                self._items.popitem(last=False)
        return selection

    def get(self, selection_id: str) -> Selection | None:
        with self._lock:
            item = self._items.get(selection_id)
            if item is not None:
                self._items.move_to_end(selection_id)
            return item

    def clear(self) -> None:
        with self._lock:
            self._items.clear()
