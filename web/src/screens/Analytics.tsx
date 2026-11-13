import { useMemo, useState } from "react";

import { BarSeries, GroupedBars } from "../components/charts/Bars";
import { BrushScatter, type BrushRange } from "../components/charts/BrushScatter";
import { MonteCarloFan } from "../components/charts/LineBands";
import { Panel } from "../components/Panel";
import { ActivityOnly } from "../components/Availability";
import { useAvailability } from "../lib/queries";
import { DISCLAIMER, EmptyScreen, ScreenError, ScreenSkeleton } from "../components/ScreenStates";
import { fmtInt, fmtMoney, fmtNumber, fmtPercent, fmtR, WEEKDAY_LABELS } from "../lib/format";
import {
  useCreateSelection,
  useExplore,
  useFan,
  useSegments,
  type ExploreData,
  type SegmentsData,
} from "../lib/phase4";
import { useDebouncedValue } from "../lib/useDebouncedValue";
import { FILTER_DEBOUNCE_MS, useFilters } from "../state/filters";
import { useUi } from "../state/ui";

const DIMENSIONS = [
  ["symbol", "Symbol"],
  ["setup", "Setup"],
  ["side", "Side"],
  ["session", "Session"],
  ["weekday", "Weekday"],
  ["hour", "Entry hour (UTC)"],
  ["holding", "Holding time"],
  ["size", "Position size"],
  ["emotion", "Emotion"],
  ["account", "Account"],
  ["tag", "Tag"],
] as const;

type Slice = SegmentsData["slices"][number];

const METRICS = {
  net_pnl: { label: "Net P&L", get: (s: Slice) => s.net_pnl, format: (v: number) => fmtMoney(v), signed: true },
  expectancy: {
    label: "Average P&L per trade",
    get: (s: Slice) => s.expectancy,
    format: (v: number) => fmtMoney(v),
    signed: true,
  },
  win_rate: { label: "Win rate", get: (s: Slice) => s.win_rate, format: (v: number) => fmtPercent(v), signed: false },
  expectancy_r: {
    label: "Average R per trade",
    get: (s: Slice) => s.expectancy_r,
    format: (v: number) => fmtR(v),
    signed: true,
  },
  n: { label: "Number of trades", get: (s: Slice) => s.n, format: (v: number) => fmtInt(v), signed: false },
} as const;
type MetricKey = keyof typeof METRICS;

const NATURAL_ORDER: Record<string, readonly string[]> = {
  weekday: WEEKDAY_LABELS,
  holding: ["under 5 min", "5 to 30 min", "30 min to 2 h", "2 to 8 h", "8 h and over"],
  size: ["small (bottom third)", "medium (middle third)", "large (top third)"],
};

const money = (value: number) => fmtMoney(value);
const dayOf = (ms: number) => new Date(ms).toISOString().slice(0, 10);
const plain = (value: number) => fmtNumber(value, 2);
const percent = (value: number) => fmtPercent(value);
const MS_DAY = 86_400_000;

function orderSlices(dimension: string, slices: Slice[], metric: MetricKey): Slice[] {
  const natural = NATURAL_ORDER[dimension];
  if (natural) {
    return [...slices].sort((a, b) => natural.indexOf(a.value) - natural.indexOf(b.value));
  }
  if (dimension === "hour") return [...slices].sort((a, b) => Number(a.value) - Number(b.value));
  const get = METRICS[metric].get;
  return [...slices].sort((a, b) => (get(b) ?? -Infinity) - (get(a) ?? -Infinity));
}

