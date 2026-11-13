import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";

import { FILTER_DEBOUNCE_MS, filtersBody, useFilters } from "../state/filters";
import { jsonBody, requestJson } from "./api";
import { useDebouncedValue } from "./useDebouncedValue";

// Schemas and query hooks for Analytics, Behavior, Simulator, and Settings.

const num = z.number().nullable();
const query = (params: string) => (params ? `&${params}` : "");

// ----- Analytics -----

const RunSchema = z.object({
  kind: z.string(),
  length: z.number(),
  start: z.string(),
  end: z.string(),
  pnl: z.number(),
});

export const ExploreSchema = z.object({
  dataset_version: z.string(),
  points: z.object({
    n: z.number(),
    t: z.array(z.number()),
    pnl: z.array(z.number()),
    r: z.array(num),
    mae: z.array(num),
    mfe: z.array(num),
    hold: z.array(z.number()),
    symbol: z.array(z.number()),
    symbols: z.array(z.string()),
  }),
  mae_mfe: z.object({
    trades_with_excursions: z.number(),
    trades_total: z.number(),
    winner_capture_ratio: num,
    winner_capture_n: z.number(),
    avg_mae_winners: num,
    avg_mae_losers: num,
    avg_mfe_losers: num,
    note: z.string(),
  }),
  streaks: z.object({
    runs: z.number(),
    longest_wins: z.array(RunSchema),
    longest_losses: z.array(RunSchema),
    histogram: z.array(z.object({ length: z.number(), wins: z.number(), losses: z.number() })),
  }),
  fee_drag: z.object({
    costs: num,
    gross: num,
    drag: num,
    rule: z.string().optional(),
    by_symbol: z.array(
      z.object({
        symbol: z.string(),
        trades: z.number(),
        costs: z.number(),
        gross: z.number(),
        net: z.number(),
        drag: num,
      }),
    ),
  }),
});
export type ExploreData = z.infer<typeof ExploreSchema>;

export const SegmentsSchema = z.object({
  dimension: z.string(),
  min_n: z.number(),
  slices_tested: z.number(),
  multiple_comparisons: z.string().optional(),
  slices: z.array(
    z.object({
      value: z.string(),
      n: z.number(),
      low_confidence: z.boolean(),
      win_rate: num,
      net_pnl: z.number(),
      expectancy: z.number(),
      expectancy_ci95: z.tuple([z.number(), z.number()]).nullable(),
      expectancy_r: num,
      q_value: num,
      verdict: z.string(),
    }),
  ),
});
export type SegmentsData = z.infer<typeof SegmentsSchema>;

const MonteCarloSchema = z.object({
  paths: z.number(),
  horizon_trades: z.number().optional(),
  assumption: z.string().optional(),
  drawdown_threshold: z.number().optional(),
  target: z.number().optional(),
  probability_drawdown_at_least_threshold: num.optional(),
  probability_reaching_target: num.optional(),
  probability_ruin: num.optional(),
  final_percentiles: z.object({ p5: z.number(), p50: z.number(), p95: z.number() }).optional(),
  fan: z
    .array(
      z.object({
        trade: z.number(),
        p5: z.number(),
        p25: z.number(),
        p50: z.number(),
        p75: z.number(),
        p95: z.number(),
      }),
    )
    .optional(),
});

export const FanSchema = z.object({
  statistics: z.object({ monte_carlo: MonteCarloSchema }).optional(),
  sample: z.object({ trades: z.number(), starting_equity: num.optional() }).passthrough(),
});
export type MonteCarlo = z.infer<typeof MonteCarloSchema>;

export const DISCIPLINE_COMPONENTS = [
  "plan_adherence",
  "risk_consistency",
  "post_loss_behavior",
  "overtrading_control",
  "stop_usage",
] as const;

export const BehaviorReportSchema = z.object({
  sample: z.object({ trades: z.number() }).passthrough(),
  discipline: z.object({
    score: num,
    components_used: z.number(),
    components_total: z.number(),
    formula: z.string(),
    components: z.record(z.string(), num),
    weights: z.record(z.string(), z.number()).optional(),
  }),
  behavior: z
    .object({
      after_win: z.object({ trades: z.number() }).passthrough(),
      after_loss: z.object({ trades: z.number() }).passthrough(),
      revenge: z.object({ flagged_trades: z.number(), rule: z.string() }).passthrough(),
      overtrading: z.object({ threshold_trades_per_day: z.number() }).passthrough(),
      plan: z.object({ known_trades: z.number() }).passthrough(),
    })
    .passthrough()
    .optional(),
});
export type BehaviorReport = z.infer<typeof BehaviorReportSchema>;

// ----- Behavior -----

