import { Panel } from "./Panel";
import type { AvailabilitySchema } from "../lib/schemas";
import type { z } from "zod";

type AvailabilityData = z.infer<typeof AvailabilitySchema>;

function Table({
  label,
  rows,
}: {
  label: string;
  rows: Array<{ name: string; count: number }>;
}) {
  return (
    <div
      className="table-wrap"
      role="region"
      aria-label={`${label} table, horizontally scrollable`}
      tabIndex={0}
    >
      <table>
        <caption>{label}</caption>
        <thead>
          <tr>
            <th scope="col">{label}</th>
            <th scope="col">Events</th>
          </tr>
        </thead>
        <tbody>
          {rows.length ? (
            rows.map((row) => (
              <tr key={row.name}>
                <th scope="row">{row.name}</th>
                <td>{row.count.toLocaleString()}</td>
              </tr>
            ))
          ) : (
            <tr>
              <td colSpan={2}>No activity recorded</td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

export function ActivityOnly({ data }: { data: AvailabilityData }) {
  if (data.available || !data.activity) return null;
  const activity = data.activity;
  const seconds = activity.average_holding_seconds;
  const duration =
    seconds === null
      ? "Not available"
      : seconds < 3600
        ? `${Math.round(seconds / 60)} min`
        : `${(seconds / 3600).toFixed(1)} h`;

  return (
    <div className="dashboard">
      <section className="glass panel" aria-labelledby="availability-title">
        <h1 id="availability-title" className="panel-title">
          Performance metrics unavailable
        </h1>
        <p>{data.message}</p>
        <p className="muted">
          Import a realized P&amp;L column and entry/exit prices. Missing financial values are not
          treated as zero.
        </p>
      </section>
      <div className="bento">
        <Panel title="Activity available" className="span-12">
          <dl className="detail-grid">
            <dt>Matched trades</dt>
            <dd>{activity.trades.toLocaleString()}</dd>
            <dt>Source events</dt>
            <dd>{activity.source_events.toLocaleString()}</dd>
            <dt>Symbols in source</dt>
            <dd>{activity.symbols.toLocaleString()}</dd>
            <dt>Average holding time</dt>
            <dd>{duration}</dd>
            <dt>Time precision</dt>
            <dd>{activity.time_precision.join(", ") || "Not available"}</dd>
            <dt>Events with leverage</dt>
            <dd>{activity.leverage_values.toLocaleString()}</dd>
            <dt>Average leverage</dt>
            <dd>{activity.average_leverage?.toFixed(2) ?? "Not available"}</dd>
            <dt>Overtraded days</dt>
            <dd>{activity.overtraded_days.toLocaleString()}</dd>
          </dl>
        </Panel>
        <Panel title="Activity by symbol" className="span-6">
          <Table
            label="Symbol"
            rows={activity.by_symbol.map((row) => ({ name: row.symbol, count: row.events }))}
          />
        </Panel>
        <Panel title="Activity by day" className="span-6">
          <Table label="Day" rows={activity.by_day.map((row) => ({ name: row.day, count: row.events }))} />
        </Panel>
        <Panel title="Activity by hour (UTC)" className="span-6">
          <Table
            label="Hour"
            rows={activity.by_hour.map((row) => ({ name: `${row.hour}:00`, count: row.events }))}
          />
        </Panel>
        <Panel title="Direction and order type" className="span-6">
          <Table
            label="Direction"
            rows={Object.entries(activity.directions).map(([name, count]) => ({ name, count }))}
          />
          <Table
            label="Order type"
            rows={Object.entries(activity.order_types).map(([name, count]) => ({ name, count }))}
          />
        </Panel>
      </div>
    </div>
  );
}
