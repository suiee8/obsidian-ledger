import { lazy, Suspense, useEffect, useState } from "react";

import { useFilters } from "../state/filters";
import { useAvailability, useDashboard } from "../lib/queries";
import { useDebouncedValue } from "../lib/useDebouncedValue";
import { FILTER_DEBOUNCE_MS } from "../state/filters";
import { fmtInt, fmtMoney, fmtNumber, fmtPercent } from "../lib/format";
import { useUi } from "../state/ui";
import { Kpi } from "../components/Kpi";
import { ActivityOnly } from "../components/Availability";
import { ChartFallback, Panel } from "../components/Panel";
import { DisciplineRing } from "../components/DisciplineRing";
import { Illustration } from "../components/Illustration";
import { DailyCalendar } from "../components/charts/DailyCalendar";
import { WeekdayHour } from "../components/charts/WeekdayHour";
import type { DashboardData } from "../lib/dashboard";

// The ECharts-based charts load in their own chunk after the KPI strip and layout paint, which keeps
// the entry bundle within the 250 KB gzip initial-JS budget.
const EquityAurora = lazy(() =>
  import("../components/charts/EquityAurora").then((module) => ({ default: module.EquityAurora })),
);


const DISCLAIMER = "Past performance review only. Obsidian Ledger does not give financial advice or trade signals.";
const HIDDEN_CAVEATS = [
  /^No starting equity is set, so Sharpe, Sortino, Calmar, and drawdown percentages are unavailable\.$/,
  /^\d+ trades have no plan-followed value, so adherence uses the rest\.$/,
  /^\d+ trades have no planned risk, so their R multiples are unavailable\.$/,
  /^\d+ trades have no MFE, so exit efficiency uses the rest\.$/,
];

function DashboardSkeleton() {
  return (
    <div className="dashboard" aria-busy="true" aria-label="Loading dashboard">
      <div className="kpi-strip">
        {Array.from({ length: 5 }, (_, index) => (
          <div key={index} className="glass kpi skeleton" />
        ))}
      </div>
      <div className="bento">
        <div className="glass panel span-12 skeleton skeleton-tall" />
      </div>
    </div>
  );
}

function EmptyDashboard() {
  const setRoute = useUi((state) => state.setRoute);
  return (
    <section className="glass empty-state" aria-labelledby="empty-title">
      <Illustration kind="empty" />
      <div>
        <p className="eyebrow">Nothing to review yet</p>
        <h2 id="empty-title">Import a journal to see your edge.</h2>
        <p className="lede">
          Drop an MT5, TradingView, or IBKR export, or any CSV or spreadsheet. The import shows every
          assumption before anything is saved.
        </p>
      </div>
      <button type="button" className="btn btn-primary" onClick={() => setRoute("import")}>
        Import a file
      </button>
    </section>
  );
}

function Headline({ data }: { data: DashboardData }) {
  const { core, risk, discipline, sample } = data.report;
  const drawdown = risk.drawdown;
  const ratios = risk.daily_ratios;
  const ratioReason = sample.starting_equity ? ratios.reason : undefined;
  return (
    <>
      <div className="kpi-strip" role="region" aria-label="Headline numbers">
        <Kpi
          label="Net P&L"
          value={core.net_pnl ?? null}
          format={(value) => fmtMoney(value)}
          tone={(core.net_pnl ?? 0) >= 0 ? "profit" : "loss"}
          note={`${fmtInt(sample.trades)} trades`}
        />
        <Kpi
          label="Win rate"
          value={core.win_rate ?? null}
          format={(value) => fmtPercent(value)}
          note={core.wins !== undefined ? `${core.wins} wins, ${core.losses ?? 0} losses` : undefined}
        />
        <Kpi
          label="Profit factor"
          value={core.profit_factor ?? null}
          format={(value) => fmtNumber(value, 2)}
          note="gross wins over gross losses"
        />

        <Kpi
          label="Max drawdown"
          value={drawdown.max_drawdown}
          format={(value) => fmtMoney(value)}
          tone="loss"
          note={
            drawdown.max_drawdown_pct !== null
              ? `${fmtPercent(drawdown.max_drawdown_pct)} of peak`
              : "set a starting equity for %"
          }
        />
        <DisciplineRing
          score={discipline.score}
          componentsUsed={discipline.components_used}
          componentsTotal={discipline.components_total}
          formula={discipline.formula}
        />
      </div>
      {ratios.available ? (
        <p className="ratio-line" aria-label="Daily-return ratios">
          Sharpe {fmtNumber(ratios.sharpe ?? null, 2)} · Sortino {fmtNumber(ratios.sortino ?? null, 2)} · Calmar{" "}
          {fmtNumber(ratios.calmar ?? null, 2)} · SQN {fmtNumber(risk.sqn, 2)}
        </p>
      ) : ratioReason || risk.sqn != null ? (
        <p className="ratio-line muted">
          {ratioReason}{ratioReason && risk.sqn != null ? " · " : ""}
          {risk.sqn != null ? `SQN ${fmtNumber(risk.sqn, 2)}` : null}
        </p>
      ) : null}
    </>
  );
}

