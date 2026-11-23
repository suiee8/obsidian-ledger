import { useMemo } from "react";

import { fmtMoney, WEEKDAY_LABELS } from "../../lib/format";
import type { DashboardData } from "../../lib/dashboard";
import { useChartPalette } from "../../lib/useChartPalette";
import { PnlLegend } from "./PnlLegend";

type Cell = DashboardData["heatmap"][number];

interface WeekdayHourProps {
  cells: Cell[];
}

/** Average P&L per trade for each weekday and UTC entry hour. Empty hours are blank. */
export function WeekdayHour({ cells }: WeekdayHourProps) {
  const palette = useChartPalette();
  const { lookup, maxAbs } = useMemo(() => {
    const map = new Map<string, Cell>();
    let max = 0;
    for (const cell of cells) {
      map.set(`${cell.weekday}-${cell.hour}`, cell);
      max = Math.max(max, Math.abs(cell.expectancy));
    }
    return { lookup: map, maxAbs: max || 1 };
  }, [cells]);

  if (cells.length === 0) return <p className="muted">No entry times in this selection.</p>;

  return (
    <>
      <p className="dashboard-chart-caption">Average P&L per trade by entry time (UTC)</p>
      <div
        className="weekday-hour"
        role="table"
        aria-label="Average P&L by weekday and UTC entry hour"
        tabIndex={0}
      >
        <div className="wh-row" role="row">
          <span className="wh-corner" role="columnheader" aria-hidden="true" />
          {Array.from({ length: 24 }, (_, hour) => (
            <span key={hour} className="wh-hour" role="columnheader" aria-label={`${String(hour).padStart(2, "0")}:00 UTC`}>
              {hour % 3 === 0 ? String(hour).padStart(2, "0") : ""}
            </span>
          ))}
        </div>
        {WEEKDAY_LABELS.map((label, weekday) => (
          <div className="wh-row" role="row" key={label}>
            <span className="wh-day" role="rowheader">
              {label}
            </span>
            {Array.from({ length: 24 }, (_, hour) => {
              const cell = lookup.get(`${weekday}-${hour}`);
              const strength = cell ? Math.min(1, Math.abs(cell.expectancy) / maxAbs) : 0;
              const color = !cell || cell.expectancy === 0
                ? undefined
                : `color-mix(in srgb, ${cell.expectancy > 0 ? palette.profit : palette.loss} ${Math.round(25 + 75 * strength)}%, transparent)`;
              const text = cell
                ? `${label} ${String(hour).padStart(2, "0")}:00 UTC: ${cell.trades} ${cell.trades === 1 ? "trade" : "trades"}, ${fmtMoney(cell.expectancy)} per trade`
                : `${label} ${String(hour).padStart(2, "0")}:00 UTC: no trades`;
              return (
                <span
                  key={hour}
                  role="cell"
                  className={`wh-cell${cell ? cell.expectancy === 0 ? " is-flat" : "" : " is-empty"}`}
                  style={{ background: color }}
                  title={text}
                  aria-label={text}
                />
              );
            })}
          </div>
        ))}
      </div>
      <PnlLegend />
    </>
  );
}
