"""An OpenAI-compatible mock provider for the browser tests. Standard library only.

    uv run --directory api python tests/llm/mock_server.py --port 11435

Like a cloud provider it needs an API key: "Bearer e2e-test-key-123456". A question that contains
the word "slow" makes the answer wait 25 seconds, so the Stop button can be tested. Everything else
answers at once with the honest mode of mock_brain.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mock_brain  # noqa: E402

SLOW_SECONDS = 25
API_KEY = "e2e-test-key-123456"


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, payload: dict[str, Any]) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _authorized(self) -> bool:
        if self.headers.get("Authorization") == f"Bearer {API_KEY}":
            return True
        self._send(401, {"error": {"message": "Invalid API key"}})
        return False

    def do_GET(self) -> None:  # noqa: N802 - the http.server API
        if self.path.rstrip("/") == "/v1/models" and not self._authorized():
            return
        if self.path.rstrip("/") == "/v1/models":
            self._send(200, mock_brain.models())
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path.rstrip("/") != "/v1/chat/completions":
            self._send(404, {"error": "not found"})
            return
        if not self._authorized():
            return
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        question = next(
            (
                str(m.get("content", ""))
                for m in body.get("messages", [])
                if m.get("role") == "user" and str(m.get("content", "")).startswith("Question:")
            ),
            "",
        )
        if "slow" in question.lower():
            time.sleep(SLOW_SECONDS)
        self._send(200, mock_brain.respond(body, "honest"))

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        return  # keep the test output quiet


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=11435)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.daemon_threads = True
    print(f"mock model on http://127.0.0.1:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
