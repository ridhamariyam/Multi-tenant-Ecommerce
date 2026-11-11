"""Platform operator view of the running system: dependencies, background
jobs, and which external providers have credentials configured."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import cache
from app.core.config import get_settings
from app.core.database import get_db
from app.core.observability import error_reporting_enabled
from app.core.responses import ApiResponse, ok
from app.merchants.dependencies import PlatformAdmin

router = APIRouter(prefix="/platform/admin", tags=["Platform Admin"])

JOB_STATUS_KEY = "cliq:jobs"
# The scheduler's jobs and default intervals (app/commands/scheduler.py).
EXPECTED_JOBS = {
    "disk-space": 600,
    "order-sheets": 60,
    "expire-orders": 300,
    "shipment-sync": 900,
    "expire-carts": 3600,
    "review-requests": 3600,
}


class JobHealth(BaseModel):
    name: str
    status: Literal["ok", "failed", "stale", "never_ran"]
    last_run_at: datetime | None = None
    last_ok_at: datetime | None = None
    every_seconds: int
    error: str | None = None


class ProviderStatus(BaseModel):
    key: str
    name: str
    configured: bool
    needed_for: str


class SystemHealth(BaseModel):
    environment: str
    release: str | None
    database: bool
    redis: bool
    error_reporting: bool
    alerts: bool
    jobs: list[JobHealth]
    providers: list[ProviderStatus]


def job_health(name: str, raw: str | None, default_every: int, now: datetime) -> JobHealth:
    if not raw:
        return JobHealth(name=name, status="never_ran", every_seconds=default_every)
    entry = json.loads(raw)
    every = int(entry.get("every_seconds") or default_every)
    timeout = int(entry.get("timeout_seconds") or 600)
    at = datetime.fromisoformat(entry["at"])
    last_ok = entry.get("last_ok_at")
    status = entry.get("status", "failed")
    # Not seen for two intervals plus its time limit: the scheduler is down or stuck.
    if (now - at).total_seconds() > 2 * every + timeout:
        status = "stale"
    return JobHealth(
        name=name,
        status=status if status in ("ok", "failed", "stale") else "failed",
        last_run_at=at,
        last_ok_at=datetime.fromisoformat(last_ok) if last_ok else None,
        every_seconds=every,
        error=entry.get("error"),
    )


def providers() -> list[ProviderStatus]:
    from app.integrations import google_sheets

    s = get_settings()
    rows = [
        ("razorpay", "Razorpay payments", bool(s.razorpay_key_id and s.razorpay_key_secret and s.razorpay_webhook_secret), "Online payments and refunds"),
        ("razorpay_subscriptions", "Razorpay Subscriptions", bool(getattr(s, "billing_razorpay_key_id", None) or (s.razorpay_key_id and getattr(s, "billing_webhook_secret", None))), "Brands paying their plan"),
        ("smtp", "Email (SMTP)", bool(getattr(s, "smtp_host", None)), "Password resets, order emails, campaigns"),
        ("msg91", "MSG91", bool(s.msg91_auth_key), "Customer OTP sign-in"),
        ("google_oauth", "Google sign-in", bool(s.google_client_id), "Customer Google sign-in"),
        ("google_sheets", "Google Sheets", google_sheets.is_configured(), "Order export to Sheets"),
        ("shiprocket", "Shiprocket", bool(s.shiprocket_email and s.shiprocket_password), "Courier booking and tracking"),
        ("fashn", "FASHN", bool(s.fashn_api_key), "AI try-on"),
        ("s3", "Object storage", s.storage_backend == "s3", "Product images"),
        ("sentry", "Sentry", bool(s.sentry_dsn), "Error reporting"),
        ("alerts", "Alert webhook", bool(s.alert_webhook_url), "Job failure alerts"),
    ]
    return [ProviderStatus(key=k, name=n, configured=c, needed_for=f) for k, n, c, f in rows]


@router.get("/system", response_model=ApiResponse[SystemHealth], summary="System health")
async def system_health(
    admin: PlatformAdmin, session: AsyncSession = Depends(get_db)
) -> ApiResponse[SystemHealth]:
    settings = get_settings()
    try:
        await session.execute(text("SELECT 1"))
        database = True
    except Exception:
        database = False
    try:
        raw = await cache.get_redis().hgetall(JOB_STATUS_KEY)
        redis_ok = True
    except Exception:
        raw, redis_ok = {}, False
    now = datetime.now(timezone.utc)
    names = list(EXPECTED_JOBS) + sorted(set(raw) - set(EXPECTED_JOBS))
    jobs = [job_health(n, raw.get(n), EXPECTED_JOBS.get(n, 3600), now) for n in names]
    return ok(
        SystemHealth(
            environment=settings.environment,
            release=settings.release,
            database=database,
            redis=redis_ok,
            error_reporting=error_reporting_enabled(),
            alerts=bool(settings.alert_webhook_url),
            jobs=jobs,
            providers=providers(),
        ),
        message="System health",
    )
