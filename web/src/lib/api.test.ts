import { afterEach, describe, expect, it, vi } from "vitest";

import { apiFetch } from "./api";

describe("API fetch policy", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("retries a failed GET and returns the first successful response", async () => {
    vi.useFakeTimers();
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockRejectedValueOnce(new TypeError("network unavailable"))
      .mockResolvedValueOnce(new Response(null, { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const result = apiFetch("/health", undefined, { timeoutMs: 1_000 });
    await vi.advanceTimersByTimeAsync(500);
    await expect(result).resolves.toMatchObject({ status: 200 });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("does not retry POST requests", async () => {
    const fetchMock = vi.fn<typeof fetch>().mockRejectedValue(new TypeError("network unavailable"));
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      apiFetch("/api/imports/commit", { method: "POST" }, { timeoutMs: 1_000 }),
    ).rejects.toThrow("network unavailable");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
