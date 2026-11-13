import { z } from "zod";

const nullableNumber = z.number().nullable();

export const ReportSchema = z
  .object({
    sample: z
      .object({
        trades: z.number(),
        excluded_no_fx: z.number(),
        low_confidence: z.boolean().optional(),
        starting_equity: nullableNumber.optional(),
      })
      .passthrough(),
    core: z
      .object({
        trades: z.number(),
        wins: nullableNumber.optional(),
        losses: nullableNumber.optional(),
        flat: nullableNumber.optional(),
        net_pnl: nullableNumber.optional(),
        win_rate: nullableNumber.optional(),
        profit_factor: nullableNumber.optional(),
        expectancy: nullableNumber.optional(),
        expectancy_r: nullableNumber.optional(),
        payoff_ratio: nullableNumber.optional(),
        fee_drag: nullableNumber.optional(),
        largest_win: nullableNumber.optional(),
        largest_loss: nullableNumber.optional(),
      })
      .passthrough(),
    risk: z
      .object({
        drawdown: z
          .object({
            max_drawdown: nullableNumber,
            max_drawdown_pct: nullableNumber,
            recovered: z.boolean().nullable(),
          })
          .passthrough(),
        daily_ratios: z
          .object({
            available: z.boolean(),
            sharpe: nullableNumber.optional(),
            sortino: nullableNumber.optional(),
            calmar: nullableNumber.optional(),
            reason: z.string().optional(),
          })
          .passthrough(),
        sqn: nullableNumber,
      })
      .passthrough(),
    discipline: z
      .object({
        score: nullableNumber,
        components_used: z.number(),
        components_total: z.number(),
        formula: z.string(),
      })
      .passthrough(),
    caveats: z.array(z.string()),
  })
  .passthrough();

export const DashboardSchema = z
  .object({
    dataset_version: z.string(),
    report: ReportSchema,
    equity: z.object({
      points: z.array(z.object({ t: z.string(), equity: z.number(), drawdown: z.number() })),
      downsampled: z.boolean(),
      source_points: z.number(),
    }),
    daily: z.array(z.object({ day: z.string(), pnl: z.number(), trades: z.number() })),
    r_histogram: z.object({
      bins: z.array(z.object({ from: z.number(), to: z.number(), count: z.number() })),
      n: z.number(),
      clipped: z.number(),
      mean: nullableNumber,
      median: nullableNumber,
    }),
    heatmap: z.array(
      z.object({
        weekday: z.number(),
        hour: z.number(),
        trades: z.number(),
        pnl: z.number(),
        expectancy: z.number(),
      }),
    ),
    radar: z.object({
      axes: z.array(z.string()),
      setups: z.array(
        z.object({
          setup: z.string(),
          n: z.number(),
          low_confidence: z.boolean(),
          raw: z.record(z.string(), nullableNumber),
          normalized: z.array(nullableNumber),
        }),
      ),
    }),
    findings: z.object({
      edges: z.array(findingSchema()),
      leaks: z.array(findingSchema()),
      slices_tested: z.number(),
      caveat: z.string(),
    }),
  })
  .passthrough();

export const AvailabilitySchema = z.object({
  available: z.boolean(),
  has_pnl: z.boolean(),
  has_prices: z.boolean(),
  message: z.string().nullable(),
  dataset_version: z.string(),
  activity: z
    .object({
      trades: z.number(),
      source_events: z.number(),
      symbols: z.number(),
      by_symbol: z.array(z.object({ symbol: z.string(), events: z.number() })),
      by_day: z.array(z.object({ day: z.string(), events: z.number() })),
      by_hour: z.array(z.object({ hour: z.number(), events: z.number() })),
      directions: z.record(z.string(), z.number()),
      order_types: z.record(z.string(), z.number()),
      leverage_values: z.number(),
      average_leverage: nullableNumber,
      hold_times_available: z.boolean(),
      average_holding_seconds: nullableNumber,
      time_precision: z.array(z.string()),
      overtraded_days: z.number(),
    })
    .nullable(),
});

function findingSchema() {
  return z.object({
    dimension: z.string(),
    value: z.string(),
    n: z.number(),
    expectancy: nullableNumber,
    expectancy_ci95: z.tuple([z.number(), z.number()]).nullable(),
    t_statistic: nullableNumber,
    q_value: nullableNumber,
  });
}

