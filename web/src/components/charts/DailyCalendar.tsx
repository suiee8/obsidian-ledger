import { useMemo } from "react";

import { fmtDay, fmtMoney } from "../../lib/format";
import type { DashboardData } from "../../lib/dashboard";
import { useChartPalette } from "../../lib/useChartPalette";

type Day = DashboardData["daily"][number];

interface DailyCalendarProps {
  days: Day[];
}

const MS_PER_DAY = 86_400_000;

function toUtcDate(iso: string): Date {
  return new Date(`${iso}T00:00:00Z`);
}

function isoDay(date: Date): string {
  return date.toISOString().slice(0, 10);
}

/** Weeks run down the page as columns. Monday is the first row. */
export function DailyCalendar({ days }: DailyCalendarProps) {
  const palette = useChartPalette();
  const layout = useMemo(() => {
    if (days.length === 0) return null;
    const byDay = new Map(days.map((day) => [day.day, day]));
    const first = toUtcDate(days[0]?.day ?? "");
    const last = toUtcDate(days[days.length - 1]?.day ?? "");
    const offset = (first.getUTCDay() + 6) % 7;
    const start = new Date(first.getTime() - offset * MS_PER_DAY);
    const weeks: { date: Date; day: Day | undefined }[][] = [];
    let week: { date: Date; day: Day | undefined }[] = [];
    for (let time = start.getTime(); time <= last.getTime(); time += MS_PER_DAY) {
      const date = new Date(time);
      week.push({ date, day: byDay.get(isoDay(date)) });
      if (week.length === 7) {
        weeks.push(week);
        week = [];
      }
    }
    if (week.length > 0) weeks.push(week);
    const maxAbs = Math.max(1, ...days.map((day) => Math.abs(day.pnl)));
    return { weeks, maxAbs };
  }, [days]);

  if (!layout) {
    return <p className="muted">No trading days in this selection.</p>;
  }

  const { weeks, maxAbs } = layout;
  return (
    <div
      className="calendar"
      role="region"
      tabIndex={0}
      aria-label={`P&L calendar across ${days.length} trading days, scrolls sideways`}
    >
      <div className="calendar-grid" style={{ gridTemplateColumns: `repeat(${weeks.length}, 14px)` }}>
        {weeks.map((column, columnIndex) =>
          column.map((cell) => {
            const pnl = cell.day?.pnl ?? null;
            const strength = pnl === null ? 0 : Math.min(1, Math.abs(pnl) / maxAbs);
            const color =
              pnl === null || pnl === 0
                ? undefined
                : pnl > 0
                  ? `color-mix(in srgb, ${palette.profit} ${Math.round(25 + 75 * strength)}%, transparent)`
                  : `color-mix(in srgb, ${palette.loss} ${Math.round(25 + 75 * strength)}%, transparent)`;
            const label = cell.day
              ? `${fmtDay(cell.day.day)}: ${fmtMoney(cell.day.pnl)} from ${cell.day.trades} trades`
              : `${fmtDay(isoDay(cell.date))}: no trades`;
            const weekdayRow = (cell.date.getUTCDay() + 6) % 7;
            return (
              <span
                key={`${columnIndex}-${isoDay(cell.date)}`}
                className={`calendar-cell${cell.day ? " has-trades" : ""}`}
                role="img"
                style={{ gridColumn: columnIndex + 1, gridRow: weekdayRow + 1, background: color }}
                title={label}
                aria-label={label}
              />
            );
          }),
        )}
      </div>
      <div className="calendar-legend" aria-hidden="true">
        <span className="legend-swatch" style={{ background: palette.loss }} /> loss
        <span className="legend-swatch" style={{ background: palette.profit }} /> profit
      </div>
    </div>
  );
}