function SegmentExplorer({ params }: { params: string }) {
  const [dimension, setDimension] = useState<string>("symbol");
  const [metric, setMetric] = useState<MetricKey>("expectancy");
  const query = useSegments(dimension, 30, params);
  const slices = useMemo(
    () => orderSlices(dimension, query.data?.slices ?? [], metric),
    [dimension, query.data, metric],
  );
  const config = METRICS[metric];
  const labels = useMemo(() => slices.map((slice) => slice.value), [slices]);
  const values = useMemo(() => slices.map((slice) => config.get(slice) ?? null), [slices, config]);
  const dimensionLabel = DIMENSIONS.find(([key]) => key === dimension)?.[1] ?? dimension;

  return (
    <Panel title="Segment explorer" className="span-12">
      <div className="control-row">
        <label className="field">
          <span>Group trades by</span>
          <select value={dimension} onChange={(event) => setDimension(event.target.value)}>
            {DIMENSIONS.map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Measure</span>
          <select value={metric} onChange={(event) => setMetric(event.target.value as MetricKey)}>
            {Object.entries(METRICS).map(([key, item]) => (
              <option key={key} value={key}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
      </div>
      {query.isError ? (
        <p role="alert" className="muted">
          Segments could not load: {query.error.message}
        </p>
      ) : slices.length === 0 ? (
        <p className="muted">No trades to group in this selection.</p>
      ) : (
        <>
          <BarSeries
            label={`${config.label} by ${dimensionLabel}`}
            labels={labels}
            values={values}
            format={config.format}
            signed={config.signed}
          />
          <div className="table-wrap" tabIndex={0} role="region" aria-label={`${dimensionLabel} segments table`}>
            <table>
              <thead>
                <tr>
                  <th scope="col">{dimensionLabel}</th>
                  <th scope="col">Trades</th>
                  <th scope="col">Win rate</th>
                  <th scope="col">Net P&L</th>
                  <th scope="col">Per trade</th>
                  <th scope="col">95% interval per trade</th>
                  <th scope="col">q-value</th>
                  <th scope="col">Verdict</th>
                </tr>
              </thead>
              <tbody>
                {slices.map((slice) => (
                  <tr key={slice.value}>
                    <th scope="row">{slice.value}</th>
                    <td>{fmtInt(slice.n)}</td>
                    <td>{fmtPercent(slice.win_rate)}</td>
                    <td>{fmtMoney(slice.net_pnl)}</td>
                    <td>{fmtMoney(slice.expectancy)}</td>
                    <td>
                      {slice.expectancy_ci95
                        ? `${fmtMoney(slice.expectancy_ci95[0])} to ${fmtMoney(slice.expectancy_ci95[1])}`
                        : "not enough trades"}
                    </td>
                    <td>{slice.q_value === null ? "—" : fmtNumber(slice.q_value, 3)}</td>
                    <td>
                      <span className={`chip${slice.verdict === "low confidence" ? " chip-warn" : ""}`}>
                        {slice.verdict}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="card-note">
            {fmtInt(query.data?.slices_tested ?? 0)} groups were tested together. Groups under 30 trades are
            marked low confidence. {query.data?.multiple_comparisons ?? ""}
          </p>
        </>
      )}
    </Panel>
  );
}

function BrushActions({
  count,
  busy,
  onOpen,
  onClear,
}: {
  count: number | null;
  busy: boolean;
  onOpen: () => void;
  onClear: () => void;
}) {
  return (
    <div className="row-actions" aria-live="polite">
      <p className="muted">
        {count === null
          ? "Drag on the chart to draw a rectangle around trades."
          : `${fmtInt(count)} trades inside the rectangle.`}
      </p>
      <button type="button" className="btn btn-primary" disabled={!count || busy} onClick={onOpen}>
        Open these trades in the Trades table
      </button>
      <button type="button" className="btn btn-quiet" disabled={count === null} onClick={onClear}>
        Clear rectangle
      </button>
    </div>
  );
}

function countInside(
  xs: readonly (number | null)[],
  ys: readonly (number | null)[],
  range: BrushRange,
): number {
  let count = 0;
  for (let i = 0; i < xs.length; i++) {
    const x = xs[i];
    const y = ys[i];
    if (x === null || x === undefined || y === null || y === undefined) continue;
    if (x >= range.x[0] && x <= range.x[1] && y >= range.y[0] && y <= range.y[1]) count++;
  }
  return count;
}

type Bound = { field: string; low?: number | null; high?: number | null };

function useOpenInTrades() {
  const mutation = useCreateSelection();
  const setSelection = useUi((state) => state.setSelection);
  const setRoute = useUi((state) => state.setRoute);
  return {
    busy: mutation.isPending,
    error: mutation.isError ? mutation.error.message : null,
    open: (bounds: Bound[], label: string) =>
      mutation.mutate(
        { bounds },
        {
          onSuccess: (result) => {
            setSelection({ id: result.selection_id, count: result.count, label });
            setRoute("trades");
          },
        },
      ),
  };
}

function Constellation({ points }: { points: ExploreData["points"] }) {
  const [yField, setYField] = useState<"pnl" | "r">("pnl");
  const [range, setRange] = useState<BrushRange | null>(null);
  const [clearToken, setClearToken] = useState(0);
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [low, setLow] = useState("");
  const [high, setHigh] = useState("");
  const { busy, error, open } = useOpenInTrades();
  const ys = yField === "pnl" ? points.pnl : points.r;
  const count = range ? countInside(points.t, ys, range) : null;
  const yName = yField === "pnl" ? "Net P&L" : "R multiple";

  const typed: Bound[] = [];
  if (from || to) {
    typed.push({
      field: "t",
      low: from ? Date.parse(`${from}T00:00:00Z`) : null,
      high: to ? Date.parse(`${to}T00:00:00Z`) + MS_DAY - 1 : null,
    });
  }
  if (low !== "" || high !== "") {
    typed.push({
      field: yField,
      low: low === "" ? null : Number(low),
      high: high === "" ? null : Number(high),
    });
  }

  return (
    <Panel title="Trade Constellation" className="span-12">
      <p className="card-note">
        Every trade is one dot: when it closed, and how it ended. Drag a rectangle to pick trades, then open
        them in the Trades table.
      </p>
      <div className="control-row">
        <label className="field">
          <span>Vertical axis</span>
          <select value={yField} onChange={(event) => setYField(event.target.value as "pnl" | "r")}>
            <option value="pnl">Net P&L</option>
            <option value="r">R multiple</option>
          </select>
        </label>
      </div>
      <BrushScatter
        label={`Trade Constellation: ${fmtInt(points.n)} trades by close date and ${yName}`}
        xs={points.t}
        ys={ys}
        outcome={points.pnl}
        xType="time"
        xName="Closed"
        yName={yName}
        formatX={dayOf}
        formatY={yField === "pnl" ? money : plain}
        onBrush={setRange}
        clearToken={clearToken}
      />
      <BrushActions
        count={count}
        busy={busy}
        onOpen={() =>
          range &&
          open(
            [
              { field: "t", low: range.x[0], high: range.x[1] },
              { field: yField, low: range.y[0], high: range.y[1] },
            ],
            "your rectangle on the Trade Constellation",
          )
        }
        onClear={() => {
          setRange(null);
          setClearToken((value) => value + 1);
        }}
      />
      <fieldset className="form-grid">
        <legend>Pick trades without dragging</legend>
        <label className="field">
          <span>Closed from</span>
          <input type="date" value={from} onChange={(event) => setFrom(event.target.value)} />
        </label>
        <label className="field">
          <span>Closed to</span>
          <input type="date" value={to} onChange={(event) => setTo(event.target.value)} />
        </label>
        <label className="field">
          <span>{yName} at least</span>
          <input
            type="number"
            step="any"
            value={low}
            onChange={(event) => setLow(event.target.value)}
          />
        </label>
        <label className="field">
          <span>{yName} at most</span>
          <input
            type="number"
            step="any"
            value={high}
            onChange={(event) => setHigh(event.target.value)}
          />
        </label>
        <button
          type="button"
          className="btn"
          disabled={typed.length === 0 || busy}
          onClick={() => open(typed, "your date and value range")}
        >
          Open in the Trades table
        </button>
      </fieldset>
      {error && (
        <p role="alert" className="muted">
          Could not pick those trades: {error}
        </p>
      )}
    </Panel>
  );
}

function MaeMfe({ data }: { data: ExploreData }) {
  const { points, mae_mfe: summary } = data;
  const [range, setRange] = useState<BrushRange | null>(null);
  const [clearToken, setClearToken] = useState(0);
  const { busy, error, open } = useOpenInTrades();
  const count = range ? countInside(points.mae, points.mfe, range) : null;

  return (
    <Panel title="MAE and MFE" className="span-6">
      {summary.trades_with_excursions === 0 ? (
        <p className="muted">
          None of these trades report MAE or MFE, so there is nothing to plot. Add those columns to your file to
          see how far trades went against you and for you.
        </p>
      ) : (
        <>
          <dl className="stat-row">
            <div>
              <dt>Trades with both</dt>
              <dd>
                {fmtInt(summary.trades_with_excursions)} of {fmtInt(summary.trades_total)}
              </dd>
            </div>
            <div>
              <dt>Winners kept (P&L ÷ MFE)</dt>
              <dd>{fmtPercent(summary.winner_capture_ratio)}</dd>
            </div>
            <div>
              <dt>Avg worst move, losers</dt>
              <dd>{fmtNumber(summary.avg_mae_losers, 2)}</dd>
            </div>
            <div>
              <dt>Avg worst move, winners</dt>
              <dd>{fmtNumber(summary.avg_mae_winners, 2)}</dd>
            </div>
          </dl>
          <BrushScatter
            label="MAE against MFE for each trade"
            xs={points.mae}
            ys={points.mfe}
            outcome={points.pnl}
            xType="value"
            xName="MAE, worst move against you"
            yName="MFE, best move for you"
            formatX={plain}
            formatY={plain}
            onBrush={setRange}
            clearToken={clearToken}
          />
          <BrushActions
            count={count}
            busy={busy}
            onOpen={() =>
              range &&
              open(
                [
                  { field: "mae", low: range.x[0], high: range.x[1] },
                  { field: "mfe", low: range.y[0], high: range.y[1] },
                ],
                "your rectangle on the MAE and MFE chart",
              )
            }
            onClear={() => {
              setRange(null);
              setClearToken((value) => value + 1);
            }}
          />
          {error && (
            <p role="alert" className="muted">
              Could not pick those trades: {error}
            </p>
          )}
          <p className="card-note">{summary.note}</p>
        </>
      )}
    </Panel>
  );
}

function Streaks({ data }: { data: ExploreData["streaks"] }) {
  const categories = useMemo(() => data.histogram.map((row) => String(row.length)), [data]);
  const wins = useMemo(() => data.histogram.map((row) => row.wins), [data]);
  const losses = useMemo(() => data.histogram.map((row) => row.losses), [data]);
  const longest = [...data.longest_wins.slice(0, 3), ...data.longest_losses.slice(0, 3)];
  return (
    <Panel title="Streaks" className="span-6">
      {data.runs === 0 ? (
        <p className="muted">No winning or losing runs yet.</p>
      ) : (
        <>
          <dl className="stat-row">
            <div>
              <dt>Longest winning run</dt>
              <dd>{data.longest_wins[0]?.length ?? 0} trades</dd>
            </div>
            <div>
              <dt>Longest losing run</dt>
              <dd>{data.longest_losses[0]?.length ?? 0} trades</dd>
            </div>
            <div>
              <dt>Runs in total</dt>
              <dd>{fmtInt(data.runs)}</dd>
            </div>
          </dl>
          <GroupedBars
            label="How many winning and losing runs of each length"
            categories={categories}
            wins={wins}
            losses={losses}
            xName="Run length (trades)"
            yName="Runs"
          />
          <div className="table-wrap" tabIndex={0} role="region" aria-label="Longest runs table">
            <table>
              <thead>
                <tr>
                  <th scope="col">Run</th>
                  <th scope="col">Length</th>
                  <th scope="col">From</th>
                  <th scope="col">To</th>
                  <th scope="col">P&L</th>
                </tr>
              </thead>
              <tbody>
                {longest.map((run) => (
                  <tr key={`${run.kind}-${run.start}-${run.length}`}>
                    <th scope="row">{run.kind === "win" ? "Winning" : "Losing"}</th>
                    <td>{run.length}</td>
                    <td>{run.start}</td>
                    <td>{run.end}</td>
                    <td>{fmtMoney(run.pnl)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </Panel>
  );
}

function FeeDrag({ data }: { data: ExploreData["fee_drag"] }) {
  const labels = useMemo(() => data.by_symbol.map((row) => row.symbol), [data]);
  const values = useMemo(() => data.by_symbol.map((row) => row.drag), [data]);
  return (
    <Panel title="Fee drag" className="span-6">
      <dl className="stat-row">
        <div>
          <dt>Total costs</dt>
          <dd>{data.costs === null ? "Not available" : fmtMoney(data.costs)}</dd>
        </div>
        <div>
          <dt>Gross P&L</dt>
          <dd>{data.gross === null ? "Not available" : fmtMoney(data.gross)}</dd>
        </div>
        <div>
          <dt>Drag</dt>
          <dd>{fmtPercent(data.drag)}</dd>
        </div>
      </dl>
      {data.by_symbol.length > 0 && (
        <BarSeries
          label="Fee drag by symbol, costs as a share of gross P&L"
          labels={labels}
          values={values}
          format={percent}
          signed={false}
        />
      )}
      <p className="card-note">{data.rule}</p>
    </Panel>
  );
}

function FanPanel({ params }: { params: string }) {
  const query = useFan(params);
  const mc = query.data?.statistics?.monte_carlo;
  return (
    <Panel title="Monte Carlo fan" className="span-12">
      {query.isError ? (
        <p role="alert" className="muted">
          The simulation could not run: {query.error.message}
        </p>
      ) : !mc || !mc.fan || mc.fan.length === 0 ? (
        <p className="muted">{query.isPending ? "Running 5,000 simulated paths…" : "No trades to simulate."}</p>
      ) : (
        <>
          <MonteCarloFan
            fan={mc.fan}
            label={`Range of possible equity over the next ${mc.horizon_trades ?? 0} trades, from ${fmtInt(mc.paths)} simulated paths`}
          />
          <dl className="stat-row">
            <div>
              <dt>Paths</dt>
              <dd>{fmtInt(mc.paths)}</dd>
            </div>
            <div>
              <dt>Median end</dt>
              <dd>{fmtMoney(mc.final_percentiles?.p50)}</dd>
            </div>
            <div>
              <dt>Worst 5% end</dt>
              <dd>{fmtMoney(mc.final_percentiles?.p5)}</dd>
            </div>
            <div>
              <dt>Best 5% end</dt>
              <dd>{fmtMoney(mc.final_percentiles?.p95)}</dd>
            </div>
            <div>
              <dt>Chance of a drawdown of {fmtMoney(mc.drawdown_threshold)} or more</dt>
              <dd>{fmtPercent(mc.probability_drawdown_at_least_threshold)}</dd>
            </div>
            <div>
              <dt>Chance of reaching {fmtMoney(mc.target)}</dt>
              <dd>{fmtPercent(mc.probability_reaching_target)}</dd>
            </div>
          </dl>
          <p className="card-note">{mc.assumption}</p>
        </>
      )}
    </Panel>
  );
}

export default function Analytics() {
  const liveParams = useFilters((state) => state.toParams());
  const params = useDebouncedValue(liveParams, FILTER_DEBOUNCE_MS);
  const availability = useAvailability(params);
  const query = useExplore(params);
  const data = query.data;

  if (query.isError) {
    return (
      <ScreenError
        title="Analytics could not load"
        message={query.error.message}
        onRetry={() => void query.refetch()}
      />
    );
  }
  if (query.isPending || data === undefined) return <ScreenSkeleton label="Loading analytics" />;
  if (availability.data && !availability.data.available) {
    return <ActivityOnly data={availability.data} />;
  }
  if (data.points.n === 0) {
    return (
      <EmptyScreen
        title="No trades to explore."
        body="Import a journal, or clear the filters, to look at your trades from every angle."
      />
    );
  }
  return (
    <div className="dashboard">
      <header>
        <h1 className="screen-title">Analytics</h1>
        <p className="lede">
          {fmtInt(data.points.n)} trades. Every figure here comes from the same trades as the dashboard.
        </p>
      </header>
      <div className="bento">
        <SegmentExplorer params={params} />
        <Constellation points={data.points} />
        <MaeMfe data={data} />
        <Streaks data={data.streaks} />
        <FeeDrag data={data.fee_drag} />
        <FanPanel params={params} />
      </div>
      <p className="footer">{DISCLAIMER}</p>
    </div>
  );
}
