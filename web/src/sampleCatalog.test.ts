import { describe, expect, it } from "vitest";

import { sampleFiles } from "./sampleCatalog";

describe("sampleFiles", () => {
  it("lists the phase 0 fixtures", () => {
    const names = sampleFiles.map((sample) => sample.file);
    expect(names).toContain("mt5_statement.csv");
    expect(names).toContain("tradingview_trades.csv");
    expect(names).toContain("ibkr_executions.csv");
    expect(names).toContain("messy_journal.csv");
    expect(names).toContain("synthetic_100k.csv");
  });
});
