import { useState } from "react";
import { useDropzone } from "react-dropzone";

import { useCommitImport, usePreviewImport } from "../lib/queries";
import type { Commit, Preview } from "../lib/schemas";
import { useUi } from "../state/ui";

const ACCEPT = {
  "text/csv": [".csv", ".tsv", ".txt"],
  "application/json": [".json"],
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
  "application/vnd.ms-excel": [".xls"],
};

type Answers = {
  shape?: string;
  dateFormat?: "dayfirst" | "monthfirst";
  defaultSymbol?: string;
  sideHeader?: string;
};

/** Build the import options from the answers. Only the questions the preview asked are sent. */
function optionsFrom(answers: Answers): Record<string, unknown> {
  const options: Record<string, unknown> = {};
  if (answers.shape) options.shape = answers.shape;
  if (answers.dateFormat) options.date_format = answers.dateFormat;
  if (answers.defaultSymbol?.trim()) options.default_symbol = answers.defaultSymbol.trim();
  if (answers.sideHeader) options.mapping = { [answers.sideHeader]: "side" };
  return options;
}

function ConfidenceChip({ confidence, source }: { confidence: string | null; source: string }) {
  if (!confidence) return <span className="chip chip-muted">not mapped</span>;
  return (
    <span className={`chip chip-${confidence}`} title={`Matched by ${source}`}>
      {confidence}
    </span>
  );
}

