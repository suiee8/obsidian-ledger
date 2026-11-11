import { useId, useState, type KeyboardEvent } from "react";

import { fmtNumber } from "../lib/format";
import { DISCIPLINE_COMPONENTS, type BehaviorReport } from "../lib/phase4";

const LABELS: Record<string, string> = {
  plan_adherence: "Plan adherence",
  risk_consistency: "Risk consistency",
  post_loss_behavior: "Post-loss behavior",
  overtrading_control: "Overtrading control",
  stop_usage: "Stop usage",
};

const MEANING: Record<string, string> = {
  plan_adherence: "Share of trades where you followed your plan.",
  risk_consistency: "How steady your planned risk per trade is. Wide swings lower it.",
  post_loss_behavior: "Share of trades after a loss that were not revenge-style re-entries.",
  overtrading_control: "Share of days that stayed within the trades-per-day limit.",
  stop_usage: "Share of trades that had a stop loss.",
};

/** A button that shows text on hover and focus, and hides it with Escape. */
function FormulaTip({ formula }: { formula: string }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const onKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    if (event.key === "Escape" && open) {
      event.stopPropagation();
      setOpen(false);
    }
  };
  return (
    <span
      className="tip"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onKeyDown={onKeyDown}
    >
      <button
        type="button"
        className="tip-button"
        aria-label="How the Discipline Score is calculated"
        aria-describedby={open ? id : undefined}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
      >
        ?
      </button>
      {open && (
        <span role="tooltip" id={id} className="tip-body">
          {formula}
        </span>
      )}
    </span>
  );
}

/** The Discipline Score with each component, its weight, and the points it adds. */
export function DisciplineBreakdown({ discipline }: { discipline: BehaviorReport["discipline"] }) {
  const weights = discipline.weights ?? {};
  const used = DISCIPLINE_COMPONENTS.filter((key) => discipline.components[key] !== null && discipline.components[key] !== undefined);
  const totalWeight = used.reduce((sum, key) => sum + (weights[key] ?? 0), 0);
  const weightedSum = used.reduce(
    (sum, key) => sum + (weights[key] ?? 0) * (discipline.components[key] ?? 0),
    0,
  );

  return (
    <div>
      <div className="score-head">
        <p className="score-value" aria-label={discipline.score === null ? "Score not available" : `Score ${fmtNumber(discipline.score, 0)} of 100`}>
          {discipline.score === null ? "—" : fmtNumber(discipline.score, 0)}
          <span className="score-of"> / 100</span>
        </p>
        <FormulaTip formula={discipline.formula} />
      </div>
      <p className="card-note">
        {discipline.components_used} of {discipline.components_total} components have data.
      </p>
      <ul className="component-list">
        {DISCIPLINE_COMPONENTS.map((key) => {
          const value = discipline.components[key] ?? null;
          const weight = weights[key] ?? 0;
          const points = value !== null && totalWeight > 0 ? (weight / totalWeight) * value : null;
          return (
            <li key={key}>
              <div className="component-head">
                <span>{LABELS[key]}</span>
                <span className="muted">
                  weight {fmtNumber(weight * 100, 0)}%
                  {points !== null ? `, adds ${fmtNumber(points, 1)} points` : ""}
                </span>
              </div>
              {value === null ? (
                <p className="muted">No data. Left out of the score; the other weights are rescaled.</p>
              ) : (
                <div
                  className="meter"
                  role="meter"
                  aria-label={`${LABELS[key]}: ${fmtNumber(value, 0)} out of 100`}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={Math.round(value)}
                >
                  <span className="meter-fill" style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
                  <span className="meter-text">{fmtNumber(value, 0)}</span>
                </div>
              )}
              <p className="card-note">{MEANING[key]}</p>
            </li>
          );
        })}
      </ul>
      {totalWeight > 0 && (
        <p className="card-note">
          Sum of weight × component = {fmtNumber(weightedSum, 1)}. Weights used = {fmtNumber(totalWeight, 2)}.{" "}
          {fmtNumber(weightedSum, 1)} ÷ {fmtNumber(totalWeight, 2)} ={" "}
          {discipline.score === null ? "—" : fmtNumber(discipline.score, 1)}.
        </p>
      )}
    </div>
  );
}
