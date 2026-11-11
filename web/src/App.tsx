import { lazy, Suspense, useEffect } from "react";
import { useIsFetching } from "@tanstack/react-query";

import { CoachDrawer } from "./components/coach/CoachDrawer";
import { CommandPalette } from "./components/CommandPalette";
import { FilterBar } from "./components/FilterBar";
import { FilterSlot } from "./components/FilterSheet";
import { HealthBadge } from "./components/HealthBadge";
import { Shell } from "./components/Shell";
import { useFilterOptions } from "./lib/queries";
import { useHealth } from "./lib/useHealth";
import { useUi, applyColorBlind } from "./state/ui";
import { useFilters } from "./state/filters";

const DashboardScreen = lazy(() => import("./screens/Dashboard"));
const AnalyticsScreen = lazy(() => import("./screens/Analytics"));
const BehaviorScreen = lazy(() => import("./screens/Behavior"));
const SimulatorScreen = lazy(() => import("./screens/Simulator"));
const SettingsScreen = lazy(() => import("./screens/Settings"));
const TradesScreen = lazy(() => import("./screens/Trades"));
const ImportScreen = lazy(() => import("./screens/Import"));
const SamplesScreen = lazy(() => import("./screens/Samples"));

const EMPTY_OPTIONS = { accounts: [], symbols: [], setups: [], sides: [] };

function ScreenFallback() {
  return (
    <div className="dashboard" aria-busy="true" aria-label="Loading screen">
      <div className="glass panel skeleton skeleton-tall" />
    </div>
  );
}

export function App() {
  const route = useUi((state) => state.route);
  const setRoute = useUi((state) => state.setRoute);
  const paletteOpen = useUi((state) => state.paletteOpen);
  const setPaletteOpen = useUi((state) => state.setPaletteOpen);
  const colorBlind = useUi((state) => state.colorBlind);
  const toggleColorBlind = useUi((state) => state.toggleColorBlind);
  const coachOpen = useUi((state) => state.coachOpen);
  const setCoachOpen = useUi((state) => state.setCoachOpen);
  const resetFilters = useFilters((state) => state.reset);
  const health = useHealth();
  const options = useFilterOptions();
  const fetching = useIsFetching() > 0;

  useEffect(() => {
    applyColorBlind(colorBlind);
  }, [colorBlind]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen(true);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [setPaletteOpen]);

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
    ) : route === "import" ? (
      <ImportScreen />
    ) : (
      <SamplesScreen />
    );

  return (
    <>
      <Shell
        route={route}
        busy={fetching || health.state.status === "loading"}
        onNavigate={setRoute}
        onOpenPalette={() => setPaletteOpen(true)}
        coachOpen={coachOpen}
        onToggleCoach={() => setCoachOpen(!coachOpen)}
        filters={
          <FilterSlot>
            <FilterBar options={options.data ?? EMPTY_OPTIONS} />
          </FilterSlot>
        }
        status={<HealthBadge state={health.state} onRecheck={health.refresh} />}
      >
        <Suspense fallback={<ScreenFallback />}>{screen}</Suspense>
      </Shell>
      <CoachDrawer />
      <CommandPalette
        open={paletteOpen}
        onOpenChange={setPaletteOpen}
        onNavigate={setRoute}
        onToggleColorBlind={toggleColorBlind}
        onRefresh={health.refresh}
        onClearFilters={resetFilters}
        onOpenCoach={() => setCoachOpen(true)}
      />
    </>
  );
}
