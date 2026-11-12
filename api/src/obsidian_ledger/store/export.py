"""Export everything the app holds into one zip file the user can keep."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

from obsidian_ledger.csvsafe import neutralize_csv, neutralize_frame
from obsidian_ledger.store.db import Store

COACH_REPORT_LIMIT = 100_000


def _json(value: Any) -> str:
    return json.dumps(value, indent=2, default=str, ensure_ascii=False)


def write_export(store: Store, destination: Path) -> dict[str, int]:
    """Write trades, imports, views, templates, Coach reports, settings, and the original files.

    Returns how many of each were written. Nothing here leaves the computer.
    """
    counts: dict[str, int] = {}
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        trades = store.load_frame()
        # Journal notes and symbols are other people's text, so formula cells are neutralized.
        archive.writestr(
            "trades.csv",
            neutralize_csv(neutralize_frame(trades).write_csv()),
        )
        counts["trades"] = trades.height

        imports = [
            record
            for item in store.list_imports()
            if (record := store.get_import(str(item["import_id"]))) is not None
        ]
        archive.writestr("imports.json", _json(imports))
        counts["imports"] = len(imports)

        views = store.list_views()
        archive.writestr("saved_views.json", _json(views))
        counts["saved_views"] = len(views)

        templates = store.list_templates()
        archive.writestr("column_templates.json", _json(templates))
        counts["column_templates"] = len(templates)

        reports = [
            json.loads(text)
            for item in store.list_coach_reports(COACH_REPORT_LIMIT)
            if (text := store.get_coach_report(str(item["report_id"]))) is not None
        ]
        archive.writestr("coach_reports.json", _json(reports))
        counts["coach_reports"] = len(reports)

        archive.writestr(
            "settings.json",
            _json(
                {
                    "starting_equity": store.get_setting("starting_equity"),
                    "preferences": store.get_preferences(),
                }
            ),
        )

        files = 0
        for folder, kind, method in (
            (store.raw_dir, "raw", zipfile.ZIP_STORED),  # parquet is already compressed
            (store.rejected_dir, "rejected", zipfile.ZIP_DEFLATED),
        ):
            for path in sorted(folder.iterdir()):
                if path.is_file():
                    archive.write(path, f"{kind}/{path.name}", compress_type=method)
                    files += 1
        counts["files"] = files
    return counts
