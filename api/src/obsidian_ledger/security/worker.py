"""Run in a child process: validate and fully analyse an untrusted file, then report one JSON line.

The parent enforces the wall-clock timeout. This process also applies an address-space and CPU limit
where the operating system supports it, so a crafted file can crash or exhaust only this process.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _limit(memory_mb: int, cpu_seconds: int) -> None:
    try:
        import resource  # POSIX only
    except ImportError:
        return
    limit = memory_mb * 1024 * 1024
    try:
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 2))
    except (ValueError, OSError):
        return


def _report(payload: dict[str, object]) -> None:
    sys.stdout.write("\n" + json.dumps(payload) + "\n")
    sys.stdout.flush()


def main(argv: list[str]) -> int:
    path, filename, timezone, memory_mb, cpu_seconds = argv[1:6]
    _limit(int(memory_mb), int(cpu_seconds))
    from obsidian_ledger.ingest.analysis import analyze
    from obsidian_ledger.ingest.errors import IngestError
    from obsidian_ledger.ingest.fileio import validate_extension_and_content
    from obsidian_ledger.ingest.options import ImportOptions

    try:
        validate_extension_and_content(Path(path), filename)
        analyze(Path(path), ImportOptions(), default_timezone=timezone, template_lookup=None)
    except IngestError as exc:
        _report({"ok": False, "code": exc.code, "message": exc.message, "status": exc.status})
        return 0
    except MemoryError:
        _report({"ok": False, "code": "parse_memory", "message": "The file needs too much memory."})
        return 0
    except Exception:  # noqa: BLE001 - any parser failure must become a structured error
        _report({"ok": False, "code": "parse_failed", "message": "The file could not be read."})
        return 0
    _report({"ok": True})
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
