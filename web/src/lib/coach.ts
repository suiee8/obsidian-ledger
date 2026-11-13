import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";

import { apiBase, requestJson } from "./api";
import { CoachReportSchema, type CoachReport } from "./schemas";

export const COACH_STEPS = [
  { key: "reading", label: "Reading" },
  { key: "mapping", label: "Mapping" },
  { key: "cleaning", label: "Cleaning" },
  { key: "computing", label: "Computing" },
  { key: "finding", label: "Finding leaks" },
  { key: "writing", label: "Writing report" },
] as const;

export type StepKey = (typeof COACH_STEPS)[number]["key"];
export type StepStatus = "waiting" | "running" | "done";
export interface StepState {
  key: StepKey;
  label: string;
  status: StepStatus;
  detail: string;
  seconds: number;
}

export type CoachPhase = "idle" | "running" | "ready" | "error";

export interface CoachRun {
  phase: CoachPhase;
  steps: StepState[];
  report: CoachReport | null;
  error: string | null;
  rerun: () => void;
}

const initialSteps = (): StepState[] =>
  COACH_STEPS.map((step) => ({ ...step, status: "waiting", detail: "", seconds: 0 }));

interface StepEvent {
  step: string;
  status: "running" | "done" | "error";
  label?: string;
  detail?: string;
  seconds?: number;
  report_id?: string;
}

function isStepEvent(value: unknown): value is StepEvent {
  return typeof value === "object" && value !== null && "step" in value && "status" in value;
}

/**
 * Runs the Coach for a filter string and streams its step timeline.
 *
 * `trigger` is any value that should start a new run when it changes (the drawer passes the
 * filter string and the run token). `enabled` is false while the drawer is closed, so a closed
 * drawer makes no request.
 */
export function useCoachRun(params: string, trigger: number, enabled: boolean): CoachRun {
  const client = useQueryClient();
  const [phase, setPhase] = useState<CoachPhase>("idle");
  const [steps, setSteps] = useState<StepState[]>(initialSteps);
  const [report, setReport] = useState<CoachReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [forced, setForced] = useState(0);
  const forceNext = useRef(false);

  const rerun = useCallback(() => {
    forceNext.current = true;
    setForced((value) => value + 1);
  }, []);

  useEffect(() => {
    if (!enabled) return undefined;
    const force = forceNext.current;
    forceNext.current = false;
    setPhase("running");
    setSteps(initialSteps());
    setError(null);
    const query = [params, force ? "force=true" : ""].filter(Boolean).join("&");
    const stream = new EventSource(`${apiBase()}/api/coach/stream${query ? `?${query}` : ""}`);
    let finished = false;
    let opened = false;
    stream.addEventListener("open", () => {
      opened = true;
    });

    const apply = (event: StepEvent) => {
      setSteps((current) =>
        current.map((step) =>
          step.key === event.step
            ? {
                ...step,
                status: event.status === "done" ? "done" : "running",
                detail: event.detail || step.detail,
                seconds: event.seconds ?? step.seconds,
              }
            : step,
        ),
      );
    };

    stream.addEventListener("step", (message) => {
      const parsed: unknown = JSON.parse((message as MessageEvent<string>).data);
      if (isStepEvent(parsed)) apply(parsed);
    });
    stream.addEventListener("done", (message) => {
      finished = true;
      stream.close();
      const parsed: unknown = JSON.parse((message as MessageEvent<string>).data);
      if (!isStepEvent(parsed) || !parsed.report_id) return;
      const id = parsed.report_id;
      void client
        .fetchQuery({
          queryKey: ["coach-report", id],
          queryFn: () => requestJson(`/api/coach/reports/${id}`, CoachReportSchema),
          staleTime: Infinity,
        })
        .then((loaded) => {
          setReport(loaded);
          setPhase("ready");
        })
        .catch((reason: unknown) => {
          setError(reason instanceof Error ? reason.message : "The report could not be read.");
          setPhase("error");
        });
    });
    stream.addEventListener("error", (message) => {
      if (finished) return;
      // A named `error` event carries a message. A dropped connection has no data. The browser
      // reconnects a connection that dropped mid-run, but one that never opened means the API is
      // unreachable, so that fails at once instead of retrying silently forever.
      const data = (message as MessageEvent<string | undefined>).data;
      if (opened && typeof data !== "string" && stream.readyState === EventSource.CONNECTING) {
        return;
      }
      let text = "The Coach could not reach the local API.";
      if (typeof data === "string" && data) {
        const parsed: unknown = JSON.parse(data);
        if (typeof parsed === "object" && parsed !== null && "detail" in parsed) {
          text = String((parsed as { detail: unknown }).detail);
        }
      }
      finished = true;
      stream.close();
      setError(text);
      setPhase("error");
    });

    return () => {
      finished = true;
      stream.close();
    };
    // `forced` restarts the run. `trigger` restarts it when the filters or a run request change.
  }, [client, enabled, params, trigger, forced]);

  return { phase, steps, report, error, rerun };
}
