import { useEffect, useState } from "react";

import { Panel } from "../components/Panel";
import { DISCLAIMER, ScreenError, ScreenSkeleton } from "../components/ScreenStates";
import { apiBase } from "../lib/api";
import { fmtInt } from "../lib/format";
import { useDeleteKey, useLlmStatus, useSaveKey, useSaveLlm, useTestLlm } from "../lib/llm";
import {
  useDeleteTemplate,
  useRenameTemplate,
  useSaveSettings,
  useSettings,
  useTemplates,
  useWipe,
  type SettingsData,
} from "../lib/phase4";
import { useFilters } from "../state/filters";
import { useUi } from "../state/ui";

function Privacy({ settings }: { settings: SettingsData }) {
  const save = useSaveSettings();
  // The boxes follow local state, which changes inside the click. The server value replaces it
  // when no save is running, so a failed save puts the boxes back.
  const [shown, setShown] = useState(settings.privacy);
  useEffect(() => {
    if (!save.isPending) setShown(settings.privacy);
  }, [settings.privacy, save.isPending]);
  const { aggregates_only, include_notes, include_trade_rows } = shown;
  const set = (patch: Partial<SettingsData["privacy"]>) => {
    let next = { ...shown, ...patch };
    if (next.aggregates_only) {
      next = { aggregates_only: true, include_notes: false, include_trade_rows: false };
    }
    setShown(next);
    save.mutate({ privacy: next });
  };
  return (
    <Panel title="Privacy" className="span-6">
      <p className="card-note">
        These choices control what the AI provider may read, if you turn one on below. Trade rows and notes
        are only sent when you turn them on here.
      </p>
      <fieldset className="check-group">
        <legend>What a language model may see</legend>
        <label className="column-option">
          <input
            type="checkbox"
            checked={aggregates_only}
            disabled={save.isPending}
            onChange={(event) => set({ aggregates_only: event.target.checked })}
          />
          Aggregates only (default): totals, rates, and ranges, never single trades
        </label>
        <label className="column-option">
          <input
            type="checkbox"
            checked={include_trade_rows}
            disabled={aggregates_only || save.isPending}
            onChange={(event) => set({ include_trade_rows: event.target.checked })}
          />
          Include individual trade rows
        </label>
        <label className="column-option">
          <input
            type="checkbox"
            checked={include_notes}
            disabled={aggregates_only || save.isPending}
            onChange={(event) => set({ include_notes: event.target.checked })}
          />
          Include my trade notes
        </label>
      </fieldset>
      {save.isError && (
        <p role="alert" className="muted">
          Could not save: {save.error.message}
        </p>
      )}
    </Panel>
  );
}

function StartingEquity({ settings }: { settings: SettingsData }) {
  const save = useSaveSettings();
  const [draft, setDraft] = useState<string>(settings.starting_equity?.toString() ?? "");
  const value = Number(draft);
  const valid = draft !== "" && Number.isFinite(value) && value > 0;
  return (
    <Panel title="Starting equity" className="span-6">
      <p className="card-note">
        Unlocks percentages of equity, Sharpe, Sortino, Calmar, and risk of ruin. Changing it recalculates every
        screen.
      </p>
      <form
        className="control-row"
        onSubmit={(event) => {
          event.preventDefault();
          if (valid) save.mutate({ starting_equity: value });
        }}
      >
        <label className="field">
          <span>Starting equity</span>
          <input
            type="number"
            min={0}
            step="any"
            value={draft}
            placeholder="Not set"
            onChange={(event) => setDraft(event.target.value)}
          />
        </label>
        <button type="submit" className="btn btn-primary" disabled={!valid || save.isPending}>
          Save
        </button>
        <button
          type="button"
          className="btn"
          disabled={settings.starting_equity === null || save.isPending}
          onClick={() => {
            setDraft("");
            save.mutate({ starting_equity: null });
          }}
        >
          Clear
        </button>
      </form>
      <p className="muted" aria-live="polite">
        {settings.starting_equity === null
          ? "No starting equity is set."
          : `Set to ${settings.starting_equity.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}.`}
      </p>
      {save.isError && (
        <p role="alert" className="muted">
          Could not save: {save.error.message}
        </p>
      )}
    </Panel>
  );
}

