import { create } from "zustand";

import type { Route } from "../routes";
import { initialBackgroundPaused } from "../shader/white";

const COLOR_BLIND_KEY = "ledger.colorBlind";
const COLUMNS_KEY = "ledger.columns";
const COACH_WIDTH_KEY = "ledger.coachWidth";

export const COACH_MIN_WIDTH = 360;
export const COACH_DEFAULT_WIDTH = 460;

/** Keep the drawer wide enough to read and narrow enough to leave room for the screen. */
export function clampCoachWidth(width: number, viewport: number): number {
  const max = Math.max(COACH_MIN_WIDTH, Math.min(900, viewport - 160));
  return Math.round(Math.min(max, Math.max(COACH_MIN_WIDTH, width)));
}

function readCoachWidth(): number {
  try {
    const raw = Number(window.localStorage.getItem(COACH_WIDTH_KEY));
    return Number.isFinite(raw) && raw > 0 ? raw : COACH_DEFAULT_WIDTH;
  } catch {
    return COACH_DEFAULT_WIDTH;
  }
}

export const TRADE_COLUMNS = [
  "exit_time",
  "symbol",
  "side",
  "setup",
  "qty",
  "net_pnl_base",
  "r_multiple",
  "holding_seconds",
  "notes",
  "tags",
  "emotion",
  "confidence",
] as const;

export type TradeColumn = (typeof TRADE_COLUMNS)[number];
export type EditableField = "notes" | "tags" | "emotion" | "confidence";

export interface UndoEntry {
  tradeKey: string;
  field: EditableField;
  previous: string | null;
}

export const BACKGROUND_PAUSED_KEY = "ledger.backgroundPaused";

function readBackgroundPaused(): boolean {
  let stored: string | null = null;
  let reduced = false;
  try {
    stored = window.localStorage.getItem(BACKGROUND_PAUSED_KEY);
  } catch {
    stored = null;
  }
  try {
    reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  } catch {
    reduced = false;
  }
  return initialBackgroundPaused(stored, reduced);
}

export function applyBackgroundPaused(paused: boolean): void {
  if (typeof document === "undefined") return;
  document.documentElement.dataset.background = paused ? "paused" : "on";
}

function readColorBlind(): boolean {
  try {
    return window.localStorage.getItem(COLOR_BLIND_KEY) === "true";
  } catch {
    return false;
  }
}

function readColumns(): TradeColumn[] {
  try {
    const raw = window.localStorage.getItem(COLUMNS_KEY);
    if (!raw) return [...TRADE_COLUMNS];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [...TRADE_COLUMNS];
    const allowed = new Set<string>(TRADE_COLUMNS);
    const chosen = parsed.filter((item): item is TradeColumn => typeof item === "string" && allowed.has(item));
    return chosen.length > 0 ? chosen : [...TRADE_COLUMNS];
  } catch {
    return [...TRADE_COLUMNS];
  }
}

export function applyColorBlind(enabled: boolean): void {
  document.documentElement.dataset.cb = enabled ? "true" : "false";
}

/** Trades picked by brushing a chart, shown by the Trades table until cleared. */
export interface TradeSelection {
  id: string;
  count: number;
  label: string;
}

interface UiStore {
  route: Route;
  paletteOpen: boolean;
  colorBlind: boolean;
  /** True when the animated background is paused. Saved locally. */
  backgroundPaused: boolean;
  toggleBackgroundPaused: () => void;
  columns: TradeColumn[];
  selectedTradeKey: string | null;
  undo: UndoEntry | null;
  coachOpen: boolean;
  coachWidth: number;
  /** Bumped to ask the Coach drawer to run a report, for example after an import. */
  coachRunToken: number;
  /** The trade a Coach chip asked the Trades table to scroll to and highlight. */
  highlightTradeKey: string | null;
  selection: TradeSelection | null;
  setSelection: (selection: TradeSelection | null) => void;
  setCoachOpen: (open: boolean) => void;
  setCoachWidth: (width: number) => void;
  requestCoachRun: () => void;
  highlightTrade: (key: string | null) => void;
  setRoute: (route: Route) => void;
  setPaletteOpen: (open: boolean) => void;
  toggleColorBlind: () => void;
  setColumns: (columns: TradeColumn[]) => void;
  selectTrade: (key: string | null) => void;
  setUndo: (entry: UndoEntry | null) => void;
}

export const useUi = create<UiStore>()((set, get) => ({
  route: "dashboard",
  paletteOpen: false,
  colorBlind: readColorBlind(),
  backgroundPaused: readBackgroundPaused(),
  toggleBackgroundPaused: () => {
    const next = !get().backgroundPaused;
    try {
      window.localStorage.setItem(BACKGROUND_PAUSED_KEY, String(next));
    } catch {
      // The choice still applies for this session.
    }
    applyBackgroundPaused(next);
    set({ backgroundPaused: next });
  },
  columns: readColumns(),
  selectedTradeKey: null,
  undo: null,
  coachOpen: false,
  coachWidth: readCoachWidth(),
  coachRunToken: 0,
  highlightTradeKey: null,
  selection: null,
  setSelection: (selection) => set({ selection }),
  setCoachOpen: (open) => set({ coachOpen: open }),
  setCoachWidth: (width) => {
    const next = clampCoachWidth(width, window.innerWidth);
    try {
      window.localStorage.setItem(COACH_WIDTH_KEY, String(next));
    } catch {
      // Keep the width for this session.
    }
    set({ coachWidth: next });
  },
  requestCoachRun: () => set({ coachOpen: true, coachRunToken: get().coachRunToken + 1 }),
  highlightTrade: (key) => set({ highlightTradeKey: key }),
  setRoute: (route) => set({ route, selectedTradeKey: null, highlightTradeKey: null }),
  setPaletteOpen: (open) => set({ paletteOpen: open }),
  toggleColorBlind: () => {
    const next = !get().colorBlind;
    try {
      window.localStorage.setItem(COLOR_BLIND_KEY, String(next));
    } catch {
      // Storage can be unavailable. The setting still applies for this session.
    }
    applyColorBlind(next);
    set({ colorBlind: next });
  },
  setColumns: (columns) => {
    const chosen = columns.length > 0 ? columns : [...TRADE_COLUMNS];
    try {
      window.localStorage.setItem(COLUMNS_KEY, JSON.stringify(chosen));
    } catch {
      // Same as above: keep the choice in memory.
    }
    set({ columns: chosen });
  },
  selectTrade: (key) => set({ selectedTradeKey: key }),
  setUndo: (entry) => set({ undo: entry }),
}));
