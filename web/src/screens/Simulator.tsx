import { useState } from "react";

import { SimulatorOverlay } from "../components/charts/LineBands";
import { Panel } from "../components/Panel";
import { DISCLAIMER } from "../components/ScreenStates";
import { fmtInt, fmtMoney } from "../lib/format";
import {
  EMPTY_RULES,
  hasRules,
  useSimulation,
  type RulesState,
  type Simulation,
} from "../lib/phase4";
import { useFilterOptions } from "../lib/queries";
import { useDebouncedValue } from "../lib/useDebouncedValue";

const RULE_DEBOUNCE_MS = 400;
const HOURS = Array.from({ length: 24 }, (_, hour) => hour);
const SKIP_LABELS: Record<string, string> = {
  symbol: "excluded symbol",
  hour: "excluded hour",
  setup: "excluded setup",
  max_trades: "over the trades-per-day limit",
  losses: "after the losing-trades limit",
  daily_loss: "after the daily loss cap",
};

function NumberRule({
  label,
  hint,
  value,
  onChange,
  integer,
}: {
  label: string;
  hint: string;
  value: number | null;
  onChange: (value: number | null) => void;
  integer?: boolean;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      <input
        type="number"
        min={integer ? 1 : 0}
        step={integer ? 1 : "any"}
        value={value ?? ""}
        placeholder="Off"
        onChange={(event) => {
          const raw = event.target.value;
          const parsed = Number(raw);
          onChange(raw === "" || !Number.isFinite(parsed) || parsed <= 0 ? null : parsed);
        }}
      />
      <small className="muted">{hint}</small>
    </label>
  );
}

function CheckGroup({
  legend,
  options,
  chosen,
  onToggle,
  compact,
}: {
  legend: string;
  options: readonly string[];
  chosen: readonly string[];
  onToggle: (value: string) => void;
  compact?: boolean;
}) {
  return (
    <fieldset className={`check-group${compact ? " check-group-compact" : ""}`}>
      <legend>{legend}</legend>
      {options.length === 0 ? (
        <p className="muted">None in your trades yet.</p>
      ) : (
        <div className="check-list">
          {options.map((option) => (
            <label key={option} className="column-option">
              <input type="checkbox" checked={chosen.includes(option)} onChange={() => onToggle(option)} />
              {option}
            </label>
          ))}
        </div>
      )}
    </fieldset>
  );
}

function toggle<T>(list: readonly T[], value: T): T[] {
  return list.includes(value) ? list.filter((item) => item !== value) : [...list, value];
}

