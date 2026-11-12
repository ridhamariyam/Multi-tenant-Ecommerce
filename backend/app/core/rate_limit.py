from __future__ import annotations

import hashlib

from app.core.cache import get_redis
from app.core.config import get_settings
from app.core.exceptions import RateLimitedError

KEY_PREFIX = "ratelimit"


def key_for(scope: str, *parts: str) -> str:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:32]
    return f"{KEY_PREFIX}:{scope}:{digest}"


async def hit(key: str, *, limit: int, window_seconds: int) -> None:
    if limit <= 0:
        return

    try:
        client = get_redis()
        pipeline = client.pipeline()
        pipeline.incr(key)
        pipeline.ttl(key)
        count, ttl = await pipeline.execute()

        if ttl < 0:
            await client.expire(key, window_seconds)
            ttl = window_seconds
    except Exception:
        # Redis is down: fail open rather than refuse every request.
        return

    if count > limit:
        raise RateLimitedError(retry_after_seconds=max(int(ttl), 1))


async def enforce(scope: str, *parts: str, limit: int, window_seconds: int) -> None:
    """Throttle one scope for whoever the caller identifies as the subject."""
    await hit(key_for(scope, *parts), limit=limit, window_seconds=window_seconds)


async def reset(key: str) -> None:
    try:
        await get_redis().delete(key)
    except Exception:
        # Best effort: an unreset counter only expires at the end of its window.
        return


async def enforce_guest_checkout(tenant_id: str, ip: str, subject: str) -> None:
    """Guest checkout throttle: per shopper (``subject``), then per IP ceiling.

    The per-IP counter is checked first so that minting new cart tokens never
    escapes it; a shopper's own retries are bounded by the per-subject limit.
    """
    settings = get_settings()
    window = settings.commerce_rate_limit_window_seconds
    await enforce("guest-checkout-ip", tenant_id, ip, limit=settings.guest_checkout_ip_rate_limit_attempts, window_seconds=window)
    await enforce("guest-checkout", tenant_id, ip, subject, limit=settings.guest_checkout_rate_limit_attempts, window_seconds=window)
