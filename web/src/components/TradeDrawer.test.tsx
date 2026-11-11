// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TradeDrawer } from "./TradeDrawer";

const KEY = "a".repeat(64);

const TRADE = {
  trade_key: KEY,
  trade_id: "90001-90002-1",
  account: "U1234567",
  symbol: "AAPL",
  asset_class: "stock",
  side: "long",
  setup: "ORB",
  entry_time: "2026-01-06T14:32:05Z",
  exit_time: "2026-01-06T16:05:12Z",
  qty: 20,
  entry_price: 189.2,
  exit_price: 190.4,
  gross_pnl: 24,
  net_pnl: 22,
  net_pnl_base: 22,
  currency: "USD",
  base_currency: "USD",
  fees: 0,
  commission: -2,
  swap: 0,
  planned_risk: null,
  r_multiple: null,
  stop_loss: null,
  take_profit: null,
  mae: null,
  mfe: null,
  holding_seconds: 5707,
  session: "london",
  timeframe: null,
  notes: "",
  tags: null,
  emotion: null,
  confidence: null,
  screenshot_path: null,
  plan_followed: null,
  source_timezone: "UTC",
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("TradeDrawer", () => {
  it("saves edited notes with a PATCH that carries only the changed journal fields", async () => {
    const calls: { url: string; method: string; body: string | undefined }[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        const method = init?.method ?? "GET";
        calls.push({ url, method, body: typeof init?.body === "string" ? init.body : undefined });
        const body = method === "PATCH" ? { ...TRADE, notes: "held through the news" } : TRADE;
        return new Response(JSON.stringify(body), {
          status: 200,
          headers: { "content-type": "application/json" },
        });
      }),
    );
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const onClose = vi.fn();
    render(
      <QueryClientProvider client={client}>
        <TradeDrawer tradeKey={KEY} onClose={onClose} />
      </QueryClientProvider>,
    );

    const notes = await screen.findByLabelText("Notes");
    fireEvent.change(notes, { target: { value: "held through the news" } });
    const save = screen.getByRole("button", { name: "Save" }) as HTMLButtonElement;
    expect(save.disabled).toBe(false);
    await act(async () => {
      fireEvent.submit(save.closest("form") as HTMLFormElement);
    });

    await waitFor(() => expect(calls.map((call) => call.method)).toContain("PATCH"));
    const patch = calls.find((call) => call.method === "PATCH");
    expect(patch?.url).toContain(`/api/trades/${KEY}`);
    expect(JSON.parse(patch?.body ?? "{}")).toMatchObject({ notes: "held through the news" });
  });

  it("closes on Escape", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify(TRADE), { status: 200, headers: { "content-type": "application/json" } })),
    );
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const onClose = vi.fn();
    render(
      <QueryClientProvider client={client}>
        <TradeDrawer tradeKey={KEY} onClose={onClose} />
      </QueryClientProvider>,
    );
    await screen.findByLabelText("Notes");
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});

