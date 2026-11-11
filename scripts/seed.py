"""Load the sample journal (samples/synthetic_preview.csv) into the local data folder.

Run through pnpm from the repository root:

    pnpm seed

It uses the same preview and commit path as the Import screen, so the result is the same as
importing the file in the browser. Running it again adds nothing, because trades are keyed by a
hash of their content.
"""

from __future__ import annotations

import hashlib
import shutil
import sys
import uuid
from pathlib import Path

from obsidian_ledger.ingest.options import ImportOptions
from obsidian_ledger.ingest.service import ImportService
from obsidian_ledger.settings import get_settings
from obsidian_ledger.store.db import Store

SAMPLE = Path(__file__).resolve().parent.parent / "samples" / "synthetic_preview.csv"


def main() -> int:
    if not SAMPLE.exists():
        print(f"Sample file not found: {SAMPLE}", file=sys.stderr)
        return 1
    settings = get_settings()
    store = Store(settings.data_dir)
    try:
        service = ImportService(
            store,
            default_timezone=settings.default_timezone,
            max_upload_bytes=settings.max_upload_mb * 1024 * 1024,
        )
        preview_id = uuid.uuid4().hex
        staged = service.staged_path(preview_id)
        shutil.copyfile(SAMPLE, staged)
        digest = _sha256(staged)
        service.preview(preview_id, staged, SAMPLE.name, digest, staged.stat().st_size)
        result = service.commit(preview_id, ImportOptions())
        print(
            f"Loaded {SAMPLE.name}: {result.accepted} trades accepted, "
            f"{result.inserted} new, {result.already_present} already present."
        )
    finally:
        store.close()
    return 0


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
