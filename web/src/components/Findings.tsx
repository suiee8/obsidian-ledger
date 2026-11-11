import { fmtMoney, fmtNumber } from "../lib/format";
import type { DashboardData } from "../lib/dashboard";

type Finding = DashboardData["findings"]["edges"][number];

interface FindingsProps {
  findings: DashboardData["findings"];
}

function FindingList({ title, items, tone }: { title: string; items: Finding[]; tone: "profit" | "loss" }) {
  return (
    <div className="finding-group">
      <h3 className={`finding-title tone-${tone}`}>{title}</h3>
      {items.length === 0 ? (
        <p className="muted">None with enough evidence yet.</p>
      ) : (
        <ul className="finding-list">
          {items.map((item) => (
            <li key={`${item.dimension}-${item.value}`} className="finding">
              <span className="finding-name">
                {item.value}
                <span className="finding-dimension"> · {item.dimension}</span>
              </span>
              <span className="finding-metrics">
                {fmtMoney(item.expectancy)} per trade, n {item.n}
                {item.q_value !== null && `, q ${fmtNumber(item.q_value, 3)}`}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function Findings({ findings }: FindingsProps) {
  return (
    <section className="glass findings" aria-labelledby="findings-title">
      <h2 id="findings-title">Strengths and leaks</h2>
      <FindingList title="Strengths to double down on" items={findings.edges} tone="profit" />
      <FindingList title="Leaks to fix first" items={findings.leaks} tone="loss" />
      <p className="caveat">{findings.caveat}</p>
    </section>
  );
}
