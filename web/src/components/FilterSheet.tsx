import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";

// Below this width the filter bar moves into a sheet opened from a "Filters" button. The bar is
// rendered in only one place at a time, so its labels never appear twice in the page.
const NARROW_QUERY = "(max-width: 639px)";

const FOCUSABLE = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  '[tabindex]:not([tabindex="-1"])',
].join(",");

function matchesNarrow(): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia(NARROW_QUERY).matches;
}

function useNarrow(): boolean {
  const [narrow, setNarrow] = useState(matchesNarrow);
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const media = window.matchMedia(NARROW_QUERY);
    const onChange = () => setNarrow(media.matches);
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, []);
  return narrow;
}

function FilterSheet({ onClose, children }: { onClose: () => void; children: ReactNode }) {
  const sheetRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    closeRef.current?.focus();
  }, []);

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
      onClose();
      return;
    }
    const sheet = sheetRef.current;
    if (event.key !== "Tab" || !sheet) return;
    const items = Array.from(sheet.querySelectorAll<HTMLElement>(FOCUSABLE));
    const first = items[0];
    const last = items[items.length - 1];
    if (!first || !last) return;
    const active = document.activeElement;
    const inside = active instanceof Node && sheet.contains(active);
    // Tab and Shift+Tab wrap inside the sheet, so focus cannot reach the page behind it.
    if (event.shiftKey && (!inside || active === first)) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && (!inside || active === last)) {
      event.preventDefault();
      first.focus();
    }
  };

  return (
    <div
      className="filter-sheet-scrim"
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        ref={sheetRef}
        role="dialog"
        aria-modal="true"
        aria-label="Filters"
        className="filter-sheet"
        onKeyDown={onKeyDown}
      >
        <div className="filter-sheet-head">
          <h2>Filters</h2>
          <button ref={closeRef} type="button" className="btn btn-quiet" onClick={onClose}>
            Close
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

// Renders its children in the top bar on wide screens. On narrow screens it renders a Filters
// button, and the children appear inside the sheet that button opens.
export function FilterSlot({ children }: { children: ReactNode }) {
  const narrow = useNarrow();
  const [open, setOpen] = useState(false);
  const buttonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!narrow) setOpen(false);
  }, [narrow]);

  if (!narrow) return <>{children}</>;

  const close = () => {
    setOpen(false);
    buttonRef.current?.focus();
  };

  return (
    <>
      <button
        ref={buttonRef}
        type="button"
        className="btn filters-toggle"
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => setOpen(true)}
      >
        Filters
      </button>
      {open ? <FilterSheet onClose={close}>{children}</FilterSheet> : null}
    </>
  );
}
