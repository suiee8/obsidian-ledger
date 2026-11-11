// Runs the production build, then the Playwright suite. Every line is printed with a timestamp.
// While a step is running, a heartbeat line prints every 15 seconds, so a quiet step (the build,
// or a long browser test) is visibly still alive. Ends with a pass and fail count.

import { spawn } from "node:child_process";
import { createInterface } from "node:readline";

const HEARTBEAT_MS = 15_000;
// Strips terminal colour codes from Playwright's output.
// eslint-disable-next-line no-control-regex
const ANSI = /\x1b\[[0-9;?]*[A-Za-z]/g;

const started = Date.now();
let lastOutput = Date.now();
let phase = "starting";
const counts = {};

const clock = () => new Date().toTimeString().slice(0, 8);
const seconds = (ms) => Math.round(ms / 1000);

function say(text) {
  lastOutput = Date.now();
  console.log(`[${clock()}] ${text}`);
}

function runStep(label, command, args) {
  phase = label;
  say(`${label}: start`);
  return new Promise((resolve) => {
    const child = spawn(command, args, {
      stdio: ["ignore", "pipe", "pipe"],
      shell: true,
      env: process.env,
    });
    for (const stream of [child.stdout, child.stderr]) {
      createInterface({ input: stream }).on("line", (raw) => {
        const line = raw.replace(ANSI, "").replace(/\r/g, "").trimEnd();
        if (line.length === 0) return;
        say(line);
        // Playwright prints a summary such as "  41 passed (1.7m)" and "  4 failed".
        const match = /^\s*(\d+) (passed|failed|flaky|skipped|did not run|interrupted)\b/.exec(line);
        if (match) counts[match[2]] = Number(match[1]);
      });
    }
    child.on("error", (error) => {
      say(`${label}: could not start (${error.message})`);
      resolve(1);
    });
    child.on("close", (code) => {
      say(`${label}: exit ${code ?? 1}`);
      resolve(code ?? 1);
    });
  });
}

const heartbeat = setInterval(() => {
  const quiet = seconds(Date.now() - lastOutput);
  console.log(
    `[${clock()}] heartbeat: ${phase} running, ${seconds(Date.now() - started)}s elapsed, last output ${quiet}s ago`,
  );
}, HEARTBEAT_MS);

let exitCode = 1;
try {
  const build = await runStep("build", "pnpm", ["run", "build"]);
  if (build === 0) {
    exitCode = await runStep("playwright", "pnpm", ["exec", "playwright", "test"]);
  } else {
    exitCode = build;
  }
} finally {
  clearInterval(heartbeat);
  say(
    `summary: ${counts.passed ?? 0} passed, ${counts.failed ?? 0} failed, ` +
      `${counts.flaky ?? 0} flaky, ${counts.skipped ?? 0} skipped, ` +
      `${counts["did not run"] ?? 0} did not run; total ${seconds(Date.now() - started)}s; exit ${exitCode}`,
  );
}
process.exitCode = exitCode;
