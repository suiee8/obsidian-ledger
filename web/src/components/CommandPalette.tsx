import { Command } from "cmdk";

import { ROUTE_LABELS, type Route } from "../routes";
import { useUi } from "../state/ui";

type CommandPaletteProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onNavigate: (route: Route) => void;
  onToggleColorBlind: () => void;
  onRefresh: () => void;
  onClearFilters: () => void;
  onOpenCoach: () => void;
};

const ROUTES: readonly Route[] = [
  "dashboard",
  "analytics",
  "behavior",
  "simulator",
  "trades",
  "import",
  "samples",
  "settings",
];

export function CommandPalette({
  open,
  onOpenChange,
  onNavigate,
  onToggleColorBlind,
  onRefresh,
  onClearFilters,
  onOpenCoach,
}: CommandPaletteProps) {
  const backgroundPaused = useUi((state) => state.backgroundPaused);
  const toggleBackground = useUi((state) => state.toggleBackgroundPaused);
  const run = (action: () => void) => () => {
    action();
    onOpenChange(false);
  };

  return (
    <Command.Dialog open={open} onOpenChange={onOpenChange} label="Command palette">
      <Command.Input placeholder="Jump to a screen or change the view" />
      <Command.List>
        <Command.Empty>No matches.</Command.Empty>
        <Command.Group heading="Go">
          {ROUTES.map((route) => (
            <Command.Item key={route} onSelect={run(() => onNavigate(route))}>
              {ROUTE_LABELS[route]}
            </Command.Item>
          ))}
        </Command.Group>
        <Command.Group heading="Coach">
          <Command.Item onSelect={run(onOpenCoach)}>Open the Coach report</Command.Item>
        </Command.Group>
        <Command.Group heading="View">
          <Command.Item onSelect={run(onToggleColorBlind)}>Toggle color-blind colors</Command.Item>
          <Command.Item onSelect={run(toggleBackground)}>
            {backgroundPaused ? "Play background" : "Pause background"}
          </Command.Item>
          <Command.Item onSelect={run(onClearFilters)}>Clear all filters</Command.Item>
          <Command.Item onSelect={run(onRefresh)}>Recheck the local API</Command.Item>
        </Command.Group>
      </Command.List>
    </Command.Dialog>
  );
}
