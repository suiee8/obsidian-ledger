"""The Coach tools as the model sees them.

The existing typed tools (coach/tools.py) compute everything. This module decides which of them a
model may call under the privacy settings, and turns each result into a short JSON of display
strings, so a small local model copies numbers instead of working them out.

Privacy:
- aggregates only (the default): get_metrics, compare_segments, find_leaks, find_strengths, and
  simulate_rule. No trade rows, no trade ids, no notes.
- include_trade_rows: also get_trade and list_trades, and evidence trade ids on findings.
- include_notes: rows also carry notes, tags, and emotion, marked as untrusted text.

Trades behind a finding are kept on the server, so the UI can show them as chips even when the
model never saw a single trade.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Final

from pydantic import ValidationError

from obsidian_ledger.coach.fmt import duration, money, r_text
from obsidian_ledger.coach.models import Finding
from obsidian_ledger.coach.tools import ToolBox
from obsidian_ledger.llm.check import Allowed
from obsidian_ledger.llm.jsonish import arr, obj

AGGREGATE_TOOLS: Final = (
    "get_metrics",
    "compare_segments",
    "find_leaks",
    "find_strengths",
    "simulate_rule",
)
ROW_TOOLS: Final = ("get_trade", "list_trades")
MAX_MODEL_ROWS: Final = 20

_LIMIT: Final = {"type": "integer", "minimum": 1, "maximum": 20}
# What the model is told it may send to each tool. Filters, seeds and resample counts are left
# to the server. The full input models in coach/tools.py still validate every call.
MODEL_PARAMETERS: Final[dict[str, dict[str, Any]]] = {
    "get_metrics": {},
    "compare_segments": {
        "dimension": {
            "type": "string",
            "enum": [
                "symbol",
                "setup",
                "side",
                "session",
                "weekday",
                "hour",
                "holding",
                "size",
                "emotion",
                "account",
                "tag",
            ],
        }
    },
    "find_leaks": {"limit": _LIMIT},
    "find_strengths": {"limit": _LIMIT},
    "simulate_rule": {
        "rules": {
            "type": "object",
            "properties": {
                "daily_loss_cap": {"type": "number"},
                "max_trades_per_day": {"type": "integer"},
                "stop_after_losses": {"type": "integer"},
                "exclude_symbols": {"type": "array", "items": {"type": "string"}},
                "exclude_hours": {"type": "array", "items": {"type": "integer"}},
                "exclude_setups": {"type": "array", "items": {"type": "string"}},
                "cap_risk_per_trade": {"type": "number"},
            },
        }
    },
    "get_trade": {"trade_key": {"type": "string"}},
    "list_trades": {
        "limit": _LIMIT,
        "sort": {
            "type": "string",
            "enum": ["exit_time", "net_pnl_base", "r_multiple", "holding_seconds", "qty"],
        },
        "descending": {"type": "boolean"},
    },
}
MAX_SLICES: Final = 12
NOTE_CHARS: Final = 300


@dataclass(frozen=True)
class Privacy:
    aggregates_only: bool = True
    include_notes: bool = False
    include_trade_rows: bool = False

    @property
    def rows(self) -> bool:
        return not self.aggregates_only and self.include_trade_rows

    @property
    def notes(self) -> bool:
        return self.rows and self.include_notes

    @classmethod
    def from_settings(cls, values: dict[str, Any]) -> Privacy:
        return cls(
            aggregates_only=bool(values.get("aggregates_only", True)),
            include_notes=bool(values.get("include_notes", False)),
            include_trade_rows=bool(values.get("include_trade_rows", False)),
        )


@dataclass(frozen=True)
class Chip:
    trade_key: str
    trade_id: str
    symbol: str
    pnl: str

    def as_dict(self) -> dict[str, str]:
        return {
            "trade_key": self.trade_key,
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "pnl": self.pnl,
        }


@dataclass
class ToolRun:
    """One tool call the model asked for, and what happened."""

    index: int
    name: str
    arguments: dict[str, Any]
    ok: bool
    summary: str
    payload: dict[str, Any]
    allowed: Allowed = field(default_factory=Allowed)
    finding_ids: set[str] = field(default_factory=set[str])
    trade_ids: set[str] = field(default_factory=set[str])

    def public(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "name": self.name,
            "arguments": self.arguments,
            "ok": self.ok,
            "summary": self.summary,
        }


@dataclass
class Evidence:
    """Trades the server can show as chips, collected from tool results in this request."""

    by_finding: dict[str, list[Chip]] = field(default_factory=dict[str, list[Chip]])
    by_trade_id: dict[str, Chip] = field(default_factory=dict[str, Chip])
    finding_rules: dict[str, str] = field(default_factory=dict[str, str])


def _pct(value: Any) -> str | None:
    return f"{float(value) * 100:.1f}%" if isinstance(value, int | float) else None


def _num(value: Any, digits: int = 2) -> str | None:
    return f"{float(value):.{digits}f}" if isinstance(value, int | float) else None


def _money(value: Any, currency: str) -> str | None:
    return money(float(value), currency) if isinstance(value, int | float) else None


def compact_finding(finding: Finding, privacy: Privacy) -> dict[str, Any]:
    interval = finding.interval_currency
    out: dict[str, Any] = {
        "id": finding.id,
        "kind": finding.kind,
        "confidence": finding.confidence,
        "title": finding.title,
        "trades": finding.n.display,
        "average_pnl_per_trade": finding.mean_currency.display,
        "gap_per_trade_vs_other_trades": finding.effect_currency.display,
        "gap_per_trade_in_r": finding.effect_r.display if finding.effect_r else None,
        "interval_95": f"{interval.low.display} to {interval.high.display}" if interval else None,
        "net_pnl_change_if_it_matched_other_trades": finding.what_if.pnl_change.display,
        "rule": finding.rule,
        "evidence_trades": len(finding.evidence),
    }
    if finding.limit is not None:
        out["limit"] = finding.limit.display
    if privacy.rows:
        out["evidence"] = [
            {"trade_id": trade.trade_id, "symbol": trade.symbol, "pnl": trade.pnl.display}
            for trade in finding.evidence[:5]
        ]
    return out


def compact_metrics(report: dict[str, Any], currency: str) -> dict[str, Any]:
    core = obj(report.get("core"))
    risk = obj(report.get("risk"))
    behavior = obj(report.get("behavior"))
    discipline = obj(report.get("discipline"))
    drawdown = obj(risk.get("drawdown"))
    ratios = obj(risk.get("daily_ratios"))
    out: dict[str, Any] = {
        "trades": core.get("trades"),
        "wins": core.get("wins"),
        "losses": core.get("losses"),
        "net_pnl": _money(core.get("net_pnl"), currency),
        "win_rate": _pct(core.get("win_rate")),
        "average_pnl_per_trade": _money(core.get("expectancy"), currency),
        "average_r_per_trade": r_text(core.get("expectancy_r"))
        if core.get("expectancy_r") is not None
        else None,
        "profit_factor": _num(core.get("profit_factor")),
        "largest_win": _money(core.get("largest_win"), currency),
        "largest_loss": _money(core.get("largest_loss"), currency),
        "fee_drag": _pct(core.get("fee_drag")),
        "max_drawdown": _money(drawdown.get("max_drawdown"), currency),
        "max_drawdown_percent_of_peak": _pct(drawdown.get("max_drawdown_pct")),
        "sqn": _num(risk.get("sqn")),
        "sharpe": _num(ratios.get("sharpe")) if ratios.get("available") else None,
        "longest_winning_streak": behavior.get("longest_win_streak"),
        "longest_losing_streak": behavior.get("longest_loss_streak"),
        "revenge_style_trades": obj(behavior.get("revenge")).get("flagged_trades"),
        "overtraded_days": obj(behavior.get("overtrading")).get("overtraded_days"),
        "discipline_score": _num(discipline.get("score"), 0),
        "low_confidence": obj(report.get("sample")).get("low_confidence"),
        "caveats": report.get("caveats", []),
    }
    return {key: value for key, value in out.items() if value is not None}


def compact_segments(table: dict[str, Any], currency: str) -> dict[str, Any]:
    slices: list[dict[str, Any]] = []
    for raw in arr(table.get("slices"))[:MAX_SLICES]:
        item = obj(raw)
        ci = arr(item.get("expectancy_ci95"))
        slices.append(
            {
                "group": item.get("value"),
                "trades": item.get("n"),
                "win_rate": _pct(item.get("win_rate")),
                "net_pnl": _money(item.get("net_pnl"), currency),
                "average_pnl_per_trade": _money(item.get("expectancy"), currency),
                "interval_95": f"{_money(ci[0], currency)} to {_money(ci[1], currency)}"
                if ci
                else None,
                "q_value": _num(item.get("q_value"), 3),
                "verdict": item.get("verdict"),
            }
        )
    return {
        "dimension": table.get("dimension"),
        "groups_tested": table.get("slices_tested"),
        "groups": slices,
        "note": "Groups under 30 trades are low confidence. q-values are adjusted for testing "
        "many groups at once.",
    }


def compact_simulation(result: dict[str, Any], currency: str) -> dict[str, Any]:
    def path(name: str) -> dict[str, Any]:
        part = obj(result.get(name))
        return {
            "net_pnl": _money(part.get("net_pnl"), currency),
            "average_pnl_per_trade": _money(part.get("expectancy"), currency),
            "max_drawdown": _money(part.get("max_drawdown"), currency),
        }

    change = obj(result.get("change"))
    ci = arr(change.get("expectancy_per_trade_ci95"))
    overfit = obj(result.get("overfit"))
    return {
        "trades": result.get("trades"),
        "trades_kept": result.get("kept_trades"),
        "trades_removed": result.get("removed_trades"),
        "actual": path("baseline"),
        "with_rules": path("simulated"),
        "net_pnl_change": _money(change.get("net_pnl"), currency),
        "change_per_trade": _money(change.get("expectancy_per_trade"), currency),
        "change_per_trade_interval_95": f"{_money(ci[0], currency)} to {_money(ci[1], currency)}"
        if ci
        else None,
        "overfitting_risk": overfit.get("level"),
        "overfitting_reasons": arr(overfit.get("reasons")),
        "warning": result.get("warning"),
    }


def compact_trade(row: dict[str, Any], privacy: Privacy, currency: str) -> dict[str, Any]:
    pnl = row.get("net_pnl_base")
    out: dict[str, Any] = {
        "trade_id": row.get("trade_id"),
        "trade_key": row.get("trade_key"),
        "symbol": row.get("symbol"),
        "side": row.get("side"),
        "setup": row.get("setup"),
        "entry_time": row.get("entry_time"),
        "exit_time": row.get("exit_time"),
        "net_pnl": _money(pnl, currency),
        "r_multiple": r_text(row.get("r_multiple")) if row.get("r_multiple") is not None else None,
        "holding_time": duration(row.get("holding_seconds")),
    }
    if privacy.notes:
        # Free text a person wrote. Marked so the model treats it as data, never as instructions.
        for key in ("notes", "tags", "emotion"):
            text = row.get(key)
            if isinstance(text, str) and text.strip():
                out[key] = {"untrusted_text": text.strip()[:NOTE_CHARS]}
    return {key: value for key, value in out.items() if value is not None}


def _chip(row: dict[str, Any], currency: str) -> Chip | None:
    key, trade_id = row.get("trade_key"), row.get("trade_id")
    if not isinstance(key, str) or not isinstance(trade_id, str):
        return None
    return Chip(
        key, trade_id, str(row.get("symbol") or ""), _money(row.get("net_pnl_base"), currency) or ""
    )


class ModelTools:
    """The tools one request may use, with privacy applied, and what they returned."""

    def __init__(
        self,
        toolbox: ToolBox,
        privacy: Privacy,
        filters: dict[str, Any],
        currency: str,
    ) -> None:
        self.toolbox = toolbox
        self.privacy = privacy
        self.filters = filters
        self.currency = currency
        self.names: tuple[str, ...] = AGGREGATE_TOOLS + (ROW_TOOLS if privacy.rows else ())
        self.runs: list[ToolRun] = []
        self.evidence = Evidence()
        self.allowed = Allowed()

    def definitions(self) -> list[dict[str, Any]]:
        """Short schemas for the model. The server adds the user's filters itself, so they are not
        offered; anything the model sends is still validated by the tool's full Pydantic model.
        Small schemas matter: on a computer without a graphics card, every prompt token costs time,
        and a long prompt can overflow a small model's context."""
        return [
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": self.toolbox.tools[name].description,
                    "parameters": {
                        "type": "object",
                        "properties": MODEL_PARAMETERS[name],
                        "additionalProperties": False,
                    },
                },
            }
            for name in self.names
        ]

    def reject(self, name: str, arguments: dict[str, Any], message: str) -> ToolRun:
        run = ToolRun(len(self.runs) + 1, name, arguments, False, message, {"error": message})
        self.runs.append(run)
        return run

    def call(self, name: str, raw_arguments: str | dict[str, Any]) -> ToolRun:
        """Validate and run one call. Unknown tools and bad arguments are rejected, not run."""
        try:
            decoded: Any = (
                json.loads(raw_arguments or "{}")
                if isinstance(raw_arguments, str)
                else raw_arguments
            )
        except json.JSONDecodeError:
            return self.reject(name, {}, "The arguments were not valid JSON.")
        if not isinstance(decoded, dict):
            return self.reject(name, {}, "The arguments must be a JSON object.")
        arguments: dict[str, Any] = dict(obj(decoded))
        if name not in self.names:
            hidden = name in ROW_TOOLS
            message = (
                f"'{name}' is turned off by the privacy settings. Only aggregate tools may be used."
                if hidden
                else f"No tool named '{name}'. Available tools: {', '.join(self.names)}."
            )
            return self.reject(name, arguments, message)
        if (
            "filters" not in arguments
            and "filters" in self.toolbox.tools[name].input_model.model_fields
        ):
            arguments["filters"] = self.filters
        if name == "list_trades":
            arguments["limit"] = min(int(arguments.get("limit", MAX_MODEL_ROWS)), MAX_MODEL_ROWS)
        try:
            result = self.toolbox.call(name, arguments)
        except ValidationError as exc:
            first = exc.errors()[0]
            where = ".".join(str(part) for part in first["loc"]) or "arguments"
            return self.reject(name, arguments, f"Invalid arguments at {where}: {first['msg']}.")
        except (KeyError, ValueError) as exc:
            return self.reject(name, arguments, str(exc).strip("'\""))
        payload, summary = self._view(name, result)
        run = ToolRun(len(self.runs) + 1, name, arguments, True, summary, payload)
        run.allowed.add_payload(payload)
        self.allowed.add_payload(payload)
        run.finding_ids = {
            str(obj(item)["id"]) for item in arr(payload.get("findings")) if obj(item).get("id")
        }
        run.trade_ids = {
            str(obj(row)["trade_id"])
            for row in arr(payload.get("trades"))
            if obj(row).get("trade_id")
        }
        if "trade" in payload and payload["trade"]:
            run.trade_ids.add(str(payload["trade"].get("trade_id")))
        self.runs.append(run)
        return run

    def _view(self, name: str, result: dict[str, Any]) -> tuple[dict[str, Any], str]:
        currency = self.currency
        if name == "get_metrics":
            payload = compact_metrics(result["report"], currency)
            return payload, f"Headline numbers for {payload.get('trades', 0)} trades"
        if name == "compare_segments":
            payload = compact_segments(result["table"], currency)
            return payload, f"{len(payload['groups'])} groups by {payload['dimension']}"
        if name in ("find_leaks", "find_strengths"):
            findings = [Finding.model_validate(item) for item in result["findings"]]
            for finding in findings:
                chips = [
                    Chip(t.trade_key, t.trade_id, t.symbol, t.pnl.display) for t in finding.evidence
                ]
                self.evidence.by_finding[finding.id] = chips
                self.evidence.finding_rules[finding.id] = finding.rule
                for chip in chips:
                    self.evidence.by_trade_id.setdefault(chip.trade_id, chip)
            payload = {
                "status": result["status"],
                "findings": [compact_finding(f, self.privacy) for f in findings],
                "caveat": result["caveat"],
            }
            kind = "leaks" if name == "find_leaks" else "strengths"
            return payload, f"{len(findings)} {kind}"
        if name == "simulate_rule":
            payload = compact_simulation(result["result"], currency)
            return payload, f"What-if over {payload.get('trades', 0)} trades"
        if name == "get_trade":
            row = result.get("trade")
            if row is None:
                return {"trade": None}, "No such trade"
            chip = _chip(row, currency)
            if chip:
                self.evidence.by_trade_id[chip.trade_id] = chip
            return {"trade": compact_trade(row, self.privacy, currency)}, "One trade"
        if name == "list_trades":
            rows = result.get("rows", [])
            for row in rows:
                chip = _chip(row, currency)
                if chip:
                    self.evidence.by_trade_id[chip.trade_id] = chip
            payload = {
                "total": result.get("total"),
                "trades": [compact_trade(row, self.privacy, currency) for row in rows],
            }
            return payload, f"{len(rows)} of {payload['total']} trades"
        return {"result": result}, name