export const TradeRowSchema = z
  .object({
    trade_key: z.string(),
    trade_id: z.string(),
    account: z.string(),
    symbol: z.string(),
    asset_class: z.string().nullable(),
    side: z.string(),
    setup: z.string().nullable(),
    entry_time: z.string(),
    exit_time: z.string(),
    qty: z.number(),
    entry_price: nullableNumber,
    exit_price: nullableNumber,
    gross_pnl: nullableNumber,
    net_pnl: nullableNumber,
    net_pnl_base: nullableNumber,
    currency: z.string(),
    base_currency: z.string(),
    fees: nullableNumber,
    commission: nullableNumber,
    swap: nullableNumber,
    planned_risk: nullableNumber,
    r_multiple: nullableNumber,
    stop_loss: nullableNumber,
    take_profit: nullableNumber,
    mae: nullableNumber,
    mfe: nullableNumber,
    holding_seconds: nullableNumber,
    session: z.string(),
    timeframe: z.string().nullable(),
    notes: z.string(),
    tags: z.string().nullable(),
    emotion: z.string().nullable(),
    confidence: z.string().nullable(),
    screenshot_path: z.string().nullable(),
    plan_followed: z.boolean().nullable(),
    source_timezone: z.string().nullable(),
  })
  .passthrough();

export type TradeRow = z.infer<typeof TradeRowSchema>;

export const TradePageSchema = z.object({
  total: z.number(),
  offset: z.number(),
  rows: z.array(TradeRowSchema),
});

export const FilterOptionsSchema = z.object({
  accounts: z.array(z.string()),
  symbols: z.array(z.string()),
  setups: z.array(z.string()),
  sides: z.array(z.string()),
  tags: z.array(z.string()),
  emotions: z.array(z.string()),
});

export const ViewSchema = z.object({
  name: z.string(),
  config: z.record(z.string(), z.unknown()),
  updated_at: z.string(),
});

export const ViewListSchema = z.array(ViewSchema);

const questionSchema = z.object({
  id: z.string(),
  text: z.string(),
  options: z.array(z.string()),
  blocking: z.boolean(),
});

const assumptionSchema = z.object({
  key: z.string(),
  value: z.string(),
  detail: z.string(),
  adjustable: z.boolean(),
});

const columnSchema = z.object({
  index: z.number(),
  header: z.string(),
  field: z.string().nullable(),
  confidence: z.string().nullable(),
  source: z.string(),
  reasons: z.array(z.string()),
});

const columnProfileSchema = z.object({
  index: z.number(),
  header: z.string(),
  type_mix: z.record(z.string(), z.number()),
  regex_shape: z.array(z.string()),
  cardinality: z.number(),
  minimum: nullableNumber,
  maximum: nullableNumber,
  monotonicity: z.string(),
  max_length: z.number(),
  samples: z.array(z.string()),
});

export const PreviewSchema = z.object({
  preview_id: z.string(),
  filename: z.string(),
  sha256: z.string(),
  size_bytes: z.number(),
  kind: z.string(),
  encoding: z.string(),
  delimiter: z.string().nullable(),
  line_ending: z.string(),
  header_record: z.number(),
  adapter: z.string().nullable(),
  shape: z.string().nullable(),
  decimal: z.string(),
  date_formats: z.string(),
  date_ambiguous: z.boolean(),
  timezone: z.string(),
  base_currency: z.string(),
  columns: z.array(columnSchema),
  profiles: z.array(columnProfileSchema),
  capabilities: z.record(z.string(), z.boolean()),
  warnings: z.array(z.string()),
  rows_profiled: z.number(),
  duplicate_rows: z.number(),
  symbol_count: z.number(),
  row_order: z.string(),
  totals_rows: z.number(),
  questions: z.array(questionSchema),
  assumptions: z.array(assumptionSchema),
  sample_rows: z.array(z.record(z.string(), z.string())),
  fingerprint: z.string(),
});

export const CommitSchema = z.object({
  import_id: z.string(),
  filename: z.string(),
  rows_total: z.number(),
  blank_rows: z.number(),
  accepted: z.number(),
  inserted: z.number(),
  already_present: z.number(),
  rejected: z.number(),
  duplicates_in_file: z.number(),
  open_positions: z.number(),
  orphan_closes: z.number(),
  quantity_conserved: z.boolean(),
  activity_events: z.number(),
  issues: z.array(
    z.object({
      code: z.string(),
      severity: z.enum(["error", "warning", "info"]),
      title: z.string(),
      count: z.number(),
      example_rows: z.array(z.number()),
      suggested_fix: z.string(),
    }),
  ),
  assumptions: z.array(assumptionSchema),
  rejected_csv_path: z.string(),
});

export type Preview = z.infer<typeof PreviewSchema>;
export type Commit = z.infer<typeof CommitSchema>;

