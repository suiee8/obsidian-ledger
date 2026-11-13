import { z } from "zod";

import { apiBase, apiFetch } from "./api";

const livenessSchema = z.object({
  status: z.literal("ok"),
  service: z.string(),
  version: z.string(),
});

const readinessSchema = z.object({
  status: z.enum(["ready", "degraded", "down"]),
  checks: z.object({ ai: z.enum(["configured", "not_configured", "unavailable", "unknown"]) }),
});

export const healthSchema = livenessSchema;

export type Health = {
  version: string;
  status: "ready" | "degraded" | "down";
  ai: "configured" | "not_configured" | "unavailable" | "unknown";
};

export async function fetchHealth(signal: AbortSignal): Promise<Health> {
  const response = await apiFetch("/health", { signal }, { probe: true, attempts: 1, timeoutMs: 5000 });
  if (!response.ok) {
    throw new Error(`Health check failed (${response.status})`);
  }
  const live = livenessSchema.parse(await response.json());
  const readyResponse = await apiFetch(
    "/health/ready",
    { signal },
    { probe: true, attempts: 1, timeoutMs: 5000 },
  );
  const ready = readinessSchema.parse(await readyResponse.json());
  return { version: live.version, status: ready.status, ai: ready.checks.ai };
}

export { apiBase };
