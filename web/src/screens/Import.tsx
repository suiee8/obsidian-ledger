import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useDropzone } from "react-dropzone";

import { ApiError } from "../lib/api";
import { IMPORT_COLUMNS, IMPORT_TEMPLATE } from "../lib/import-format";
import { useImportSession, type ImportedFile } from "../lib/import-session";
import { dashboardQuery, useCommitImport, usePreviewImport } from "../lib/queries";
import type { Preview } from "../lib/schemas";
import { useFilters } from "../state/filters";
import { useUi } from "../state/ui";

const ACCEPT = {
  "text/csv": [".csv", ".tsv", ".txt"],
  "application/json": [".json"],
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
  "application/vnd.ms-excel": [".xls"],
};

const ROLES = [
  "trade_id",
  "order_id",
  "account",
  "symbol",
  "side",
  "action",
  "qty",
  "entry_price",
  "exit_price",
  "fill_price",
  "notional",
  "entry_time",
  "exit_time",
  "fill_time",
  "fees",
  "commission",
  "swap",
  "gross_pnl",
  "net_pnl",
  "leverage",
  "order_type",
  "status",
  "stop_loss",
  "take_profit",
  "notes",
  "tags",
  "setup",
  "asset_class",
  "currency",
  "multiplier",
] as const;

const CAPABILITIES = [
  ["has_time", "Time"],
  ["has_direction", "Direction or action"],
  ["has_quantity", "Quantity"],
  ["has_notional", "Notional value"],
  ["has_price", "Price"],
  ["has_fees", "Fees"],
  ["has_pnl", "P&L"],
  ["has_stop", "Stop"],
] as const;

const WARNING_LABELS: Record<string, string> = {
  hour_precision: "Hour-only timestamps; holding durations are approximate.",
  truncated_symbols: "Some symbols may be truncated; values are preserved as-is.",
  duplicates: "Exact duplicate rows were found and will be kept.",
  zero_leverage: "Zero leverage values were found.",
  partial_fills: "Order and filled quantities differ; filled quantities are used.",
  totals_row: "Trailing totals rows will be ignored.",
};

type Options = Record<string, unknown>;
type Question = Preview["questions"][number];
type Answer = {
  key: string;
  label: string;
  choices: string[];
  initial: string;
  apply: (options: Options, value: string) => Options;
};

function chooseAnswers(preview: Preview, error: ApiError): Answer[] {
  const details = error.details as { questions?: Question[]; fields?: string[] } | undefined;
  const questions = details?.questions ?? preview.questions.filter((question) => question.blocking);
  const headers = preview.columns.map((column) => column.header);
  const mapping = (options: Options, header: string, value: string | null): Options => ({
    ...options,
    mapping: { ...(options.mapping as Record<string, string | null> | undefined), [header]: value },
  });
  const columnAnswer = (field: string): Answer => {
    const types = preview.profiles;
    const known = preview.columns.find((column) => column.field === field)?.header;
    const aliases: Record<string, string> = {
      qty: "Trade size",
      notional: "Trade value",
      side: "Buy or sell",
      action: "Open or close",
      entry_time: "Entry time",
      exit_time: "Exit time",
      fill_time: "Trade time",
      leg_time: "Trade time",
      symbol: "Instrument",
    };
    const candidates = known ? headers : types.filter((profile) =>
      field.endsWith("_time") ? profile.type_mix.date || profile.type_mix.datetime
        : field === "qty" || field === "notional" ? profile.type_mix.number
          : profile.samples.some(Boolean),
    ).map((profile) => profile.header);
    const choices = candidates.length ? [...new Set([...candidates, ...headers])] : headers;
    return {
      key: field, label: aliases[field] ?? field.replaceAll("_", " "), choices,
      initial: known ?? choices[0] ?? "",
      apply: (options, value) => mapping(options, value, field),
    };
  };
  if (error.code === "needs_column_confirmation") return (details?.fields ?? []).map(columnAnswer);
  return questions.flatMap((question): Answer[] => {
    if (question.id === "mapping_ambiguity") {
      return question.options.map((header) => {
        const detected = preview.columns.find((column) => column.header === header)?.field;
        return {
          key: header, label: `What is “${header}”?`, choices: ["", ...ROLES],
          initial: detected && (ROLES as readonly string[]).includes(detected) ? detected : "",
          apply: (options, value) => mapping(options, header, value || null),
        };
      });
    }
    if (question.id === "mapping") {
      return (details?.fields ?? []).filter((field) =>
        field !== "side" || !questions.some((item) => item.id === "side"),
      ).map(columnAnswer);
    }
    if (question.id === "side") return [columnAnswer("side")];
    if (question.id === "shape" || question.id === "date_format") {
      const key = question.id;
      return [{
        key, label: key === "shape" ? "What does each row describe?" : "How are dates written?",
        choices: question.options, initial: question.options[0] ?? "",
        apply: (options, value) => ({ ...options, [key]: value }),
      }];
    }
    return [];
  });
}

