import { hasActiveFilters, useFilters, type FilterValues } from "../state/filters";

type ListKey = "accounts" | "symbols" | "sides";

interface FilterBarProps {
  options: {
    accounts: string[];
    symbols: string[];
    sides: string[];
  };
}

const LIST_LABELS: Record<ListKey, string> = {
  accounts: "account",
  symbols: "symbol",
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
              <option value="">{LIST_LABELS[key]}</option>
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
      {hasActiveFilters(values) && (
        <button type="button" className="btn btn-quiet" onClick={reset}>
          Clear
        </button>
      )}
    </div>
  );
}
