"""What every try-on provider implements. Provider HTTP stays in its own module."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


class ProviderError(Exception):
    """A provider call failed.

    `retryable` marks transient failures (rate limit, concurrency, 5xx,
    network) worth trying again; others (bad input, no credits, auth) are final.
    """

    def __init__(self, code: str, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


@dataclass(frozen=True)
class TryOnRequest:
    model_image: bytes
    model_image_type: str
    product_image: bytes
    product_image_type: str
    resolution: str
    generation_mode: str
    output_format: str
    num_images: int
    seed: int | None = None
    prompt: str | None = None
    webhook_url: str | None = None


@dataclass(frozen=True)
class ProviderStatus:
    """Normalised status. `state` is one of starting/processing/completed/failed."""

    state: str
    outputs: list[str] = field(default_factory=list)  # URLs or data: URIs
    error_code: str | None = None
    error_message: str | None = None
    retryable: bool = False
    credits_used: int | None = None
    raw: dict | None = None


@dataclass(frozen=True)
class FetchedOutput:
    data: bytes
    content_type: str | None


class TryOnProvider(Protocol):
    name: str
    model_name: str

    async def generate_tryon(self, request: TryOnRequest) -> str:
        """Submit one request. Returns the provider's prediction id."""
        ...

    async def get_status(self, prediction_id: str) -> ProviderStatus: ...

    async def handle_result(self, output: str, *, max_bytes: int) -> FetchedOutput:
        """Fetch one output (URL or data URI) safely, server-side."""
        ...
