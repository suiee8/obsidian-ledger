/* global document, requestAnimationFrame -- used inside page.evaluate, which runs in the browser */
// Browser measurements for the benchmark: dashboard readiness, filter-change latency, and
// table scroll frame rate. Expects the API to hold the dataset and the web preview to be running.
// Prints one JSON object as the last line of stdout. Uses the installed Microsoft Edge.
//
//   node web/scripts/bench-ui.mjs http://127.0.0.1:5173/
//
// The table is scrolled at two speeds. "Wheel" is about 1.5 rows per frame, like a mouse wheel
// or trackpad. "Fast" is 10 rows per frame, like dragging the scroll bar, so the table has to
// fetch a new 200-row block every 20 frames. Both scroll far enough to leave the first block, and
// after each one we count how many rows on screen show real data and not a placeholder.

import { chromium } from "@playwright/test";

const url = process.argv[2] ?? "http://127.0.0.1:5173/";
const SCROLL_MS = 3000;
const SCENARIOS = [
  { name: "wheel", step: 60 },
  { name: "fast", step: 400 },
];

const browser = await chromium.launch({ channel: "msedge", headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });

  const started = Date.now();
  await page.goto(url, { waitUntil: "domcontentloaded" });
  await page.waitForSelector(".kpi-strip", { timeout: 120_000 });
  await page.waitForSelector(".chart-equity canvas", { timeout: 120_000 });
  const dashboardReady = (Date.now() - started) / 1000;

  const filterSelect = page.getByLabel("Add symbol filter");
  const responseDone = page.waitForResponse(
    (response) => response.url().includes("/api/dashboard") && response.url().includes("symbol=NVDA"),
    { timeout: 120_000 },
  );
  const changeStarted = Date.now();
  await filterSelect.selectOption("NVDA");
  await responseDone;
  await page.waitForSelector('.filter-group .chip-button:has-text("NVDA")');
  const filterReady = (Date.now() - changeStarted) / 1000;

  await page.getByRole("button", { name: "Remove symbol filter NVDA" }).click().catch(() => undefined);
  await page.waitForLoadState("networkidle");

  await page.getByRole("button", { name: "Trades", exact: true }).click();
  const tableStarted = Date.now();
  await page.waitForSelector(".grid-body", { timeout: 120_000 });
  const tableReady = (Date.now() - tableStarted) / 1000;

  const results = {};
  for (const scenario of SCENARIOS) {
    await page.evaluate(() => {
      const container = document.querySelector(".grid-scroll");
      if (container) container.scrollTop = 0;
    });
    await page.waitForTimeout(800);
    results[scenario.name] = await page.evaluate(
      ({ durationMs, step }) =>
        new Promise((resolve) => {
          const container = document.querySelector(".grid-scroll");
          if (!container) {
            resolve({ error: "no .grid-scroll element" });
            return;
          }
          const longTasks = [];
          const observer = new PerformanceObserver((list) => {
            for (const entry of list.getEntries()) longTasks.push(entry.duration);
          });
          observer.observe({ entryTypes: ["longtask"] });
          const stamps = [];
          const begin = performance.now();
          const tick = (now) => {
            stamps.push(now);
            container.scrollTop += step;
            if (now - begin < durationMs) {
              requestAnimationFrame(tick);
              return;
            }
            observer.disconnect();
            const intervals = [];
            for (let i = 1; i < stamps.length; i += 1) intervals.push(stamps[i] - stamps[i - 1]);
            intervals.sort((a, b) => a - b);
            const elapsed = (stamps[stamps.length - 1] - stamps[0]) / 1000;
            resolve({
              frames: stamps.length,
              fps: (stamps.length - 1) / elapsed,
              p50_frame_ms: intervals[Math.floor(intervals.length * 0.5)] ?? 0,
              p95_frame_ms: intervals[Math.floor(intervals.length * 0.95)] ?? 0,
              worst_frame_ms: intervals[intervals.length - 1] ?? 0,
              long_tasks: longTasks.length,
              longest_task_ms: longTasks.length ? Math.max(...longTasks) : 0,
              scrolled_px: container.scrollTop,
            });
          };
          requestAnimationFrame(tick);
        }),
      { durationMs: SCROLL_MS, step: scenario.step },
    );
    await page.waitForTimeout(1500);
    results[scenario.name].loaded = await page.evaluate(() => {
      const rows = [...document.querySelectorAll(".grid-body")];
      return { rows: rows.length, filled: rows.filter((row) => row.querySelector(".cell")).length };
    });
  }

  // The ceiling: the same scroll loop over an empty container. Headless browsers on some machines
  // cannot reach 60 fps even then, and the table cannot beat that number.
  const empty = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  await empty.setContent(
    "<div id=s style='height:600px;overflow:auto'><div style='height:400000px'></div></div>",
  );
  const ceiling = await empty.evaluate(
    () =>
      new Promise((resolve) => {
        const el = document.querySelector("#s");
        const stamps = [];
        const begin = performance.now();
        const tick = (now) => {
          stamps.push(now);
          el.scrollTop += 60;
          if (now - begin < 2500) requestAnimationFrame(tick);
          else resolve((stamps.length - 1) / ((stamps[stamps.length - 1] - stamps[0]) / 1000));
        };
        requestAnimationFrame(tick);
      }),
  );
  await empty.close();

  // The cost the table itself adds to each frame, from the browser's own counters.
  const session = await page.context().newCDPSession(page);
  await session.send("Performance.enable");
  const counters = async () => {
    const { metrics } = await session.send("Performance.getMetrics");
    return Object.fromEntries(metrics.map((metric) => [metric.name, metric.value]));
  };
  await page.evaluate(() => {
    const container = document.querySelector(".grid-scroll");
    if (container) container.scrollTop = 0;
  });
  await page.waitForTimeout(800);
  const before = await counters();
  const probeFrames = await page.evaluate(
    () =>
      new Promise((resolve) => {
        const container = document.querySelector(".grid-scroll");
        let count = 0;
        const begin = performance.now();
        const tick = (now) => {
          count += 1;
          container.scrollTop += 60;
          if (now - begin < 2500) requestAnimationFrame(tick);
          else resolve(count);
        };
        requestAnimationFrame(tick);
      }),
  );
  const after = await counters();
  const perFrameMs = (name) => (((after[name] ?? 0) - (before[name] ?? 0)) * 1000) / probeFrames;

  const wheel = results.wheel;
  const fast = results.fast;
  console.log(
    JSON.stringify({
      dashboard_ready_s: dashboardReady,
      filter_ready_s: filterReady,
      table_ready_s: tableReady,
      scroll_fps: wheel.fps,
      scroll_p95_frame_ms: wheel.p95_frame_ms,
      scroll_ceiling_fps: ceiling,
      main_thread_ms_per_frame: perFrameMs("TaskDuration"),
      script_ms_per_frame: perFrameMs("ScriptDuration"),
      layout_ms_per_frame: perFrameMs("LayoutDuration"),
      scroll_fast_fps: fast.fps,
      scroll_fast_p95_frame_ms: fast.p95_frame_ms,
      rows_on_screen: wheel.loaded.rows,
      rows_loaded: wheel.loaded.filled,
      rows_scrolled: Math.round(wheel.scrolled_px / 40),
      scenarios: results,
      scroll_error: wheel.error ?? fast.error ?? null,
    }),
  );
} finally {
  await browser.close();
}
