import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { importSample } from "./helpers";

const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];

type Screen = { name: string; open: (page: Page) => Promise<void> };

const SCREENS: Screen[] = [
  {
    name: "dashboard",
    open: async (page) => {
      await page.goto("/");
      await expect(page.locator(".chart-equity canvas")).toBeVisible();
    },
  },
  {
    name: "trades",
    open: async (page) => {
      await page.goto("/");
      await page.getByRole("button", { name: "Trades", exact: true }).click();
      await expect(page.locator(".grid-body").first()).toBeVisible();
    },
  },
  {
    name: "import",
    open: async (page) => {
      await page.goto("/");
      await page.getByRole("button", { name: "Import", exact: true }).click();
      await expect(page.locator('input[type="file"]')).toBeAttached();
    },
  },
  {
    name: "samples",
    open: async (page) => {
      await page.goto("/");
      await page.getByRole("button", { name: "Sample files", exact: true }).click();
      await expect(page.getByRole("heading", { name: "Sample files" })).toBeVisible();
    },
  },
  {
    name: "analytics",
    open: async (page) => {
      await page.goto("/");
      await page.getByRole("button", { name: "Analytics", exact: true }).click();
      await expect(page.locator(".chart-scatter canvas").first()).toBeVisible();
      await expect(page.getByRole("region", { name: "Monte Carlo fan" }).locator("canvas")).toBeVisible();
    },
  },
  {
    name: "behavior",
    open: async (page) => {
      await page.goto("/");
      await page.getByRole("button", { name: "Behavior", exact: true }).click();
      await expect(page.getByRole("region", { name: "Overtrading timeline" }).locator("canvas")).toBeVisible();
      await expect(page.getByRole("region", { name: "Discipline Score" }).getByRole("meter").first()).toBeVisible();
    },
  },
  {
    name: "simulator with a result",
    open: async (page) => {
      await page.goto("/");
      await page.getByRole("button", { name: "Simulator", exact: true }).click();
      await page.getByLabel("Most trades per day").fill("3");
      await expect(page.getByRole("region", { name: "Before and after table" })).toBeVisible();
      await expect(page.getByText(/with a 95% interval of/)).toBeVisible();
    },
  },
  {
    name: "settings",
    open: async (page) => {
      await page.goto("/");
      await page.getByRole("button", { name: "Settings", exact: true }).click();
      await expect(page.getByRole("region", { name: "Wipe everything" })).toBeVisible();
    },
  },
];

async function expectNoViolations(page: Page, include?: string) {
  let builder = new AxeBuilder({ page }).withTags(WCAG_TAGS);
  if (include) builder = builder.include(include);
  const results = await builder.analyze();
  const problems = results.violations.map((violation) => {
    const sample = violation.nodes
      .slice(0, 2)
      .map((node) => node.target.join(" "))
      .join(" | ");
    return `${violation.id} (${violation.nodes.length}) ${sample}: ${violation.help}`;
  });
  expect(problems).toEqual([]);
}

// Every screen at desktop width and at phone width, where the filters sit behind a button.
for (const width of [1440, 390]) {
  test.describe(`at ${width} px`, () => {
    test.use({ viewport: { width, height: 900 } });

    for (const screen of SCREENS) {
      test(`${screen.name} has no WCAG 2.1 AA violations`, async ({ page, request }) => {
        await importSample(request);
        await screen.open(page);
        await expectNoViolations(page);
      });
    }

    test("the Coach drawer has no WCAG 2.1 AA violations", async ({ page, request }) => {
      await importSample(request);
      await page.goto("/");
      await page.getByRole("button", { name: "Coach", exact: true }).click();
      await expect(page.getByRole("complementary", { name: "Coach" })).toHaveAttribute(
        "data-phase",
        "ready",
      );
      await expectNoViolations(page, ".coach-drawer");
    });
  });
}

test.describe("filter sheet at 390 px", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("traps focus, has no violations, closes with Escape, and returns focus to its button", async ({
    page,
    request,
  }) => {
    await importSample(request);
    await page.goto("/");
    const button = page.getByRole("button", { name: "Filters", exact: true });
    await button.click();
    const sheet = page.getByRole("dialog", { name: "Filters" });
    await expect(sheet).toBeVisible();
    await expect(sheet.getByLabel("Add symbol filter")).toBeVisible();
    await expectNoViolations(page);

    // Tab more times than the sheet has controls. Focus must stay inside the sheet every time.
    for (let step = 0; step < 40; step++) {
      await page.keyboard.press("Tab");
      const inside = await page.evaluate(() =>
        Boolean(document.activeElement?.closest('[role="dialog"][aria-label="Filters"]')),
      );
      expect(inside, `focus left the sheet on Tab ${step + 1}`).toBe(true);
    }

    await page.keyboard.press("Escape");
    await expect(sheet).toHaveCount(0);
    await expect(button).toBeFocused();
  });
});