function TemplateRow({
  fingerprint,
  name,
  mapped,
  updated,
}: {
  fingerprint: string;
  name: string;
  mapped: number;
  updated: string;
}) {
  const rename = useRenameTemplate();
  const remove = useDeleteTemplate();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(name);
  const [confirming, setConfirming] = useState(false);
  return (
    <li className="template-row">
      {editing ? (
        <form
          className="control-row"
          onSubmit={(event) => {
            event.preventDefault();
            if (draft.trim() === "") return;
            rename.mutate({ fingerprint, name: draft.trim() }, { onSuccess: () => setEditing(false) });
          }}
        >
          <label className="field">
            <span>New name for {name}</span>
            <input value={draft} maxLength={80} onChange={(event) => setDraft(event.target.value)} />
          </label>
          <button type="submit" className="btn btn-primary" disabled={draft.trim() === "" || rename.isPending}>
            Save name
          </button>
          <button type="button" className="btn btn-quiet" onClick={() => setEditing(false)}>
            Cancel
          </button>
        </form>
      ) : (
        <>
          <div>
            <strong>{name}</strong>
            <p className="muted">
              {mapped} columns mapped. Saved {updated.slice(0, 10)}.
            </p>
          </div>
          <div className="row-actions">
            <button type="button" className="btn" onClick={() => setEditing(true)} aria-label={`Rename ${name}`}>
              Rename
            </button>
            {confirming ? (
              <>
                <button
                  type="button"
                  className="btn btn-danger"
                  disabled={remove.isPending}
                  onClick={() => remove.mutate(fingerprint)}
                  aria-label={`Confirm delete ${name}`}
                >
                  Yes, delete
                </button>
                <button type="button" className="btn btn-quiet" onClick={() => setConfirming(false)}>
                  Keep
                </button>
              </>
            ) : (
              <button
                type="button"
                className="btn"
                onClick={() => setConfirming(true)}
                aria-label={`Delete ${name}`}
              >
                Delete
              </button>
            )}
          </div>
        </>
      )}
      {(rename.isError || remove.isError) && (
        <p role="alert" className="muted">
          {(rename.error ?? remove.error)?.message}
        </p>
      )}
    </li>
  );
}

function Templates() {
  const query = useTemplates();
  return (
    <Panel title="Column templates" className="span-12">
      <p className="card-note">
        A template remembers how the columns of one file layout map to Obsidian Ledger fields, so the next
        import of the same layout needs no questions.
      </p>
      {query.isError ? (
        <p role="alert" className="muted">
          Templates could not load: {query.error.message}
        </p>
      ) : !query.data || query.data.length === 0 ? (
        <p className="muted">No templates yet. Name one when you import a file.</p>
      ) : (
        <ul className="template-list">
          {query.data.map((template) => (
            <TemplateRow
              key={template.fingerprint}
              fingerprint={template.fingerprint}
              name={template.name}
              mapped={Object.values(template.mapping).filter((field) => field !== null).length}
              updated={template.updated_at}
            />
          ))}
        </ul>
      )}
    </Panel>
  );
}

