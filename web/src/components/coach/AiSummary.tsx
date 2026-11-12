import { useState } from "react";

import { UNAVAILABLE, useAiSummary, type LlmStatus } from "../../lib/llm";

interface AiSummaryProps {
  reportId: string;
  status: LlmStatus | undefined;
  statusPending: boolean;
}

/** The optional plain-language summary. The computed report below it is always the source. */
export function AiSummary({ reportId, status, statusPending }: AiSummaryProps) {
  const ready = status?.ready === true;
  // Asked for, not automatic: on a computer without a graphics card one summary can take minutes,
  // and it would hold the model while you ask a question.
  const [requested, setRequested] = useState(false);
  const query = useAiSummary(reportId, ready && requested);
  const data = query.data;
  const limit = status?.answer_seconds ?? 30;

  let body;
  if (statusPending) {
    body = <p className="muted">Reading the AI settings…</p>;
  } else if (!ready) {
    const reason = UNAVAILABLE[status?.reason ?? "no_provider"] ?? "";
    body = (
      <p className="muted" role="status">
        AI summary unavailable. {reason} The computed report below is complete without it.
      </p>
    );
  } else if (!requested && !data) {
    body = (
      <div className="row-actions">
        <button type="button" className="btn" onClick={() => setRequested(true)}>
          Write an AI summary
        </button>
        <span className="muted">
          With {status.model} at {status.provider_name}, up to {limit} s. Sends computed results only. The
          report below is already complete.
        </span>
      </div>
    );
  } else if (query.isPending || query.isFetching) {
    body = (
      <p className="muted" role="status">
        Writing a summary with {status.model}, up to {limit} s…
      </p>
    );
  } else if (query.isError || !data) {
    body = (
      <p className="muted" role="status">
        AI summary unavailable. {query.error?.message ?? ""} The computed report below is complete without it.
      </p>
    );
  } else if (data.status === "unavailable") {
    body = (
      <p className="muted" role="status">
        AI summary unavailable. {UNAVAILABLE[data.reason] ?? ""} {data.message} The computed report below is
        complete without it.
      </p>
    );
  } else {
    const replaced = data.paragraphs.filter((paragraph) => paragraph.replaced).length;
    body = (
      <>
        <p className="ai-headline">{data.headline}</p>
        {data.paragraphs.map((paragraph) => (
          <p key={paragraph.section} className={paragraph.replaced ? "is-replaced" : undefined}>
            <strong>{paragraph.title}.</strong> {paragraph.text}
          </p>
        ))}
        <p className="ask-meta">
          {data.model}, {data.seconds.toFixed(1)} s, from {data.tools_used.map((tool) => tool.name).join(", ")}.{" "}
          {replaced > 0
            ? `${replaced} paragraph${replaced === 1 ? " was" : "s were"} replaced with the computed text because a number did not match.`
            : "Every number matched a computed figure."}
        </p>
      </>
    );
  }

  return (
    <section className="coach-ai" aria-label="AI summary">
      <h3>
        AI summary <span className="confidence confidence-low">optional</span>
      </h3>
      {body}
    </section>
  );
}
