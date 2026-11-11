import { useMemo } from "react";

import { fmtMoney, WEEKDAY_LABELS } from "../../lib/format";
import type { DashboardData } from "../../lib/dashboard";
import { useChartPalette } from "../../lib/useChartPalette";

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

  return (
    <div
      className="weekday-hour"
      role="table"
      aria-label="Average P&L by weekday and UTC entry hour"
      tabIndex={0}
    >
      <div className="wh-row" role="row">
        <span className="wh-corner" role="columnheader" aria-hidden="true" />
        {Array.from({ length: 24 }, (_, hour) => (
          <span key={hour} className="wh-hour" role="columnheader">
            {hour % 3 === 0 ? hour : ""}
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
            const color = !cell
              ? undefined
              : cell.expectancy >= 0
                ? `color-mix(in srgb, ${palette.profit} ${Math.round(15 + 85 * strength)}%, transparent)`
                : `color-mix(in srgb, ${palette.loss} ${Math.round(15 + 85 * strength)}%, transparent)`;
            const text = cell
              ? `${label} ${String(hour).padStart(2, "0")}:00 UTC: ${cell.trades} trades, ${fmtMoney(cell.expectancy)} per trade`
              : `${label} ${String(hour).padStart(2, "0")}:00 UTC: no trades`;
            return (
              <span
                key={hour}
                role="cell"
                className={`wh-cell${cell ? "" : " is-empty"}`}
                style={{ background: color }}
                title={text}
                aria-label={text}
              />
            );
          })}
        </div>
      ))}
    </div>
  );
}
