"""Limit the data folder to the current user where the operating system allows it."""

from __future__ import annotations

import os
from pathlib import Path


def restrict_data_dir(data_dir: Path) -> None:
    """POSIX: mode 700. Windows has no chmod equivalent; docs/security.md shows the icacls command."""
    if os.name != "posix":
        return
    try:
        data_dir.chmod(0o700)
    except OSError:
        return