function Questions({
  preview,
  answers,
  onChange,
}: {
  preview: Preview;
  answers: Answers;
  onChange: (next: Answers) => void;
}) {
  const blocking = preview.questions.filter((question) => question.blocking);
  if (blocking.length === 0) {
    return <p className="chip chip-ok">No blocking questions. Review the assumptions below, then import.</p>;
  }
  return (
    <div className="questions" role="group" aria-label="Questions to answer before importing">
      {blocking.map((question) => {
        if (question.id === "date_format") {
          return (
            <fieldset key={question.id}>
              <legend>{question.text}</legend>
              {(["dayfirst", "monthfirst"] as const).map((choice) => (
                <label key={choice} className="radio">
                  <input
                    type="radio"
                    name="date_format"
                    checked={answers.dateFormat === choice}
                    onChange={() => onChange({ ...answers, dateFormat: choice })}
                  />
                  {choice === "dayfirst" ? "Day first (01/06 is 1 June)" : "Month first (01/06 is 6 January)"}
                </label>
              ))}
            </fieldset>
          );
        }
        if (question.id === "default_symbol") {
          return (
            <label key={question.id} className="question">
              <span>{question.text}</span>
              <input
                value={answers.defaultSymbol ?? ""}
                maxLength={64}
                onChange={(event) => onChange({ ...answers, defaultSymbol: event.target.value })}
                placeholder="for example BTCUSD"
              />
            </label>
          );
        }
        if (question.id === "shape") {
          return (
            <label key={question.id} className="question">
              <span>{question.text}</span>
              <select value={answers.shape ?? ""} onChange={(event) => onChange({ ...answers, shape: event.target.value })}>
                <option value="">Choose</option>
                {question.options.map((option) => (
                  <option key={option} value={option}>
                    {option.replace("_", " ")}
                  </option>
                ))}
              </select>
            </label>
          );
        }
        if (question.id === "side") {
          return (
            <label key={question.id} className="question">
              <span>{question.text}</span>
              <select
                value={answers.sideHeader ?? ""}
                onChange={(event) => onChange({ ...answers, sideHeader: event.target.value })}
              >
                <option value="">Choose a column</option>
                {question.options.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </label>
          );
        }
        return (
          <p key={question.id} className="chip">
            {question.text}
          </p>
        );
      })}
    </div>
  );
}

function PreviewPanel({
  preview,
  onImported,
}: {
  preview: Preview;
  onImported: (commit: Commit) => void;
}) {
  const [answers, setAnswers] = useState<Answers>({});
  const commit = useCommitImport();
  const blocking = preview.questions.filter((question) => question.blocking);
  const answered = blocking.every((question) => {
    if (question.id === "date_format") return answers.dateFormat !== undefined;
    if (question.id === "default_symbol") return (answers.defaultSymbol ?? "").trim() !== "";
    if (question.id === "shape") return answers.shape !== undefined && answers.shape !== "";
    if (question.id === "side") return answers.sideHeader !== undefined && answers.sideHeader !== "";
    return false;
  });

  return (
    <section className="glass panel import-preview" aria-labelledby="preview-title">
      <h2 id="preview-title" className="panel-title">
        {preview.filename}
      </h2>
      <p className="muted">
        {preview.kind.toUpperCase()} · {preview.encoding} · header on line {preview.header_record}
        {preview.delimiter ? ` · delimiter "${preview.delimiter}"` : ""}
        {preview.adapter ? ` · recognised as ${preview.adapter}` : ""}
        {preview.shape ? ` · ${preview.shape.replace("_", " ")}` : ""}
      </p>

      <Questions preview={preview} answers={answers} onChange={setAnswers} />

      <h3 className="section-title">Columns</h3>
      <table className="mapping-table">
        <thead>
          <tr>
            <th scope="col">File column</th>
            <th scope="col">Means</th>
            <th scope="col">Confidence</th>
          </tr>
        </thead>
        <tbody>
          {preview.columns.map((column) => (
            <tr key={column.index}>
              <td>{column.header}</td>
              <td>{column.field ?? "ignored"}</td>
              <td>
                <ConfidenceChip confidence={column.confidence} source={column.source} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3 className="section-title">Assumptions</h3>
      <ul className="assumptions">
        {preview.assumptions.map((assumption) => (
          <li key={assumption.key}>
            <strong>{assumption.key.replace("_", " ")}:</strong> {assumption.value}
            <span className="muted"> — {assumption.detail}</span>
          </li>
        ))}
      </ul>

      <h3 className="section-title">First rows</h3>
      <div className="table-wrap">
        <table className="sample-table">
          <tbody>
            {preview.sample_rows.map((row, index) => (
              <tr key={index}>
                {Object.entries(row).map(([header, value]) => (
                  <td key={header}>{value}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="row-actions">
        <button
          type="button"
          className="btn btn-primary"
          disabled={!answered || commit.isPending}
          onClick={() =>
            commit.mutate(
              { previewId: preview.preview_id, options: optionsFrom(answers) },
              { onSuccess: (result) => onImported(result) },
            )
          }
        >
          {commit.isPending ? "Importing…" : "Import"}
        </button>
        {!answered && blocking.length > 0 && <span className="muted">Answer the question above to enable import.</span>}
      </div>
      {commit.isError && (
        <p className="tone-loss" role="alert">
          {commit.error.message}
        </p>
      )}
    </section>
  );
}

function CommitPanel({ result }: { result: Commit }) {
  const setRoute = useUi((state) => state.setRoute);
  const base = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000";
  return (
    <section className="glass panel" aria-labelledby="result-title">
      <h2 id="result-title" className="panel-title">
        Imported {result.filename}
      </h2>
      <dl className="detail-grid">
        <dt>Accepted</dt>
        <dd>{result.accepted}</dd>
        <dt>Saved now</dt>
        <dd>{result.inserted}</dd>
        <dt>Already in the journal</dt>
        <dd>{result.already_present}</dd>
        <dt>Rejected</dt>
        <dd>{result.rejected}</dd>
        <dt>Open positions not counted</dt>
        <dd>{result.open_positions}</dd>
      </dl>
      {result.issues.length > 0 && (
        <>
          <h3 className="section-title">Data-quality report</h3>
          <ul className="issues">
            {result.issues.map((issue) => (
              <li key={`${issue.code}-${issue.title}`} className={`issue issue-${issue.severity}`}>
                <strong>{issue.title}</strong> · {issue.count} · {issue.severity}
                <span className="muted"> — {issue.suggested_fix}</span>
              </li>
            ))}
          </ul>
        </>
      )}
      <div className="row-actions">
        {result.rejected > 0 && (
          <a className="btn" href={`${base}${result.rejected_csv_path}`} download>
            Download rejected rows
          </a>
        )}
        <button type="button" className="btn btn-primary" onClick={() => setRoute("dashboard")}>
          Open dashboard
        </button>
      </div>
    </section>
  );
}

export default function Import() {
  const preview = usePreviewImport();
  const [result, setResult] = useState<Commit | null>(null);
  const dropzone = useDropzone({
    accept: ACCEPT,
    multiple: false,
    maxSize: 200 * 1024 * 1024,
    onDrop: (accepted) => {
      const file = accepted[0];
      if (!file) return;
      setResult(null);
      preview.mutate({ file });
    },
  });

  return (
    <div className="import-screen">
      <h1 className="screen-title">Import</h1>
      <p className="lede">
        Drop a trade file. Nothing is saved until you confirm. Every assumption is listed first, and you can change any of them.
      </p>

      <div
        {...dropzone.getRootProps({
          className: `dropzone glass${dropzone.isDragActive ? " is-active" : ""}`,
        })}
        aria-label="Drop a trade file here, or press Enter to choose one"
      >
        <input {...dropzone.getInputProps()} aria-label="Trade file" />
        <p>
          {dropzone.isDragActive ? "Release to read the file" : "Drop a CSV, TSV, TXT, XLSX, XLS, or JSON file here"}
        </p>
        <p className="muted">Up to 200 MB. Files stay on this machine.</p>
      </div>

      {preview.isPending && <p className="muted" aria-live="polite">Reading the file…</p>}
      {preview.isError && (
        <p className="tone-loss" role="alert">
          {preview.error.message}
        </p>
      )}
      {!result && preview.data && <PreviewPanel preview={preview.data} onImported={setResult} />}
      {result && <CommitPanel result={result} />}
    </div>
  );
}
