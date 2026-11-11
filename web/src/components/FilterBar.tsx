import { hasActiveFilters, useFilters, type FilterValues } from "../state/filters";

type ListKey = "accounts" | "symbols" | "setups" | "sides";

interface FilterBarProps {
  options: {
    accounts: string[];
    symbols: string[];
    setups: string[];
    sides: string[];
  };
}

const LIST_LABELS: Record<ListKey, string> = {
  accounts: "account",
  symbols: "symbol",
  setups: "setup",
  sides: "side",
};

export function FilterBar({ options }: FilterBarProps) {
  const values = useFilters((state) => state);
  const set = useFilters((state) => state.set);
  const reset = useFilters((state) => state.reset);

  const addValue = (key: ListKey, value: string) => {
    if (!value) return;
    const current = values[key];
    if (current.includes(value)) return;
    set({ [key]: [...current, value] } as Partial<FilterValues>);
  };

  const removeValue = (key: ListKey, value: string) => {
    set({ [key]: values[key].filter((item) => item !== value) } as Partial<FilterValues>);
  };

  return (
    <div className="filter-bar" role="group" aria-label="Filters">
      <label className="filter-date">
        <span className="visually-hidden">From date</span>
        <input
          type="date"
          value={values.dateFrom ?? ""}
          max={values.dateTo ?? undefined}
          onChange={(event) => set({ dateFrom: event.target.value || null })}
          aria-label="From date"
        />
      </label>
      <label className="filter-date">
        <span className="visually-hidden">To date</span>
        <input
          type="date"
          value={values.dateTo ?? ""}
          min={values.dateFrom ?? undefined}
          onChange={(event) => set({ dateTo: event.target.value || null })}
          aria-label="To date"
        />
      </label>
      {(Object.keys(LIST_LABELS) as ListKey[]).map((key) => {
        const available = options[key].filter((item) => !values[key].includes(item));
        if (options[key].length === 0) return null;
        return (
          <div className="filter-group" key={key}>
            <select
              aria-label={`Add ${LIST_LABELS[key]} filter`}
              value=""
              onChange={(event) => addValue(key, event.target.value)}
            >
              <option value="">{`+ ${LIST_LABELS[key]}`}</option>
              {available.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
            {values[key].map((item) => (
              <button
                type="button"
                key={item}
                className="chip chip-button"
                onClick={() => removeValue(key, item)}
                aria-label={`Remove ${LIST_LABELS[key]} filter ${item}`}
              >
                {item}
              </button>
            ))}
          </div>
        );
      })}
      <input
        className="filter-tag"
        type="search"
        placeholder="Tag or emotion"
        aria-label="Tag or emotion filter"
        value={values.tag ?? ""}
        onChange={(event) => set({ tag: event.target.value.trim() || null })}
      />
      {hasActiveFilters(values) && (
        <button type="button" className="btn btn-quiet" onClick={reset}>
          Clear
        </button>
      )}
    </div>
  );
}
