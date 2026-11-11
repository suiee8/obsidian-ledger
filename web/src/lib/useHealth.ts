import { useEffect, useState } from "react";

import { fetchHealth, type Health } from "./health";

export type HealthState =
  | { status: "loading" }
  | { status: "online"; health: Health }
  | { status: "offline" };

export function useHealth(): { state: HealthState; refresh: () => void } {
  const [nonce, setNonce] = useState(0);
  const [state, setState] = useState<HealthState>({ status: "loading" });

  useEffect(() => {
    const controller = new AbortController();
    setState({ status: "loading" });
    fetchHealth(controller.signal)
      .then((health) => {
        if (!controller.signal.aborted) {
          setState({ status: "online", health });
        }
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          setState({ status: "offline" });
        }
      });
    return () => controller.abort();
  }, [nonce]);

  return {
    state,
    refresh: () => setNonce((value) => value + 1),
  };
}
