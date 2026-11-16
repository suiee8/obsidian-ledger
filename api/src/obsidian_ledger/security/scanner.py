"""Optional malware scanner hook. Off by default; uses a locally installed scanner."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

ScanStatus = Literal["clean", "not_scanned", "infected"]


@dataclass(frozen=True)
class ScanResult:
    status: ScanStatus


def _defender_path() -> str | None:
    program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
    candidate = Path(program_files) / "Windows Defender" / "MpCmdRun.exe"
    return str(candidate) if candidate.is_file() else None


def _command(mode: str, path: Path) -> list[str] | None:
    if mode == "clamd":
        exe = shutil.which("clamdscan") or shutil.which("clamscan")
        return [exe, "--no-summary", str(path)] if exe else None
    if mode == "defender":
        exe = _defender_path()
        if exe is None:
            return None
        return [exe, "-Scan", "-ScanType", "3", "-File", str(path), "-DisableRemediation"]
    return None


def scan_file(path: Path, mode: str, timeout: float = 120.0) -> ScanResult:
    """Scan one quarantined file. A missing or failing scanner reports `not_scanned`."""
    command = _command(mode, path)
    if command is None:
        return ScanResult("not_scanned")
    try:
        completed = subprocess.run(  # noqa: S603 - fixed argv, no shell, path is our own random name
            command, capture_output=True, timeout=timeout, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return ScanResult("not_scanned")
    if mode == "clamd":
        if completed.returncode == 1:
            return ScanResult("infected")
        return ScanResult("clean" if completed.returncode == 0 else "not_scanned")
    return ScanResult("clean" if completed.returncode == 0 else "infected")
