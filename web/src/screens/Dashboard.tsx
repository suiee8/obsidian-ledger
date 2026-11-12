import { lazy, Suspense, useEffect, useState } from "react";

import { useFilters } from "../state/filters";
import { useDashboard } from "../lib/queries";
import { useDebouncedValue } from "../lib/useDebouncedValue";
import { FILTER_DEBOUNCE_MS } from "../state/filters";
import { fmtInt, fmtMoney, fmtNumber, fmtPercent, fmtR } from "../lib/format";
import { useUi } from "../state/ui";
import { Kpi } from "../components/Kpi";
import { ChartFallback, Panel } from "../components/Panel";
import { DisciplineRing } from "../components/DisciplineRing";
import { Findings } from "../components/Findings";
import { DailyCalendar } from "../components/charts/DailyCalendar";
import { WeekdayHour } from "../components/charts/WeekdayHour";
import type { DashboardData } from "../lib/dashboard";

// The ECharts-based charts load in their own chunk after the KPI strip and layout paint, which keeps
// the entry bundle within the 250 KB gzip initial-JS budget.
const EquityAurora = lazy(() =>
  import("../components/charts/EquityAurora").then((module) => ({ default: module.EquityAurora })),
);
const RHistogram = lazy(() =>
  import("../components/charts/RHistogram").then((module) => ({ default: module.RHistogram })),
);
const EdgeRadar = lazy(() =>
  import("../components/charts/EdgeRadar").then((module) => ({ default: module.EdgeRadar })),
);

const DISCLAIMER = "Past performance review only. Obsidian Ledger does not give financial advice or trade signals.";

function DashboardSkeleton() {
  return (
    <div className="dashboard" aria-busy="true" aria-label="Loading dashboard">
      <div className="kpi-strip">
        {Array.from({ length: 6 }, (_, index) => (
          <div key={index} className="glass kpi skeleton" />
        ))}
      </div>
      <div className="bento">
        <div className="glass panel span-8 skeleton skeleton-tall" />
        <div className="glass panel span-4 skeleton skeleton-tall" />
      </div>
    </div>
  );
}

function EmptyDashboard() {
  const setRoute = useUi((state) => state.setRoute);
  return (
    <section className="glass empty-state" aria-labelledby="empty-title">
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
          label="Expectancy"
          value={core.expectancy_r ?? null}
          format={(value) => fmtR(value)}
          tone={(core.expectancy_r ?? 0) >= 0 ? "profit" : "loss"}
          note={core.expectancy !== undefined && core.expectancy !== null ? `${fmtMoney(core.expectancy)} per trade` : undefined}
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
      ) : (
        <p className="ratio-line muted">
          {ratios.reason ?? "Set a starting equity to unlock daily-return ratios."} SQN {fmtNumber(risk.sqn, 2)}
        </p>
      )}
    </>
  );
}

export default function Dashboard() {
  const [chartsReady, setChartsReady] = useState(false);
  const liveParams = useFilters((state) => state.toParams());
  const params = useDebouncedValue(liveParams, FILTER_DEBOUNCE_MS);
  const query = useDashboard(params);
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
  if (data.report.sample.trades === 0 && data.equity.points.length === 0) {
    return <EmptyDashboard />;
  }

  const low = data.report.sample.low_confidence;
  return (
    <div className="dashboard">
      <Headline data={data} />
      {(low || data.report.caveats.length > 0) && (
        <ul className="caveats" aria-label="Data caveats">
          {low && <li className="chip chip-warn">Low confidence: fewer than 30 trades in this selection</li>}
          {data.report.caveats.map((note) => (
            <li key={note} className="chip">
              {note}
            </li>
          ))}
        </ul>
      )}
      <div className="bento">
        <Panel title="Equity" className="span-8 panel-fill">
          <Suspense fallback={<ChartFallback sizeClass="chart-equity" />}>
            {chartsReady ? <EquityAurora equity={data.equity} /> : <ChartFallback sizeClass="chart-equity" />}
          </Suspense>
        </Panel>
        <Findings findings={data.findings} />
        <Panel title="P&L calendar" className="span-7 panel-hug">
          <DailyCalendar days={data.daily} />
        </Panel>
        <Panel title="Edge radar by setup" className="span-5">
          <Suspense fallback={<ChartFallback sizeClass="chart-radar" />}>
            {chartsReady ? <EdgeRadar radar={data.radar} /> : <ChartFallback sizeClass="chart-radar" />}
          </Suspense>
        </Panel>
        <Panel title="R distribution" className="span-6">
          <Suspense fallback={<ChartFallback sizeClass="chart-r" />}>
            {chartsReady ? <RHistogram histogram={data.r_histogram} /> : <ChartFallback sizeClass="chart-r" />}
          </Suspense>
        </Panel>
        <Panel title="Weekday and hour" className="span-6 panel-hug">
          <WeekdayHour cells={data.heatmap} />
        </Panel>
      </div>
      <p className="footer">{DISCLAIMER}</p>
    </div>
  );
}
