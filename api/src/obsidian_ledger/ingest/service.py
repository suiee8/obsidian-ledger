"""Preview and commit an import: the two steps behind the HTTP routes."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from obsidian_ledger.ingest.analysis import Analysis, analyze
from obsidian_ledger.ingest.errors import IngestError
from obsidian_ledger.ingest.export import rejected_csv
from obsidian_ledger.ingest.fileio import validate_extension_and_content
from obsidian_ledger.ingest.options import ImportOptions
from obsidian_ledger.ingest.quality import build_issues
from obsidian_ledger.ingest.run import run_import
from obsidian_ledger.ingest.schemas import (
    AssumptionOut,
    ColumnOut,
    CommitOut,
    IssueOut,
    PreviewOut,
    QuestionOut,
)
from obsidian_ledger.store.db import Store
from obsidian_ledger.store.raw import write_raw


def _question_out(analysis: Analysis) -> list[QuestionOut]:
    return [
        QuestionOut(id=q.id, text=q.text, options=list(q.options), blocking=q.blocking)
        for q in analysis.questions
    ]


def _assumption_out(analysis: Analysis) -> list[AssumptionOut]:
    return [
        AssumptionOut(key=a.key, value=a.value, detail=a.detail, adjustable=a.adjustable)
        for a in analysis.assumptions
    ]


class ImportService:
    def __init__(self, store: Store, default_timezone: str, max_upload_bytes: int) -> None:
        self.store = store
        self.default_timezone = default_timezone
        self.max_upload_bytes = max_upload_bytes

    def _analyze(self, path: Path, options: ImportOptions) -> Analysis:
        return analyze(
            path,
            options,
            default_timezone=self.default_timezone,
            template_lookup=self.store.get_template,
        )

    def staged_path(self, preview_id: str) -> Path:
        return self.store.staging_dir / f"{preview_id}.bin"

    def preview(
        self, preview_id: str, path: Path, filename: str, sha256: str, size: int
    ) -> PreviewOut:
        validate_extension_and_content(path, filename)
        analysis = self._analyze(path, ImportOptions())
        meta = {"filename": filename, "sha256": sha256, "size_bytes": size}
        path.with_suffix(".json").write_text(json.dumps(meta), encoding="utf-8")
        date = analysis.date
        return PreviewOut(
            preview_id=preview_id,
            filename=filename,
            sha256=sha256,
            size_bytes=size,
            kind=analysis.source.kind,
            encoding=analysis.source.encoding or "utf-8",
            delimiter=analysis.source.delimiter,
            header_record=analysis.source.header_record,
            adapter=analysis.adapter,
            shape=analysis.shape,
            decimal=analysis.context.decimal,
            date_formats=date.summary(),
            date_ambiguous=date.ambiguous,
            timezone=analysis.context.tz_name,
            base_currency=analysis.context.base_currency,
            columns=[
                ColumnOut(
                    index=c.index,
                    header=c.header,
                    field=c.field,
                    confidence=c.confidence,
                    source=c.source,
                )
                for c in analysis.columns
            ],
            questions=_question_out(analysis),
            assumptions=_assumption_out(analysis),
            sample_rows=analysis.preview_rows,
            fingerprint=analysis.fingerprint,
        )

    def commit(self, preview_id: str, options: ImportOptions) -> CommitOut:
        staged = self.staged_path(preview_id)
        if not staged.exists():
            raise IngestError(
                "preview_not_found", "That preview has expired or does not exist.", status=404
            )
        meta_path = staged.with_suffix(".json")
        meta: dict[str, Any] = json.loads(meta_path.read_text(encoding="utf-8"))
        filename = str(meta["filename"])
        sha256 = str(meta["sha256"])

        analysis = self._analyze(staged, options)
        if analysis.blocking:
            raise IngestError(
                "needs_answers",
                "Answer the blocking questions before importing.",
                details={"questions": [q.__dict__ for q in analysis.blocking]},
            )

        outcome = run_import(analysis, options)
        issues = build_issues(outcome)
        import_id = uuid.uuid4().hex

        raw_rows = write_raw(analysis.source, self.store.raw_dir / f"{import_id}.parquet")
        rejected_path = self.store.rejected_dir / f"{import_id}.csv"
        rejected_path.write_bytes(rejected_csv(analysis.source.headers, outcome.rejected))

        inserted, present = self.store.insert_frame(import_id, outcome.frame, options.base_currency)
        if options.starting_equity is not None:
            self.store.set_setting("starting_equity", repr(options.starting_equity))
        if options.template_name:
            mapping = {column.header: column.field for column in analysis.columns}
            self.store.save_template(analysis.fingerprint, options.template_name, mapping)

        duplicates = sum(
            1
            for rejected in outcome.rejected
            if any(r.code == "duplicate_in_file" for r in rejected.reasons)
        )
        record: dict[str, Any] = {
            "rows_total": outcome.rows_total,
            "blank_rows": outcome.blank_rows,
            "accepted": outcome.frame.height,
            "inserted": inserted,
            "already_present": present,
            "rejected": len(outcome.rejected),
            "duplicates_in_file": duplicates,
            "raw_rows": raw_rows,
            "adapter": analysis.adapter,
            "shape": analysis.shape,
            "assumptions": [a.key + ": " + a.value for a in analysis.assumptions],
            "issues": [issue.code for issue in issues],
            "options": options.model_dump(exclude_none=True),
            "created_at": datetime.now(UTC).isoformat(),
        }
        self.store.record_import(import_id, filename, sha256, record)
        staged.unlink(missing_ok=True)
        meta_path.unlink(missing_ok=True)

        return CommitOut(
            import_id=import_id,
            filename=filename,
            rows_total=outcome.rows_total,
            blank_rows=outcome.blank_rows,
            accepted=outcome.frame.height,
            inserted=inserted,
            already_present=present,
            rejected=len(outcome.rejected),
            duplicates_in_file=duplicates,
            open_positions=len(outcome.open_positions),
            issues=[
                IssueOut(
                    code=i.code,
                    severity=i.severity,
                    title=i.title,
                    count=i.count,
                    example_rows=list(i.example_rows),
                    suggested_fix=i.suggested_fix,
                )
                for i in issues
            ],
            assumptions=_assumption_out(analysis),
            rejected_csv_path=f"/api/imports/{import_id}/rejected.csv",
        )
