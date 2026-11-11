import { lazy, Suspense } from "react";

import type { CoachFinding, Evidence } from "../../lib/schemas";

// ECharts loads in its own chunk, the same one the Dashboard charts use.
const FindingChart = lazy(() => import("./FindingChart"));

interface FindingCardProps {
  finding: CoachFinding;
  onChip: (trade: Evidence) => void;
  onApplyFilter: (finding: CoachFinding) => void;
  /** The compact form leaves out the chart. Used for the long list of behavior patterns. */
  compact?: boolean;
}

function toneFor(value: number | null): string {
  if (value === null) return "";
  return value < 0 ? "tone-loss" : "tone-profit";
}

export function FindingCard({ finding, onChip, onApplyFilter, compact = false }: FindingCardProps) {
  const headingId = `finding-${finding.id.replace(/[^a-zA-Z0-9]/g, "-")}`;
  const interval = finding.interval_currency;
  return (
    <article className="coach-finding" aria-labelledby={headingId} data-finding={finding.id}>
      <header className="coach-finding-head">
        <span className={`confidence confidence-${finding.confidence}`}>
          {finding.confidence} confidence
        </span>
        <h4 id={headingId}>{finding.title}</h4>
      </header>
      <p className="coach-numbers">
        <span>{finding.n.display} trades</span>
        <span>
          avg <span className={toneFor(finding.mean_currency.value)}>{finding.mean_currency.display}</span>
        </span>
        <span>
          gap <span className={toneFor(finding.effect_currency.value)}>{finding.effect_currency.display}</span>
        </span>
        {finding.effect_r && <span>{finding.effect_r.display} per trade</span>}
        {finding.limit && <span>limit {finding.limit.display} trades a day</span>}
        {interval && (
          <span>
            95% {interval.low.display} to {interval.high.display}
          </span>
        )}
      </p>
      {!compact && finding.effect_currency.value !== null && (
        <Suspense fallback={<div className="chart chart-mini skeleton" aria-hidden="true" />}>
          <FindingChart finding={finding} />
        </Suspense>
      )}
      <p className="coach-whatif">{finding.what_if.description}</p>
      <p className="coach-rule">
        <strong>Rule.</strong> {finding.rule}
      </p>
      {finding.note && <p className="muted">{finding.note}</p>}
      {finding.evidence.length > 0 && (
        <div className="trade-chips" role="group" aria-label={`Evidence trades for ${finding.title}`}>
          {finding.evidence.map((trade) => (
            <button
              key={trade.trade_key}
              type="button"
              className={`trade-chip ${toneFor(trade.pnl.value)}`}
              aria-label={`Show trade ${trade.trade_id} in the Trades table, ${trade.pnl.display}`}
              onClick={() => onChip(trade)}
            >
              {trade.trade_id}
            </button>
          ))}
        </div>
      )}
      <div className="row-actions">
        <button
          type="button"
          className="btn"
          aria-label={`Apply as filter: ${finding.title}`}
          onClick={() => onApplyFilter(finding)}
        >
          Apply as filter
        </button>
      </div>
    </article>
  );
}
