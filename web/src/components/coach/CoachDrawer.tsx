import { useEffect, type KeyboardEvent, type PointerEvent, type ReactNode } from "react";

import { apiBase } from "../../lib/api";
import { useCoachRun, type CoachRun } from "../../lib/coach";
import type { CoachFinding, CoachReport, Evidence } from "../../lib/schemas";
import { useSelectFinding } from "../../lib/phase4";
import { useDebouncedValue } from "../../lib/useDebouncedValue";
import { FILTER_DEBOUNCE_MS, filterParams, useFilters } from "../../state/filters";
import { COACH_MIN_WIDTH, useUi } from "../../state/ui";
import { FindingCard } from "./FindingCard";
import { Timeline } from "./Timeline";

const KEY_STEP = 24;

function Section({ title, children }: { title: string; children: ReactNode }) {
  const id = `coach-${title.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
  return (
    <section className="coach-section" aria-labelledby={id}>
      <h3 id={id}>{title}</h3>
      {children}
    </section>
  );
}

function Verdict({ report }: { report: CoachReport }) {
  const { verdict } = report;
  return (
    <section className="coach-verdict" aria-label="Verdict">
      <p className="eyebrow">Verdict</p>
      <h3>
        {verdict.headline} <span className={`confidence confidence-${verdict.confidence}`}>{verdict.confidence} confidence</span>
      </h3>
      <ul>
        {verdict.lines.map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
      <p className="muted">Basis: {verdict.basis}.</p>
    </section>
  );
}

function Findings({
  title,
  empty,
  findings,
  compact,
  onChip,
  onApplyFilter,
}: {
  title: string;
  empty: string;
  findings: CoachFinding[];
  compact?: boolean;
  onChip: (trade: Evidence) => void;
  onApplyFilter: (finding: CoachFinding) => void;
}) {
  return (
    <Section title={title}>
      {findings.length === 0 ? (
        <p className="muted">{empty}</p>
      ) : (
        findings.map((finding) => (
          <FindingCard
            key={finding.id}
            finding={finding}
            compact={compact}
            onChip={onChip}
            onApplyFilter={onApplyFilter}
          />
        ))
      )}
    </Section>
  );
}

function Body({
  report,
  onChip,
  onApplyFilter,
}: {
  report: CoachReport;
  onChip: (trade: Evidence) => void;
  onApplyFilter: (finding: CoachFinding) => void;
}) {
  const setRoute = useUi((state) => state.setRoute);
  const reset = useFilters((state) => state.reset);
  if (report.status === "empty") {
    return (
      <div className="coach-state" role="status">
        <h3>No trades to review</h3>
        <p className="muted">There are no trades in this selection.</p>
        <div className="row-actions">
          <button type="button" className="btn" onClick={reset}>
            Clear filters
          </button>
          <button type="button" className="btn btn-primary" onClick={() => setRoute("import")}>
            Import a file
          </button>
        </div>
      </div>
    );
  }
  if (report.status === "too_few_trades") {
    return (
      <div className="coach-state" role="status">
        <h3>Not enough trades yet</h3>
        <p>{report.verdict.lines[0]}</p>
        <p className="muted">
          Nothing is tested below 30 trades, because a small sample makes almost any pattern look
          real. Import more history, then run the report again.
        </p>
        <div className="row-actions">
          <button type="button" className="btn btn-primary" onClick={() => setRoute("import")}>
            Import more trades
          </button>
        </div>
      </div>
    );
  }
  const change = report.change_vs_previous;
  return (
    <>
      <Verdict report={report} />
      <Findings
        title="Top leaks"
        empty="No leak cleared the false-discovery filter. That means none is proven, not that none exists."
        findings={report.top_leaks}
        onChip={onChip}
        onApplyFilter={onApplyFilter}
      />
      <Findings
        title="Top strengths"
        empty="No strength cleared the false-discovery filter yet."
        findings={report.top_strengths}
        onChip={onChip}
        onApplyFilter={onApplyFilter}
      />
      <Findings
        title="Behavior patterns"
        empty="No behavior patterns were measured."
        findings={report.behavior_patterns}
        compact
        onChip={onChip}
        onApplyFilter={onApplyFilter}
      />
      <Section title="Risk review">
        <dl className="coach-risk">
          {report.risk_review.map((item) => (
            <div key={item.key}>
              <dt>{item.title}</dt>
              <dd>{item.figure.display}</dd>
              <dd className="muted">{item.note}</dd>
            </div>
          ))}
        </dl>
      </Section>
      <Section title="7-day action plan">
        <ol className="coach-plan">
          {report.action_plan.map((day) => (
            <li key={day.day}>
              <strong>Day {day.day}: {day.focus}.</strong> {day.task}
            </li>
          ))}
        </ol>
      </Section>
      <Section title="Pre-trade checklist">
        <ul className="coach-checklist">
          {report.checklist.map((item) => (
            <li key={item.question}>
              <strong>{item.question}</strong> <span className="muted">{item.reason}</span>
            </li>
          ))}
        </ul>
      </Section>
      {change && (
        <Section title="Change since the previous report">
          <table className="coach-change">
            <thead>
              <tr>
                <th scope="col">Measure</th>
                <th scope="col">Before</th>
                <th scope="col">Now</th>
              </tr>
            </thead>
            <tbody>
              {change.metrics.map((item) => (
                <tr key={item.key}>
                  <th scope="row">{item.label}</th>
                  <td>{item.previous.display}</td>
                  <td>{item.current.display}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {change.new_finding_ids.length > 0 && <p className="muted">New: {change.new_finding_ids.join(", ")}</p>}
          {change.resolved_finding_ids.length > 0 && (
            <p className="muted">No longer ranked: {change.resolved_finding_ids.join(", ")}</p>
          )}
        </Section>
      )}
      {report.low_confidence_leads.length > 0 && (
        <details className="coach-leads">
          <summary>Low-confidence leads ({report.low_confidence_leads.length})</summary>
          <p className="muted">
            These did not clear the false-discovery filter. Treat them as questions to test, not findings.
          </p>
          {report.low_confidence_leads.map((finding) => (
            <FindingCard key={finding.id} finding={finding} compact onChip={onChip} onApplyFilter={onApplyFilter} />
          ))}
        </details>
      )}
      <Section title="Data caveats">
        <ul>
          {report.caveats.map((caveat) => (
            <li key={caveat.text}>{caveat.text}</li>
          ))}
        </ul>
      </Section>
    </>
  );
}

function Resizer() {
  const width = useUi((state) => state.coachWidth);
  const setWidth = useUi((state) => state.setCoachWidth);
  const onPointerDown = (event: PointerEvent<HTMLDivElement>) => {
    event.currentTarget.setPointerCapture(event.pointerId);
  };
  const onPointerMove = (event: PointerEvent<HTMLDivElement>) => {
    if (!event.currentTarget.hasPointerCapture(event.pointerId)) return;
    setWidth(window.innerWidth - event.clientX);
  };
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "ArrowLeft") setWidth(width + KEY_STEP);
    else if (event.key === "ArrowRight") setWidth(width - KEY_STEP);
    else return;
    event.preventDefault();
  };
  return (
    <div
      className="coach-resize"
      role="separator"
      aria-orientation="vertical"
      aria-label="Resize the Coach panel"
      aria-valuenow={width}
      aria-valuemin={COACH_MIN_WIDTH}
      aria-valuemax={900}
      tabIndex={0}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onKeyDown={onKeyDown}
    />
  );
}

/** The Coach, docked on the right. It runs when opened, when filters change, and after an import. */
export function CoachDrawer() {
  const open = useUi((state) => state.coachOpen);
  const width = useUi((state) => state.coachWidth);
  const setOpen = useUi((state) => state.setCoachOpen);
  const runToken = useUi((state) => state.coachRunToken);
  const setRoute = useUi((state) => state.setRoute);
  const highlightTrade = useUi((state) => state.highlightTrade);
  const setSelection = useUi((state) => state.setSelection);
  const selectFinding = useSelectFinding();
  const liveParams = useFilters((state) => filterParams(state));
  const params = useDebouncedValue(liveParams, FILTER_DEBOUNCE_MS);
  const run: CoachRun = useCoachRun(params, runToken, open);

  // The rest of the layout makes room for the drawer through this variable.
  useEffect(() => {
    document.documentElement.style.setProperty("--coach-offset", open ? `${width}px` : "0px");
  }, [open, width]);

  useEffect(() => {
    if (!open) return undefined;
    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape" && !document.querySelector(".drawer")) setOpen(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, setOpen]);

  if (!open) return null;

  const showTrade = (trade: Evidence) => {
    setRoute("trades");
    highlightTrade(trade.trade_key);
  };
  const applyFilter = (finding: CoachFinding) => {
    const hint = finding.filter;
    if (!hint) {
      // The app's filters cannot express this finding (an hour, a behavior). Show the exact
      // trades it was measured on instead.
      selectFinding.mutate(finding.id, {
        onSuccess: (result) => {
          setSelection({ id: result.selection_id, count: result.count, label: finding.title });
          setRoute("trades");
        },
      });
      return;
    }
    setSelection(null);
    // Narrow the view the report was built for. Dates, accounts, and anything else the finding
    // does not name stay as they are, so the table shows the finding's own trades.
    const current = useFilters.getState();
    current.set({
      symbols: hint.symbols.length > 0 ? hint.symbols : current.symbols,
      setups: hint.setups.length > 0 ? hint.setups : current.setups,
      sides: hint.sides.length > 0 ? hint.sides : current.sides,
      accounts: hint.accounts.length > 0 ? hint.accounts : current.accounts,
      tag: hint.tag ?? current.tag,
    });
    setRoute("trades");
  };
  const reportId = run.report?.report_id;

  return (
    <aside
      className="coach-drawer glass"
      role="complementary"
      aria-label="Coach"
      style={{ width }}
      data-phase={run.phase}
    >
      <Resizer />
      {selectFinding.isError && (
        <p role="alert" className="muted">
          Could not open those trades: {selectFinding.error.message}
        </p>
      )}
      <header className="coach-head">
        <div>
          <p className="eyebrow">Coach</p>
          <h2>Review of your trades</h2>
        </div>
        <div className="coach-actions">
          <button type="button" className="btn btn-quiet" onClick={run.rerun} disabled={run.phase === "running"}>
            Run again
          </button>
          {reportId && (
            <>
              <a className="btn btn-quiet" href={`${apiBase()}/api/coach/reports/${reportId}/export?format=md`} download>
                Markdown
              </a>
              <a
                className="btn btn-quiet"
                href={`${apiBase()}/api/coach/reports/${reportId}/export?format=html`}
                target="_blank"
                rel="noreferrer"
              >
                Print view
              </a>
            </>
          )}
          <button type="button" className="btn btn-quiet" onClick={() => setOpen(false)}>
            Close
          </button>
        </div>
      </header>
      <div className={`pulse-bar coach-pulse`} data-busy={run.phase === "running" ? "true" : "false"} aria-hidden="true" />
      <Timeline steps={run.steps} />
      {run.phase === "error" && (
        <div className="coach-state" role="alert">
          <h3>The Coach could not finish</h3>
          <p className="muted">{run.error}</p>
          <button type="button" className="btn" onClick={run.rerun}>
            Try again
          </button>
        </div>
      )}
      {run.phase === "ready" && run.report && (
        <div className="coach-body">
          <p className="muted">
            {run.report.sample_trades.display} trades. Built in {run.report.seconds_to_build.toFixed(2)} s. The
            report follows the filters above. Past performance review only, not financial advice.
          </p>
          <Body report={run.report} onChip={showTrade} onApplyFilter={applyFilter} />
        </div>
      )}
    </aside>
  );
}
