import type { HealthState } from "../lib/useHealth";

interface HealthBadgeProps {
  state: HealthState;
  onRecheck: () => void;
}

/** Local API status in the top bar. Clicking it checks again. */
export function HealthBadge({ state, onRecheck }: HealthBadgeProps) {
  const tone = state.status === "online" ? "ok" : state.status === "offline" ? "warn" : "dim";
  const label =
    state.status === "online"
      ? "Local API online"
      : state.status === "offline"
        ? "Local API offline"
        : "Checking local API";
  return (
    <button type="button" className="health-badge" onClick={onRecheck} aria-label={label} title={label}>
      <span className={`status-dot ${tone}`} aria-hidden="true" />
      <span className="health-text">{state.status === "online" ? "online" : state.status === "offline" ? "offline" : "…"}</span>
    </button>
  );
}
