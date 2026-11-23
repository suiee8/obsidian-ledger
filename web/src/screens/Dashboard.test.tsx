// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, cleanup } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import Dashboard from "./Dashboard";

vi.mock("../lib/echarts", () => ({
  echarts: {
    init: () => ({ setOption: () => undefined, resize: () => undefined, dispose: () => undefined }),
    use: () => undefined,
  },
}));

const PAYLOAD = {
  dataset_version: "v1",
  report: {
    sample: { trades: 4, excluded_no_fx: 0, low_confidence: true, starting_equity: null },
    core: {
      trades: 4,
      wins: 2,
      losses: 2,
      flat: 0,
      net_pnl: 120.95,
      win_rate: 0.5,
      profit_factor: 1.75,
      expectancy: 30.24,
      expectancy_r: null,
      payoff_ratio: 1.2,
    },
    risk: {
      drawdown: { max_drawdown: -162.05, max_drawdown_pct: null, recovered: false },
      daily_ratios: {
        available: false,
        reason: "Enter a starting equity to compute daily-return ratios. Without it, only P&L-based and R-based figures are shown.",
      },
      sqn: null,
    },
    discipline: { score: null, components_used: 0, components_total: 5, formula: "weights" },
    caveats: [
      "Only 4 trades in this selection.",
      "No starting equity is set, so Sharpe, Sortino, Calmar, and drawdown percentages are unavailable.",
      "4 trades have no plan-followed value, so adherence uses the rest.",
      "3 trades have no planned risk, so their R multiples are unavailable.",
      "2 trades have no MFE, so exit efficiency uses the rest.",
    ],
  },
  equity: {
    points: [
      { t: "2026-01-06T16:05:12Z", equity: 22, drawdown: 0 },
      { t: "2026-01-08T11:00:00Z", equity: 283, drawdown: 0 },
    ],
    downsampled: false,
    source_points: 2,
  },
  daily: [{ day: "2026-01-06", pnl: 22, trades: 1 }, { day: "2026-01-08", pnl: 0, trades: 1 }],
  r_histogram: { bins: [], n: 0, clipped: 0, mean: null, median: null },
  heatmap: [{ weekday: 0, hour: 9, trades: 1, pnl: 0, expectancy: 0 }],
  radar: { axes: ["win_rate"], setups: [] },
  findings: { edges: [], leaks: [], slices_tested: 0, caveat: "Leads to test." },
};

beforeAll(() => {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
  window.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
  })) as unknown as typeof window.matchMedia;
});

afterEach(() => {
  vi.restoreAllMocks();
});

afterEach(() => cleanup());

describe("Dashboard", () => {
  it("shows the headline numbers and the low-confidence caveat from the API", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify(PAYLOAD), { status: 200, headers: { "content-type": "application/json" } })),
    );
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <Dashboard />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.getByLabelText("Net P&L: +$120.95")).toBeTruthy());
    expect(screen.getByLabelText("Win rate: 50.0%")).toBeTruthy();
    expect(screen.getByText(/Low confidence/)).toBeTruthy();
    expect(screen.getByText("Only 4 trades in this selection.")).toBeTruthy();
    expect(screen.queryByText(/Enter a starting equity to compute/)).toBeNull();
    for (const notice of PAYLOAD.report.caveats.slice(1)) {
      expect(screen.queryByText(notice)).toBeNull();
    }
    expect(screen.getByText("Latest equity").nextElementSibling?.textContent).toBe("+$283.00");
    expect(screen.getByRole("img", { name: /8 Jan 2026.*\$0.00 from 1 trade/ }).classList.contains("is-flat")).toBe(true);
    expect(screen.getByRole("img", { name: /7 Jan 2026.*no trades/ }).classList.contains("is-empty")).toBe(true);
    expect(screen.getByRole("columnheader", { name: "09:00 UTC" })).toBeTruthy();
    expect(screen.getByRole("cell", { name: /Mon 09:00 UTC: 1 trade, \$0\.00/ }).classList.contains("is-flat")).toBe(true);
  });

  it("explains an API failure instead of showing empty panels", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ error: { code: "x", message: "Local store is busy." } }), { status: 500, headers: { "content-type": "application/json" } })),
    );
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <Dashboard />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.getByRole("alert")).toBeTruthy());
    expect(screen.getByText("Local store is busy.")).toBeTruthy();
  });
});

