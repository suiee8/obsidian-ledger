import logging
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from obsidian_ledger import __version__
from obsidian_ledger.coach.routes import router as coach_router
from obsidian_ledger.coach.service import CoachService
from obsidian_ledger.coach.tools import ToolBox
from obsidian_ledger.ingest.errors import IngestError
from obsidian_ledger.ingest.routes import router as imports_router
from obsidian_ledger.ingest.service import ImportService
from obsidian_ledger.llm.coach import LLMCoach
from obsidian_ledger.llm.routes import router as llm_router
from obsidian_ledger.llm.secrets import make_secrets
from obsidian_ledger.logging_setup import configure_api_logger
from obsidian_ledger.metrics.engine import AnalysisEngine
from obsidian_ledger.metrics.routes import router as analysis_router
from obsidian_ledger.middleware import (
    RequestBodyLimitMiddleware,
    RequestBodyTooLarge,
    RequestPolicyMiddleware,
    SecurityHeadersMiddleware,
)
from obsidian_ledger.settings import Settings, get_settings
from obsidian_ledger.store.db import Store
from obsidian_ledger.workspace.data_routes import router as data_router
from obsidian_ledger.workspace.routes import router as workspace_router
from obsidian_ledger.workspace.selection import SelectionStore

MEGABYTE = 1024 * 1024


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None]:
    logger: logging.Logger = configure_api_logger(app.state.settings.data_dir)
    logger.info("API process started")
    try:
        yield
    finally:
        store: Store = app.state.store
        store.close()
        logger.info("API process stopped")


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
    app.state.settings = resolved
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    # Dashboard and table payloads are large JSON. Compress anything above about 1 KB.
    app.add_middleware(GZipMiddleware, minimum_size=1024)

    allowed_origins = set(resolved.cors_origin_list)

    @app.middleware("http")
    async def enforce_origin(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        origin = request.headers.get("origin")
        if origin is not None and origin not in allowed_origins:
            return Response("Disallowed origin", status_code=403)
        return await call_next(request)

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
    app.state.llm = LLMCoach(
        store,
        app.state.analysis,
        app.state.coach,
        app.state.tools,
        make_secrets(resolved.llm_secret_store),
        test_provider_url=resolved.llm_test_provider_url,
    )
    app.include_router(analysis_router)
    app.include_router(coach_router)
    app.include_router(workspace_router)
    app.include_router(data_router)
    app.include_router(llm_router)
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

    @app.exception_handler(RequestBodyTooLarge)
    async def request_body_too_large(_: Request, exc: RequestBodyTooLarge) -> JSONResponse:
        return JSONResponse(
            status_code=413,
            content={"error": {"code": exc.code, "message": str(exc)}},
        )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "obsidian-ledger", "version": __version__}

    @app.get("/health/ready")
    def health_ready(response: Response) -> dict[str, object]:
        checks: dict[str, object] = app.state.store.health_check()
        core_ready = (
            checks["database"] == "ok"
            and checks["data_dir_writable"] is True
            and checks["disk_space_ok"] is True
        )
        if not core_ready:
            ai_status = "unknown"
        else:
            config = app.state.llm.config()
            if config.provider in app.state.llm.providers:
                ai_status = (
                    "unavailable"
                    if app.state.llm.provider_unavailable(config.provider)
                    else "configured"
                )
            else:
                ai_status = "not_configured"
        checks["ai"] = ai_status
        if not core_ready:
            status = "down"
            response.status_code = 503
        elif ai_status == "unavailable":
            status = "degraded"
        else:
            status = "ready"
        return {
            "status": status,
            "service": "obsidian-ledger",
            "version": __version__,
            "checks": checks,
        }

    @app.get("/")
    def root() -> dict[str, str]:
        return {
            "service": "obsidian-ledger",
            "version": __version__,
            "phase": "1",
            "docs": "/docs",
        }

    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["127.0.0.1", "localhost"],
    )
    app.add_middleware(
        RequestBodyLimitMiddleware,
        max_body_bytes=resolved.max_upload_mb * MEGABYTE,
    )
    app.add_middleware(
        RequestPolicyMiddleware,
        heavy_limit=2,
        requests_per_minute=resolved.requests_per_minute,
        timeout_seconds=resolved.request_timeout_seconds,
    )
    app.add_middleware(SecurityHeadersMiddleware)

    return app


app = create_app()
