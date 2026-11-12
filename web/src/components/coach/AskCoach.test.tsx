// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { readSse, type LlmStatus } from "../../lib/llm";
import { AskCoach } from "./AskCoach";

const READY: LlmStatus = {
  provider: "zai",
  provider_name: "Z.ai (GLM)",
  host: "api.z.ai",
  model: "glm-4.7-flash",
  models: ["glm-4.7-flash"],
  free_models: ["glm-4.7-flash"],
  key_saved: true,
  key_hint: "…abcd",
  consented: true,
  answer_seconds: 30,
  providers: [],
  ready: true,
  reason: null,
  message: null,
};

function sse(events: { event: string; data: unknown }[], split = 7): ReadableStream<Uint8Array> {
  const text = events.map(({ event, data }) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`).join(": ping\n\n");
  const bytes = new TextEncoder().encode(text);
  return new ReadableStream({
    start(controller) {
      // Deliberately cut blocks mid-line, the way a network does.
      for (let offset = 0; offset < bytes.length; offset += split) controller.enqueue(bytes.slice(offset, offset + split));
      controller.close();
    },
  });
}

const ANSWER = [
  { event: "status", data: { type: "status", phase: "thinking", message: "Reading your question" } },
  { event: "tool", data: { type: "tool", index: 1, name: "find_leaks", arguments: {}, ok: true, summary: "3 leaks" } },
  {
    event: "tool",
    data: { type: "tool", index: 2, name: "delete_everything", arguments: {}, ok: false, summary: "No tool named 'delete_everything'." },
  },
  {
    event: "paragraph",
    data: {
      type: "paragraph",
      index: 0,
      text: "Revenge-style re-entries averaged -62.10 USD per trade.",
      replaced: false,
      unmatched: [],
      finding_ids: ["beh~revenge"],
      chips: [{ trade_key: "a".repeat(64), trade_id: "T000042", symbol: "AAA", pnl: "-190.00 USD" }],
      sources: [1],
    },
  },
  {
    event: "paragraph",
    data: {
      type: "paragraph",
      index: 1,
      text: "Pause after a loss for at least 10 minutes.",
      replaced: true,
      unmatched: ["3.71"],
      finding_ids: ["beh~revenge"],
      chips: [],
      sources: [1],
    },
  },
  { event: "done", data: { type: "done", model: "mock-coach", tools_used: [], tool_calls: 1, seconds: 0.4 } },
];

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function mount(status: LlmStatus | undefined = READY, hasTrades = true) {
  const onChip = vi.fn();
  render(<AskCoach status={status} statusError={null} hasTrades={hasTrades} onChip={onChip} onOpenSettings={vi.fn()} />);
  return onChip;
}

describe("readSse", () => {
  it("rebuilds events cut across chunks and skips pings", async () => {
    const seen: string[] = [];
    for await (const item of readSse(sse(ANSWER, 3))) seen.push(item.event);
    expect(seen).toEqual(["status", "tool", "tool", "paragraph", "paragraph", "done"]);
  });
});

describe("AskCoach", () => {
  it("streams an answer with trade chips, its sources, and the tools it used", async () => {
    const fetchMock = vi.fn(async () => new Response(sse(ANSWER), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const onChip = mount();
    fireEvent.change(screen.getByLabelText("Your question"), { target: { value: "What is my biggest leak?" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));

    expect(await screen.findByText(/averaged -62.10 USD per trade/)).toBeTruthy();
    const body = JSON.parse(String((fetchMock.mock.calls[0] as unknown as [string, RequestInit])[1].body)) as {
      question: string;
    };
    expect(body.question).toBe("What is my biggest leak?");
    expect(screen.getAllByText("From result #1")).toHaveLength(2);
    expect(screen.getByText(/The model wrote 3.71/)).toBeTruthy();
    expect(screen.getByText(/Tool results used: 1, 1 rejected/)).toBeTruthy();
    expect(screen.getByText(/rejected: No tool named/)).toBeTruthy();
    expect(screen.getByText(/mock-coach, 0.4 s/)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /Show trade T000042/ }));
    expect(onChip).toHaveBeenCalledWith(expect.objectContaining({ trade_id: "T000042" }));
  });

  it("shows Stop while answering, and stopping says so", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        (_url: string, init?: RequestInit) =>
          new Promise<Response>((_resolve, reject) => {
            init?.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
          }),
      ),
    );
    mount();
    fireEvent.change(screen.getByLabelText("Your question"), { target: { value: "slow question" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    const stop = await screen.findByRole("button", { name: "Stop" });
    expect(screen.queryByRole("button", { name: "Ask" })).toBeNull();
    fireEvent.click(stop);
    expect(await screen.findByText(/Stopped. No further model calls were made./)).toBeTruthy();
    await waitFor(() => expect(screen.getByRole("button", { name: "Ask" })).toBeTruthy());
  });

  it("explains an error event from the server", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(
            sse([{ event: "error", data: { type: "error", reason: "timeout", message: "The model did not finish within 30 seconds." } }]),
          ),
      ),
    );
    mount();
    fireEvent.change(screen.getByLabelText("Your question"), { target: { value: "anything" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    expect(await screen.findByText(/did not answer within the time limit/)).toBeTruthy();
  });

  it("is turned off with a reason when no model is ready, and sends nothing", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    mount({ ...READY, key_saved: false, key_hint: null, ready: false, reason: "no_key", message: "Save an API key." });
    expect(screen.getByText(/AI answers are unavailable. No API key is saved for the chosen provider./)).toBeTruthy();
    expect((screen.getByLabelText("Your question") as HTMLTextAreaElement).disabled).toBe(true);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("asks for data first when there are no trades", () => {
    mount(READY, false);
    expect(screen.getByText(/Import trades first. Nothing is sent to a model/)).toBeTruthy();
    expect((screen.getByRole("button", { name: "Ask" }) as HTMLButtonElement).disabled).toBe(true);
  });
});
