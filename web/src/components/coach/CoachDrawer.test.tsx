// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { CoachFinding, CoachReport, Figure } from "../../lib/schemas";
import { EMPTY_FILTERS, useFilters } from "../../state/filters";
import { COACH_DEFAULT_WIDTH, useUi } from "../../state/ui";
import { CoachDrawer } from "./CoachDrawer";

// ECharts needs a canvas, which jsdom does not have. The chart is exercised in the browser tests.
vi.mock("./FindingChart", () => ({ default: () => <div data-testid="finding-chart" /> }));

type Listener = (event: MessageEvent<string>) => void;

class FakeEventSource {
  static instances: FakeEventSource[] = [];
  readonly url: string;
  closed = false;
  private listeners = new Map<string, Listener[]>();

  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }

  addEventListener(name: string, listener: Listener) {
    this.listeners.set(name, [...(this.listeners.get(name) ?? []), listener]);
  }

  close() {
    this.closed = true;
  }

  emit(name: string, payload: unknown) {
    const event = { data: JSON.stringify(payload) } as MessageEvent<string>;
    for (const listener of this.listeners.get(name) ?? []) listener(event);
  }
}

function figure(display: string, value: number | null = 1, unit: Figure["unit"] = "currency"): Figure {
  return { value, unit, display, source: "test|source", label: "label", kind: "exact" };
}

function finding(overrides: Partial<CoachFinding> = {}): CoachFinding {
  return {
    id: "beh~revenge",
    kind: "leak",
    category: "behavior",
    dimension: "revenge",
    title: "Revenge-style re-entries after a loss underperform your other trades",
    n: figure("368", 368, "count"),
    mean_currency: figure("-62.10 USD", -62.1),
    effect_currency: figure("-61.96 USD", -61.96),
    effect_r: null,
    total_currency: figure("-22,800.00 USD", -22800),
    interval_currency: {
      low: figure("-74.00 USD", -74),
      high: figure("-49.00 USD", -49),
      level: 0.95,
      method: "bootstrap",
    },
    interval_r: null,
    confidence: "high",
    p_value: 0.001,
    q_value: 0.001,
    evidence: [
      { trade_key: "a".repeat(64), trade_id: "T000042", symbol: "AAA", pnl: figure("-190.00 USD", -190) },
      { trade_key: "b".repeat(64), trade_id: "T000077", symbol: "BBB", pnl: figure("-120.00 USD", -120) },
    ],
    what_if: { description: "If those trades matched your others, P&L would be higher.", pnl_change: figure("+22,000 USD"), in_sample_note: "" },
    rule: "After a loss, wait at least 10 minutes.",
    filter: null,
    note: null,
    ...overrides,
  };
}

function report(overrides: Partial<CoachReport> = {}): CoachReport {
  return {
    schema_version: 1,
    report_id: "f".repeat(32),
    dataset_version: "v1",
    filter_key: "k",
    filters: {},
    generated_at: "2026-11-11T12:00:00+00:00",
    status: "ok",
    base_currency: "USD",
    sample_trades: figure("1,358", 1358, "count"),
    verdict: {
      label: "negative",
      headline: "Negative",
      lines: ["Negative: you averaged -0.24 R per trade.", "Biggest leak: revenge.", "No strength cleared the filter yet."],
      confidence: "high",
      basis: "expectancy in R over 1358 trades",
      expectancy: figure("-0.24 R", -0.24, "R"),
      interval: null,
      n: figure("1,358", 1358, "count"),
    },
    top_leaks: [
      finding(),
      finding({
        id: "seg~symbol~AAA",
        category: "segment",
        dimension: "symbol",
        title: "AAA trades underperform your other trades",
        filter: { symbols: ["AAA"], setups: [], sides: [], accounts: [], tag: null },
      }),
    ],
    top_strengths: [],
    low_confidence_leads: [],
    behavior_patterns: [],
    risk_review: [{ key: "max_drawdown", title: "Largest drawdown", figure: figure("-2,563.82 USD"), note: "From a peak." }],
    action_plan: [{ day: 1, focus: "Review the evidence", task: "Open the worst trades.", finding_id: null }],
    checklist: [{ question: "Did your last trade lose?", reason: "Revenge trades lose.", finding_id: null, figure: null }],
    caveats: [{ text: "Impacts are likely overstated.", figure: null }],
    key_figures: {},
    change_vs_previous: null,
    seconds_to_build: 0.21,
    params: {},
    ...overrides,
  };
}

