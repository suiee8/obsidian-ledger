import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useRef, useState } from "react";
import { z } from "zod";

import { filtersBody, useFilters } from "../state/filters";
import { apiFetch, jsonBody, requestJson } from "./api";

// The optional local model. Nothing here is needed for the Coach report itself.

const ProviderSchema = z.object({
  id: z.string(),
  name: z.string(),
  host: z.string().nullable(),
  key_page: z.string(),
  models: z.array(z.string()),
  free_models: z.array(z.string()),
  note: z.string(),
});
export type ProviderOption = z.infer<typeof ProviderSchema>;

export const LlmStatusSchema = z.object({
  provider: z.string(),
  provider_name: z.string().nullable(),
  host: z.string().nullable(),
  model: z.string().nullable(),
  models: z.array(z.string()),
  free_models: z.array(z.string()),
  key_saved: z.boolean(),
  key_hint: z.string().nullable(),
  consented: z.boolean(),
  answer_seconds: z.number(),
  providers: z.array(ProviderSchema),
  ready: z.boolean(),
  reason: z.string().nullable(),
  message: z.string().nullable(),
});
export type LlmStatus = z.infer<typeof LlmStatusSchema>;

export const LlmTestSchema = z.object({
  ok: z.boolean(),
  reason: z.string().nullable(),
  message: z.string(),
  models: z.array(z.string()).optional(),
  milliseconds: z.number().optional(),
});
const ToolUseSchema = z.object({
  index: z.number(),
  name: z.string(),
  arguments: z.record(z.string(), z.unknown()),
  ok: z.boolean(),
  summary: z.string(),
});
export type ToolUse = z.infer<typeof ToolUseSchema>;

export const AiSummarySchema = z.union([
  z.object({
    status: z.literal("ok"),
    model: z.string(),
    report_id: z.string(),
    headline: z.string(),
    headline_replaced: z.boolean(),
    paragraphs: z.array(
      z.object({
        section: z.string(),
        title: z.string(),
        text: z.string(),
        replaced: z.boolean(),
        unmatched: z.array(z.string()),
      }),
    ),
    tools_used: z.array(ToolUseSchema),
    seconds: z.number(),
  }),
  z.object({
    status: z.literal("unavailable"),
    reason: z.string(),
    message: z.string(),
    model: z.string().nullable().optional(),
  }),
]);
export type AiSummary = z.infer<typeof AiSummarySchema>;

const ChipSchema = z.object({ trade_key: z.string(), trade_id: z.string(), symbol: z.string(), pnl: z.string() });
export type AnswerChip = z.infer<typeof ChipSchema>;

const ParagraphSchema = z.object({
  index: z.number(),
  text: z.string(),
  replaced: z.boolean(),
  unmatched: z.array(z.string()),
  finding_ids: z.array(z.string()),
  chips: z.array(ChipSchema),
  sources: z.array(z.number()),
});
export type AnswerParagraph = z.infer<typeof ParagraphSchema>;

const DoneSchema = z.object({
  model: z.string(),
  tools_used: z.array(ToolUseSchema),
  tool_calls: z.number(),
  seconds: z.number(),
});

/** Messages for each reason the AI layer can be unavailable. The report is always shown. */
export const UNAVAILABLE: Record<string, string> = {
  no_data: "There are no trades to explain yet.",
  no_provider: "No AI provider is set up.",
  no_key: "No API key is saved for the chosen provider.",
  no_model: "No model is selected.",
  no_consent: "Sending results to the provider has not been confirmed.",
  unreachable: "The AI provider could not be reached.",
  model_missing: "The provider does not offer the selected model.",
  timeout: "The provider did not answer within the time limit. Try again, or raise the limit in Settings.",
  invalid_output: "The model's reply could not be used.",
  bad_response: "The provider sent an unusable reply.",
  bad_key: "The provider did not accept the API key.",
  no_credit: "The provider account has no credit left.",
  rate_limited: "The provider is limiting requests. Try again in a minute.",
  unsupported: "The selected model cannot use tools. Choose another model.",
  stopped: "Stopped.",
};
export function useLlmStatus() {
  return useQuery({
    queryKey: ["llm-status"],
    queryFn: ({ signal }) => requestJson("/api/llm/status", LlmStatusSchema, { signal }),
    staleTime: 10_000,
    retry: false,
  });
}

function useLlmMutation<T>(run: (input: T) => Promise<LlmStatus>) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: run,
    onSuccess: (status) => {
      client.setQueryData(["llm-status"], status);
      void client.invalidateQueries({ queryKey: ["ai-summary"] });
    },
  });
}

export function useSaveLlm() {
  return useLlmMutation(
    (patch: { provider?: string; model?: string | null; answer_seconds?: number; consent?: boolean }) =>
      requestJson("/api/llm/config", LlmStatusSchema, { ...jsonBody(patch), method: "PUT" }),
  );
}

/** Saves a key to the system keychain. The key is never sent back. */
export function useSaveKey() {
  return useLlmMutation((input: { provider: string; api_key: string }) =>
    requestJson("/api/llm/key", LlmStatusSchema, { ...jsonBody(input), method: "PUT" }),
  );
}

export function useDeleteKey() {
  return useLlmMutation((provider: string) =>
    requestJson(`/api/llm/key/${encodeURIComponent(provider)}`, LlmStatusSchema, { method: "DELETE" }),
  );
}

