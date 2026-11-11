import { describe, expect, it } from "vitest";

import { healthSchema } from "./health";
import { cn } from "./cn";

describe("cn", () => {
  it("lets the later tailwind class win", () => {
    expect(cn("px-2", "px-4")).toBe("px-4");
  });
});

describe("healthSchema", () => {
  it("accepts the API payload", () => {
    expect(healthSchema.parse({ status: "ok", service: "obsidian-ledger" })).toEqual({
      status: "ok",
      service: "obsidian-ledger",
    });
  });

  it("rejects a payload that invents a status", () => {
    expect(() => healthSchema.parse({ status: "fine", service: "x" })).toThrow();
  });
});
