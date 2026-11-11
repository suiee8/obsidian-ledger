import { describe, expect, it } from "vitest";

import { fmtDateTime, fmtDay, fmtDuration, fmtMoney, fmtPercent, fmtR } from "./format";

describe("money and ratios", () => {
  it("shows a sign on money and dashes for missing values", () => {
    expect(fmtMoney(120.95)).toBe("+$120.95");
    expect(fmtMoney(-37.25)).toBe("-$37.25");
    expect(fmtMoney(null)).toBe("—");
    expect(fmtMoney(Number.NaN)).toBe("—");
  });

  it("formats win rate as a percentage with one decimal", () => {
    expect(fmtPercent(0.5)).toBe("50.0%");
    expect(fmtPercent(undefined)).toBe("—");
  });

  it("signs R multiples", () => {
    expect(fmtR(1.284)).toBe("+1.28 R");
    expect(fmtR(-0.5)).toBe("-0.50 R");
  });
});

describe("durations and dates", () => {
  it("picks the two largest units", () => {
    expect(fmtDuration(5601)).toBe("1h 33m");
    expect(fmtDuration(90)).toBe("1m 30s");
    expect(fmtDuration(200_000)).toBe("2d 7h");
    expect(fmtDuration(null)).toBe("—");
  });

  it("labels trade times as UTC", () => {
    expect(fmtDateTime("2026-01-06T14:32:01Z")).toContain("UTC");
    expect(fmtDateTime("not a date")).toBe("—");
  });

  it("formats a calendar day in UTC", () => {
    expect(fmtDay("2026-01-06")).toContain("2026");
  });
});
