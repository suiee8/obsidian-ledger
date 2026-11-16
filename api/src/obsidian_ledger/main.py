import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
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
from obsidian_ledger.llm.coach import LLMCoach
from obsidian_ledger.llm.routes import router as llm_router
from obsidian_ledger.llm.secrets import make_secrets
from obsidian_ledger.logging_setup import configure_api_logger
from obsidian_ledger.metrics.engine import AnalysisEngine
from obsidian_ledger.metrics.routes import router as analysis_router
from obsidian_ledger.middleware import (
    AccessControlMiddleware,
    GuardMiddleware,
    RequestBodyLimitMiddleware,
    RequestBodyTooLarge,
    RequestPolicyMiddleware,
    SecurityHeadersMiddleware,
)
from obsidian_ledger.security.auth import LoginThrottle, SessionStore
from obsidian_ledger.security.events import SecurityLog
from obsidian_ledger.security.perms import restrict_data_dir
from obsidian_ledger.security.routes import router as auth_router
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
        app.state.security_log.close()
        logger.info("API process stopped")


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings if settings is not None else get_settings()
    if resolved.public:
        if not resolved.password_hash:
            raise RuntimeError("LEDGER_PUBLIC=1 needs LEDGER_PASSWORD_HASH (see docs/security.md).")
        if "cors_origins" not in resolved.model_fields_set:
            raise RuntimeError("LEDGER_PUBLIC=1 needs an explicit LEDGER_CORS_ORIGINS list.")
    app = FastAPI(
        title="Obsidian Ledger",
        version=__version__,
        description=(
            "Local-first trading journal API. Reviews past behavior. "
            "It does not predict markets or issue trade signals. Not financial advice."
        ),
        lifespan=_lifespan,
        # Interactive docs stay on locally and are off in public mode.
        docs_url=None if resolved.public else "/docs",
        redoc_url=None if resolved.public else "/redoc",
        openapi_url=None if resolved.public else "/openapi.json",
    )
    app.state.settings = resolved
    app.state.sessions = SessionStore(resolved.session_idle_minutes * 60)
    app.state.login_throttle = LoginThrottle()

    # Innermost first. A request passes CORS, gzip, the login and read-only gate, the body limit,
    # then the host/origin/method/header guard, the rate limit, and finally the response headers.
    app.add_middleware(
        AccessControlMiddleware,
        public=resolved.public,
        read_only=resolved.demo_readonly,
        sessions=app.state.sessions,
    )
    # Dashboard and table payloads are large JSON. Compress anything above about 1 KB.
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-Ledger-Client"],
    )

    store = Store(resolved.data_dir)
    app.state.store = store
    app.state.security_log = SecurityLog(resolved.data_dir)
    if resolved.public:
        restrict_data_dir(resolved.data_dir)
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
        scanner=resolved.scanner,
        isolate_parsing=resolved.parse_isolation,
        parse_timeout_seconds=resolved.parse_timeout_seconds,
        parse_memory_mb=resolved.parse_memory_mb,
        security_log=app.state.security_log,
    )
    app.include_router(imports_router)
    app.include_router(auth_router)

    @app.exception_handler(IngestError)
    async def ingest_error(_: Request, exc: IngestError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status,
            content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
        )

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Field names and rules only. FastAPI's default also echoes the submitted values.
        problems = [
            {"loc": [str(part) for part in err["loc"]], "type": err["type"], "msg": err["msg"]}
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={
                "error": {"code": "invalid_request", "message": "Invalid request."},
                "detail": problems,
            },
        )

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logging.getLogger("obsidian_ledger").error("Unhandled %s", type(exc).__name__)
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "internal_error", "message": "Something went wrong."}},
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
        RequestBodyLimitMiddleware,
        max_body_bytes=resolved.max_upload_mb * MEGABYTE,
    )
    app.add_middleware(
        GuardMiddleware,
        allowed_hosts=resolved.allowed_host_list,
        allowed_origins=resolved.cors_origin_list,
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