export default function Dashboard() {
  const [chartsReady, setChartsReady] = useState(false);
  const liveParams = useFilters((state) => state.toParams());
  const params = useDebouncedValue(liveParams, FILTER_DEBOUNCE_MS);
  const query = useDashboard(params);
  const availability = useAvailability(params);
  const data = query.data;
  const hasTrades = data !== undefined && data.report.sample.trades > 0;

  useEffect(() => {
    if (!hasTrades || chartsReady) return;
    let secondFrame = 0;
    const firstFrame = requestAnimationFrame(() => {
      secondFrame = requestAnimationFrame(() => setChartsReady(true));
    });
    return () => {
      cancelAnimationFrame(firstFrame);
      cancelAnimationFrame(secondFrame);
    };
  }, [chartsReady, hasTrades]);

  if (query.isError) {
    return (
      <section className="glass panel" role="alert">
        <Illustration kind="error" />
        <h2 className="panel-title">The dashboard could not load</h2>
        <p className="muted">{query.error.message}</p>
        <button type="button" className="btn" onClick={() => void query.refetch()}>
          Try again
        </button>
      </section>
    );
  }
  if (query.isPending || data === undefined) {
    return <DashboardSkeleton />;
  }
  if (availability.data && !availability.data.available) {
    return <ActivityOnly data={availability.data} />;
  }
  if (data.report.sample.trades === 0 && data.equity.points.length === 0) {
    return <EmptyDashboard />;
  }

  const low = data.report.sample.low_confidence;
  const caveats = data.report.caveats.filter((note) => !HIDDEN_CAVEATS.some((pattern) => pattern.test(note)));
  return (
    <div className="dashboard">
      <header className="hero">
        <p className="eyebrow">Performance review</p>
        <h1 className="screen-title">Overview</h1>
        <p className="lede">Your edge, risk, and discipline for the trades in the current selection.</p>
      </header>
      <Headline data={data} />
      {(low || caveats.length > 0) && (
        <ul className="caveats" aria-label="Data caveats">
          {low && <li className="chip chip-warn">Low confidence: fewer than 30 trades in this selection</li>}
          {caveats.map((note) => (
            <li key={note} className="chip">
              {note}
            </li>
          ))}
        </ul>
      )}
      <div className="bento">
        <Panel title="Equity" className="span-12 panel-fill">
          <Suspense fallback={<ChartFallback sizeClass="chart-equity" />}>
            {chartsReady ? <EquityAurora equity={data.equity} /> : <ChartFallback sizeClass="chart-equity" />}
          </Suspense>
        </Panel>
        <Panel title="P&L calendar" className="span-12 panel-hug">
          <DailyCalendar days={data.daily} />
        </Panel>
        <Panel title="Weekday and hour" className="span-12 panel-hug">
          <WeekdayHour cells={data.heatmap} />
        </Panel>
      </div>
      <p className="footer">{DISCLAIMER}</p>
    </div>
  );
}
