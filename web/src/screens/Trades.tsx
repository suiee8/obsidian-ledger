import { memo, useEffect, useMemo, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useVirtualizer } from "@tanstack/react-virtual";

import { useDebouncedValue } from "../lib/useDebouncedValue";
import {
  FILTER_DEBOUNCE_MS,
  filterParams,
  useFilters,
  type FilterValues,
} from "../state/filters";
import { TRADE_COLUMNS, useUi, type EditableField, type TradeColumn } from "../state/ui";
import {
  BLOCK_ROWS,
  useDeleteView,
  useEditTrade,
  useFilterOptions,
  useSaveView,
  useTradeBlocks,
  useViews,
} from "../lib/queries";
import { fmtDateTime, fmtDuration, fmtMoney, fmtR } from "../lib/format";
import { requestJson } from "../lib/api";
import { TradePositionSchema, type TradeRow } from "../lib/schemas";
import { TradeDrawer } from "../components/TradeDrawer";

const ROW_HEIGHT = 40;

const COLUMN_LABELS: Record<TradeColumn, string> = {
  exit_time: "Closed",
  symbol: "Symbol",
  side: "Side",
  setup: "Setup",
  qty: "Qty",
  net_pnl_base: "P&L",
  r_multiple: "R",
  holding_seconds: "Held",
  notes: "Notes",
  tags: "Tags",
  emotion: "Emotion",
  confidence: "Confidence",
};

const COLUMN_WIDTHS: Record<TradeColumn, string> = {
  exit_time: "minmax(150px, 1.4fr)",
  symbol: "minmax(90px, 0.8fr)",
  side: "minmax(60px, 0.5fr)",
  setup: "minmax(100px, 1fr)",
  qty: "minmax(70px, 0.6fr)",
  net_pnl_base: "minmax(100px, 0.9fr)",
  r_multiple: "minmax(80px, 0.6fr)",
  holding_seconds: "minmax(80px, 0.7fr)",
  notes: "minmax(160px, 2fr)",
  tags: "minmax(120px, 1fr)",
  emotion: "minmax(100px, 0.8fr)",
  confidence: "minmax(100px, 0.8fr)",
};

// Server-side sort keys. Columns not listed here cannot be sorted.
const SORT_KEYS: Partial<Record<TradeColumn, string>> = {
  exit_time: "exit_time",
  symbol: "symbol",
  side: "side",
  setup: "setup",
  qty: "qty",
  net_pnl_base: "net_pnl_base",
  r_multiple: "r_multiple",
  holding_seconds: "holding_seconds",
};

const EDITABLE_COLUMNS: ReadonlySet<TradeColumn> = new Set<TradeColumn>([
  "notes",
  "tags",
  "emotion",
  "confidence",
]);

interface UndoEntry {
  tradeKey: string;
  field: EditableField;
  previous: string | null;
}

function cellText(row: TradeRow, column: TradeColumn): string {
  switch (column) {
    case "exit_time":
      return fmtDateTime(row.exit_time);
    case "symbol":
      return row.symbol;
    case "side":
      return row.side;
    case "setup":
      return row.setup ?? "—";
    case "qty":
      return String(row.qty);
    case "net_pnl_base":
      return fmtMoney(row.net_pnl_base);
    case "r_multiple":
      return fmtR(row.r_multiple);
    case "holding_seconds":
      return fmtDuration(row.holding_seconds);
    case "notes":
      return row.notes;
    case "tags":
      return row.tags ?? "";
    case "emotion":
      return row.emotion ?? "";
    case "confidence":
      return row.confidence ?? "";
  }
}

function EditableCell({
  row,
  field,
  onSaved,
}: {
  row: TradeRow;
  field: EditableField;
  onSaved: (entry: UndoEntry) => void;
}) {
  const edit = useEditTrade();
  const current = row[field] ?? "";
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(current);

  const begin = () => {
    setDraft(current);
    setEditing(true);
  };

  const commit = () => {
    setEditing(false);
    if (draft === current) return;
    edit.mutate(
      { tradeKey: row.trade_key, patch: { [field]: draft.trim() === "" ? null : draft } },
      { onSuccess: () => onSaved({ tradeKey: row.trade_key, field, previous: current || null }) },
    );
  };

  if (!editing) {
    return (
      <span
        role="cell"
        className="cell cell-edit"
        tabIndex={0}
        onDoubleClick={begin}
        onKeyDown={(event) => {
          if (event.key === "Enter") begin();
        }}
        title="Double-click or press Enter to edit"
      >
        {current || <span className="muted">—</span>}
      </span>
    );
  }
  return (
    <span role="cell" className="cell">
      <input
        autoFocus
        className="cell-input"
        aria-label={`${field} for ${row.symbol}`}
        value={draft}
        maxLength={field === "notes" ? 5000 : 300}
        onChange={(event) => setDraft(event.target.value)}
        onBlur={commit}
        onKeyDown={(event) => {
          if (event.key === "Enter") commit();
          if (event.key === "Escape") {
            setDraft(current);
            setEditing(false);
          }
        }}
      />
    </span>
  );
}