export const TimelineSchema = z.object({
  trades: z.number(),
  days: z.array(
    z.object({
      day: z.string(),
      trades: z.number(),
      pnl: z.number(),
      revenge: z.number(),
      revenge_pnl: z.number(),
      tilt: z.number(),
      tilt_pnl: z.number(),
      overtraded: z.boolean(),
    }),
  ),
  thresholds: z
    .object({
      overtrading_trades_per_day: z.number(),
      revenge_gap_minutes: z.number(),
      revenge_size_jump: z.number(),
      tilt_losses: z.number(),
    })
    .optional(),
  rules: z.object({ revenge: z.string(), tilt: z.string(), overtrading: z.string() }).optional(),
  totals: z
    .object({
      revenge_trades: z.number(),
      tilt_trades: z.number(),
      overtraded_days: z.number(),
      days: z.number(),
    })
    .optional(),
  post_loss: z
    .array(
      z.object({
        key: z.string(),
        label: z.string(),
        trades: z.number(),
        win_rate: num,
        expectancy: num,
        net_pnl: z.number(),
      }),
    )
    .optional(),
});
export type Timeline = z.infer<typeof TimelineSchema>;

// ----- Simulator -----

export interface RulesState {
  daily_loss_cap: number | null;
  max_trades_per_day: number | null;
  stop_after_losses: number | null;
  exclude_symbols: string[];
  exclude_hours: number[];
  exclude_setups: string[];
  cap_risk_per_trade: number | null;
}

export const EMPTY_RULES: RulesState = {
  daily_loss_cap: null,
  max_trades_per_day: null,
  stop_after_losses: null,
  exclude_symbols: [],
  exclude_hours: [],
  exclude_setups: [],
  cap_risk_per_trade: null,
};

export function hasRules(rules: RulesState): boolean {
  return (
    rules.daily_loss_cap !== null ||
    rules.max_trades_per_day !== null ||
    rules.stop_after_losses !== null ||
    rules.cap_risk_per_trade !== null ||
    rules.exclude_symbols.length > 0 ||
    rules.exclude_hours.length > 0 ||
    rules.exclude_setups.length > 0
  );
}

const PathSchema = z.object({ net_pnl: z.number(), expectancy: num, max_drawdown: z.number() });

export const SimulationSchema = z.object({
  trades: z.number(),
  kept_trades: z.number().optional(),
  removed_trades: z.number().optional(),
  skipped_by_reason: z.record(z.string(), z.number()).optional(),
  risk_capped_trades: z.number().optional(),
  baseline: PathSchema.optional(),
  simulated: PathSchema.optional(),
  change: z
    .object({
      net_pnl: z.number(),
      expectancy_per_trade: z.number(),
      expectancy_per_trade_ci95: z.tuple([z.number(), z.number()]).nullable(),
      net_pnl_ci95: z.tuple([z.number(), z.number()]).nullable().optional(),
      method: z.string(),
    })
    .optional(),
  warning: z.string(),
  overfit: z
    .object({ level: z.string(), active_rules: z.number(), reasons: z.array(z.string()) })
    .optional(),
  intervals: z.enum(["ready", "pending"]).optional(),
  curves: z
    .object({
      trades: z.number(),
      x: z.array(z.number()),
      baseline: z.array(z.number()),
      simulated: z.array(z.number()),
    })
    .optional(),
  no_rules_set: z.boolean().optional(),
});
export type Simulation = z.infer<typeof SimulationSchema>;

// ----- Settings -----

export const SettingsSchema = z.object({
  starting_equity: num,
  privacy: z.object({
    aggregates_only: z.boolean(),
    include_notes: z.boolean(),
    include_trade_rows: z.boolean(),
  }),
  llm: z.object({ provider: z.string(), note: z.string() }),
  data: z.object({ trades: z.number(), imports: z.number(), templates: z.number() }),
  wipe_phrase: z.string(),
});
export type SettingsData = z.infer<typeof SettingsSchema>;

export const TemplatesSchema = z.array(
  z.object({
    fingerprint: z.string(),
    name: z.string(),
    mapping: z.record(z.string(), z.string().nullable()),
    updated_at: z.string(),
  }),
);

export const SelectionSchema = z.object({ selection_id: z.string(), count: z.number() });

// ----- hooks -----

export function useExplore(params: string) {
  return useQuery({
    queryKey: ["explore", params],
    queryFn: ({ signal }) =>
      requestJson(`/api/explore${params ? `?${params}` : ""}`, ExploreSchema, { signal }),
    placeholderData: keepPreviousData,
    staleTime: 15_000,
  });
}

export function useSegments(by: string, minN: number, params: string) {
  return useQuery({
    queryKey: ["segments", by, minN, params],
    queryFn: ({ signal }) =>
      requestJson(`/api/segments?by=${by}&min_n=${minN}${query(params)}`, SegmentsSchema, { signal }),
    placeholderData: keepPreviousData,
    staleTime: 15_000,
  });
}