const CHOICE_LABELS: Record<string, string> = {
  "": "Ignore this column",
  round_trip: "One completed trade",
  executions: "One fill",
  orders: "One order",
  legs: "One opening or closing entry",
  dayfirst: "Day first (01/06 is 1 June)",
  monthfirst: "Month first (01/06 is 6 January)",
  qty: "Quantity",
  net_pnl: "Net profit or loss",
};

function TemplateLink() {
  return <a className="btn" href={IMPORT_TEMPLATE} download>Download template</a>;
}

function ImportDialog({ title, onClose, children, drawer = false }: { title: string; onClose: () => void; children: ReactNode; drawer?: boolean }) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  useEffect(() => { ref.current?.showModal(); }, []);
  return (
    <dialog ref={ref} className={`easy-import-dialog glass panel${drawer ? " import-details-dialog" : ""}`} aria-labelledby={titleId} onClose={onClose}>
      <div className="row-actions">
        <h2 id={titleId} className="panel-title">{title}</h2>
        <button type="button" className="btn" onClick={() => ref.current?.close()}>Close</button>
      </div>
      {children}
    </dialog>
  );
}

function ColumnGuide({ onClose }: { onClose: () => void }) {
  return (
    <ImportDialog title="Column guide" onClose={onClose}>
      <p>Use symbol, side, entry and exit times, and quantity. Include both prices or net P&L.</p>
      <div className="table-wrap" role="region" aria-label="Import column guide" tabIndex={0}>
        <table>
          <thead><tr><th scope="col">Column</th><th scope="col">Meaning</th><th scope="col">Accepted values</th><th scope="col">Example</th></tr></thead>
          <tbody>{IMPORT_COLUMNS.map(([column, meaning, values, example]) => (
            <tr key={column}><th scope="row">{column}</th><td>{meaning}</td><td>{values}</td><td>{example}</td></tr>
          ))}</tbody>
        </table>
      </div>
    </ImportDialog>
  );
}

function Inspection({ entry, onUpdate }: { entry: ImportedFile; onUpdate: (entry: ImportedFile) => void }) {
  const { preview, result } = entry;
  const [editing, setEditing] = useState(false);
  const [mapping, setMapping] = useState<Record<string, string | null>>(
    () => (entry.options.mapping as Record<string, string | null> | undefined) ?? {},
  );
  const [message, setMessage] = useState("");
  const read = usePreviewImport();
  const commit = useCommitImport();
  const busy = read.isPending || commit.isPending;
  async function reimport() {
    setMessage("");
    try {
      const updated = await read.mutateAsync({ file: entry.file });
      const options = { ...entry.options, mapping, easy_import: "confirm" };
      const outcome = await commit.mutateAsync({ previewId: updated.preview_id, options });
      onUpdate({ ...entry, preview: updated, result: { ...outcome, inserted: entry.result.inserted + outcome.inserted }, options });
      setEditing(false);
      setMessage(`Re-imported. Added ${outcome.inserted.toLocaleString()} new trades.`);
    } catch (error) {
      setMessage(error instanceof ApiError ? error.message : "We couldn't read this file again.");
    }
  }
  return (
    <section aria-label={preview.filename}>
      <h3>{preview.filename}</h3>
      <h4>Capabilities</h4>
      <ul className="assumptions">{CAPABILITIES.map(([key, label]) => (
        <li key={key}>{label}: {preview.capabilities[key] ? "found" : "not found"}</li>
      ))}</ul>
      <h4>Assumptions</h4>
      <ul className="assumptions">{result.assumptions.map((item) => (
        <li key={item.key}>{item.key.replaceAll("_", " ")}: {item.value}. {item.detail}</li>
      ))}</ul>
      {preview.warnings.length > 0 && <>
        <h4>Warnings</h4>
        <ul className="assumptions">{preview.warnings.map((warning) => <li key={warning}>{WARNING_LABELS[warning] ?? warning}</li>)}</ul>
      </>}
      {result.issues.length > 0 && <ul className="assumptions">{result.issues.map((issue) => (
        <li key={issue.code}>{issue.title} ({issue.count.toLocaleString()})</li>
      ))}</ul>}
      <h4>Column mapping</h4>
      <div className="table-wrap" role="region" aria-label="Column mapping" tabIndex={0}>
        <table className="mapping-table">
          <thead><tr><th scope="col">File column</th><th scope="col">Role</th><th scope="col">Confidence</th></tr></thead>
          <tbody>{preview.columns.map((column) => {
            const value = Object.hasOwn(mapping, column.header) ? mapping[column.header] : column.field;
            return (
              <tr key={column.index}>
                <th scope="row">{column.header}</th>
                <td>{editing ? (
                  <select aria-label={`Role for ${column.header}`} value={value ?? ""}
                    onChange={(event) => setMapping({ ...mapping, [column.header]: event.target.value || null })}>
                    <option value="">Ignore</option>
                    {Array.from(new Set([...(column.field ? [column.field] : []), ...ROLES])).map((role) =>
                      <option key={role} value={role}>{role.replaceAll("_", " ")}</option>)}
                  </select>
                ) : value?.replaceAll("_", " ") ?? "Ignored"}</td>
                <td>{column.confidence ?? "—"}</td>
              </tr>
            );
          })}</tbody>
        </table>
      </div>
      <div className="row-actions">
        <button type="button" className="btn" disabled={busy} onClick={() => setEditing(!editing)}>
          {editing ? "Done editing" : "Edit mapping"}
        </button>
        <button type="button" className="btn btn-primary" disabled={busy} onClick={() => void reimport()}>
          {busy ? "Re-importing…" : "Re-import with these settings"}
        </button>
      </div>
      {message && <p role="status">{message}</p>}
    </section>
  );
}