function Overfit({ result }: { result: Simulation | undefined }) {
  const high = result?.overfit?.level === "high";
  return (
    <aside className={`glass overfit${high ? " overfit-high" : ""}`} aria-label="Overfitting warning">
      <p className="overfit-title">
        {high ? "High risk of overfitting" : "Overfitting warning"}
      </p>
      <p>
        {result?.warning ??
          "Rules chosen after looking at the same trades they are tested on tend to look better than they will later. Test them on trades they were not chosen from."}
      </p>
      {result?.overfit && result.overfit.reasons.length > 0 && (
        <ul>
          {result.overfit.reasons.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      )}
    </aside>
  );
}

function Compare({ result }: { result: Simulation }) {
  const { baseline, simulated, change } = result;
  if (!baseline || !simulated || !change) return null;
  return (
    <div className="table-wrap" tabIndex={0} role="region" aria-label="Before and after table">
      <table>
        <thead>
          <tr>
            <th scope="col">Measure</th>
            <th scope="col">Your trades</th>
            <th scope="col">With the rules</th>
            <th scope="col">Change</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <th scope="row">Net P&L</th>
            <td>{fmtMoney(baseline.net_pnl)}</td>
            <td>{fmtMoney(simulated.net_pnl)}</td>
            <td className={change.net_pnl >= 0 ? "tone-profit" : "tone-loss"}>{fmtMoney(change.net_pnl)}</td>
          </tr>
          <tr>
            <th scope="row">Average per trade taken</th>
            <td>{fmtMoney(baseline.expectancy)}</td>
            <td>{fmtMoney(simulated.expectancy)}</td>
            <td>
              {baseline.expectancy !== null && simulated.expectancy !== null
                ? fmtMoney(simulated.expectancy - baseline.expectancy)
                : "—"}
            </td>
          </tr>
          <tr>
            <th scope="row">Largest drawdown</th>
            <td>{fmtMoney(baseline.max_drawdown)}</td>
            <td>{fmtMoney(simulated.max_drawdown)}</td>
            <td>{fmtMoney(simulated.max_drawdown - baseline.max_drawdown)}</td>
          </tr>
          <tr>
            <th scope="row">Trades taken</th>
            <td>{fmtInt(result.trades)}</td>
            <td>{fmtInt(result.kept_trades ?? 0)}</td>
            <td>{fmtInt(-(result.removed_trades ?? 0))}</td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}

function Interval({ fast, ready }: { fast: Simulation; ready: Simulation | undefined }) {
  const change = (ready ?? fast).change;
  if (!change) return null;
  const interval = ready?.change?.expectancy_per_trade_ci95 ?? null;
  const net = ready?.change?.net_pnl_ci95 ?? null;
  const spansZero = interval !== null && interval[0] <= 0 && interval[1] >= 0;
  return (
    <div aria-live="polite" className="interval-note">
      <p>
        Change per trade: <strong>{fmtMoney(change.expectancy_per_trade)}</strong>
        {interval ? (
          <>
            {" "}
            with a 95% interval of {fmtMoney(interval[0])} to {fmtMoney(interval[1])}
            {net ? ` (${fmtMoney(net[0])} to ${fmtMoney(net[1])} over all ${fmtInt(fast.trades)} trades)` : ""}.
          </>
        ) : (
          <span className="muted"> Working out the interval…</span>
        )}
      </p>
      {interval && (
        <p className="muted">
          {spansZero
            ? "The interval includes zero, so this change cannot be told apart from noise."
            : "The interval excludes zero, but see the overfitting warning before relying on it."}
        </p>
      )}
      <p className="card-note">{change.method}</p>
    </div>
  );
}

export default function Simulator() {
  const [rules, setRules] = useState<RulesState>(EMPTY_RULES);
  const options = useFilterOptions();
  const settled = useDebouncedValue(rules, RULE_DEBOUNCE_MS);
  const active = hasRules(settled);
  const { fast, full } = useSimulation(settled, active);
  const patch = (change: Partial<RulesState>) => setRules((current) => ({ ...current, ...change }));

  const result = full.data ?? fast.data;
  const stale = rules !== settled;
  const skipped = Object.entries(result?.skipped_by_reason ?? {});

  return (
    <div className="dashboard">
      <header>
        <h1 className="screen-title">Simulator</h1>
        <p className="lede">
          Replay your own trades under rules you choose and see what would have changed. The point estimate
          appears first. The interval is worked out right after.
        </p>
      </header>
      <div className="bento">
        <Panel title="What-if rules" className="span-4">
          <form className="p4-form" onSubmit={(event) => event.preventDefault()}>
            <NumberRule
              label="Daily loss cap"
              hint="Stop taking trades for the day after losing this much."
              value={rules.daily_loss_cap}
              onChange={(value) => patch({ daily_loss_cap: value })}
            />
            <NumberRule
              label="Most trades per day"
              hint="Skip any trade after this many in a day."
              value={rules.max_trades_per_day}
              integer
              onChange={(value) => patch({ max_trades_per_day: value })}
            />
            <NumberRule
              label="Stop after losing trades"
              hint="Stop for the day after this many losses."
              value={rules.stop_after_losses}
              integer
              onChange={(value) => patch({ stop_after_losses: value })}
            />
            <NumberRule
              label="Cap risk per trade"
              hint="Scale a trade down when its planned risk is above this."
              value={rules.cap_risk_per_trade}
              onChange={(value) => patch({ cap_risk_per_trade: value })}
            />
            <CheckGroup
              legend="Skip these symbols"
              options={options.data?.symbols ?? []}
              chosen={rules.exclude_symbols}
              onToggle={(value) => patch({ exclude_symbols: toggle(rules.exclude_symbols, value) })}
            />
            <CheckGroup
              legend="Skip these setups"
              options={options.data?.setups ?? []}
              chosen={rules.exclude_setups}
              onToggle={(value) => patch({ exclude_setups: toggle(rules.exclude_setups, value) })}
            />
            <CheckGroup
              legend="Skip these entry hours (UTC)"
              options={HOURS.map((hour) => String(hour).padStart(2, "0"))}
              chosen={rules.exclude_hours.map((hour) => String(hour).padStart(2, "0"))}
              compact
              onToggle={(value) => patch({ exclude_hours: toggle(rules.exclude_hours, Number(value)) })}
            />
            <button type="button" className="btn" disabled={!hasRules(rules)} onClick={() => setRules(EMPTY_RULES)}>
              Clear all rules
            </button>
          </form>
        </Panel>
        <div className="span-8 stack">
          <Overfit result={result} />
          <Panel title="Before and after" className="span-12">
            {!active ? (
              <p className="muted">Set at least one rule to replay your trades under it.</p>
            ) : fast.isError ? (
              <p role="alert" className="muted">
                The simulation could not run: {fast.error.message}
              </p>
            ) : !result || result.trades === 0 ? (
              <p className="muted" role="status">
                {fast.isPending || fast.isFetching ? "Replaying your trades…" : "No trades in this selection."}
              </p>
            ) : (
              <>
                <p className="muted" role="status">
                  {stale || fast.isFetching ? "Updating…" : `${fmtInt(result.trades)} trades replayed.`}
                </p>
                <Compare result={result} />
                <Interval fast={fast.data ?? result} ready={full.data} />
                {result.curves && (
                  <SimulatorOverlay
                    x={result.curves.x}
                    baseline={result.curves.baseline}
                    simulated={result.curves.simulated}
                    label="Cumulative P&L of your trades and of the same trades under the rules"
                  />
                )}
                {skipped.length > 0 && (
                  <ul className="caveats" aria-label="Why trades were skipped">
                    {skipped.map(([reason, count]) => (
                      <li key={reason} className="chip">
                        {fmtInt(count)} {SKIP_LABELS[reason] ?? reason}
                      </li>
                    ))}
                    {(result.risk_capped_trades ?? 0) > 0 && (
                      <li className="chip">{fmtInt(result.risk_capped_trades ?? 0)} scaled down by the risk cap</li>
                    )}
                  </ul>
                )}
              </>
            )}
          </Panel>
        </div>
      </div>
      <p className="footer">{DISCLAIMER}</p>
    </div>
  );
}
