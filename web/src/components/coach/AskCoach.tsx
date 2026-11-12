import { useState, type FormEvent, type KeyboardEvent } from "react";

import { UNAVAILABLE, useAskCoach, type AnswerChip, type AskTurn, type LlmStatus } from "../../lib/llm";

interface AskCoachProps {
  status: LlmStatus | undefined;
  statusError: string | null;
  hasTrades: boolean;
  onChip: (chip: AnswerChip) => void;
  onOpenSettings: () => void;
}

const SUGGESTIONS = ["What is my biggest leak?", "What do my strengths have in common?", "How did my risk look?"];

function Turn({ turn, onChip }: { turn: AskTurn; onChip: (chip: AnswerChip) => void }) {
  const used = turn.tools.filter((tool) => tool.ok);
  const rejected = turn.tools.filter((tool) => !tool.ok);
  return (
    <li className="ask-turn" aria-busy={turn.phase === "running"}>
      <p className="ask-question">
        <span className="visually-hidden">You asked: </span>
        {turn.question}
      </p>
      <div className="ask-answer" aria-live="polite">
        {turn.phase === "running" && (
          <p className="muted ask-status" role="status">
            {turn.status || "Working"}…
          </p>
        )}
        {turn.paragraphs.map((paragraph) => (
          <div key={paragraph.index} className={`ask-paragraph${paragraph.replaced ? " is-replaced" : ""}`}>
            <p>{paragraph.text}</p>
            {paragraph.replaced && (
              <p className="ask-note">
                The model wrote {paragraph.unmatched.join(", ")}, which is not in the results it read, so the
                computed text is shown instead.
              </p>
            )}
            {paragraph.sources.length > 0 && (
              <p className="ask-sources">
                From result {paragraph.sources.map((index) => `#${index}`).join(", ")}
              </p>
            )}
            {paragraph.chips.length > 0 && (
              <div className="trade-chips" role="group" aria-label="Trades this paragraph is about">
                {paragraph.chips.map((chip) => (
                  <button
                    key={chip.trade_key}
                    type="button"
                    className="trade-chip"
                    aria-label={`Show trade ${chip.trade_id} in the Trades table, ${chip.pnl}`}
                    onClick={() => onChip(chip)}
                  >
                    {chip.trade_id}
                  </button>
                ))}
              </div>
            )}
          </div>
        ))}
        {turn.phase === "error" && turn.error && (
          <p className={turn.error.reason === "stopped" ? "muted" : "ask-error"} role="alert">
            {turn.error.reason === "stopped"
              ? turn.error.message
              : `${UNAVAILABLE[turn.error.reason] ?? "The answer failed."} ${turn.error.message}`}
          </p>
        )}
        {turn.tools.length > 0 && (
          <details className="ask-tools">
            <summary>
              Tool results used: {used.length}
              {rejected.length > 0 ? `, ${rejected.length} rejected` : ""}
            </summary>
            <ol>
              {turn.tools.map((tool) => (
                <li key={tool.index} className={tool.ok ? "" : "is-rejected"}>
                  <code>
                    #{tool.index} {tool.name}
                  </code>{" "}
                  {tool.ok ? tool.summary : `rejected: ${tool.summary}`}
                </li>
              ))}
            </ol>
          </details>
        )}
        {turn.phase === "done" && turn.model && (
          <p className="ask-meta">
            {turn.model}, {turn.seconds?.toFixed(1)} s. Numbers were checked against the tool results.
          </p>
        )}
      </div>
    </li>
  );
}

/** "Ask the Coach": questions answered by the chosen AI provider from tool results only. */
export function AskCoach({ status, statusError, hasTrades, onChip, onOpenSettings }: AskCoachProps) {
  const { turns, ask, stop, running } = useAskCoach();
  const [draft, setDraft] = useState("");
  const ready = status?.ready === true;
  const canAsk = ready && hasTrades && !running;

  const submit = (event?: FormEvent) => {
    event?.preventDefault();
    const question = draft.trim();
    if (!question || !canAsk) return;
    setDraft("");
    void ask(question);
  };
  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  };

  let notice: string | null = null;
  if (!hasTrades) notice = "Import trades first. Nothing is sent to a model while there is no data.";
  else if (statusError) notice = `The model status could not be read: ${statusError}`;
  else if (status && !ready)
    notice = `AI answers are unavailable. ${UNAVAILABLE[status.reason ?? ""] ?? ""} ${status.message ?? ""}`.trim();

  return (
    <section className="ask-coach" aria-label="Ask the Coach">
      <p className="muted">
        {status?.ready
          ? `Answers come from ${status.model ?? "the model"} at ${status.provider_name ?? "your AI provider"}.`
          : "Answers come from the AI provider you choose in Settings."}{" "}
        It reads computed results through tools and never calculates. Every number is checked; anything that does not
        match is replaced.
      </p>
      {notice && (
        <div className="coach-state ask-unavailable" role="status">
          <p>{notice}</p>
          {hasTrades && (
            <button type="button" className="btn" onClick={onOpenSettings}>
              AI settings
            </button>
          )}
        </div>
      )}
      {turns.length > 0 && (
        <ol className="ask-turns" aria-label="Questions and answers">
          {turns.map((turn) => (
            <Turn key={turn.id} turn={turn} onChip={onChip} />
          ))}
        </ol>
      )}
      <form className="ask-form" onSubmit={submit}>
        <label htmlFor="ask-input">Your question</label>
        <textarea
          id="ask-input"
          rows={3}
          maxLength={500}
          value={draft}
          placeholder="What is my biggest leak?"
          disabled={!ready || !hasTrades}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={onKeyDown}
        />
        <div className="row-actions">
          {running ? (
            <button type="button" className="btn btn-danger" onClick={stop}>
              Stop
            </button>
          ) : (
            <button type="submit" className="btn btn-primary" disabled={!canAsk || draft.trim() === ""}>
              Ask
            </button>
          )}
          {!running && ready && hasTrades && turns.length === 0 && (
            <div className="ask-suggestions" role="group" aria-label="Example questions">
              {SUGGESTIONS.map((text) => (
                <button key={text} type="button" className="chip chip-button" onClick={() => setDraft(text)}>
                  {text}
                </button>
              ))}
            </div>
          )}
        </div>
      </form>
    </section>
  );
}
