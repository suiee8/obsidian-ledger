import { create } from "zustand";

export interface FilterValues {
  dateFrom: string | null;
  dateTo: string | null;
  accounts: string[];
  symbols: string[];
  setups: string[];
  sides: string[];
  tag: string | null;
}

/** Milliseconds a filter must stay unchanged before screens request new data. */
export const FILTER_DEBOUNCE_MS = 250;

export const EMPTY_FILTERS: FilterValues = {
  dateFrom: null,
  dateTo: null,
  accounts: [],
  symbols: [],
  setups: [],
  sides: [],
  tag: null,
};

/** The filter query string the API expects. Every value is a separate parameter. */
export function filterParams(values: FilterValues): string {
  const params = new URLSearchParams();
  if (values.dateFrom) params.set("date_from", values.dateFrom);
  if (values.dateTo) params.set("date_to", values.dateTo);
  for (const account of values.accounts) params.append("account", account);
  for (const symbol of values.symbols) params.append("symbol", symbol);
  for (const setup of values.setups) params.append("setup", setup);
  for (const side of values.sides) params.append("side", side);
  if (values.tag) params.set("tag", values.tag);
  return params.toString();
}

/** The same filters as a JSON body, for endpoints that take POST. */
export function filtersBody(values: FilterValues) {
  return {
    date_from: values.dateFrom,
    date_to: values.dateTo,
    accounts: values.accounts,
    symbols: values.symbols,
    setups: values.setups,
    sides: values.sides,
    tag: values.tag,
  };
}

export function hasActiveFilters(values: FilterValues): boolean {
  return filterParams(values) !== "";
}

interface FilterStore extends FilterValues {
  set: (patch: Partial<FilterValues>) => void;
  reset: () => void;
  toParams: () => string;
}

export const useFilters = create<FilterStore>()((set, get) => ({
  ...EMPTY_FILTERS,
  set: (patch) => set(patch),
  reset: () => set(EMPTY_FILTERS),
  toParams: () => filterParams(get()),
}));