function mountDrawer() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <CoachDrawer />
    </QueryClientProvider>,
  );
}

function stubReport(body: CoachReport) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify(body), { status: 200, headers: { "content-type": "application/json" } })),
  );
}

function finishRun(id = "f".repeat(32)) {
  const stream = FakeEventSource.instances.at(-1);
  if (!stream) throw new Error("no stream was opened");
  act(() => stream.emit("done", { step: "done", status: "done", report_id: id }));
}

beforeEach(() => {
  FakeEventSource.instances = [];
  vi.stubGlobal("EventSource", FakeEventSource);
  act(() => {
    useFilters.setState({ ...EMPTY_FILTERS });
    useUi.setState({
      coachOpen: true,
      coachWidth: COACH_DEFAULT_WIDTH,
      coachRunToken: 0,
      route: "dashboard",
      highlightTradeKey: null,
      selection: null,
    });
  });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("CoachDrawer", () => {
  it("renders nothing and opens no stream while closed", () => {
    act(() => useUi.setState({ coachOpen: false }));
    mountDrawer();
    expect(screen.queryByRole("complementary", { name: "Coach" })).toBeNull();
    expect(FakeEventSource.instances).toHaveLength(0);
  });

  it("shows the six steps and marks them as the stream reports them", async () => {
    stubReport(report());
    mountDrawer();
    const steps = within(screen.getByRole("region", { name: "Report steps" }));
    for (const label of ["Reading", "Mapping", "Cleaning", "Computing", "Finding leaks", "Writing report"]) {
      expect(steps.getByText(label)).toBeTruthy();
    }
    const stream = FakeEventSource.instances[0]!;
    act(() => stream.emit("step", { step: "reading", status: "done", detail: "Read 1,000 rows from j.csv.", seconds: 0 }));
    act(() => stream.emit("step", { step: "finding", status: "running", detail: "", seconds: 0 }));
    expect(screen.getByText("Read 1,000 rows from j.csv.")).toBeTruthy();
    expect(screen.getByRole("complementary", { name: "Coach" }).getAttribute("data-phase")).toBe("running");
    finishRun();
    await screen.findByText("Top leaks");
  });

  it("shows the verdict, findings, and the sections of the report", async () => {
    stubReport(report());
    mountDrawer();
    finishRun();
    expect(await screen.findByText("Negative")).toBeTruthy();
    expect(screen.getByText(/Revenge-style re-entries/)).toBeTruthy();
    expect(screen.getByText("7-day action plan")).toBeTruthy();
    expect(screen.getByText("Pre-trade checklist")).toBeTruthy();
    expect(screen.getAllByTestId("finding-chart").length).toBeGreaterThan(0);
    expect(screen.getByText(/Largest drawdown/)).toBeTruthy();
  });

  it("a trade chip sends you to the Trades table with that trade highlighted", async () => {
    stubReport(report());
    mountDrawer();
    finishRun();
    const chips = await screen.findAllByRole("button", { name: /Show trade T000042/ });
    fireEvent.click(chips[0]!);
    expect(useUi.getState().route).toBe("trades");
    expect(useUi.getState().highlightTradeKey).toBe("a".repeat(64));
  });

  it("applies every finding: a filter when the app can express it, the exact trades when it cannot", async () => {
    const calls: { url: string; body: { finding_id: string } }[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        const json = { status: 200, headers: { "content-type": "application/json" } };
        if (String(url).includes("/findings/selection")) {
          calls.push({ url: String(url), body: JSON.parse(String(init?.body)) as { finding_id: string } });
          return new Response(JSON.stringify({ selection_id: "s".repeat(32), count: 368 }), json);
        }
        return new Response(JSON.stringify(report()), json);
      }),
    );
    mountDrawer();
    finishRun();

    // Every finding has the button, with its own name.
    const behavior = await screen.findByRole("button", { name: /Apply as filter: Revenge-style/ });
    const segment = screen.getByRole("button", { name: /Apply as filter: AAA trades/ });
    expect(screen.getAllByRole("button", { name: /^Apply as filter/ })).toHaveLength(2);

    // A segment the filter bar can express narrows the current filters and keeps the others.
    act(() => useFilters.setState({ accounts: ["main"], dateFrom: "2024-01-01" }));
    fireEvent.click(segment);
    expect(useFilters.getState().symbols).toEqual(["AAA"]);
    expect(useFilters.getState().accounts).toEqual(["main"]);
    expect(useFilters.getState().dateFrom).toBe("2024-01-01");
    expect(useUi.getState().selection).toBeNull();
    expect(useUi.getState().route).toBe("trades");

    // A behavior cannot be written as filters, so the exact trades are selected for the table.
    act(() => useUi.setState({ route: "dashboard" }));
    fireEvent.click(behavior);
    await waitFor(() => expect(useUi.getState().selection?.count).toBe(368));
    expect(calls).toHaveLength(1);
    expect(calls[0]?.body.finding_id).toBe("beh~revenge");
    expect(useUi.getState().selection?.label).toMatch(/Revenge-style/);
    expect(useUi.getState().route).toBe("trades");
  });
  it("says so when the trades behind a finding cannot be opened", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) =>
        String(url).includes("/findings/selection")
          ? new Response(JSON.stringify({ detail: "That finding is not in this data." }), {
              status: 404,
              headers: { "content-type": "application/json" },
            })
          : new Response(JSON.stringify(report()), { status: 200, headers: { "content-type": "application/json" } }),
      ),
    );
    mountDrawer();
    finishRun();
    fireEvent.click(await screen.findByRole("button", { name: /Apply as filter: Revenge-style/ }));
    expect(await screen.findByText(/That finding is not in this data/)).toBeTruthy();
    expect(useUi.getState().route).toBe("dashboard");
  });  it("explains a journal with fewer than 30 trades", async () => {
    stubReport(report({ status: "too_few_trades", top_leaks: [], verdict: { ...report().verdict, lines: ["Only 12 trades. At least 30 are needed."] } }));
    mountDrawer();
    finishRun();
    expect(await screen.findByText("Not enough trades yet")).toBeTruthy();
    expect(screen.getByText(/Only 12 trades/)).toBeTruthy();
    expect(screen.queryByText("Top leaks")).toBeNull();
  });

  it("explains an empty selection and offers to clear filters", async () => {
    stubReport(report({ status: "empty", top_leaks: [] }));
    mountDrawer();
    finishRun();
    expect(await screen.findByText("No trades to review")).toBeTruthy();
    act(() => useFilters.setState({ symbols: ["AAA"] }));
    fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(useFilters.getState().symbols).toEqual([]);
  });

  it("shows an error with a retry that starts a new run", async () => {
    mountDrawer();
    const stream = FakeEventSource.instances[0]!;
    act(() => stream.emit("error", { step: "error", status: "error", detail: "database is busy" }));
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("database is busy");
    const before = FakeEventSource.instances.length;
    fireEvent.click(within(alert).getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(FakeEventSource.instances.length).toBeGreaterThan(before));
    expect(FakeEventSource.instances.at(-1)!.url).toContain("force=true");
  });

  it("asks the API for a new run when the run token changes", () => {
    stubReport(report());
    mountDrawer();
    expect(FakeEventSource.instances).toHaveLength(1);
    act(() => useUi.getState().requestCoachRun());
    expect(FakeEventSource.instances).toHaveLength(2);
    expect(FakeEventSource.instances[0]!.closed).toBe(true);
  });

  it("resizes from the keyboard and keeps the width within bounds", () => {
    stubReport(report());
    mountDrawer();
    const handle = screen.getByRole("separator", { name: /Resize/ });
    fireEvent.keyDown(handle, { key: "ArrowLeft" });
    expect(useUi.getState().coachWidth).toBeGreaterThan(COACH_DEFAULT_WIDTH);
    for (let index = 0; index < 40; index += 1) fireEvent.keyDown(handle, { key: "ArrowRight" });
    expect(useUi.getState().coachWidth).toBe(360);
  });
});
