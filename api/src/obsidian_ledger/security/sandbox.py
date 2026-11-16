"""Parse untrusted files in a separate process with a hard timeout."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from obsidian_ledger.ingest.errors import IngestError


def run_isolated_probe(
    path: Path,
    filename: str,
    *,
    timezone: str,
    timeout_seconds: int,
    memory_mb: int,
) -> None:
    """Raise IngestError when the worker rejects, crashes, or times out. Returns when it is safe."""
    environment = {k: v for k, v in os.environ.items() if not k.startswith("LEDGER_")}
    environment.update({"OPENBLAS_NUM_THREADS": "1", "POLARS_MAX_THREADS": "2"})
    command = [
        sys.executable,
        "-m",
        "obsidian_ledger.security.worker",
        str(path),
        filename,
        timezone,
        str(memory_mb),
        str(timeout_seconds),
    ]
    try:
        completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
            command,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
            env=environment,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired as exc:
        raise IngestError(
            "parse_timeout", "Reading the file took too long, so it was refused."
        ) from exc
    except OSError as exc:
        raise IngestError("parse_failed", "The file could not be read.") from exc
    lines = [line for line in completed.stdout.decode("utf-8", "replace").splitlines() if line]
    try:
        result = json.loads(lines[-1])
    except (IndexError, ValueError) as exc:
        raise IngestError(
            "parse_failed", "The file crashed the reader and was refused."
        ) from exc
    if not isinstance(result, dict) or result.get("ok") is not True:
        status = result.get("status", 422) if isinstance(result, dict) else 422
        raise IngestError(
            str(result.get("code", "parse_failed")) if isinstance(result, dict) else "parse_failed",
            str(result.get("message", "The file could not be read."))
            if isinstance(result, dict)
            else "The file could not be read.",
            status=int(status) if isinstance(status, int) else 422,
        )
