"""The Coach engine as typed tool functions.

Each tool has a Pydantic input model and a Pydantic output model, so a later LLM phase only needs
a loop: list `tool_schemas()`, let the model pick a tool and arguments, call `call_tool`, and pass
the validated JSON result back. Tools read data only. None of them writes or changes anything.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from obsidian_ledger.coach.models import Finding
from obsidian_ledger.coach.service import CoachService
from obsidian_ledger.metrics.engine import AnalysisEngine, Params
from obsidian_ledger.metrics.routes import FiltersIn, RulesIn
from obsidian_ledger.metrics.segments import DIMENSIONS
from obsidian_ledger.store.db import Store
from obsidian_ledger.store.queries import SORTABLE, order_clause, where_clause

TRADE_KEY = r"^[a-f0-9]{64}$"
MAX_ROWS = 100


class ToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ToolOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ----- inputs -----


class GetMetricsIn(ToolInput):
    filters: FiltersIn = Field(default_factory=FiltersIn)


class CompareSegmentsIn(ToolInput):
    dimension: Literal[
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
    ]
    filters: FiltersIn = Field(default_factory=FiltersIn)
    min_n: int = Field(default=30, ge=1, le=10000)


class FindFindingsIn(ToolInput):
    filters: FiltersIn = Field(default_factory=FiltersIn)
    limit: int = Field(default=5, ge=1, le=20)


class GetTradeIn(ToolInput):
    trade_key: str = Field(pattern=TRADE_KEY)


class ListTradesIn(ToolInput):
    filters: FiltersIn = Field(default_factory=FiltersIn)
    limit: int = Field(default=20, ge=1, le=MAX_ROWS)
    offset: int = Field(default=0, ge=0)
    sort: str = "exit_time"
    descending: bool = True


class SimulateRuleIn(ToolInput):
    filters: FiltersIn = Field(default_factory=FiltersIn)
    rules: RulesIn
    resamples: int = Field(default=1000, ge=100, le=10000)
    seed: int = 42


# ----- outputs -----


class MetricsOut(ToolOutput):
    report: dict[str, Any]


class SegmentsOut(ToolOutput):
    table: dict[str, Any]


class FindingsOut(ToolOutput):
    status: str
    findings: list[Finding]
    comparisons_run: int | None
    caveat: str


class TradeOut(ToolOutput):
    trade: dict[str, Any] | None


class TradesOut(ToolOutput):
    total: int
    rows: list[dict[str, Any]]


class SimulationOut(ToolOutput):
    result: dict[str, Any]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_model: type[ToolInput]
    output_model: type[ToolOutput]
    run: Callable[[Any], ToolOutput]


class ToolBox:
    """The tools, bound to one store, engine, and Coach service."""

    def __init__(self, store: Store, engine: AnalysisEngine, coach: CoachService) -> None:
        self.store = store
        self.engine = engine
        self.coach = coach
        self.tools: dict[str, Tool] = {
            tool.name: tool
            for tool in (
                Tool(
                    "get_metrics",
                    "Headline performance, risk, behavior and discipline numbers for a set of "
                    "filters. Use it before making any claim about results.",
                    GetMetricsIn,
                    MetricsOut,
                    self._get_metrics,
                ),
                Tool(
                    "compare_segments",
                    "Compare every value of one dimension (symbol, setup, hour, ...) with the "
                    "rest, with sample size and multiple-comparison-adjusted significance.",
                    CompareSegmentsIn,
                    SegmentsOut,
                    self._compare_segments,
                ),
                Tool(
                    "find_leaks",
                    "The leaks that survived the false-discovery filter, worst first, each with "
                    "evidence trades, an interval, and a rule.",
                    FindFindingsIn,
                    FindingsOut,
                    self._find_leaks,
                ),
                Tool(
                    "find_strengths",
                    "The strengths that survived the false-discovery filter, best first.",
                    FindFindingsIn,
                    FindingsOut,
                    self._find_strengths,
                ),
                Tool(
                    "get_trade",
                    "One trade by its trade key, with its derived fields and journal notes.",
                    GetTradeIn,
                    TradeOut,
                    self._get_trade,
                ),
                Tool(
                    "list_trades",
                    "A page of trades for a set of filters, sorted. At most 100 per call.",
                    ListTradesIn,
                    TradesOut,
                    self._list_trades,
                ),
                Tool(
                    "simulate_rule",
                    "What-if: replay the trades under trading rules (daily loss cap, trade "
                    "limits, excluded symbols or hours) and compare with what happened.",
                    SimulateRuleIn,
                    SimulationOut,
                    self._simulate_rule,
                ),
            )
        }

    # ----- implementations -----

    def _get_metrics(self, args: GetMetricsIn) -> MetricsOut:
        report = self.engine.report(args.filters.to_filters(), Params())
        return MetricsOut(report=report)

    def _compare_segments(self, args: CompareSegmentsIn) -> SegmentsOut:
        if args.dimension not in DIMENSIONS:
            raise ValueError(f"Unknown dimension '{args.dimension}'.")
        table = self.engine.segments(args.filters.to_filters(), args.dimension, args.min_n)
        return SegmentsOut(table=table)

    def _findings(self, args: FindFindingsIn, which: Literal["leaks", "strengths"]) -> FindingsOut:
        report = self.coach.report(args.filters.to_filters())
        chosen = report.top_leaks if which == "leaks" else report.top_strengths
        return FindingsOut(
            status=report.status,
            findings=chosen[: args.limit],
            comparisons_run=None,
            caveat=(
                "Findings are filtered with Benjamini-Hochberg across all comparisons. "
                "An empty list means none is proven, not that none exists."
            ),
        )

    def _find_leaks(self, args: FindFindingsIn) -> FindingsOut:
        return self._findings(args, "leaks")

    def _find_strengths(self, args: FindFindingsIn) -> FindingsOut:
        return self._findings(args, "strengths")

    def _get_trade(self, args: GetTradeIn) -> TradeOut:
        row = self.store.get_trade(args.trade_key)
        return TradeOut(trade=_plain(row) if row is not None else None)

    def _list_trades(self, args: ListTradesIn) -> TradesOut:
        if args.sort not in SORTABLE:
            raise ValueError(f"Cannot sort by '{args.sort}'. Choose one of {sorted(SORTABLE)}.")
        where, params = where_clause(args.filters.to_filters())
        total, rows = self.store.query_page(
            where, params, order_clause(args.sort, args.descending), args.limit, args.offset
        )
        return TradesOut(total=total, rows=[_plain(row) for row in rows])

    def _simulate_rule(self, args: SimulateRuleIn) -> SimulationOut:
        result = self.engine.simulate(
            args.filters.to_filters(), args.rules.to_rules(), args.resamples, args.seed
        )
        return SimulationOut(result=result)

    # ----- public API -----

    def schemas(self) -> list[dict[str, Any]]:
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_model.model_json_schema(),
                "output_schema": tool.output_model.model_json_schema(),
            }
            for tool in self.tools.values()
        ]

    def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Validate the arguments, run the tool, and return its validated output as JSON."""
        tool = self.tools.get(name)
        if tool is None:
            raise KeyError(f"No tool named '{name}'. Available: {sorted(self.tools)}.")
        parsed = tool.input_model.model_validate(arguments)
        return tool.run(parsed).model_dump(mode="json")


def _plain(row: dict[str, Any]) -> dict[str, Any]:
    """JSON-safe copy of a stored row: timestamps as ISO text, NaN as None."""
    out: dict[str, Any] = {}
    for key, value in row.items():
        if hasattr(value, "isoformat"):
            out[key] = value.isoformat()
        elif isinstance(value, float) and value != value:
            out[key] = None
        else:
            out[key] = value
    return out
