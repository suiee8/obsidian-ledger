import { describe, expect, it } from "vitest";

import { EMPTY_FILTERS, filterParams, hasActiveFilters } from "./filters";

describe("filter query string", () => {
  it("is empty when nothing is selected", () => {
    expect(filterParams(EMPTY_FILTERS)).toBe("");
    expect(hasActiveFilters(EMPTY_FILTERS)).toBe(false);
  });

  it("repeats list filters once per value, the way the API reads them", () => {
    const params = filterParams({ ...EMPTY_FILTERS, symbols: ["AAPL", "MSFT"], dateFrom: "2026-01-01" });
    expect(params).toBe("date_from=2026-01-01&symbol=AAPL&symbol=MSFT");
  });

  it("encodes free-text tags safely", () => {
    const params = filterParams({ ...EMPTY_FILTERS, tag: "fomo & revenge" });
    expect(new URLSearchParams(params).get("tag")).toBe("fomo & revenge");
  });
});
