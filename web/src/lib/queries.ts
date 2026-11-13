import {
  keepPreviousData,
  useMutation,
  useQueries,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { useEffect } from "react";
import { z } from "zod";

import { useUi } from "../state/ui";
import { apiFetch, jsonBody, requestJson } from "./api";
import {
  CommitSchema,
  AvailabilitySchema,
  DashboardSchema,
  FilterOptionsSchema,
  PreviewSchema,
  TradePageSchema,
  TradeRowSchema,
  ViewListSchema,
  ViewSchema,
} from "./schemas";

export const BLOCK_ROWS = 200;

/** Aborts in-flight requests whose filter or sort state is no longer on screen. The current state
 *  keeps running, and the previous data stays visible while it loads (keepPreviousData). */
function useAbortSuperseded(
  queryName: string,
  isCurrent: (queryKey: readonly unknown[]) => boolean,
  deps: readonly unknown[],
) {
  const client = useQueryClient();
  useEffect(() => {
    void client.cancelQueries({
      predicate: (query) => query.queryKey[0] === queryName && !isCurrent(query.queryKey),
    });
    // The predicate is rebuilt from `deps` on each change, so the effect re-runs with them.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [client, queryName, ...deps]);
}

export function useDashboard(params: string) {
  useAbortSuperseded("dashboard", (key) => key[1] === params, [params]);
  return useQuery({
    queryKey: ["dashboard", params],
    queryFn: ({ signal }) =>
      requestJson(`/api/dashboard${params ? `?${params}` : ""}`, DashboardSchema, { signal }),
    placeholderData: keepPreviousData,
    staleTime: 15_000,
  });
}

export function useAvailability(params: string) {
  useAbortSuperseded("availability", (key) => key[1] === params, [params]);
  return useQuery({
    queryKey: ["availability", params],
    queryFn: ({ signal }) =>
      requestJson(`/api/availability${params ? `?${params}` : ""}`, AvailabilitySchema, { signal }),
    placeholderData: keepPreviousData,
    staleTime: 15_000,
  });
}

export function useFilterOptions() {
  return useQuery({
    queryKey: ["filter-options"],
    queryFn: ({ signal }) => requestJson("/api/filter-options", FilterOptionsSchema, { signal }),
    staleTime: 60_000,
  });
}

export function useTradeBlocks(params: string, sortParams: string, blocks: number[]) {
  useAbortSuperseded(
    "trades-page",
    (key) => key[1] === params && key[2] === sortParams,
    [params, sortParams],
  );
  return useQueries({
    queries: blocks.map((block) => ({
      queryKey: ["trades-page", params, sortParams, block],
      queryFn: ({ signal }: { signal: AbortSignal }) =>
        requestJson(
          `/api/trades/page?${[params, sortParams].filter(Boolean).join("&")}&limit=${BLOCK_ROWS}&offset=${block * BLOCK_ROWS}`,
          TradePageSchema,
          { signal },
        ),
      placeholderData: keepPreviousData,
      staleTime: 10_000,
    })),
  });
}

export function useTrade(tradeKey: string | null) {
  return useQuery({
    queryKey: ["trade", tradeKey],
    queryFn: ({ signal }) => requestJson(`/api/trades/${tradeKey}`, TradeRowSchema, { signal }),
    enabled: tradeKey !== null,
  });
}

export interface TradeEdit {
  tradeKey: string;
  patch: Partial<Record<"notes" | "tags" | "emotion" | "confidence", string | null>>;
}

export function useEditTrade() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ tradeKey, patch }: TradeEdit) =>
      requestJson(`/api/trades/${tradeKey}`, TradeRowSchema, {
        ...jsonBody(patch),
        method: "PATCH",
      }),
    onSuccess: (row) => {
      client.setQueryData(["trade", row.trade_key], row);
      void client.invalidateQueries({ queryKey: ["trades-page"] });
      void client.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
}

export function useViews() {
  return useQuery({
    queryKey: ["views"],
    queryFn: ({ signal }) => requestJson("/api/views", ViewListSchema, { signal }),
  });
}

export function useSaveView() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ name, config }: { name: string; config: Record<string, unknown> }) =>
      requestJson("/api/views", ViewSchema, jsonBody({ name, config })),
    onSuccess: () => void client.invalidateQueries({ queryKey: ["views"] }),
  });
}

export function useDeleteView() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (name: string) =>
      requestJson(`/api/views/${encodeURIComponent(name)}`, z.undefined(), { method: "DELETE" }),
    onSuccess: () => void client.invalidateQueries({ queryKey: ["views"] }),
  });
}

export function usePreviewImport() {
  return useMutation({
    mutationFn: async ({ file }: { file: File }) => {
      const response = await apiFetch(
        `/api/imports/preview?filename=${encodeURIComponent(file.name)}`,
        {
          method: "POST",
          headers: { "content-type": "application/octet-stream" },
          body: file,
        },
        { timeoutMs: 120_000 },
      );
      if (!response.ok) {
        throw new Error(await readErrorMessage(response));
      }
      return PreviewSchema.parse((await response.json()) as unknown);
    },
  });
}

export function useCommitImport() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ previewId, options }: { previewId: string; options: Record<string, unknown> }) =>
      requestJson(`/api/imports/${previewId}/commit`, CommitSchema, jsonBody(options)),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["dashboard"] });
      void client.invalidateQueries({ queryKey: ["trades-page"] });
      void client.invalidateQueries({ queryKey: ["filter-options"] });
      void client.invalidateQueries({ queryKey: ["availability"] });
      void client.invalidateQueries({ queryKey: ["explore"] });
      void client.invalidateQueries({ queryKey: ["segments"] });
      void client.invalidateQueries({ queryKey: ["fan"] });
      void client.invalidateQueries({ queryKey: ["behavior-report"] });
      void client.invalidateQueries({ queryKey: ["timeline"] });
      void client.invalidateQueries({ queryKey: ["simulate"] });
      // The Coach runs on the new data and streams its steps in the drawer.
      useUi.getState().requestCoachRun();
    },
  });
}

async function readErrorMessage(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { error?: { message?: string } };
    return body.error?.message ?? `Upload failed (${response.status})`;
  } catch {
    return `Upload failed (${response.status})`;
  }
}
