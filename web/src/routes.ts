export type Route =
  | "dashboard"
  | "analytics"
  | "behavior"
  | "simulator"
  | "trades"
  | "import"
  | "samples"
  | "settings";

export const ROUTE_LABELS: Record<Route, string> = {
  dashboard: "Dashboard",
  analytics: "Analytics",
  behavior: "Behavior",
  simulator: "Simulator",
  trades: "Trades",
  import: "Import",
  samples: "Sample files",
  settings: "Settings",
};