function snapshotFilters(values: FilterValues): FilterValues {
  return {
    dateFrom: values.dateFrom,
    dateTo: values.dateTo,
    accounts: values.accounts,
    symbols: values.symbols,
    setups: values.setups,
    sides: values.sides,
    tag: values.tag,
  };
}

interface ViewConfig {
  sort: string;
  dir: "asc" | "desc";
  columns: TradeColumn[];
  filters: FilterValues;
}

function readViewConfig(config: Record<string, unknown>): ViewConfig {
  const allowed = new Set<string>(TRADE_COLUMNS);
  const columns = Array.isArray(config.columns)
    ? config.columns.filter((item): item is TradeColumn => typeof item === "string" && allowed.has(item))
    : [];
  const saved = (config.filters ?? {}) as Partial<FilterValues>;
  return {
    sort: typeof config.sort === "string" ? config.sort : "exit_time",
    dir: config.dir === "asc" ? "asc" : "desc",
    columns: columns.length > 0 ? columns : [...TRADE_COLUMNS],
    filters: {
      dateFrom: saved.dateFrom ?? null,
      dateTo: saved.dateTo ?? null,
      accounts: saved.accounts ?? [],
      symbols: saved.symbols ?? [],
      setups: saved.setups ?? [],
      sides: saved.sides ?? [],
      tag: saved.tag ?? null,
    },
  };
}

function ViewControls({
  sort,
  direction,
  onApply,
}: {
  sort: string;
  direction: "asc" | "desc";
  onApply: (config: ViewConfig) => void;
}) {
  const views = useViews();
  const save = useSaveView();
  const remove = useDeleteView();
  const columns = useUi((state) => state.columns);
  const [name, setName] = useState("");
  const [selected, setSelected] = useState("");

  return (
    <div className="views" role="group" aria-label="Saved views">
      <select
        aria-label="Apply a saved view"
        value={selected}
        onChange={(event) => {
          const chosen = event.target.value;
          setSelected(chosen);
          const view = views.data?.find((item) => item.name === chosen);
          if (!view) return;
          const config = readViewConfig(view.config);
          useFilters.getState().set(config.filters);
          onApply(config);
        }}
      >
        <option value="">Saved views</option>
        {views.data?.map((view) => (
          <option key={view.name} value={view.name}>
            {view.name}
          </option>
        ))}
      </select>
      {selected !== "" && (
        <button
          type="button"
          className="btn btn-quiet"
          onClick={() => {
            remove.mutate(selected);
            setSelected("");
          }}
        >
          Delete view
        </button>
      )}
      <input
        aria-label="New view name"
        placeholder="Name this view"
        value={name}
        maxLength={60}
        onChange={(event) => setName(event.target.value)}
      />
      <button
        type="button"
        className="btn"
        disabled={name.trim() === "" || save.isPending}
        onClick={() => {
          const config: ViewConfig = {
            sort,
            dir: direction,
            columns,
            filters: snapshotFilters(useFilters.getState()),
          };
          save.mutate(
            { name: name.trim(), config: { ...config } },
            { onSuccess: () => setName("") },
          );
        }}
      >
        Save view
      </button>
    </div>
  );
}

interface GridRowProps {
  index: number;
  start: number;
  row: TradeRow | undefined;
  columns: TradeColumn[];
  template: string;
  selected: boolean;
  highlighted: boolean;
  onSelect: (tradeKey: string) => void;
  onSaved: (entry: UndoEntry) => void;
}

