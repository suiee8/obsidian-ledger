import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    document.documentElement.dataset.shader = "off";
  });
});

test("the black frame has equal sides and balanced header insets", async ({ page }) => {
  await page.goto("/");
  for (const width of [1440, 390, 320]) {
    await page.setViewportSize({ width, height: 900 });
    if (width <= 800) await expect(page.getByRole("button", { name: "Filters", exact: true })).toBeVisible();
    const geometry = await page.locator(".shell").evaluate((shell) => {
      const style = getComputedStyle(shell);
      const header = shell.querySelector<HTMLElement>(".topbar")!;
      const brand = header.querySelector<HTMLElement>(".brand")!;
      const coach = header.querySelector<HTMLElement>(".coach-toggle")!;
      const opening = getComputedStyle(shell.querySelector("main")!);
      const bounds = header.getBoundingClientRect();
      return {
        edges: [style.borderTopWidth, style.borderRightWidth, style.borderBottomWidth, style.borderLeftWidth],
        color: style.borderTopColor,
        innerRadius: parseFloat(opening.borderRadius),
        outerRadius: parseFloat(style.borderRadius),
        leftInset: brand.getBoundingClientRect().left - bounds.left,
        rightInset: bounds.right - coach.getBoundingClientRect().right,
        pageWidth: document.documentElement.scrollWidth,
      };
    });
    const edge = parseFloat(geometry.edges[0]!);
    expect(geometry.edges.every((width) => width === geometry.edges[0])).toBe(true);
    expect(Math.abs(edge - (1.2 * 96) / 2.54)).toBeLessThan(1);
    expect(geometry.color).toBe("rgb(0, 0, 0)");
    expect(Math.abs(geometry.outerRadius - geometry.innerRadius - edge)).toBeLessThan(1);
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
