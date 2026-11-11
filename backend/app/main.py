import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.api.v1 import api_router
from app.core.cache import close_redis, redis_healthy
from app.core.config import get_settings
from app.core.database import dispose_engine, engine
from app.core.error_handlers import register_exception_handlers
from app.core.request_context import sanitize_request_id, set_request_id
from app.core.storage import get_storage

settings = get_settings()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.storage_backend == "s3" and settings.s3_create_bucket:
        storage = get_storage()
        try:
            for step in await storage.ensure_bucket():  # type: ignore[attr-defined]
                logger.info("storage: %s", step)
        except Exception:  # the API still serves; uploads will report the outage
            logger.exception("storage: could not prepare bucket %s", settings.s3_bucket)
    yield
    await dispose_engine()
    await close_redis()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        docs_url="/docs" if settings.api_docs_enabled else None,
        redoc_url="/redoc" if settings.api_docs_enabled else None,
        openapi_url="/openapi.json" if settings.api_docs_enabled else None,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-Id", "Content-Disposition"],
    )

    @app.middleware("http")
    async def add_request_id(request: Request, call_next):
        """Give every request an id that error responses and the client share."""
        request_id = sanitize_request_id(request.headers.get("X-Request-Id"))
        set_request_id(request_id)
        request.state.request_id = request_id

        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        if request.url.path.startswith(settings.storage_public_base_url):
            response.headers["Content-Security-Policy"] = "default-src 'none'; sandbox"
        return response

    # Local storage keeps files on disk, so the app serves them itself. With
    # S3 the bucket serves new files, but images stored before the switch keep
    # their /media URLs, so the mount stays.
    uploads = Path(settings.storage_local_path)
    uploads.mkdir(parents=True, exist_ok=True)
    app.mount(
        settings.storage_public_base_url,
        StaticFiles(directory=uploads),
        name="media",
    )

    @app.get("/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        """Liveness: the process is up and serving."""
        return {"status": "ok"}

    @app.get("/health/ready", include_in_schema=False)
    async def ready() -> JSONResponse:
        """Readiness: the database and Redis both answer."""
        try:
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
            database = True
        except Exception:
            database = False
        cache = await redis_healthy()

        healthy = database and cache
        return JSONResponse(
            status_code=200 if healthy else 503,
            content={
                "status": "ok" if healthy else "unavailable",
                "database": "ok" if database else "unavailable",
                "redis": "ok" if cache else "unavailable",
            },
        )

    register_exception_handlers(app)

    app.include_router(api_router, prefix=settings.api_v1_prefix)

    return app


app = create_app()
