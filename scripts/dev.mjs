// Starts the API and the web dev server together. Ctrl+C, or either process exiting, stops both.
// Output from each process is prefixed so the two streams stay readable.

import { spawn } from "node:child_process";

const processes = [
  {
    name: "api",
    command: "uv run --directory api uvicorn obsidian_ledger.main:app --host 127.0.0.1 --port 8000",
  },
  { name: "web", command: "pnpm -C web dev" },
];

const children = [];
let stopping = false;

function stopAll() {
  if (stopping) return;
  stopping = true;
  for (const child of children) {
    // Stop the whole tree. On Windows, a plain kill leaves uvicorn's worker process running.
    if (child.pid) {
      spawn("taskkill", ["/PID", String(child.pid), "/T", "/F"], { stdio: "ignore" });
    }
  }
}

for (const { name, command } of processes) {
  const child = spawn(command, { shell: true, stdio: ["ignore", "pipe", "pipe"] });
  children.push(child);
  for (const stream of [child.stdout, child.stderr]) {
    stream.on("data", (chunk) => {
      for (const line of chunk.toString().split(/\r?\n/)) {
        if (line.trim()) process.stdout.write(`[${name}] ${line}\n`);
      }
    });
  }
  child.on("exit", (code) => {
    process.stdout.write(`[${name}] exited with code ${code ?? "unknown"}\n`);
    stopAll();
    process.exitCode = code ?? 1;
  });
}

process.on("SIGINT", () => {
  stopAll();
  process.exit(0);
});
