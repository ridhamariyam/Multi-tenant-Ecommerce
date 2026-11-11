"""Run the platform's periodic jobs from one long-lived process.

    python -m app.commands.scheduler          # run forever
    python -m app.commands.scheduler --check  # exit 0 if the loop is alive (healthcheck)

Jobs run one after another (never two at once, so they never share a
database connection pool mid-run), each with a time limit. A job that fails
or times out is logged and tried again at its next interval; it never stops
the others. Every log line is one JSON object so a log collector can alert
on `"status": "failed"`. The loop touches a heartbeat file each tick; the
container healthcheck fails if it goes stale.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

HEARTBEAT = Path(os.environ.get("SCHEDULER_HEARTBEAT_FILE", "/tmp/cliq-scheduler-heartbeat"))
TICK_SECONDS = 15
STALE_AFTER_SECONDS = 300


@dataclass
class Job:
    name: str
    every_seconds: int
    timeout_seconds: int
    run: Callable[[], Awaitable[object]]
    next_at: float = 0.0


def _jobs() -> list[Job]:
    # Imported here so --check stays fast and needs no database settings.
    from app.commands.expire_carts import expire_carts
    from app.commands.expire_orders import expire_orders
    from app.commands.send_emails import send_emails
    from app.commands.send_review_requests import send_review_requests
    from app.commands.sync_order_sheets import sync_order_sheets
    from app.commands.sync_shipments import sync_shipments

    def every(name: str, default: int) -> int:
        return int(os.environ.get(f"JOB_{name.upper().replace('-', '_')}_SECONDS", default))

    return [
        Job("disk-space", every("disk-space", 600), 30, check_disk_space),
        Job("emails", every("emails", 30), 120, send_emails),
        Job("order-sheets", every("order-sheets", 60), 300, sync_order_sheets),
        Job("expire-orders", every("expire-orders", 300), 300, expire_orders),
        Job("shipment-sync", every("shipment-sync", 900), 600, sync_shipments),
        Job("expire-carts", every("expire-carts", 3600), 600, expire_carts),
        Job("review-requests", every("review-requests", 3600), 600, send_review_requests),
    ]


JOB_STATUS_KEY = "cliq:jobs"


async def check_disk_space() -> dict | bool:
    """Fail (and so alert) when the disk Docker keeps volumes on is nearly full.

    Postgres, MinIO and backups share that disk; a full disk stops orders.
    """
    import shutil

    path = os.environ.get("DISK_CHECK_PATH", "/")
    minimum = float(os.environ.get("DISK_ALERT_FREE_PERCENT", "10"))
    usage = shutil.disk_usage(path)
    free_percent = round(usage.free * 100 / usage.total, 1)
    if free_percent < minimum:
        raise RuntimeError(f"only {free_percent}% disk free ({usage.free // 2**20} MB)")
    return {"free_percent": free_percent}


def log(**fields: object) -> None:
    print(json.dumps({"ts": datetime.now(timezone.utc).isoformat(), "logger": "scheduler", **fields}), flush=True)


async def record(job: Job, status: str, duration_ms: int, error: str | None) -> None:
    """Keep each job's latest outcome where the platform console can read it,
    and alert (throttled) when a job fails. Never raises."""
    from app.core.cache import get_redis
    from app.core.observability import send_alert

    entry = {
        "status": status,
        "at": datetime.now(timezone.utc).isoformat(),
        "duration_ms": duration_ms,
        "every_seconds": job.every_seconds,
        "timeout_seconds": job.timeout_seconds,
        "error": error,
    }
    try:
        redis = get_redis()
        if status == "ok":
            entry["last_ok_at"] = entry["at"]
        else:
            previous = await redis.hget(JOB_STATUS_KEY, job.name)
            if previous:
                entry["last_ok_at"] = json.loads(previous).get("last_ok_at")
        await redis.hset(JOB_STATUS_KEY, job.name, json.dumps(entry))
    except Exception as exc:
        log(job=job.name, status="record-failed", error=type(exc).__name__)
    if status != "ok":
        await send_alert(f"job:{job.name}", f"Background job {job.name} failed: {error or 'see logs'}")


async def run_once(job: Job) -> None:
    from app.core.observability import capture_exception

    started = time.monotonic()

    def elapsed() -> int:
        return int((time.monotonic() - started) * 1000)

    try:
        result = await asyncio.wait_for(job.run(), timeout=job.timeout_seconds)
    except asyncio.TimeoutError:
        log(job=job.name, status="failed", error="timeout", duration_ms=elapsed())
        await record(job, "failed", elapsed(), "timed out")
        return
    except Exception as exc:  # one job's failure never stops the scheduler
        log(job=job.name, status="failed", error=type(exc).__name__, detail=str(exc)[:300],
            duration_ms=elapsed())
        capture_exception(exc, job=job.name)
        await record(job, "failed", elapsed(), f"{type(exc).__name__}: {str(exc)[:200]}")
        return
    # Commands report partial failure by returning False.
    status = "failed" if result is False else "ok"
    log(job=job.name, status=status, duration_ms=elapsed(),
        **({"result": result} if isinstance(result, (int, dict)) else {}))
    await record(job, status, elapsed(), "reported a partial failure" if status == "failed" else None)


async def loop(jobs: list[Job]) -> None:
    log(status="started", jobs={j.name: j.every_seconds for j in jobs})
    while True:
        HEARTBEAT.touch()
        now = time.monotonic()
        for job in jobs:
            if now >= job.next_at:
                await run_once(job)
                job.next_at = time.monotonic() + job.every_seconds
                HEARTBEAT.touch()
        await asyncio.sleep(TICK_SECONDS)


def check() -> int:
    try:
        age = time.time() - HEARTBEAT.stat().st_mtime
    except FileNotFoundError:
        return 1
    return 0 if age < STALE_AFTER_SECONDS else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="CliQ. periodic jobs")
    parser.add_argument("--check", action="store_true", help="healthcheck: is the loop alive?")
    args = parser.parse_args()
    if args.check:
        sys.exit(check())
    from app.core.config import get_settings
    from app.core.observability import init_error_reporting

    settings = get_settings()
    init_error_reporting(dsn=settings.sentry_dsn, environment=settings.environment,
                         release=settings.release, service="scheduler")
    asyncio.run(loop(_jobs()))


if __name__ == "__main__":
    main()
