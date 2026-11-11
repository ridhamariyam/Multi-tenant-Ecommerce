from __future__ import annotations

from app.core.config import Settings


def _settings(**values) -> Settings:
    base = {
        "database_url": "postgresql+asyncpg://u:p@h/d",
        "redis_url": "redis://h/0",
        "jwt_secret": "a" * 32,
        "jwt_refresh_secret": "b" * 32,
        "razorpay_key_id": None,
        "razorpay_key_secret": None,
        "sandbox_razorpay_api_key": "rzp_test_k",
        "sandbox_razorpay_api_secret": "test-secret",
        "production_razorpay_api_key": "rzp_live_k",
        "production_razorpay_api_secret": "live-secret",
    }
    return Settings(_env_file=None, **{**base, **values})


def test_sandbox_credentials_are_used_by_default() -> None:
    settings = _settings()
    assert (settings.razorpay_key_id, settings.razorpay_key_secret) == ("rzp_test_k", "test-secret")


def test_production_environment_selects_live_credentials() -> None:
    settings = _settings(razorpay_environment="production")
    assert (settings.razorpay_key_id, settings.razorpay_key_secret) == ("rzp_live_k", "live-secret")


def test_placeholder_secret_leaves_gateway_unconfigured() -> None:
    settings = _settings(
        razorpay_environment="production",
        production_razorpay_api_secret="your_live_key_secret",
    )
    assert settings.razorpay_key_id is None
    assert settings.razorpay_key_secret is None


def test_explicit_key_wins() -> None:
    settings = _settings(razorpay_key_id="rzp_explicit", razorpay_key_secret="explicit")
    assert settings.razorpay_key_id == "rzp_explicit"
