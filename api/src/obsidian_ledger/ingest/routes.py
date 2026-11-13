"""HTTP routes for importing trade files and reading the results."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path as FilePath
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Path, Query, Request
from fastapi.responses import FileResponse

from obsidian_ledger.atomic import atomic_path
from obsidian_ledger.ingest.errors import IngestError
from obsidian_ledger.ingest.options import ImportOptions
from obsidian_ledger.ingest.schemas import CommitOut, PreviewOut
from obsidian_ledger.ingest.service import ImportService

router = APIRouter(prefix="/api", tags=["imports"])

HEX_ID = r"^[a-f0-9]{32}$"
CHUNK_BYTES = 1024 * 1024


def _service(request: Request) -> ImportService:
    service: ImportService = request.app.state.imports
    return service


async def _save_stream(
    request: Request, service: ImportService, destination: FilePath
) -> tuple[int, str]:
    """Write the request body to disk while enforcing the size limit."""
    digest = hashlib.sha256()
    total = 0
    try:
        with atomic_path(destination) as temporary:
            with temporary.open("wb") as handle:
                async for chunk in request.stream():
                    total += len(chunk)
                    if total > service.max_upload_bytes:
                        raise IngestError(
                            "too_large",
                            f"Files over {service.max_upload_bytes // (1024 * 1024)} MB "
                            "are not accepted.",
                            status=413,
                        )
                    digest.update(chunk)
                    handle.write(chunk)
            if total == 0:
                raise IngestError("empty_file", "The upload is empty.")
    except BaseException:
        destination.unlink(missing_ok=True)
        destination.with_suffix(".json").unlink(missing_ok=True)
        raise
    return total, digest.hexdigest()


@router.post("/imports/preview", response_model=PreviewOut)
async def preview_import(
    request: Request,
    filename: Annotated[str, Query(min_length=1, max_length=255)],
) -> PreviewOut:
    """Send the raw file as the request body. Returns the detected layout and questions."""
    service = _service(request)
    preview_id = uuid4().hex
    staged = service.staged_path(preview_id)
    size, digest = await _save_stream(request, service, staged)
    try:
        return service.preview(preview_id, staged, filename, digest, size)
    except BaseException:
        staged.unlink(missing_ok=True)
        staged.with_suffix(".json").unlink(missing_ok=True)
        raise


@router.post("/imports/{preview_id}/commit", response_model=CommitOut)
def commit_import(
    request: Request,
    preview_id: Annotated[str, Path(pattern=HEX_ID)],
    options: ImportOptions,
) -> CommitOut:
    return _service(request).commit(preview_id, options)


@router.get("/imports")
def list_imports(request: Request) -> list[dict[str, Any]]:
    return _service(request).store.list_imports()


@router.get("/imports/{import_id}")
def get_import(request: Request, import_id: Annotated[str, Path(pattern=HEX_ID)]) -> dict[str, Any]:
    record = _service(request).store.get_import(import_id)
    if record is None:
        raise IngestError("import_not_found", "No import with that id.", status=404)
    return record


@router.get("/imports/{import_id}/rejected.csv")
def rejected_csv(request: Request, import_id: Annotated[str, Path(pattern=HEX_ID)]) -> FileResponse:
    path = _service(request).store.rejected_dir / f"{import_id}.csv"
    if not path.exists():
        raise IngestError("import_not_found", "No rejected-rows file for that import.", status=404)
    return FileResponse(path, media_type="text/csv", filename=f"rejected-{import_id}.csv")


@router.get("/trades")
def list_trades(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[dict[str, Any]]:
    rows = _service(request).store.list_trades(limit, offset)
    for row in rows:
        for key, value in row.items():
            if isinstance(value, datetime):
                row[key] = value.replace(tzinfo=UTC).isoformat().replace("+00:00", "Z")
    return rows


@router.get("/templates")
def list_templates(request: Request) -> list[dict[str, Any]]:
    return _service(request).store.list_templates()
