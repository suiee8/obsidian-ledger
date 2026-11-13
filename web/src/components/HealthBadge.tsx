import type { HealthState } from "../lib/useHealth";

interface HealthBadgeProps {
  state: HealthState;
  onRecheck: () => void;
}

/** Local API status in the top bar. Clicking it checks again. */
export function HealthBadge({ state, onRecheck }: HealthBadgeProps) {
  const tone =
    state.status === "online"
      ? "ok"
      : state.status === "offline" || state.status === "degraded"
        ? "warn"
        : "dim";
  const labels = {
    online: "Local API online",
    offline: "Local API offline; displayed data may be stale",
    degraded: "Local API degraded",
    "ai-unavailable": "AI unavailable; deterministic Coach remains available",
    "version-mismatch": "API version mismatch; restart the local app",
    loading: "Checking local API",
  } as const;
  const label = labels[state.status];
  const text = {
    online: "online",
    offline: "offline · stale",
    degraded: "degraded",
    "ai-unavailable": "AI unavailable",
    "version-mismatch": "version mismatch",
    loading: "…",
  } as const;
  return (
    <button type="button" className="health-badge" onClick={onRecheck} aria-label={label} title={label}>
      <span className={`status-dot ${tone}`} aria-hidden="true" />
      <span className="health-text">{text[state.status]}</span>
    </button>
  );
}
