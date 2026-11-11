from __future__ import annotations

from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings
from app.core.error_codes import ErrorCode
from app.core.exceptions import ConflictError

_settings = get_settings()

engine: AsyncEngine = create_async_engine(
    _settings.database_url,
    pool_pre_ping=True,
    pool_size=_settings.db_pool_size,
    max_overflow=_settings.db_max_overflow,
    pool_recycle=_settings.db_pool_recycle_seconds,
    pool_timeout=_settings.db_pool_timeout_seconds,
    connect_args={
        "server_settings": {
            "statement_timeout": str(_settings.db_statement_timeout_seconds * 1000),
            "application_name": _settings.app_name,
        },
    },
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autoflush=False,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    session = AsyncSessionLocal()
    try:
        yield session
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


@asynccontextmanager
async def conflict_on_integrity_error(
    session: AsyncSession, message: str, *, error_code: ErrorCode | None = None
) -> AsyncIterator[None]:
    """Turn a constraint violation inside the block into a rollback and a 409 with `message`."""
    try:
        yield
    except IntegrityError as exc:
        await session.rollback()
        raise ConflictError(message, error_code=error_code) from exc


async def dispose_engine() -> None:
    await engine.dispose()
