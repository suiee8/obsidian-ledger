interface DisciplineRingProps {
  score: number | null;
  componentsUsed: number;
  componentsTotal: number;
  formula: string;
}

const RADIUS = 34;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

/** Discipline Score as a ring. The formula is shown on hover and read by screen readers. */
export function DisciplineRing({ score, componentsUsed, componentsTotal, formula }: DisciplineRingProps) {
  const fraction = score === null ? 0 : Math.max(0, Math.min(100, score)) / 100;
  const label = score === null ? "Discipline score not available" : `Discipline score ${score.toFixed(0)} of 100`;
  return (
    <article className="glass kpi discipline" title={formula}>
      <p className="label">Discipline</p>
      <svg width="88" height="88" viewBox="0 0 88 88" role="img" aria-label={label}>
        <circle cx="44" cy="44" r={RADIUS} fill="none" className="ring-track" strokeWidth="8" />
        <circle
          cx="44"
          cy="44"
          r={RADIUS}
          fill="none"
          className="ring-value"
          strokeWidth="8"
          strokeLinecap="round"
          strokeDasharray={`${fraction * CIRCUMFERENCE} ${CIRCUMFERENCE}`}
          transform="rotate(-90 44 44)"
        />
        <text x="44" y="49" textAnchor="middle" className="ring-text">
          {score === null ? "—" : score.toFixed(0)}
        </text>
      </svg>
      <p className="kpi-note">
        {componentsUsed} of {componentsTotal} components
      </p>
    </article>
  );
}
