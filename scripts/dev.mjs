// Starts the API and web server together, restarting API crashes with bounded backoff.

import net from "node:net";
import { spawn } from "node:child_process";

const children = new Set();
let stopping = false;
let exitCode = 0;
let apiRestarts = 0;
let restartTimer;

function isPortAvailable(port) {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once("error", (error) => {
      if (error.code === "EADDRINUSE") resolve(false);
      else reject(error);
    });
    server.listen(port, "127.0.0.1", () => {
      server.close((error) => (error ? reject(error) : resolve(true)));
    });
  });
}

function stopChild(child) {
  if (!child.pid) return;
  if (process.platform === "win32") {
    spawn("taskkill", ["/PID", String(child.pid), "/T", "/F"], { stdio: "ignore" });
  } else {
    child.kill("SIGTERM");
  }
}

function stopAll(code) {
  if (stopping) return;
  stopping = true;
  exitCode = code;
  if (restartTimer) clearTimeout(restartTimer);
  for (const child of children) stopChild(child);
  if (children.size === 0) process.exitCode = exitCode;
}

function start(name, command) {
  if (stopping) return;
  const child = spawn(command, { shell: true, stdio: ["ignore", "pipe", "pipe"] });
  children.add(child);
  for (const stream of [child.stdout, child.stderr]) {
    stream?.on("data", (chunk) => {
      for (const line of chunk.toString().split(/\r?\n/)) {
        if (line.trim()) process.stdout.write(`[${name}] ${line}\n`);
      }
    });
  }
  child.on("error", (error) => {
    process.stderr.write(`[${name}] failed to start: ${error.message}\n`);
  });
  child.on("exit", (code) => {
    children.delete(child);
    process.stdout.write(`[${name}] exited with code ${code ?? "unknown"}\n`);
    if (stopping) {
      if (children.size === 0) process.exitCode = exitCode;
      return;
    }
    if (name === "api" && code !== 0) {
      const delay = Math.min(30_000, 500 * 2 ** apiRestarts);
      apiRestarts += 1;
      process.stderr.write(`[api] restarting in ${delay} ms (attempt ${apiRestarts})\n`);
      restartTimer = setTimeout(
        () =>
          start(
            "api",
            "uv run --directory api uvicorn obsidian_ledger.main:app --host 127.0.0.1 --port 8000",
          ),
        delay,
      );
      return;
    }
    stopAll(code ?? 1);
  });
}

async function main() {
  for (const [name, port] of [
    ["API", 8000],
    ["web", 5173],
  ]) {
    if (!(await isPortAvailable(port))) {
      process.stderr.write(`[${name}] Port ${port} on 127.0.0.1 is already in use; stop its owner and retry.\n`);
      process.exitCode = 1;
      return;
    }
  }

  start(
    "api",
    "uv run --directory api uvicorn obsidian_ledger.main:app --host 127.0.0.1 --port 8000",
  );
  start("web", "pnpm -C web dev");
}

process.on("SIGINT", () => stopAll(130));
process.on("SIGTERM", () => stopAll(143));
main().catch((error) => {
  process.stderr.write(`[dev] ${error instanceof Error ? error.message : String(error)}\n`);
  stopAll(1);
});
