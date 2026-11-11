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
  const response = await fetch(`${apiBase()}${path}`, init);
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
