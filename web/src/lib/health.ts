import { z } from "zod";

export const healthSchema = z.object({
  status: z.literal("ok"),
  service: z.string(),
});

export type Health = z.infer<typeof healthSchema>;

export function apiBase(): string {
  return import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000";
}

export async function fetchHealth(signal: AbortSignal): Promise<Health> {
  const response = await fetch(`${apiBase()}/health`, { signal });
  if (!response.ok) {
    throw new Error(`Health check failed (${response.status})`);
  }
  return healthSchema.parse(await response.json());
}