/** One virtual row. Memoized, so a scroll step re-renders only the rows whose data changed. */
const GridRow = memo(function GridRow({
  index,
  start,
  row,
  columns,
  template,
  selected,
  highlighted,
  onSelect,
  onSaved,
}: GridRowProps) {
  return (
    <div
      role="row"
      aria-rowindex={index + 1}
      className={`grid-row grid-body${selected ? " is-selected" : ""}${highlighted ? " is-highlight" : ""}`}
      data-trade-id={row?.trade_id}
      style={{
        gridTemplateColumns: template,
        transform: `translateY(${start}px)`,
        height: ROW_HEIGHT,
        position: "absolute",
        top: 0,
        left: 0,
        right: 0,
      }}
      onClick={(event) => {
        if (row && !(event.target instanceof HTMLInputElement)) onSelect(row.trade_key);
      }}
      tabIndex={row ? 0 : -1}
      onKeyDown={(event) => {
        // Only the row itself reacts to Enter or Space. Keys typed in an inline editor do not.
        if (!row || event.target !== event.currentTarget) return;
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onSelect(row.trade_key);
        }
      }}
    >
      {row === undefined ? (
        <span role="cell" className="skeleton-line" aria-hidden="true" />
      ) : (
        columns.map((column) =>
          EDITABLE_COLUMNS.has(column) ? (
            <EditableCell
              key={column}
              row={row}
              field={column as EditableField}
              onSaved={onSaved}
            />
          ) : (
            <span
              key={column}
              role="cell"
              className={`cell cell-${column}${
                column === "net_pnl_base" && row.net_pnl_base !== null
                  ? row.net_pnl_base < 0
                    ? " tone-loss"
                    : " tone-profit"
                  : ""
              }`}
            >
              {cellText(row, column)}
            </span>
          ),
        )
      )}
    </div>
  );
});