function LanguageModel({ settings }: { settings: SettingsData }) {
  const status = useLlmStatus();
  const save = useSaveLlm();
  const saveKey = useSaveKey();
  const deleteKey = useDeleteKey();
  const test = useTestLlm();
  const current = status.data;
  const [keyDraft, setKeyDraft] = useState("");
  const [limit, setLimit] = useState<string | null>(null);
  // The box changes inside the click; the saved value replaces it once the server answers.
  const [consentShown, setConsentShown] = useState<boolean | null>(null);

  if (status.isPending) {
    return (
      <Panel title="AI provider" className="span-6">
        <p className="muted">Loading…</p>
      </Panel>
    );
  }
  if (status.isError || !current) {
    return (
      <Panel title="AI provider" className="span-6">
        <p role="alert" className="muted">
          The AI settings could not be read: {status.error?.message}
        </p>
      </Panel>
    );
  }

  const chosen = current.providers.find((item) => item.id === current.provider) ?? null;
  const tested = test.data;
  const models = Array.from(new Set([...(tested?.models ?? []), ...current.models]));
  const savedLimit = current.answer_seconds;
  const shownLimit = limit ?? String(savedLimit);
  const limitValue = Number(shownLimit);
  const limitValid = Number.isInteger(limitValue) && limitValue >= 10 && limitValue <= 600;
  const busy = save.isPending || saveKey.isPending || deleteKey.isPending;
  const failure = save.error ?? saveKey.error ?? deleteKey.error ?? test.error;

  return (
    <Panel title="AI provider" className="span-6">
      <p className="card-note">{settings.llm.note}</p>
      <p className={current.ready ? "llm-status is-ready" : "llm-status"} role="status">
        {current.ready
          ? `Ready: ${current.provider_name ?? ""}, ${current.model ?? ""}.`
          : `Off. ${current.message ?? ""}`}
      </p>

      <label className="field">
        <span>Provider</span>
        <select
          value={current.provider}
          disabled={busy}
          onChange={(event) => {
            setKeyDraft("");
            test.reset();
            save.mutate({ provider: event.target.value });
          }}
        >
          <option value="none">None (AI off)</option>
          {current.providers.map((item) => (
            <option key={item.id} value={item.id}>
              {item.name}
            </option>
          ))}
        </select>
      </label>

      {chosen && (
        <>
          <p className="card-note">
            {chosen.note}{" "}
            {chosen.key_page && (
              <a href={chosen.key_page} target="_blank" rel="noreferrer">
                Get an API key
              </a>
            )}
          </p>

          {current.key_saved ? (
            <div className="control-row">
              <p className="muted">API key saved in Windows Credential Manager ({current.key_hint}).</p>
              <button
                type="button"
                className="btn"
                disabled={busy}
                onClick={() => {
                  test.reset();
                  deleteKey.mutate(chosen.id);
                }}
              >
                Remove key
              </button>
            </div>
          ) : (
            <form
              className="control-row"
              onSubmit={(event) => {
                event.preventDefault();
                const key = keyDraft.trim();
                if (key) saveKey.mutate({ provider: chosen.id, api_key: key }, { onSuccess: () => setKeyDraft("") });
              }}
            >
              <label className="field">
                <span>API key for {chosen.name}</span>
                <input
                  type="password"
                  value={keyDraft}
                  autoComplete="off"
                  spellCheck={false}
                  onChange={(event) => setKeyDraft(event.target.value)}
                />
              </label>
              <button type="submit" className="btn btn-primary" disabled={busy || keyDraft.trim().length < 8}>
                Save key
              </button>
            </form>
          )}

          <div className="control-row">
            <button
              type="button"
              className="btn"
              disabled={test.isPending || (!current.key_saved && keyDraft.trim().length < 8)}
              onClick={() =>
                test.mutate({
                  provider: chosen.id,
                  model: current.model,
                  api_key: current.key_saved ? undefined : keyDraft.trim(),
                })
              }
            >
              {test.isPending ? "Testing…" : "Test connection"}
            </button>
            <span className="muted" aria-live="polite">
              {tested
                ? `${tested.message}${tested.milliseconds !== undefined ? ` (${tested.milliseconds} ms)` : ""}`
                : "Sends one short test message. No journal data."}
            </span>
          </div>

          <label className="field">
            <span>Model</span>
            <select
              value={current.model ?? ""}
              disabled={busy || models.length === 0}
              onChange={(event) => save.mutate({ model: event.target.value || null })}
            >
              <option value="">Choose a model</option>
              {models.map((name) => (
                <option key={name} value={name}>
                  {name}
                  {current.free_models.includes(name) ? " (free)" : ""}
                </option>
              ))}
            </select>
          </label>

          <fieldset className="check-group">
            <legend>What leaves this computer</legend>
            <label className="column-option">
              <input
                type="checkbox"
                checked={consentShown ?? current.consented}
                disabled={busy}
                onChange={(event) => {
                  const next = event.target.checked;
                  setConsentShown(next);
                  save.mutate({ consent: next }, { onSettled: () => setConsentShown(null) });
                }}
              />
              Send computed results to {chosen.name} ({chosen.host})
            </label>
            <p className="card-note">
              With the privacy default this is totals, rates, ranges, and finding descriptions, never single
              trades or notes. Trade rows and notes are only sent if you turn them on under Privacy.
            </p>
          </fieldset>
        </>
      )}

      <form
        className="control-row"
        onSubmit={(event) => {
          event.preventDefault();
          if (limitValid) save.mutate({ answer_seconds: limitValue }, { onSuccess: () => setLimit(null) });
        }}
      >
        <label className="field">
          <span>Time limit per answer (seconds)</span>
          <input
            type="number"
            min={10}
            max={600}
            step={10}
            value={shownLimit}
            onChange={(event) => setLimit(event.target.value)}
          />
        </label>
        <button type="submit" className="btn" disabled={!limitValid || busy || limitValue === savedLimit}>
          Save limit
        </button>
      </form>
      {failure && (
        <p role="alert" className="muted">
          {failure.message}
        </p>
      )}
    </Panel>
  );
}