/** The full Monte Carlo (5,000 paths) for the fan chart. */
export function useFan(params: string) {
  return useQuery({
    queryKey: ["fan", params],
    queryFn: ({ signal }) =>
      requestJson(`/api/metrics?bootstrap=100&paths=5000${query(params)}`, FanSchema, { signal }),
    placeholderData: keepPreviousData,
    staleTime: 30_000,
  });
}

/** The same report the dashboard uses (same resampling sizes), so its cache is shared. */
export function useBehaviorReport(params: string) {
  return useQuery({
    queryKey: ["behavior-report", params],
    queryFn: ({ signal }) =>
      requestJson(
        `/api/metrics?bootstrap=200&paths=500${query(params)}`,
        BehaviorReportSchema,
        { signal },
      ),
    placeholderData: keepPreviousData,
    staleTime: 15_000,
  });
}

export function useTimeline(params: string) {
  return useQuery({
    queryKey: ["timeline", params],
    queryFn: ({ signal }) =>
      requestJson(`/api/behavior/timeline${params ? `?${params}` : ""}`, TimelineSchema, { signal }),
    placeholderData: keepPreviousData,
    staleTime: 15_000,
  });
}

/**
 * Runs the simulator in two steps. The first request returns the point estimate at once. The
 * second adds bootstrap intervals and starts only after the first has returned.
 */
export function useSimulation(rules: RulesState, enabled: boolean) {
  const live = useFilters((state) => JSON.stringify(filtersBody(state)));
  const filters: unknown = JSON.parse(useDebouncedValue(live, FILTER_DEBOUNCE_MS));
  const body = { filters, rules };
  const key = JSON.stringify(body);
  const fast = useQuery({
    queryKey: ["simulate", "fast", key],
    queryFn: ({ signal }) =>
      requestJson("/api/simulate", SimulationSchema, {
        ...jsonBody({ ...body, intervals: false }),
        signal,
      }),
    enabled,
    placeholderData: keepPreviousData,
    staleTime: 60_000,
  });
  const full = useQuery({
    queryKey: ["simulate", "full", key],
    queryFn: ({ signal }) =>
      requestJson("/api/simulate", SimulationSchema, {
        ...jsonBody({ ...body, intervals: true, resamples: 1000 }),
        signal,
      }),
    enabled: enabled && fast.isSuccess && !fast.isPlaceholderData,
    staleTime: 60_000,
  });
  return { fast, full };
}

export function useCreateSelection() {
  return useMutation({
    mutationFn: (input: {
      bounds: { field: string; low?: number | null; high?: number | null }[];
    }) =>
      requestJson(
        "/api/selections",
        SelectionSchema,
        jsonBody({ filters: filtersBody(useFilters.getState()), bounds: input.bounds }),
      ),
  });
}

/** The trades behind one Coach finding, as a selection the Trades table can show. */
export function useSelectFinding() {
  return useMutation({
    mutationFn: (findingId: string) =>
      requestJson(
        "/api/coach/findings/selection",
        SelectionSchema,
        jsonBody({ filters: filtersBody(useFilters.getState()), finding_id: findingId }),
      ),
  });
}

export function useSettings() {
  return useQuery({
    queryKey: ["settings"],
    queryFn: ({ signal }) => requestJson("/api/settings", SettingsSchema, { signal }),
  });
}

export function useSaveSettings() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (patch: {
      starting_equity?: number | null;
      privacy?: { aggregates_only: boolean; include_notes: boolean; include_trade_rows: boolean };
    }) => requestJson("/api/settings", SettingsSchema, { ...jsonBody(patch), method: "PUT" }),
    onSuccess: (data, patch) => {
      client.setQueryData(["settings"], data);
      // Starting equity changes every ratio. Privacy choices change no number.
      if ("starting_equity" in patch) void client.invalidateQueries();
    },
  });
}

export function useTemplates() {
  return useQuery({
    queryKey: ["templates"],
    queryFn: ({ signal }) => requestJson("/api/templates", TemplatesSchema, { signal }),
  });
}

export function useRenameTemplate() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: { fingerprint: string; name: string }) =>
      requestJson(
        `/api/templates/${encodeURIComponent(input.fingerprint)}`,
        z.object({ name: z.string() }).passthrough(),
        { ...jsonBody({ name: input.name }), method: "PATCH" },
      ),
    onSuccess: () => client.invalidateQueries({ queryKey: ["templates"] }),
  });
}

export function useDeleteTemplate() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (fingerprint: string) =>
      requestJson(`/api/templates/${encodeURIComponent(fingerprint)}`, z.undefined(), {
        method: "DELETE",
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["templates"] });
      void client.invalidateQueries({ queryKey: ["settings"] });
    },
  });
}

export function useWipe() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (confirm: string) =>
      requestJson(
        "/api/wipe",
        z.object({ wiped: z.boolean(), removed: z.record(z.string(), z.number()) }),
        jsonBody({ confirm }),
      ),
    // Invalidate, not reset: Settings keeps its data, so the confirmation message stays on screen.
    onSuccess: () => client.invalidateQueries(),
  });
}
