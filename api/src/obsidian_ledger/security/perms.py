"""Limit the data folder to the current user where the operating system allows it."""

from __future__ import annotations

import os
from pathlib import Path


def restrict_data_dir(data_dir: Path) -> None:
    """POSIX: mode 700. On Windows see the icacls command in docs/security.md."""
    if os.name != "posix":
        return
    try:
        data_dir.chmod(0o700)
    except OSError:
        return
