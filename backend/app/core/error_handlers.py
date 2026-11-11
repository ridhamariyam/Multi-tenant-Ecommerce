from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, InterfaceError, OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.error_codes import AuthErrorCode, CommonErrorCode, ErrorCode
from app.core.exceptions import AppError, RateLimitedError
from app.core.request_context import get_request_id
from app.core.responses import ErrorPayload, ErrorResponse

_STATUS_ERROR_CODES: dict[int, ErrorCode] = {
    status.HTTP_401_UNAUTHORIZED: AuthErrorCode.AUTHENTICATION_FAILED,
    status.HTTP_403_FORBIDDEN: CommonErrorCode.PERMISSION_DENIED,
    status.HTTP_404_NOT_FOUND: CommonErrorCode.NOT_FOUND,
    status.HTTP_405_METHOD_NOT_ALLOWED: CommonErrorCode.METHOD_NOT_ALLOWED,
    status.HTTP_409_CONFLICT: CommonErrorCode.CONFLICT,
    status.HTTP_429_TOO_MANY_REQUESTS: CommonErrorCode.RATE_LIMITED,
}


def _envelope(
    *,
    message: str,
    error_code: ErrorCode,
    details: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    body = ErrorResponse(
        message=message,
        error=ErrorPayload(
            code=error_code.value,
            message=message,
            details=details or [],
            request_id=get_request_id(),
        ),
    )
    return body.model_dump(mode="json")


def _json(
    status_code: int,
    body: dict[str, Any],
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(status_code=status_code, content=body, headers=headers)


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    headers = None
    if isinstance(exc, RateLimitedError) and exc.retry_after_seconds:
        headers = {"Retry-After": str(exc.retry_after_seconds)}

    return _json(
        exc.status_code,
        _envelope(message=exc.message, error_code=exc.error_code, details=exc.details),
        headers,
    )


async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Report which field failed and why, never the value that was submitted."""
    details = [
        {
            "field": ".".join(str(part) for part in error.get("loc", ())[1:]),
            "type": error.get("type", "value_error"),
            "message": error.get("msg", "Invalid value"),
        }
        for error in exc.errors()
    ]

    return _json(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        _envelope(
            message="The request could not be validated",
            error_code=CommonErrorCode.VALIDATION_ERROR,
            details=details,
        ),
    )


async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    error_code = _STATUS_ERROR_CODES.get(exc.status_code, CommonErrorCode.HTTP_ERROR)
    message = exc.detail if isinstance(exc.detail, str) else "Request failed"

    return _json(
        exc.status_code,
        _envelope(message=message, error_code=error_code),
        dict(exc.headers) if exc.headers else None,
    )


async def integrity_error_handler(request: Request, exc: IntegrityError) -> JSONResponse:
    """A constraint the service did not anticipate, usually two requests racing."""
    return _json(
        status.HTTP_409_CONFLICT,
        _envelope(
            message="The request conflicts with existing data. Please refresh and try again.",
            error_code=CommonErrorCode.CONFLICT,
        ),
    )


async def database_unavailable_handler(request: Request, exc: Exception) -> JSONResponse:
    """Lost or refused database connections. Never echoes the driver's message."""
    return _json(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        _envelope(
            message="Service temporarily unavailable",
            error_code=CommonErrorCode.SERVICE_UNAVAILABLE,
        ),
    )


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Last resort: a generic 500 that reveals nothing internal to the caller."""
    return _json(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        _envelope(
            message="An unexpected error occurred",
            error_code=CommonErrorCode.INTERNAL_ERROR,
        ),
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(IntegrityError, integrity_error_handler)
    app.add_exception_handler(OperationalError, database_unavailable_handler)
    app.add_exception_handler(InterfaceError, database_unavailable_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)
