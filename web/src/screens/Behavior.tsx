import { useMemo } from "react";

import { BarSeries, DayBars } from "../components/charts/Bars";
import { DisciplineBreakdown } from "../components/DisciplineBreakdown";
import { Panel } from "../components/Panel";
import { ActivityOnly } from "../components/Availability";
import { DISCLAIMER, EmptyScreen, ScreenError, ScreenSkeleton } from "../components/ScreenStates";
import { fmtInt, fmtMoney, fmtPercent } from "../lib/format";
import { useBehaviorReport, useTimeline, type Timeline } from "../lib/phase4";
import { useAvailability } from "../lib/queries";
import { useDebouncedValue } from "../lib/useDebouncedValue";
import { FILTER_DEBOUNCE_MS, useFilters } from "../state/filters";

type Day = Timeline["days"][number];

function DayTimeline({
  title,
  rule,
  summary,
  days,
  pick,
  flag,
  name,
  threshold,
}: {
  title: string;
  rule: string;
  summary: string;
  days: Day[];
  pick: (day: Day) => number;
  flag: (day: Day) => boolean;
  name: string;
  threshold?: { value: number; label: string };
}) {
  const labels = useMemo(() => days.map((day) => day.day), [days]);
  const values = useMemo(() => days.map(pick), [days, pick]);
  const flagged = useMemo(() => days.map(flag), [days, flag]);
  return (
    <Panel title={title} className="span-12">
      <p className="card-note">{rule}</p>
      <DayBars
        label={`${title}: ${name} for each trading day. ${summary}`}
        days={labels}
        values={values}
        flagged={flagged}
        name={name}
        threshold={threshold}
      />
      <p className="muted" aria-live="polite">
        {summary}
      </p>
    </Panel>
  );
}

const revengeCount = (day: Day) => day.revenge;
const revengeFlag = (day: Day) => day.revenge > 0;
const tiltCount = (day: Day) => day.tilt;
const tiltFlag = (day: Day) => day.tilt > 0;
const dayTrades = (day: Day) => day.trades;
const dayOver = (day: Day) => day.overtraded;
const money = (value: number) => fmtMoney(value);

function PostLoss({ groups }: { groups: NonNullable<Timeline["post_loss"]> }) {
  const labels = useMemo(() => groups.map((g) => `${g.label} (${fmtInt(g.trades)})`), [groups]);
  const values = useMemo(() => groups.map((g) => g.expectancy), [groups]);
  return (
    <Panel title="Performance after a loss" className="span-12">
      <p className="card-note">
        Average P&L per trade, split by what happened just before the trade was entered. The number of trades in
        each group is in brackets.
      </p>
      <BarSeries
        label="Average P&L per trade after a win, after a calm loss, after a revenge-style entry, and on tilt"
        labels={labels}
        values={values}
        format={money}
        signed
      />
      <div className="table-wrap" tabIndex={0} role="region" aria-label="Post-loss performance table">
        <table>
          <thead>
            <tr>
              <th scope="col">Entered</th>
              <th scope="col">Trades</th>
              <th scope="col">Win rate</th>
              <th scope="col">Per trade</th>
              <th scope="col">Net P&L</th>
            </tr>
          </thead>
          <tbody>
            {groups.map((group) => (
              <tr key={group.key}>
                <th scope="row">{group.label}</th>
                <td>{fmtInt(group.trades)}</td>
                <td>{fmtPercent(group.win_rate)}</td>
                <td>{fmtMoney(group.expectancy)}</td>
                <td>{fmtMoney(group.net_pnl)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="card-note">
        A trade can be in both the revenge-style and tilt groups. Groups under 30 trades are too small to trust.
      </p>
    </Panel>
  );
}

export default function Behavior() {
  const liveParams = useFilters((state) => state.toParams());
  const params = useDebouncedValue(liveParams, FILTER_DEBOUNCE_MS);
  const availability = useAvailability(params);
  const timeline = useTimeline(params);
  const report = useBehaviorReport(params);

  if (timeline.isError || report.isError) {
    const message = (timeline.error ?? report.error)?.message ?? "Request failed.";
    return (
      <ScreenError
        title="Behavior could not load"
        message={message}
        onRetry={() => {
          void timeline.refetch();
          void report.refetch();
        }}
      />
    );
  }
  const data = timeline.data;
  const scored = report.data;
  if (timeline.isPending || report.isPending || data === undefined || scored === undefined) {
    return <ScreenSkeleton label="Loading behavior" />;
  }
  if (availability.data && !availability.data.available) {
    return <ActivityOnly data={availability.data} />;
  }
  if (data.trades === 0 || !data.totals || !data.post_loss || !data.rules || !data.thresholds) {
    return (
      <EmptyScreen
        title="No trades to review for behavior."
        body="Import a journal, or clear the filters, to see revenge trading, tilt, and overtrading over time."
      />
    );
  }
  const { totals, thresholds, rules } = data;
  return (
    <div className="dashboard">
      <header>
        <h1 className="screen-title">Behavior</h1>
        <p className="lede">
          How you trade after losses and on busy days. These are patterns in what you did, not predictions.
        </p>
      </header>
      <div className="bento">
        <Panel title="Discipline Score" className="span-5">
          <DisciplineBreakdown discipline={scored.discipline} />
        </Panel>
        <div className="span-7 stack">
          <DayTimeline
            title="Revenge timeline"
            rule={rules.revenge}
            summary={`${fmtInt(totals.revenge_trades)} revenge-style trades across ${fmtInt(totals.days)} days.`}
            days={data.days}
            pick={revengeCount}
            flag={revengeFlag}
            name="Revenge-style trades"
          />
        </div>
        <DayTimeline
          title="Tilt timeline"
          rule={rules.tilt}
          summary={`${fmtInt(totals.tilt_trades)} trades entered after ${thresholds.tilt_losses} or more losses in a row.`}
          days={data.days}
          pick={tiltCount}
          flag={tiltFlag}
          name="Trades on tilt"
        />
        <DayTimeline
          title="Overtrading timeline"
          rule={rules.overtrading}
          summary={`${fmtInt(totals.overtraded_days)} of ${fmtInt(totals.days)} days went over ${thresholds.overtrading_trades_per_day} trades.`}
          days={data.days}
          pick={dayTrades}
          flag={dayOver}
          name="Trades per day"
          threshold={{
            value: thresholds.overtrading_trades_per_day,
            label: `Limit ${thresholds.overtrading_trades_per_day}`,
          }}
        />
        <PostLoss groups={data.post_loss} />
      </div>
      <p className="footer">{DISCLAIMER}</p>
    </div>
  );
}