export default function Trades() {
  const liveParams = useFilters((state) => filterParams(state));
  const filterQuery = useDebouncedValue(liveParams, FILTER_DEBOUNCE_MS);
  const selection = useUi((state) => state.selection);
  const setSelection = useUi((state) => state.setSelection);
  // A brushed selection narrows the table on top of the filters.
  const params = selection
    ? [filterQuery, `selection=${selection.id}`].filter(Boolean).join("&")
    : filterQuery;
  const columns = useUi((state) => state.columns);
  const setColumns = useUi((state) => state.setColumns);
  const selectedKey = useUi((state) => state.selectedTradeKey);
  const selectTrade = useUi((state) => state.selectTrade);
  const undo = useUi((state) => state.undo);
  const setUndo = useUi((state) => state.setUndo);
  const highlightKey = useUi((state) => state.highlightTradeKey);
  const client = useQueryClient();
  const [hiddenNote, setHiddenNote] = useState(false);
  const scrolledFor = useRef("");
  const [sortKey, setSortKey] = useState("exit_time");
  const [direction, setDirection] = useState<"asc" | "desc">("desc");
  const sortParams = `sort=${sortKey}&dir=${direction}`;
  const scrollRef = useRef<HTMLDivElement>(null);
  const filterOptions = useFilterOptions();
  const edit = useEditTrade();

  // Block 0 is always loaded, because it carries the total. Visible rows add their blocks.
  const [loadedTotal, setLoadedTotal] = useState(0);
  const virtualizer = useVirtualizer({
    count: loadedTotal,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 12,
  });
  // The virtualizer object is stable, so the blocks must come from the rows it reports as
  // visible on this render. Keying on the object itself would load block 0 and never another.
  const virtualItems = virtualizer.getVirtualItems();
  const firstBlock = Math.floor((virtualItems[0]?.index ?? 0) / BLOCK_ROWS);
  const lastBlock = Math.floor((virtualItems[virtualItems.length - 1]?.index ?? 0) / BLOCK_ROWS);
  const blocks = useMemo(() => {
    const wanted = new Set([0]);
    for (let block = firstBlock; block <= lastBlock; block += 1) wanted.add(block);
    return [...wanted];
  }, [firstBlock, lastBlock]);
  const pages = useTradeBlocks(params, sortParams, blocks);
  const total = pages[0]?.data?.total ?? 0;

  useEffect(() => {
    setLoadedTotal(total);
  }, [total]);

  // A Coach chip asks for a trade. Find where it sits in the current sort and filters, then scroll
  // to it. A trade the filters hide cannot be shown, and the screen says so.
  useEffect(() => {
    if (!highlightKey || loadedTotal === 0) return undefined;
    const marker = `${highlightKey}|${params}|${sortParams}`;
    if (scrolledFor.current === marker) return undefined;
    let cancelled = false;
    const query = [params, sortParams].filter(Boolean).join("&");
    void client
      .fetchQuery({
        queryKey: ["trade-position", marker],
        queryFn: ({ signal }) =>
          requestJson(`/api/trades/${highlightKey}/position?${query}`, TradePositionSchema, { signal }),
        staleTime: 0,
      })
      .then((found) => {
        if (cancelled) return;
        scrolledFor.current = marker;
        setHiddenNote(found.index === null);
        if (found.index !== null) virtualizer.scrollToIndex(found.index, { align: "center" });
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [client, highlightKey, loadedTotal, params, sortParams, virtualizer]);

  const rowAt = (index: number): TradeRow | undefined => {
    const block = Math.floor(index / BLOCK_ROWS);
    const position = blocks.indexOf(block);
    return pages[position]?.data?.rows[index % BLOCK_ROWS];
  };

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const typing = target?.tagName === "INPUT" || target?.tagName === "TEXTAREA";
      if (!typing && (event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "z" && undo) {
        event.preventDefault();
        edit.mutate({ tradeKey: undo.tradeKey, patch: { [undo.field]: undo.previous } });
        setUndo(null);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [edit, setUndo, undo]);

  const template = columns.map((column) => COLUMN_WIDTHS[column]).join(" ");

  const toggleSort = (column: TradeColumn) => {
    const key = SORT_KEYS[column];
    if (!key) return;
    if (sortKey === key) {
      setDirection(direction === "asc" ? "desc" : "asc");
    } else {
      setSortKey(key);
      setDirection("desc");
    }
  };

  const failed = pages[0]?.isError ? (pages[0].error as Error) : null;

  return (
    <div className="trades">
      <div className="trades-toolbar">
        <h1 className="screen-title">Trades</h1>
        <p className="muted" aria-live="polite">
          {total.toLocaleString("en-US")} trades
        </p>
        <details className="column-menu">
          <summary className="btn">Columns</summary>
          <fieldset>
            <legend className="visually-hidden">Visible columns</legend>
            {TRADE_COLUMNS.map((column) => (
              <label key={column} className="column-option">
                <input
                  type="checkbox"
                  checked={columns.includes(column)}
                  onChange={(event) => {
                    const next = event.target.checked
                      ? TRADE_COLUMNS.filter((item) => item === column || columns.includes(item))
                      : columns.filter((item) => item !== column);
                    setColumns(next);
                  }}
                />
                {COLUMN_LABELS[column]}
              </label>
            ))}
          </fieldset>
        </details>
        <ViewControls
          sort={sortKey}
          direction={direction}
          onApply={(config) => {
            setSortKey(config.sort);
            setDirection(config.dir);
            setColumns(config.columns);
          }}
        />
        {filterOptions.isError && <span className="muted">Filter menus unavailable.</span>}
      </div>

      {selection && (
        <p className="glass panel selection-note" role="status">
          Showing the {selection.count.toLocaleString("en-US")} trades behind: {selection.label}.{" "}
          <button type="button" className="btn btn-quiet" onClick={() => setSelection(null)}>
            Show all trades
          </button>
        </p>
      )}
      {highlightKey && hiddenNote && (
        <p className="glass panel" role="status">
          The trade you picked is hidden by the current filters. Clear the filters to see it.
        </p>
      )}

      {failed && (
        <p className="glass panel" role="alert">
          Trades could not load: {failed.message}
        </p>
      )}

      <div className="grid-wrap" role="table" aria-label="Trades" aria-rowcount={total}>
        <div className="grid-row grid-head" role="row" style={{ gridTemplateColumns: template }}>
          {columns.map((column) => {
            const sortable = SORT_KEYS[column] !== undefined;
            const active = SORT_KEYS[column] === sortKey;
            return (
              <span
                key={column}
                role="columnheader"
                aria-sort={active ? (direction === "asc" ? "ascending" : "descending") : "none"}
                className="grid-head-cell"
              >
                {sortable ? (
                  <button
                    type="button"
                    className={`sort-button${active ? ` is-${direction}` : ""}`}
                    onClick={() => toggleSort(column)}
                  >
                    {COLUMN_LABELS[column]}
                  </button>
                ) : (
                  COLUMN_LABELS[column]
                )}
              </span>
            );
          })}
        </div>
        <div className="grid-scroll" ref={scrollRef}>
          <div style={{ height: virtualizer.getTotalSize(), position: "relative" }}>
            {virtualizer.getVirtualItems().map((item) => {
              const row = rowAt(item.index);
              return (
                <GridRow
                  key={item.key}
                  index={item.index}
                  start={item.start}
                  row={row}
                  columns={columns}
                  template={template}
                  selected={row !== undefined && row.trade_key === selectedKey}
                  highlighted={row !== undefined && row.trade_key === highlightKey}
                  onSelect={selectTrade}
                  onSaved={setUndo}
                />
              );
            })}
          </div>
        </div>
        {total === 0 && pages[0]?.isSuccess && <p className="empty-note">No trades match these filters.</p>}
      </div>

      {undo && (
        <p className="undo-hint" role="status">
          Edited {undo.field}. Press Ctrl+Z to undo.
        </p>
      )}

      {selectedKey && (
        <TradeDrawer key={selectedKey} tradeKey={selectedKey} onClose={() => selectTrade(null)} />
      )}
    </div>
  );
}
