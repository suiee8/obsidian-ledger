"""Run the Coach: cache and store reports, compare with the previous one, and stream progress."""

from __future__ import annotations

import json
import threading
import time
import uuid
from collections.abc import Callable, Iterator
from dataclasses import asdict
from typing import Any

import polars as pl

from obsidian_ledger.coach.models import Change, ChangeItem, CoachReport
from obsidian_ledger.coach.params import CoachParams
from obsidian_ledger.coach.report import build_report
from obsidian_ledger.coach.slices import MEASURED_PATTERNS, SliceBuilder
from obsidian_ledger.metrics.data import Filters
from obsidian_ledger.metrics.engine import AnalysisEngine
from obsidian_ledger.store.db import Store

STEPS: tuple[tuple[str, str], ...] = (
    ("reading", "Reading"),
    ("mapping", "Mapping"),
    ("cleaning", "Cleaning"),
    ("computing", "Computing"),
    ("finding", "Finding leaks"),
    ("writing", "Writing report"),
)
CHANGE_LABELS: dict[str, str] = {
    "trades": "Trades",
    "net_pnl": "Net P&L",
    "expectancy": "Average P&L per trade",
    "expectancy_r": "Average R per trade",
    "win_rate": "Win rate",
    "max_drawdown": "Largest drawdown",
}


def filters_dict(filters: Filters) -> dict[str, Any]:
    return {
        "date_from": filters.date_from.isoformat() if filters.date_from else None,
        "date_to": filters.date_to.isoformat() if filters.date_to else None,
        "accounts": list(filters.accounts),
        "symbols": list(filters.symbols),
        "setups": list(filters.setups),
        "sides": list(filters.sides),
        "tag": filters.tag,
    }


def compare(previous: CoachReport, current: CoachReport) -> Change:
    """What moved between two reports: headline numbers and which findings appeared or went."""
    items: list[ChangeItem] = []
    for key, label in CHANGE_LABELS.items():
        before = previous.key_figures.get(key)
        after = current.key_figures.get(key)
        if before is not None and after is not None:
            items.append(ChangeItem(key=key, label=label, previous=before, current=after))

    def ids(report: CoachReport) -> set[str]:
        return {f.id for f in report.top_leaks + report.top_strengths}

    return Change(
        previous_report_id=previous.report_id,
        previous_generated_at=previous.generated_at,
        metrics=items,
        new_finding_ids=sorted(ids(current) - ids(previous)),
        resolved_finding_ids=sorted(ids(previous) - ids(current)),
    )


