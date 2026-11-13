import { useEffect, useRef, useState } from "react";

import { fetchHealth, type Health } from "./health";
import { subscribeConnectivity } from "./api";

export type HealthState =
  | { status: "loading" }
  | { status: "online"; health: Health }
  | { status: "degraded"; health: Health }
  | { status: "ai-unavailable"; health: Health }
  | { status: "version-mismatch"; health: Health }
  | { status: "offline" };

const EXPECTED_API_VERSION = import.meta.env.VITE_API_VERSION ?? "0.1.0";

export function useHealth(): { state: HealthState; refresh: () => void } {
  const [nonce, setNonce] = useState(0);
  const [probe, setProbe] = useState(0);
  const [state, setState] = useState<HealthState>({ status: "loading" });
  const failures = useRef(0);

  useEffect(() => {
    const controller = new AbortController();
    let timer: number | undefined;
    fetchHealth(controller.signal)
      .then((health) => {
        if (!controller.signal.aborted) {
          failures.current = 0;
          if (health.version !== EXPECTED_API_VERSION) {
            setState({ status: "version-mismatch", health });
          } else if (health.status === "down" || health.status === "degraded") {
            setState({ status: "degraded", health });
          } else if (health.ai === "unavailable") {
            setState({ status: "ai-unavailable", health });
          } else {
            setState({ status: "online", health });
          }
        }
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          setState({ status: "offline" });
          const delay = Math.min(30_000, 1_000 * 2 ** failures.current);
          failures.current += 1;
          timer = window.setTimeout(() => setProbe((value) => value + 1), delay);
        }
      });
    return () => {
      controller.abort();
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [nonce, probe]);

  useEffect(
    () =>
      subscribeConnectivity((offline) => {
        if (offline) setState({ status: "offline" });
      }),
    [],
  );

  return {
    state,
    refresh: () => setNonce((value) => value + 1),
  };
}
