from __future__ import annotations

from app.ai.providers.base import TryOnProvider
from app.core.config import get_settings

_override: TryOnProvider | None = None


def configured_provider_name() -> str | None:
    settings = get_settings()
    if _override is not None:
        return _override.name
    if settings.ai_provider == "fashn" and not settings.fashn_api_key:
        return None
    return settings.ai_provider


def get_provider() -> TryOnProvider | None:
    """The configured provider, or None when AI generation is not set up."""
    if _override is not None:
        return _override
    settings = get_settings()
    if settings.ai_provider == "fashn" and settings.fashn_api_key:
        from app.ai.providers.fashn import FashnProvider

        return FashnProvider(
            api_key=settings.fashn_api_key,
            base_url=settings.fashn_api_url,
            model_name=settings.fashn_model_name,
            timeout=settings.fashn_timeout_seconds,
        )
    if settings.ai_provider == "mock" and not settings.is_production:
        from app.ai.providers.mock import MockProvider

        return MockProvider()
    return None


def set_provider(provider: TryOnProvider | None) -> None:
    """Tests: install a provider (or None to go back to settings)."""
    global _override
    _override = provider
