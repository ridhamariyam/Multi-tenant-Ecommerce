from __future__ import annotations

from pydantic import Field

from app.core.schemas import StrictModel

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


class PageParams(StrictModel):
    """Query parameters every listing accepts, and nothing else."""

    page: int = Field(default=1, ge=1, description="1-based page number")
    page_size: int = Field(
        default=DEFAULT_PAGE_SIZE,
        ge=1,
        le=MAX_PAGE_SIZE,
        description=f"Items per page (max {MAX_PAGE_SIZE})",
    )

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        return self.page_size


def total_pages(total_items: int, page_size: int) -> int:
    return (total_items + page_size - 1) // page_size
