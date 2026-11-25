import { lazy, Suspense, useEffect } from "react";
import { useIsFetching } from "@tanstack/react-query";

import { CoachDrawer } from "./components/coach/CoachDrawer";
import { FilterBar } from "./components/FilterBar";
import { FilterSlot } from "./components/FilterSheet";
import { HealthBadge } from "./components/HealthBadge";
import { Shell } from "./components/Shell";
import { useImportSession } from "./lib/import-session";
import { useFilterOptions } from "./lib/queries";
import { useHealth } from "./lib/useHealth";
import { useUi, applyColorBlind } from "./state/ui";

const DashboardScreen = lazy(() => import("./screens/Dashboard"));
const AnalyticsScreen = lazy(() => import("./screens/Analytics"));
const BehaviorScreen = lazy(() => import("./screens/Behavior"));
const SimulatorScreen = lazy(() => import("./screens/Simulator"));
const SettingsScreen = lazy(() => import("./screens/Settings"));
const TradesScreen = lazy(() => import("./screens/Trades"));
const ImportScreen = lazy(() => import("./screens/Import"));

const ImportNotice = lazy(() => import("./screens/Import").then((module) => ({ default: module.ImportNotice })));

const EMPTY_OPTIONS = { accounts: [], symbols: [], setups: [], sides: [] };

function ScreenFallback() {
  return (
    <div className="dashboard" aria-busy="true" aria-label="Loading screen">
      <div className="glass panel skeleton skeleton-tall" />
    </div>
  );
}

export function App() {
  const hasImportNotice = useImportSession((state) => state.files.length > 0);
  const route = useUi((state) => state.route);
  const setRoute = useUi((state) => state.setRoute);
  const colorBlind = useUi((state) => state.colorBlind);
  const coachOpen = useUi((state) => state.coachOpen);
  const setCoachOpen = useUi((state) => state.setCoachOpen);
  const health = useHealth();
  const options = useFilterOptions();
  const fetching = useIsFetching() > 0;
  useEffect(() => {
    applyColorBlind(colorBlind);
  }, [colorBlind]);

  const screen =
    route === "dashboard" ? (
      <DashboardScreen />
    ) : route === "analytics" ? (
      <AnalyticsScreen />
    ) : route === "behavior" ? (
      <BehaviorScreen />
    ) : route === "simulator" ? (
      <SimulatorScreen />
    ) : route === "settings" ? (
      <SettingsScreen />
    ) : route === "trades" ? (
      <TradesScreen />
    ) : (
      <ImportScreen />
    );

  return (
    <>
      <Shell
        route={route}
        busy={fetching || health.state.status === "loading"}
        onNavigate={setRoute}
        coachOpen={coachOpen}
        onToggleCoach={() => setCoachOpen(!coachOpen)}
        filters={
          <FilterSlot>
            <FilterBar options={options.data ?? EMPTY_OPTIONS} />
          </FilterSlot>
        }
        status={<HealthBadge state={health.state} onRecheck={health.refresh} />}
      >
        {route === "dashboard" && hasImportNotice && <Suspense fallback={null}><ImportNotice /></Suspense>}
        <Suspense fallback={<ScreenFallback />}>{screen}</Suspense>
      </Shell>
      <CoachDrawer />
    </>
  );
}