// ---------------------------------------------------------------------------------------------
// Coach report. Mirrors api/src/obsidian_ledger/coach/models.py.
// ---------------------------------------------------------------------------------------------

export const FigureSchema = z.object({
  value: z.number().nullable(),
  unit: z.enum(["currency", "R", "count", "ratio", "number", "seconds", "score", "text"]),
  display: z.string(),
  source: z.string(),
  label: z.string(),
  kind: z.enum(["exact", "bootstrap"]),
});
export type Figure = z.infer<typeof FigureSchema>;

const ConfidenceSchema = z.enum(["high", "medium", "low"]);
export type Confidence = z.infer<typeof ConfidenceSchema>;

const IntervalSchema = z.object({ low: FigureSchema, high: FigureSchema, level: z.number(), method: z.string() });

const EvidenceSchema = z.object({
  trade_key: z.string(),
  trade_id: z.string(),
  symbol: z.string(),
  pnl: FigureSchema,
});
export type Evidence = z.infer<typeof EvidenceSchema>;

export const CoachFindingSchema = z.object({
  id: z.string(),
  kind: z.enum(["leak", "strength", "pattern"]),
  category: z.enum(["segment", "behavior"]),
  dimension: z.string(),
  title: z.string(),
  n: FigureSchema,
  mean_currency: FigureSchema,
  effect_currency: FigureSchema,
  effect_r: FigureSchema.nullable(),
  total_currency: FigureSchema,
  interval_currency: IntervalSchema.nullable(),
  interval_r: IntervalSchema.nullable(),
  confidence: ConfidenceSchema,
  p_value: z.number().nullable(),
  q_value: z.number().nullable(),
  evidence: z.array(EvidenceSchema),
  what_if: z.object({ description: z.string(), pnl_change: FigureSchema, in_sample_note: z.string() }),
  rule: z.string(),
  filter: z
    .object({
      symbols: z.array(z.string()),
      setups: z.array(z.string()),
      sides: z.array(z.string()),
      accounts: z.array(z.string()),
      tag: z.string().nullable(),
    })
    .nullable(),
  note: z.string().nullable(),
  limit: FigureSchema.nullable().optional(),
});
export type CoachFinding = z.infer<typeof CoachFindingSchema>;

export const CoachReportSchema = z.object({
  schema_version: z.literal(1),
  report_id: z.string(),
  dataset_version: z.string(),
  filter_key: z.string(),
  filters: z.record(z.string(), z.unknown()),
  generated_at: z.string(),
  status: z.enum(["ok", "too_few_trades", "empty", "cannot_be_assessed"]),
  base_currency: z.string(),
  sample_trades: FigureSchema,
  verdict: z.object({
    label: z.enum(["edge_present", "unproven", "negative", "cannot_be_assessed"]),
    headline: z.string(),
    lines: z.array(z.string()),
    confidence: ConfidenceSchema,
    basis: z.string(),
    expectancy: FigureSchema,
    interval: IntervalSchema.nullable(),
    n: FigureSchema,
  }),
  top_leaks: z.array(CoachFindingSchema),
  top_strengths: z.array(CoachFindingSchema),
  low_confidence_leads: z.array(CoachFindingSchema),
  behavior_patterns: z.array(CoachFindingSchema),
  risk_review: z.array(
    z.object({ key: z.string(), title: z.string(), figure: FigureSchema, note: z.string() }),
  ),
  action_plan: z.array(
    z.object({ day: z.number(), focus: z.string(), task: z.string(), finding_id: z.string().nullable() }),
  ),
  checklist: z.array(
    z.object({
      question: z.string(),
      reason: z.string(),
      finding_id: z.string().nullable(),
      figure: FigureSchema.nullable(),
    }),
  ),
  caveats: z.array(z.object({ text: z.string(), figure: FigureSchema.nullable() })),
  key_figures: z.record(z.string(), FigureSchema),
  change_vs_previous: z
    .object({
      previous_report_id: z.string(),
      previous_generated_at: z.string(),
      metrics: z.array(
        z.object({ key: z.string(), label: z.string(), previous: FigureSchema, current: FigureSchema }),
      ),
      new_finding_ids: z.array(z.string()),
      resolved_finding_ids: z.array(z.string()),
    })
    .nullable(),
  seconds_to_build: z.number(),
  params: z.record(z.string(), z.unknown()),
});
export type CoachReport = z.infer<typeof CoachReportSchema>;

export const TradePositionSchema = z.object({ index: z.number().nullable(), total: z.number() });
