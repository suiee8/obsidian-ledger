import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

const css = readFileSync(resolve(__dirname, "index.css"), "utf8");

/** CSS with the `:root { ... }` token blocks removed. Colors may only be defined inside them. */
function withoutTokenBlocks(source: string): string {
  return source.replace(/^:root[^{]*\{[^}]*\}/gm, "");
}

describe("index.css colors", () => {
  it("has no color literal outside the token blocks", () => {
    const rest = withoutTokenBlocks(css);
    const literals = rest.match(/#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(/g) ?? [];
    expect(literals).toEqual([]);
  });

  it("names every token by role, not by value", () => {
    const byValue = css.match(/--color-(?:rgba-|[0-9a-f]{6}\b)[\w-]*/g) ?? [];
    expect(byValue).toEqual([]);
  });

  it("uses the P&L color tokens only for P&L", () => {
    // Status and confidence colors have their own tokens. The P&L pair is for profit and loss.
    const uses = [...withoutTokenBlocks(css).matchAll(/([^{}]+)\{[^{}]*var\(--pnl-(?:profit|loss)\)/g)];
    const selectors = uses.map((match) => match[1]?.trim() ?? "");
    for (const selector of selectors) {
      expect(selector).toMatch(/tone-|pnl|profit|loss|gain|calendar|heat|chart|legend|bar|cell/i);
    }
  });

  it("preserves the original global focus-visible outline", () => {
    expect(css).toContain(
      ":focus-visible {\n  outline: 2px solid var(--palette-royal400);\n  outline-offset: 2px;\n}",
    );
    expect(css).not.toMatch(
      /(?:input|select|textarea|button|a):focus-visible\s*,[\s\S]*?\{\s*outline-color:/,
    );
  });
});