class CoachService:
    def __init__(
        self, store: Store, engine: AnalysisEngine, params: CoachParams | None = None
    ) -> None:
        self.store = store
        self.engine = engine
        self.params = params or CoachParams()
        self._lock = threading.Lock()

    def report(
        self,
        filters: Filters,
        *,
        force: bool = False,
        progress: Callable[[str], None] | None = None,
    ) -> CoachReport:
        """The report for these filters. Cached by dataset version, filters, and parameters.

        A cache hit returns the stored report unchanged. A new report is saved with its change
        against the latest earlier report for the same filters.
        """
        version, prepared = self.engine.trades_for(filters)
        filter_key = filters.key()
        params_key = json.dumps(asdict(self.params), sort_keys=True)
        with self._lock:
            if not force:
                stored = self.store.find_coach_report(version, filter_key, params_key)
                if stored is not None:
                    return CoachReport.model_validate_json(stored)
            frame = prepared.frame
            currency = str(frame["base_currency"][0]) if frame.height else "USD"
            built = build_report(
                frame,
                filters=filters_dict(filters),
                filter_key=filter_key,
                dataset_version=version,
                params=self.params,
                currency=currency,
                starting_equity=self.engine.starting_equity(),
                excluded_no_fx=prepared.excluded_no_fx,
                progress=progress,
            )
            previous_json = self.store.latest_coach_report(filter_key)
            change = (
                compare(CoachReport.model_validate_json(previous_json), built)
                if previous_json is not None and built.status == "ok"
                else None
            )
            report = built.model_copy(
                update={"report_id": uuid.uuid4().hex, "change_vs_previous": change}
            )
            self.store.save_coach_report(
                report.report_id, version, filter_key, params_key, report.model_dump_json()
            )
            return report

    def finding_trade_keys(self, filters: Filters, finding_id: str) -> list[str] | None:
        """The trades one finding is about, for the same filters its report was built with.

        This is the same mask the finding's own figures were computed from, so the count always
        equals the finding's `n`. Returns None when the id names nothing in this data.
        """
        _version, prepared = self.engine.trades_for(filters)
        frame = prepared.frame
        if frame.height == 0:
            return None
        builder = SliceBuilder(frame, self.params, str(frame["base_currency"][0]))
        name = finding_id.removeprefix("beh~") if finding_id.startswith("beh~") else ""
        if name in MEASURED_PATTERNS:
            measured = builder.amounts(name)
            mask = measured[0] if measured is not None else None
        else:
            found = builder.get(finding_id)
            mask = found.mask if found is not None else None
        if mask is None:
            return None
        return builder.frame["trade_key"].filter(pl.Series(mask)).to_list()

    def stored(self, report_id: str) -> CoachReport | None:
        text = self.store.get_coach_report(report_id)
        return CoachReport.model_validate_json(text) if text is not None else None

    # ----- streaming -----

    def _import_details(self) -> dict[str, str]:
        """What the import already did, for the first three timeline steps."""
        record = self.store.latest_import()
        if record is None:
            return {
                "reading": "No import on record. Using the trades already stored.",
                "mapping": "Nothing to map.",
                "cleaning": "Nothing to clean.",
            }
        total = int(record.get("rows_total", 0))
        accepted = int(record.get("accepted", 0))
        rejected = int(record.get("rejected", 0))
        issues = record.get("issues", [])
        return {
            "reading": f"Read {total:,} rows from {record.get('filename', 'the file')}.",
            "mapping": (
                f"Layout: {record.get('adapter') or 'generic'}, "
                f"{record.get('shape') or 'unknown'} rows."
            ),
            "cleaning": (
                f"{accepted:,} rows accepted, {rejected:,} rejected, "
                f"{len(issues) if isinstance(issues, list) else 0} data-quality notes."  # pyright: ignore
            ),
        }

    def stream(self, filters: Filters, *, force: bool = False) -> Iterator[dict[str, Any]]:
        """Yield one event per step change, then a final `done` or `error` event.

        The first three steps describe what the import recorded. The last three run now, and
        their timings are measured.
        """
        details = self._import_details()
        for key, label in STEPS[:3]:
            yield {
                "step": key,
                "label": label,
                "status": "done",
                "detail": details[key],
                "seconds": 0.0,
            }
        events: list[dict[str, Any]] = []
        started: dict[str, float] = {}
        order = [key for key, _ in STEPS[3:]]
        labels = dict(STEPS)
        outcome: dict[str, Any] = {}

        def on_progress(stage: str) -> None:
            now = time.perf_counter()
            index = order.index(stage)
            if index > 0:
                previous = order[index - 1]
                events.append(
                    {
                        "step": previous,
                        "label": labels[previous],
                        "status": "done",
                        "detail": "",
                        "seconds": now - started[previous],
                    }
                )
            started[stage] = now
            events.append(
                {
                    "step": stage,
                    "label": labels[stage],
                    "status": "running",
                    "detail": "",
                    "seconds": 0.0,
                }
            )

        def work() -> None:
            try:
                outcome["report"] = self.report(filters, force=force, progress=on_progress)
            except Exception as exc:  # noqa: BLE001 - reported to the client as an error event
                outcome["error"] = str(exc)

        worker = threading.Thread(target=work, daemon=True)
        worker.start()
        sent = 0
        while worker.is_alive() or sent < len(events):
            while sent < len(events):
                yield events[sent]
                sent += 1
            worker.join(timeout=0.02)
        report = outcome.get("report")
        if isinstance(report, CoachReport):
            last = order[-1]
            if last in started:
                yield {
                    "step": last,
                    "label": labels[last],
                    "status": "done",
                    "detail": "",
                    "seconds": time.perf_counter() - started[last],
                }
            else:  # served from the stored report, so the run steps had nothing to do
                for key in order:
                    yield {
                        "step": key,
                        "label": labels[key],
                        "status": "done",
                        "detail": "Reused the stored report for this data.",
                        "seconds": 0.0,
                    }
            yield {"step": "done", "status": "done", "report_id": report.report_id}
        else:
            yield {"step": "error", "status": "error", "detail": outcome.get("error", "failed")}