function ExportAll({ settings }: { settings: SettingsData }) {
  return (
    <Panel title="Export all data" className="span-6">
      <p className="card-note">
        One zip file with every trade as a CSV, your imports, saved views, column templates, Coach reports,
        settings, and the original uploaded files. It is made on this computer.
      </p>
      <p className="muted">
        {fmtInt(settings.data.trades)} trades, {fmtInt(settings.data.imports)} imports,{" "}
        {fmtInt(settings.data.templates)} templates.
      </p>
      <a className="btn btn-primary" href={`${apiBase()}/api/export`} download>
        Download everything
      </a>
    </Panel>
  );
}

function Wipe({ settings }: { settings: SettingsData }) {
  const wipe = useWipe();
  const resetFilters = useFilters((state) => state.reset);
  const setSelection = useUi((state) => state.setSelection);
  const [typed, setTyped] = useState("");
  const phrase = settings.wipe_phrase;
  const ready = typed === phrase;
  const removed = wipe.data?.removed;
  return (
    <Panel title="Wipe everything" className="span-12">
      <p className="card-note">
        Permanently deletes all {fmtInt(settings.data.trades)} trades, imports, saved views, templates, Coach
        reports, settings, and uploaded files from this computer. It cannot be undone. Export first if you want
        a copy.
      </p>
      <form
        className="control-row"
        onSubmit={(event) => {
          event.preventDefault();
          if (!ready) return;
          wipe.mutate(typed, {
            onSuccess: () => {
              resetFilters();
              setSelection(null);
              setTyped("");
            },
          });
        }}
      >
        <label className="field">
          <span>
            Type <code>{phrase}</code> to confirm
          </span>
          <input
            value={typed}
            autoComplete="off"
            spellCheck={false}
            onChange={(event) => setTyped(event.target.value)}
          />
        </label>
        <button type="submit" className="btn btn-danger" disabled={!ready || wipe.isPending}>
          Wipe everything
        </button>
      </form>
      <div aria-live="polite">
        {removed && (
          <p role="status">
            Everything was deleted: {fmtInt(removed.trades ?? 0)} trades and {fmtInt(removed.files ?? 0)} files.
          </p>
        )}
        {wipe.isError && (
          <p role="alert" className="muted">
            Nothing was deleted: {wipe.error.message}
          </p>
        )}
      </div>
    </Panel>
  );
}

export default function Settings() {
  const query = useSettings();
  if (query.isError) {
    return (
      <ScreenError
        title="Settings could not load"
        message={query.error.message}
        onRetry={() => void query.refetch()}
      />
    );
  }
  if (query.isPending) return <ScreenSkeleton label="Loading settings" />;
  const settings = query.data;
  return (
    <div className="dashboard">
      <header>
        <h1 className="screen-title">Settings</h1>
        <p className="lede">Everything here is stored on this computer.</p>
      </header>
      <div className="bento">
        <Privacy settings={settings} />
        <StartingEquity key={String(settings.starting_equity)} settings={settings} />
        <LanguageModel settings={settings} />
        <ExportAll settings={settings} />
        <Templates />
        <Wipe settings={settings} />
      </div>
      <p className="footer">{DISCLAIMER}</p>
    </div>
  );
}
