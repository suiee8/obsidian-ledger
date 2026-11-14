import { lazy, Suspense, useEffect, useState, type ReactNode } from "react";

import { AgentPresence, type AgentActivity } from "./AgentPresence";
import { ROUTE_LABELS, type Route } from "../routes";
import { useUi } from "../state/ui";
import {
  IconAnalytics,
  IconBehavior,
  IconImport,
  IconOverview,
  IconPause,
  IconPlay,
  IconSamples,
  IconSettings,
  IconSimulator,
  IconTrades,
} from "./icons";

const SapphireAurora = lazy(() => import("../shader/SapphireAurora"));

type ShellProps = {
  route: Route;
  busy: boolean;
  agentState: AgentActivity;
  onNavigate: (route: Route) => void;
  onOpenPalette: () => void;
  coachOpen: boolean;
  onToggleCoach: () => void;
  filters: ReactNode;
  status: ReactNode;
  children: ReactNode;
};

const NAV: readonly { id: Route; icon: ReactNode }[] = [
  { id: "dashboard", icon: <IconOverview /> },
  { id: "analytics", icon: <IconAnalytics /> },
  { id: "behavior", icon: <IconBehavior /> },
  { id: "simulator", icon: <IconSimulator /> },
  { id: "trades", icon: <IconTrades /> },
  { id: "import", icon: <IconImport /> },
  { id: "samples", icon: <IconSamples /> },
  { id: "settings", icon: <IconSettings /> },
];

export function Shell({
  route,
  busy,
  agentState,
  onNavigate,
  onOpenPalette,
  coachOpen,
  onToggleCoach,
  filters,
  status,
  children,
}: ShellProps) {
  const [shaderReady, setShaderReady] = useState(false);
  const backgroundPaused = useUi((state) => state.backgroundPaused);
  const toggleBackground = useUi((state) => state.toggleBackgroundPaused);

  useEffect(() => {
    const timer = window.setTimeout(() => setShaderReady(true), 0);
    return () => window.clearTimeout(timer);
  }, []);

  return (
    <div className="shell" data-route={route} data-coach-open={coachOpen ? "true" : "false"}>
      {shaderReady && (
        <Suspense fallback={<div className="aurora-layer" aria-hidden="true" />}>
          <SapphireAurora />
        </Suspense>
      )}
      <a className="skip-link" href="#content">
        Skip to content
      </a>
      <div className={`pulse-bar${busy ? " is-busy" : ""}`} data-busy={busy ? "true" : "false"} />
      <header className="topbar">
        <p className="brand">
          <span className="mark" aria-hidden="true" />
          Obsidian Ledger
        </p>
        <div className="topbar-center">{filters}</div>
        <div className="topbar-end">
          {status}
          <AgentPresence state={agentState} />
          <button
            type="button"
            className={`coach-toggle${coachOpen ? " is-open" : ""}`}
            aria-pressed={coachOpen}
            onClick={onToggleCoach}
          >
            Coach
          </button>
          <button
            type="button"
            className="bg-toggle"
            data-testid="background-toggle"
            aria-label="Pause background"
            aria-pressed={backgroundPaused}
            title={backgroundPaused ? "Background paused" : "Pause background"}
            onClick={toggleBackground}
          >
            {backgroundPaused ? <IconPlay /> : <IconPause />}
          </button>
          <button type="button" className="kbd-hint" onClick={onOpenPalette} title="Open command palette">
            Ctrl K
          </button>
        </div>
      </header>
      <nav className="rail" aria-label="Primary">
        {NAV.map((item) => (
          <button
            key={item.id}
            type="button"
            className="rail-button"
            aria-label={ROUTE_LABELS[item.id]}
            title={ROUTE_LABELS[item.id]}
            aria-current={route === item.id ? "page" : undefined}
            onClick={() => onNavigate(item.id)}
          >
            {item.icon}
          </button>
        ))}
      </nav>
      <main className="main" id="content">
        {children}
      </main>
    </div>
  );
}
