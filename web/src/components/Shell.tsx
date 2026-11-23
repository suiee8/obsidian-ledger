import { lazy, Suspense, useEffect, useState, type MouseEvent, type ReactNode } from "react";

import { AgentPresence, type AgentActivity } from "./AgentPresence";
import { CursorEffects } from "./CursorEffects";
import { FlipBrand, LiquidFilter, SocialFooter } from "./ShellEffects";
import { ROUTE_LABELS, type Route } from "../routes";
import {
  IconAnalytics,
  IconBehavior,
  IconImport,
  IconOverview,
  IconSettings,
  IconSimulator,
  IconTrades,
} from "./icons";

const GlyphFieldBackground = lazy(() => import("./GlyphFieldBackground"));
const SapphireAurora = lazy(() => import("../shader/SapphireAurora"));

type ShellProps = {
  route: Route;
  busy: boolean;
  agentState: AgentActivity;
  onNavigate: (route: Route) => void;
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
  { id: "settings", icon: <IconSettings /> },
];

const LIQUID_CONTROL = ".rail-button, .coach-toggle, .health-badge, .filters-toggle, .filter-bar button";

function animateShellClick(event: MouseEvent<HTMLElement>) {
  if (matchMedia("(prefers-reduced-motion: reduce)").matches || !(event.target instanceof Element)) return;
  const button = event.target.closest<HTMLButtonElement>(LIQUID_CONTROL);
  if (!button || !event.currentTarget.contains(button) || button.disabled) return;

  const bounds = button.getBoundingClientRect();
  const x = event.detail ? event.clientX - bounds.left : bounds.width / 2;
  const y = event.detail ? event.clientY - bounds.top : bounds.height / 2;
  const radius = Math.hypot(Math.max(x, bounds.width - x), Math.max(y, bounds.height - y));
  button.style.setProperty("--liquid-x", `${x}px`);
  button.style.setProperty("--liquid-y", `${y}px`);
  button.style.setProperty("--liquid-radius", `${radius}px`);

  const running = button.getAnimations({ subtree: true }).find(
    (animation) => animation instanceof CSSAnimation && animation.animationName === "shell-liquid-click",
  );
  if (running) {
    running.currentTime = 0;
    return;
  }

  button.dataset.liquidClick = "";
  button.addEventListener("animationend", function clearClick(animation) {
    if (animation.animationName !== "shell-liquid-click") return;
    delete button.dataset.liquidClick;
    button.removeEventListener("animationend", clearClick);
  });
}

export function Shell({
  route,
  busy,
  agentState,
  onNavigate,
  coachOpen,
  onToggleCoach,
  filters,
  status,
  children,
}: ShellProps) {
  const [shaderReady, setShaderReady] = useState(false);

  useEffect(() => {
    const timer = window.setTimeout(() => setShaderReady(true), 0);
    return () => window.clearTimeout(timer);
  }, []);

  return (
    <div className="shell" data-route={route} data-coach-open={coachOpen ? "true" : "false"}>
      <CursorEffects />
      <LiquidFilter />
      <a className="skip-link" href="#content">
        Skip to content
      </a>
      <div className={`pulse-bar${busy ? " is-busy" : ""}`} data-busy={busy ? "true" : "false"} />
      <header className="topbar" onClickCapture={animateShellClick}>
        <p className="brand">
          <span className="mark" aria-hidden="true" />
          <FlipBrand />
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
        </div>
      </header>
      <nav className="rail" aria-label="Primary" onClickCapture={animateShellClick}>
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
        {shaderReady && (
          <div className="shell-ambient" aria-hidden="true">
            <Suspense fallback={<div className="aurora-layer" />}>
              <SapphireAurora />
            </Suspense>
          </div>
        )}
        {shaderReady && (
          <Suspense fallback={null}>
            <GlyphFieldBackground />
          </Suspense>
        )}
        {children}
      </main>
      <SocialFooter />
    </div>
  );
}
