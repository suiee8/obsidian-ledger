import { useMemo } from "react";

import { fmtDay, fmtInt, fmtMoney, WEEKDAY_LABELS } from "../../lib/format";
import type { DashboardData } from "../../lib/dashboard";
import { useChartPalette } from "../../lib/useChartPalette";
import { PnlLegend } from "./PnlLegend";

type Day = DashboardData["daily"][number];

interface DailyCalendarProps {
  days: Day[];
}

const MS_PER_DAY = 86_400_000;
const monthName = new Intl.DateTimeFormat("en", { month: "short", timeZone: "UTC" });
const monthTitle = new Intl.DateTimeFormat("en", { month: "long", year: "numeric", timeZone: "UTC" });

function toUtcDate(iso: string): Date {
  return new Date(`${iso}T00:00:00Z`);
}

function isoDay(date: Date): string {
  return date.toISOString().slice(0, 10);
}

/** Each column is a week, starting on Monday. */
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
    const maxAbs = days.reduce((max, day) => Math.max(max, Math.abs(day.pnl)), 1);
    const months = weeks.flatMap((column, index) => {
      const end = column.at(-1)!.date;
      const previous = weeks[index - 1]?.at(-1)?.date;
      return previous?.getUTCMonth() === end.getUTCMonth() ? [] : [{ index, date: end }];
    });
    const monthLabels = months.filter((month, index) => (months[index + 1]?.index ?? Infinity) - month.index >= 3);
    return { weeks, maxAbs, monthLabels };
  }, [days]);

  if (!layout) {
    return <p className="muted">No trading days in this selection.</p>;
  }

  const { weeks, maxAbs, monthLabels } = layout;
  return (
    <>
      <p className="dashboard-chart-caption">Daily P&L · {fmtInt(days.length)} trading {days.length === 1 ? "day" : "days"}</p>
      <div
        className="calendar"
        role="region"
        tabIndex={0}
        aria-label={`P&L calendar across ${days.length} trading days, scrolls sideways`}
      >
        <div className="calendar-grid" style={{ gridTemplateColumns: `var(--chart-day-width) repeat(${weeks.length}, var(--calendar-cell-size))` }}>
          {monthLabels.map(({ index, date }) => (
            <span
              className="calendar-month"
              key={index}
              style={{ gridColumn: index + 2, gridRow: 1 }}
              title={monthTitle.format(date)}
            >
              {monthName.format(date)}
            </span>
          ))}
          {WEEKDAY_LABELS.map((day, index) => (
            <span className="calendar-day" key={day} style={{ gridColumn: 1, gridRow: index + 2 }} aria-hidden="true">
              {day}
            </span>
          ))}
          {weeks.map((column, columnIndex) =>
            column.map((cell) => {
              const pnl = cell.day?.pnl ?? null;
              const strength = pnl === null ? 0 : Math.min(1, Math.abs(pnl) / maxAbs);
              const color = pnl === null || pnl === 0
                ? undefined
                : `color-mix(in srgb, ${pnl > 0 ? palette.profit : palette.loss} ${Math.round(25 + 75 * strength)}%, transparent)`;
              const day = isoDay(cell.date);
              const label = cell.day
                ? `${fmtDay(day)}: ${fmtMoney(pnl)} from ${cell.day.trades} ${cell.day.trades === 1 ? "trade" : "trades"}`
                : `${fmtDay(day)}: no trades`;
              const state = pnl === null ? "is-empty" : pnl === 0 ? "has-trades is-flat" : "has-trades";
              return (
                <span
                  key={day}
                  className={`calendar-cell ${state}`}
                  role="img"
                  style={{ gridColumn: columnIndex + 2, gridRow: (cell.date.getUTCDay() + 6) % 7 + 2, background: color }}
                  title={label}
                  aria-label={label}
                />
              );
            }),
          )}
        </div>
      </div>
      <PnlLegend />
    </>
  );
}