/** Checks the key and lists models. Sends one short test message and no journal data. */
export function useTestLlm() {
  return useMutation({
    mutationFn: (body: { provider?: string; model?: string | null; api_key?: string }) =>
      requestJson("/api/llm/test", LlmTestSchema, jsonBody(body)),
  });
}
/** The AI summary of one report. Only asked for when a model is ready. */
export function useAiSummary(reportId: string | null, enabled: boolean) {
  const filters = useFilters((state) => JSON.stringify(filtersBody(state)));
  return useQuery({
    queryKey: ["ai-summary", reportId, filters],
    queryFn: ({ signal }) =>
      requestJson("/api/coach/ai/summary", AiSummarySchema, {
        ...jsonBody({ filters: JSON.parse(filters) as unknown }),
        signal,
      }),
    enabled: enabled && reportId !== null,
    staleTime: Infinity,
    retry: false,
    placeholderData: keepPreviousData,
  });
}

// ----- asking -----

export type AskPhase = "idle" | "running" | "done" | "error";

export interface AskTurn {
  id: number;
  question: string;
  phase: AskPhase;
  status: string;
  tools: ToolUse[];
  paragraphs: AnswerParagraph[];
  error: { reason: string; message: string } | null;
  model: string | null;
  seconds: number | null;
}

interface SseEvent {
  event: string;
  data: unknown;
}

/** Reads `event:`/`data:` blocks from a fetch body. Comment lines (pings) are skipped. */
export async function* readSse(body: ReadableStream<Uint8Array>): AsyncGenerator<SseEvent> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
    let cut = buffer.indexOf("\n\n");
    while (cut !== -1) {
      const block = buffer.slice(0, cut);
      buffer = buffer.slice(cut + 2);
      let event = "message";
      const data: string[] = [];
      for (const line of block.split("\n")) {
        if (line.startsWith("event: ")) event = line.slice(7);
        else if (line.startsWith("data: ")) data.push(line.slice(6));
      }
      if (data.length > 0) yield { event, data: JSON.parse(data.join("\n")) as unknown };
      cut = buffer.indexOf("\n\n");
    }
  }
}

/** Ask the Coach, one question at a time. `stop` aborts the request; the server stops too. */
export function useAskCoach() {
  const [turns, setTurns] = useState<AskTurn[]>([]);
  const controller = useRef<AbortController | null>(null);
  const counter = useRef(0);

  const update = useCallback((id: number, change: (turn: AskTurn) => AskTurn) => {
    setTurns((current) => current.map((turn) => (turn.id === id ? change(turn) : turn)));
  }, []);

  const ask = useCallback(
    async (question: string) => {
      controller.current?.abort();
      const abort = new AbortController();
      controller.current = abort;
      counter.current += 1;
      const id = counter.current;
      setTurns((current) => [
        ...current,
        {
          id,
          question,
          phase: "running",
          status: "Sending your question",
          tools: [],
          paragraphs: [],
          error: null,
          model: null,
          seconds: null,
        },
      ]);
      const fail = (reason: string, message: string) =>
        update(id, (turn) => ({ ...turn, phase: "error", error: { reason, message }, status: "" }));
      try {
        const response = await apiFetch(
          "/api/coach/ask",
          {
            ...jsonBody({ filters: filtersBody(useFilters.getState()), question }),
            signal: abort.signal,
          },
          { timeoutMs: 120_000 },
        );
        if (!response.ok || !response.body) {
          fail("bad_response", `The question could not be sent (${response.status}).`);
          return;
        }
        for await (const { event, data } of readSse(response.body)) {
          if (event === "status") {
            const message = (data as { message?: string }).message ?? "";
            update(id, (turn) => ({ ...turn, status: message }));
          } else if (event === "tool") {
            const parsed = ToolUseSchema.safeParse(data);
            if (parsed.success) update(id, (turn) => ({ ...turn, tools: [...turn.tools, parsed.data] }));
          } else if (event === "paragraph") {
            const parsed = ParagraphSchema.safeParse(data);
            if (parsed.success) {
              update(id, (turn) => ({ ...turn, paragraphs: [...turn.paragraphs, parsed.data] }));
            }
          } else if (event === "done") {
            const parsed = DoneSchema.safeParse(data);
            update(id, (turn) => ({
              ...turn,
              phase: "done",
              status: "",
              model: parsed.success ? parsed.data.model : null,
              seconds: parsed.success ? parsed.data.seconds : null,
            }));
          } else if (event === "error") {
            const detail = data as { reason?: string; message?: string };
            fail(detail.reason ?? "bad_response", detail.message ?? "The answer failed.");
          }
        }
        // A stream that ends without done or error was cut off.
        update(id, (turn) =>
          turn.phase === "running"
            ? { ...turn, phase: "error", status: "", error: { reason: "bad_response", message: "The answer was cut off." } }
            : turn,
        );
      } catch (reason) {
        if (abort.signal.aborted) fail("stopped", "Stopped. No further model calls were made.");
        else fail("unreachable", reason instanceof Error ? reason.message : "The local API is not reachable.");
      } finally {
        if (controller.current === abort) controller.current = null;
      }
    },
    [update],
  );

  const stop = useCallback(() => controller.current?.abort(), []);
  const running = turns.some((turn) => turn.phase === "running");
  return { turns, ask, stop, running };
}
