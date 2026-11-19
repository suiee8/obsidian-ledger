import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    document.documentElement.dataset.shader = "off";
  });
});

test("the black frame is 1.2 cm on all four sides with concentric corners", async ({ page }) => {
  await page.goto("/");
  for (const width of [1440, 900, 390, 320]) {
    await page.setViewportSize({ width, height: 900 });
    if (width <= 800) await expect(page.getByRole("button", { name: "Filters", exact: true })).toBeVisible();
    const geometry = await page.locator(".shell").evaluate((shell) => {
      const inner = getComputedStyle(shell, "::after");
      const outer = getComputedStyle(shell, "::before");
      const header = shell.querySelector<HTMLElement>(".topbar")!;
      const coach = header.querySelector<HTMLElement>(".coach-toggle")!;
      const brand = header.querySelector<HTMLElement>(".mark")!;
      const bounds = header.getBoundingClientRect();
      const toggle = coach.getBoundingClientRect();
      return {
        edges: [inner.top, inner.right, inner.bottom, inner.left].map(parseFloat),
        color: getComputedStyle(shell, "::after").boxShadow,
        innerRadius: parseFloat(inner.borderTopLeftRadius),
        innerRadii: [inner.borderTopLeftRadius, inner.borderTopRightRadius, inner.borderBottomRightRadius, inner.borderBottomLeftRadius],
        outerRadius: parseFloat(outer.borderTopLeftRadius),
        headerHeight: bounds.height,
        topGap: toggle.top - bounds.top,
        bottomGap: bounds.bottom - toggle.bottom,
        leftInset: brand.getBoundingClientRect().left - bounds.left,
        rightInset: bounds.right - toggle.right,
        pageWidth: document.documentElement.scrollWidth,
      };
    });
    const edge = (1.2 * 96) / 2.54;
    for (const side of geometry.edges) expect(Math.abs(side - edge)).toBeLessThan(0.5);
    expect(geometry.color).toContain("rgb(0, 0, 0)");
    expect(new Set(geometry.innerRadii).size).toBe(1);
    expect(Math.abs(geometry.outerRadius - geometry.innerRadius - edge)).toBeLessThan(0.5);
    expect(Math.abs(geometry.headerHeight - edge)).toBeLessThan(0.5);
    expect(Math.abs(geometry.topGap - geometry.bottomGap)).toBeLessThan(0.5);
    expect(Math.abs(geometry.leftInset - geometry.rightInset)).toBeLessThan(1);
    expect(geometry.pageWidth).toBe(width);
  }
});
test("the cursor stays visible over Coach and native form controls keep their cursor", async ({ page }) => {
  await page.goto("/");
  const arrow = page.locator(".cursor-arrow");
  const trail = page.locator(".cursor-trail");

  await page.getByRole("button", { name: "Coach", exact: true }).click();
  const coach = page.getByRole("complementary", { name: "Coach" });
  const title = coach.getByRole("heading", { name: "Review of your trades" });
  const box = await title.boundingBox();
  if (!box) throw new Error("Coach heading is missing");
  const x = Math.round(box.x + 10);
  const y = Math.round(box.y + box.height / 2);

  await page.mouse.move(x, y, { steps: 8 });
  await expect(arrow).toBeVisible();
  await expect(trail).toBeVisible();
  expect(await arrow.boundingBox()).toMatchObject({ x: x - 3, y: y - 2 });
  expect(await arrow.evaluate((element) => element.parentElement === document.body)).toBe(true);
  await expect(title).toHaveCSS("cursor", "none");

  await coach.getByRole("tab", { name: "Ask the Coach" }).click();
  const input = coach.getByLabel("Your question");
  await input.hover();
  await expect(arrow).toBeHidden();
  await expect(input).not.toHaveCSS("cursor", "none");

  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.mouse.move(x, y);
  await expect(arrow).toBeHidden();
  await expect(trail).toBeHidden();
  await expect(title).not.toHaveCSS("cursor", "none");
});

test("the black shell animates on click and the footer opens the requested contacts", async ({ page }) => {
  await page.goto("/");
  const rail = page.getByRole("navigation", { name: "Primary" });
  const top = page.locator(".topbar");
  await expect(rail).toHaveCSS("background-color", "rgb(0, 0, 0)");
  await expect(top).toHaveCSS("background-color", "rgb(0, 0, 0)");
  await expect(page.locator(".shell-flip-brand > span").first()).toHaveCSS("animation-name", "shell-brand-flip");
  for (const button of [rail.getByRole("button", { name: "Analytics" }), top.getByRole("button", { name: "Coach" })]) {
    expect(await button.evaluate((element: HTMLButtonElement) => {
      element.click();
      return getComputedStyle(element, "::before").animationName;
    })).toBe("shell-liquid-click");
  }

  const socials = page.getByRole("navigation", { name: "Social links" });
  await expect(socials.getByRole("link", { name: "GitHub" })).toHaveAttribute("href", "https://github.com/suiee8");
  await expect(socials.getByRole("link", { name: "LinkedIn" })).toHaveAttribute("href", "https://www.linkedin.com/in/madhvikpanchal");
  await expect(socials.getByRole("link", { name: "Email" })).toHaveAttribute("href", "mailto:themadhvik@gmail.com");
  await socials.getByRole("link", { name: "LinkedIn" }).focus();
  await expect.poll(() => socials.locator(".shell-social-card").first().evaluate(
    (card) => new DOMMatrix(getComputedStyle(card).transform).m11,
  )).toBeCloseTo(-1, 2);
});
