from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

from app.core.pagination import PageParams, total_pages

T = TypeVar("T")


class PageMeta(BaseModel):
    page: int
    page_size: int
    total_items: int
    total_pages: int


class ApiResponse(BaseModel, Generic[T]):
    success: bool = True
    message: str = "OK"
    data: T | None = None
    meta: PageMeta | None = None


class ErrorPayload(BaseModel):
    """The machine-readable part of a failure. Branch on `code`, show `message`.

    `code` is one of the values in app.core.error_codes. `details` is always a
    list (empty when there is nothing field-level to report).
    """

    code: str = Field(examples=["ORDER_NOT_FOUND"])
    message: str = Field(examples=["Order not found"])
    details: list[dict[str, Any]] = Field(default_factory=list)
    request_id: str | None = None


class ErrorResponse(BaseModel):
    success: bool = False
    message: str = "Request failed"
    error: ErrorPayload


def ok(data: T | None = None, message: str = "OK") -> ApiResponse[T]:
    return ApiResponse[T](success=True, message=message, data=data)


def paginated(
    items: Sequence[T],
    *,
    total_items: int,
    params: PageParams,
    message: str = "OK",
) -> ApiResponse[list[T]]:
    return ApiResponse[list[T]](
        success=True,
        message=message,
        data=list(items),
        meta=PageMeta(
            page=params.page,
            page_size=params.page_size,
            total_items=total_items,
            total_pages=total_pages(total_items, params.page_size),
        ),
    )
