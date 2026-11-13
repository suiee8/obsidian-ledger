import type { z } from "zod";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string | undefined;
  readonly details: unknown;

  constructor(status: number, message: string, code?: string, details?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

export function apiBase(): string {
  return import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000";
}

type FetchPolicy = {
  probe?: boolean;
  attempts?: number;
  timeoutMs?: number;
};

let connectionFailures = 0;
let circuitOpen = false;
const connectivityListeners = new Set<(offline: boolean) => void>();

function setCircuit(open: boolean): void {
  if (circuitOpen === open) return;
  circuitOpen = open;
  for (const listener of connectivityListeners) listener(open);
}

function recordConnectionSuccess(): void {
  connectionFailures = 0;
  setCircuit(false);
}

function recordConnectionFailure(): void {
  connectionFailures += 1;
  if (connectionFailures >= 3) setCircuit(true);
}

export function subscribeConnectivity(listener: (offline: boolean) => void): () => void {
  connectivityListeners.add(listener);
  return () => connectivityListeners.delete(listener);
}

export async function apiFetch(
  path: string,
  init?: RequestInit,
  policy: FetchPolicy = {},
): Promise<Response> {
  const method = (init?.method ?? "GET").toUpperCase();
  const canRetry = method === "GET";
  const attempts = policy.attempts ?? (canRetry ? 3 : 1);
  if (circuitOpen && !policy.probe) {
    throw new ApiError(503, "The local API is offline; waiting for a health check.", "api_offline");
  }

  let lastError: unknown = new Error("The local API request failed.");
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    const controller = new AbortController();
    const externalSignal = init?.signal;
    const abortFromCaller = () => controller.abort(externalSignal?.reason);
    if (externalSignal?.aborted) abortFromCaller();
    else externalSignal?.addEventListener("abort", abortFromCaller, { once: true });
    const timeout = globalThis.setTimeout(
      () => controller.abort(new DOMException("The local API request timed out.", "TimeoutError")),
      policy.timeoutMs ?? 120_000,
    );
    try {
      const response = await fetch(`${apiBase()}${path}`, { ...init, signal: controller.signal });
      recordConnectionSuccess();
      if (canRetry && [502, 503, 504].includes(response.status) && attempt + 1 < attempts) {
        await response.body?.cancel();
        await new Promise((resolve) =>
          globalThis.setTimeout(resolve, 150 * 2 ** attempt * (0.5 + Math.random())),
        );
        continue;
      }
      return response;
    } catch (reason) {
      lastError = reason;
      if (externalSignal?.aborted) throw reason;
      if (!canRetry || attempt + 1 >= attempts) {
        recordConnectionFailure();
        throw reason;
      }
    } finally {
      globalThis.clearTimeout(timeout);
      externalSignal?.removeEventListener("abort", abortFromCaller);
    }
    await new Promise((resolve) =>
      globalThis.setTimeout(resolve, 150 * 2 ** attempt * (0.5 + Math.random())),
    );
  }
  throw lastError;
}

async function toApiError(response: Response): Promise<ApiError> {
  let message = `Request failed (${response.status})`;
  let code: string | undefined;
  let details: unknown;
  try {
    const body: unknown = await response.json();
    if (body && typeof body === "object") {
      const record = body as Record<string, unknown>;
      const error = record.error as Record<string, unknown> | undefined;
      if (error && typeof error.message === "string") {
        message = error.message;
        code = typeof error.code === "string" ? error.code : undefined;
        details = error.details;
      } else if (typeof record.detail === "string") {
        message = record.detail;
      }
    }
  } catch {
    // The body was not JSON. Keep the status message.
  }
  return new ApiError(response.status, message, code, details);
}

/** GET or other JSON request. The response is parsed with the schema, so a shape change fails loudly. */
export async function requestJson<T>(
  path: string,
  schema: z.ZodType<T, z.ZodTypeDef, unknown>,
  init?: RequestInit,
): Promise<T> {
  const response = await apiFetch(path, init);
  if (!response.ok) {
    throw await toApiError(response);
  }
  if (response.status === 204) {
    return schema.parse(undefined);
  }
  return schema.parse((await response.json()) as unknown);
}

export function jsonBody(value: unknown): RequestInit {
  return {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(value),
  };
}