export function ImportNotice() {
  const files = useImportSession((state) => state.files);
  const [details, setDetails] = useState(false);
  if (files.length === 0) return null;
  const imported = files.reduce((total, file) => total + file.result.inserted, 0);
  const filename = files.length === 1 ? files[0]!.result.filename : `${files.length} files`;
  const needsPrices = files.some(({ preview }) => !preview.capabilities.has_price && !preview.capabilities.has_pnl);
  return (
    <>
      <div className="import-status glass">
        <p role="status">
          Imported {imported.toLocaleString()} {imported === 1 ? "trade" : "trades"} from {filename}.
          {needsPrices && <> Profit numbers need prices or P&L. <a href={IMPORT_TEMPLATE} download>Download template</a>.</>}
        </p>
        <button type="button" className="btn btn-quiet" onClick={() => setDetails(true)}>Details</button>
        <button type="button" className="btn btn-quiet" onClick={() => useImportSession.setState({ files: [] })}>Dismiss</button>
      </div>
      {details && (
        <ImportDialog title="What we found" drawer onClose={() => setDetails(false)}>
          {files.map((entry, index) => (
            <Inspection key={`${entry.preview.sha256}-${index}`} entry={entry} onUpdate={(updated) => {
              useImportSession.setState((state) => ({
                files: state.files.map((file) => file === entry ? updated : file),
              }));
            }} />
          ))}
        </ImportDialog>
      )}
    </>
  );
}

type Pending = { file: File; preview: Preview; options: Options; answers: Answer[]; message: string; version: number };

function OneThing({ pending, onContinue }: { pending: Pending; onContinue: (options: Options) => void }) {
  const answers = pending.answers.slice(0, 3);
  const [values, setValues] = useState(() => answers.map((answer) => answer.initial));
  return (
    <form className="glass panel" onSubmit={(event) => {
      event.preventDefault();
      onContinue(answers.reduce((options, answer, index) => answer.apply(options, values[index] ?? ""), pending.options));
    }}>
      <h2 className="panel-title">One thing we need</h2>
      <p>{pending.message}</p>
      <div className="control-row">
        {answers.map((answer, index) => (
          <label key={answer.key} className="field">
            <span>{answer.label}</span>
            <select value={values[index]} required={!answer.choices.includes("")}
              onChange={(event) => setValues(values.map((value, i) => i === index ? event.target.value : value))}>
              {answer.choices.map((choice) => <option value={choice} key={choice}>{CHOICE_LABELS[choice] ?? choice.replaceAll("_", " ")}</option>)}
            </select>
          </label>
        ))}
      </div>
      <button className="btn btn-primary" type="submit">Continue</button>
    </form>
  );
}

