import { useEffect, useRef, useState } from "react";

import { fmtDateTime, fmtDuration, fmtMoney, fmtNumber, fmtR } from "../lib/format";
import { useEditTrade, useTrade } from "../lib/queries";
import type { TradeRow } from "../lib/schemas";

interface TradeDrawerProps {
  tradeKey: string;
  onClose: () => void;
}

type Draft = { notes: string; tags: string; emotion: string; confidence: string };

function draftFrom(row: TradeRow): Draft {
  return {
    notes: row.notes,
    tags: row.tags ?? "",
    emotion: row.emotion ?? "",
    confidence: row.confidence ?? "",
  };
}

/** Trade detail with its timeline, excursions, and editable journal fields. Escape closes it. */
export function TradeDrawer({ tradeKey, onClose }: TradeDrawerProps) {
  const query = useTrade(tradeKey);
  const edit = useEditTrade();
  const [draft, setDraft] = useState<Draft | null>(null);
  const [saved, setSaved] = useState<Draft | null>(null);
  const [previous, setPrevious] = useState<Draft | null>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    closeRef.current?.focus();
  }, []);

  // Escape closes the drawer wherever focus is. Focus can sit on a control that is replaced when
  // the trade finishes loading, so a listener on the element itself would miss the key.
  useEffect(() => {
    const onEscape = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onEscape);
    return () => window.removeEventListener("keydown", onEscape);
  }, [onClose]);

  useEffect(() => {
    if (query.data && draft === null) {
      const initial = draftFrom(query.data);
      setDraft(initial);
      setSaved(initial);
    }
  }, [query.data, draft]);

  if (query.isPending || !draft || !query.data) {
    return (
      <aside className="drawer glass" role="dialog" aria-modal="true" aria-label="Trade detail">
        <button type="button" ref={closeRef} className="btn btn-quiet drawer-close" onClick={onClose}>
          Close
        </button>
        <p className="muted">Loading trade…</p>
      </aside>
    );
  }
  const trade = query.data;
  const dirty = JSON.stringify(draft) !== JSON.stringify(saved);

  const save = () => {
    const patch: Record<string, string | null> = {
      notes: draft.notes,
      tags: draft.tags.trim() || null,
      emotion: draft.emotion.trim() || null,
      confidence: draft.confidence.trim() || null,
    };
    edit.mutate(
      { tradeKey, patch },
      {
        onSuccess: () => {
          setPrevious(saved);
          setSaved({ ...draft });
        },
      },
    );
  };

  const undo = () => {
    if (!previous) return;
    edit.mutate(
      {
        tradeKey,
        patch: {
          notes: previous.notes,
          tags: previous.tags || null,
          emotion: previous.emotion || null,
          confidence: previous.confidence || null,
        },
      },
      {
        onSuccess: () => {
          setDraft(previous);
          setSaved(previous);
          setPrevious(null);
        },
      },
    );
  };

  return (
    <aside className="drawer glass" role="dialog" aria-modal="true" aria-label={`Trade ${trade.trade_id}`}>
      <div className="drawer-head">
        <div>
          <p className="eyebrow">{trade.side === "long" ? "Long" : "Short"} · {trade.setup ?? "no setup"}</p>
          <h2>{trade.symbol}</h2>
        </div>
        <button type="button" ref={closeRef} className="btn btn-quiet" onClick={onClose} aria-label="Close trade detail">
          Close
        </button>
      </div>

      <div className="timeline" aria-label={`Held for ${fmtDuration(trade.holding_seconds)}`}>
        <span className="timeline-bar" aria-hidden="true" />
        <span className="timeline-entry">{fmtDateTime(trade.entry_time)}</span>
        <span className="timeline-exit">{fmtDateTime(trade.exit_time)}</span>
      </div>

      <dl className="detail-grid">
        <dt>Net P&L</dt>
        <dd
          className={
            trade.net_pnl_base === null ? "muted" : trade.net_pnl_base < 0 ? "tone-loss" : "tone-profit"
          }
        >
          {fmtMoney(trade.net_pnl_base)}
        </dd>
        <dt>R multiple</dt>
        <dd>{fmtR(trade.r_multiple)}</dd>
        <dt>Quantity</dt>
        <dd>{fmtNumber(trade.qty, 4)}</dd>
        <dt>Entry / exit</dt>
        <dd>
          {fmtNumber(trade.entry_price, 5)} → {fmtNumber(trade.exit_price, 5)}
        </dd>
        <dt>Costs</dt>
        <dd>
          {trade.fees === null || trade.commission === null || trade.swap === null
            ? "Not available from this file"
            : fmtMoney(trade.fees + trade.commission + trade.swap, trade.currency)}
        </dd>
        <dt>Planned risk</dt>
        <dd>{fmtMoney(trade.planned_risk, trade.currency)}</dd>
        <dt>Stop / target</dt>
        <dd>
          {fmtNumber(trade.stop_loss, 5)} / {fmtNumber(trade.take_profit, 5)}
        </dd>
        <dt>Max adverse / favourable</dt>
        <dd>
          {fmtMoney(trade.mae, trade.currency)} / {fmtMoney(trade.mfe, trade.currency)}
        </dd>
        <dt>Trade ID</dt>
        <dd className="mono">{trade.trade_id}</dd>
        <dt>Source timezone</dt>
        <dd>{trade.source_timezone ?? "timestamps had an offset"}</dd>
        <dt>Screenshot</dt>
        <dd>{trade.screenshot_path ?? "none"}</dd>
      </dl>

      <form
        className="journal-form"
        onSubmit={(event) => {
          event.preventDefault();
          save();
        }}
      >
        <label>
          <span className="label">Notes</span>
          <textarea
            value={draft.notes}
            maxLength={5000}
            rows={4}
            onChange={(event) => setDraft({ ...draft, notes: event.target.value })}
          />
        </label>
        <label>
          <span className="label">Tags (comma separated)</span>
          <input value={draft.tags} onChange={(event) => setDraft({ ...draft, tags: event.target.value })} />
        </label>
        <label>
          <span className="label">Emotion</span>
          <input value={draft.emotion} onChange={(event) => setDraft({ ...draft, emotion: event.target.value })} />
        </label>
        <label>
          <span className="label">Confidence</span>
          <input value={draft.confidence} onChange={(event) => setDraft({ ...draft, confidence: event.target.value })} />
        </label>
        <div className="row-actions">
          <button type="submit" className="btn btn-primary" disabled={!dirty || edit.isPending}>
            {edit.isPending ? "Saving…" : "Save"}
          </button>
          <button type="button" className="btn" onClick={undo} disabled={edit.isPending || previous === null}>
            Undo last save
          </button>
        </div>
        {edit.isError && (
          <p className="tone-loss" role="alert">
            {edit.error.message}
          </p>
        )}
      </form>
    </aside>
  );
}
