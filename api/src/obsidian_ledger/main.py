from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.gzip import GZipMiddleware

from obsidian_ledger import __version__
from obsidian_ledger.coach.routes import router as coach_router
from obsidian_ledger.coach.service import CoachService
from obsidian_ledger.coach.tools import ToolBox
from obsidian_ledger.ingest.errors import IngestError
from obsidian_ledger.ingest.routes import router as imports_router
from obsidian_ledger.ingest.service import ImportService
from obsidian_ledger.metrics.engine import AnalysisEngine
from obsidian_ledger.metrics.routes import router as analysis_router
from obsidian_ledger.settings import Settings, get_settings
from obsidian_ledger.store.db import Store
from obsidian_ledger.workspace.data_routes import router as data_router
from obsidian_ledger.workspace.routes import router as workspace_router
from obsidian_ledger.workspace.selection import SelectionStore

MEGABYTE = 1024 * 1024


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None]:
    yield
    store: Store = app.state.store
    store.close()


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings if settings is not None else get_settings()
    app = FastAPI(
        title="Obsidian Ledger",
        version=__version__,
        description=(
            "Local-first trading journal API. Reviews past behavior. "
            "It does not predict markets or issue trade signals. Not financial advice."
        ),
        lifespan=_lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    # Dashboard and table payloads are large JSON. Compress anything above about 1 KB.
    app.add_middleware(GZipMiddleware, minimum_size=1024)

    @app.middleware("http")
    async def security_headers(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        return response

    store = Store(resolved.data_dir)
    app.state.store = store
    app.state.analysis = AnalysisEngine(store)
    app.state.selections = SelectionStore()
    app.state.coach = CoachService(store, app.state.analysis)
    app.state.tools = ToolBox(store, app.state.analysis, app.state.coach)
    app.include_router(analysis_router)
    app.include_router(coach_router)
    app.include_router(workspace_router)
    app.include_router(data_router)
    app.state.imports = ImportService(
        store,
        default_timezone=resolved.default_timezone,
        max_upload_bytes=resolved.max_upload_mb * MEGABYTE,
    )
    app.include_router(imports_router)

    @app.exception_handler(IngestError)
    async def ingest_error(_: Request, exc: IngestError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status,
            content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
        )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "obsidian-ledger"}

    @app.get("/")
    def root() -> dict[str, str]:
        return {
            "service": "obsidian-ledger",
            "version": __version__,
            "phase": "1",
            "docs": "/docs",
        }

    return app


app = create_app()
