"""Response models for the import API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ColumnOut(BaseModel):
    index: int
    header: str
    field: str | None
    confidence: str | None
    source: str


class QuestionOut(BaseModel):
    id: str
    text: str
    options: list[str]
    blocking: bool


class AssumptionOut(BaseModel):
    key: str
    value: str
    detail: str
    adjustable: bool


class IssueOut(BaseModel):
    code: str
    severity: Literal["error", "warning", "info"]
    title: str
    count: int
    example_rows: list[int]
    suggested_fix: str


class PreviewOut(BaseModel):
    preview_id: str
    filename: str
    sha256: str
    size_bytes: int
    kind: str
    encoding: str
    delimiter: str | None
    header_record: int
    adapter: str | None
    shape: str | None
    decimal: str
    date_formats: str
    date_ambiguous: bool
    timezone: str
    base_currency: str
    columns: list[ColumnOut]
    questions: list[QuestionOut]
    assumptions: list[AssumptionOut]
    sample_rows: list[dict[str, str]]
    fingerprint: str


class CommitOut(BaseModel):
    import_id: str
    filename: str
    rows_total: int
    blank_rows: int
    accepted: int
    inserted: int
    already_present: int
    rejected: int
    duplicates_in_file: int
    open_positions: int
    issues: list[IssueOut]
    assumptions: list[AssumptionOut]
    rejected_csv_path: str
