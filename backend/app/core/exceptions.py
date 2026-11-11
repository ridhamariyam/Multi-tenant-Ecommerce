from __future__ import annotations

from typing import Any

from app.core.error_codes import AuthErrorCode, CommonErrorCode, ErrorCode


class AppError(Exception):
    """An expected failure: a safe message, a stable code and an HTTP status.

    Subclasses fix the status and a generic code; pass `error_code` to name the
    specific case (`NotFoundError("Order not found", error_code=OrderErrorCode.NOT_FOUND)`).
    """

    status_code: int = 400
    error_code: ErrorCode = CommonErrorCode.BAD_REQUEST
    default_message: str = "Request could not be processed"

    def __init__(
        self,
        message: str | None = None,
        *,
        details: list[dict[str, Any]] | None = None,
        error_code: ErrorCode | None = None,
    ) -> None:
        self.message = message or self.default_message
        self.details = details or []
        if error_code:
            self.error_code = error_code
        super().__init__(self.message)


class ValidationError(AppError):
    status_code = 400
    error_code = CommonErrorCode.VALIDATION_ERROR
    default_message = "Request could not be validated"


class NotFoundError(AppError):
    status_code = 404
    error_code = CommonErrorCode.NOT_FOUND
    default_message = "Resource not found"


class ConflictError(AppError):
    status_code = 409
    error_code = CommonErrorCode.CONFLICT
    default_message = "Resource conflict"


class AuthenticationError(AppError):
    status_code = 401
    error_code = AuthErrorCode.AUTHENTICATION_FAILED
    default_message = "Authentication failed"


class PermissionDeniedError(AppError):
    status_code = 403
    error_code = CommonErrorCode.PERMISSION_DENIED
    default_message = "You do not have permission to perform this action"


class ServiceUnavailableError(AppError):
    status_code = 503
    error_code = CommonErrorCode.SERVICE_UNAVAILABLE
    default_message = "Service temporarily unavailable"


class RateLimitedError(AppError):
    status_code = 429
    error_code = CommonErrorCode.RATE_LIMITED
    default_message = "Too many requests. Please try again later."

    def __init__(
        self,
        message: str | None = None,
        *,
        retry_after_seconds: int | None = None,
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message, details=details)
        self.retry_after_seconds = retry_after_seconds