export default function Import() {
  const read = usePreviewImport();
  const commit = useCommitImport();
  const setRoute = useUi((state) => state.setRoute);
  const client = useQueryClient();
  const [guide, setGuide] = useState(false);
  const [stage, setStage] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState<Pending | null>(null);
  const queue = useRef<File[]>([]);
  const completed = useRef<ImportedFile[]>([]);
  const version = useRef(0);
  const running = useRef(false);

  async function finish() {
    if (completed.current.length === 0) return;
    setStage("Analyzing");
    await client.fetchQuery(dashboardQuery(useFilters.getState().toParams())).catch(() => undefined);
    useImportSession.setState({ files: completed.current });
    setRoute("dashboard");
  }

  async function run(resume?: { file: File; preview: Preview; options: Options }) {
    if (running.current) return;
    running.current = true;
    setError("");
    setPending(null);
    try {
      while (resume || queue.current.length > 0) {
        const file = resume?.file ?? queue.current.shift()!;
        setStage("Reading");
        const preview = resume?.preview ?? await read.mutateAsync({ file });
        const options = { easy_import: "auto", ...resume?.options };
        resume = undefined;
        setStage("Understanding columns");
        try {
          setStage("Building trades");
          const result = await commit.mutateAsync({ previewId: preview.preview_id, options });
          const assumptions = Object.fromEntries(result.assumptions.map((item) => [item.key, item.value]));
          completed.current.push({
            file, preview, result,
            options: {
              ...options, timezone: assumptions.timezone,
              default_symbol: assumptions.default_symbol, side_mode: assumptions.buy_sell,
            },
          });
        } catch (failure) {
          if (failure instanceof ApiError && ["needs_answers", "needs_column_confirmation", "confirm_valid_rows"].includes(failure.code ?? "")) {
            const answers = failure.code === "confirm_valid_rows" ? [] : chooseAnswers(preview, failure);
            if (answers.length > 0 || failure.code === "confirm_valid_rows") {
              setPending({ file, preview, options: failure.code === "confirm_valid_rows"
                ? { ...options, easy_import: "confirm" } : options, answers, version: ++version.current,
                message: failure.code === "confirm_valid_rows" ? failure.message : "Check the suggested choices so we can read this file." });
              return;
            }
          }
          throw failure;
        }
      }
      await finish();
    } catch (failure) {
      const mostlyInvalid = failure instanceof ApiError && failure.code === "too_few_valid_rows";
      setError(mostlyInvalid ? "We couldn't read most of this file. Try the template to check the format."
        : "We couldn't import this file. Check the file type or try the template.");
    } finally {
      running.current = false;
      setStage("");
    }
  }

  const dropzone = useDropzone({
    accept: ACCEPT,
    multiple: true,
    disabled: Boolean(stage),
    maxSize: 200 * 1024 * 1024,
    onDrop: (accepted, rejected) => {
      if (running.current) return;
      if (rejected.length > 0) {
        setPending(null);
        setError("We couldn't open one of these files. Choose a supported file under 200 MB or try the template.");
        return;
      }
      if (accepted.length === 0) return;
      queue.current = [...accepted];
      completed.current = [];
      void run();
    },
  });

  return (
    <div className="import-screen">
      <h1 className="screen-title">Import</h1>
      <p className="lede">Drop your trade files to import them and see your analysis.</p>
      <input {...dropzone.getInputProps()} aria-label="Trade file" />
      <div {...dropzone.getRootProps({ className: `dropzone glass${dropzone.isDragActive ? " is-active" : ""}`, role: "button" })}
        aria-label="Drop a trade file here, or press Enter to choose one">
        <p>{dropzone.isDragActive ? "Release to read the files" : "Drop files here or choose files"}</p>
        <p className="muted">CSV, TSV, TXT, XLSX, XLS, or JSON. Up to 200 MB per file.</p>
      </div>
      <div className="row-actions">
        <TemplateLink />
        <button type="button" className="btn" onClick={() => setGuide(true)}>Column guide</button>
      </div>
      {stage && <ol className="import-progress" aria-label="Import progress">
        {["Reading", "Understanding columns", "Building trades", "Analyzing"].map((step) => (
          <li key={step} aria-current={step === stage ? "step" : undefined}>{step}</li>
        ))}
      </ol>}
      <span className="sr-only" role="status">{stage}</span>
      {error && <div className="glass panel"><p role="alert">{error}</p>
        <div className="row-actions">
          <TemplateLink />
          {queue.current.length > 0 && <button className="btn" type="button" onClick={() => void run()}>Import remaining files</button>}
          {completed.current.length > 0 && <button className="btn" type="button" onClick={() => void finish()}>Open Dashboard</button>}
        </div>
      </div>}
      {pending && <OneThing key={pending.version} pending={pending} onContinue={(options) => void run({ ...pending, options })} />}
      {guide && <ColumnGuide onClose={() => setGuide(false)} />}
    </div>
  );
}
