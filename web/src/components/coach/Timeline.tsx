import type { StepState } from "../../lib/coach";

interface TimelineProps {
  steps: StepState[];
}

const STATUS_TEXT = { waiting: "waiting", running: "running", done: "done" } as const;

/** The six report steps. Reading to Cleaning describe the import. The rest run now. */
export function Timeline({ steps }: TimelineProps) {
  const active = steps.find((step) => step.status === "running");
  return (
    <section aria-label="Report steps" className="coach-timeline">
      <ol>
        {steps.map((step) => (
          <li key={step.key} className={`step step-${step.status}`}>
            <span className="step-dot" aria-hidden="true" />
            <span className="step-label">{step.label}</span>
            <span className="visually-hidden">: {STATUS_TEXT[step.status]}</span>
            {step.detail && <span className="step-detail">{step.detail}</span>}
            {step.status === "done" && step.seconds > 0.005 && (
              <span className="step-time">{step.seconds.toFixed(2)} s</span>
            )}
          </li>
        ))}
      </ol>
      <p className="visually-hidden" role="status" aria-live="polite">
        {active ? `${active.label} is running.` : ""}
      </p>
    </section>
  );
}
