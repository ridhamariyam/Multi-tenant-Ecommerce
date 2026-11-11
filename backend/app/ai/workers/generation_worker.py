"""Celery tasks. Thin wrappers: the logic lives in app.ai.services.job_service."""

from __future__ import annotations

import asyncio
import logging
import uuid

from app.ai.celery_app import celery_app
from app.ai.services import job_service
from app.ai.workers.dispatch import enqueue_poll, enqueue_submit
from app.core.cache import close_redis
from app.core.database import AsyncSessionLocal, dispose_engine

logger = logging.getLogger(__name__)


def _run(coro_factory):
    """Each task gets its own event loop; connections must not outlive it."""

    async def runner():
        try:
            return await coro_factory()
        finally:
            await dispose_engine()
            await close_redis()

    return asyncio.run(runner())


async def _step(kind: str, job_id: uuid.UUID) -> None:
    async with AsyncSessionLocal() as session:
        step = job_service.submit_job if kind == "submit" else job_service.poll_job
        result = await step(session, job_id)
    follow_up(job_id, result)


def follow_up(job_id: uuid.UUID, result: job_service.StepResult) -> None:
    if result.submit_in is not None:
        enqueue_submit(job_id, result.submit_in)
    if result.poll_in is not None:
        enqueue_poll(job_id, result.poll_in)


@celery_app.task(name="ai.submit")
def submit(job_id: str) -> None:
    _run(lambda: _step("submit", uuid.UUID(job_id)))


@celery_app.task(name="ai.poll")
def poll(job_id: str) -> None:
    _run(lambda: _step("poll", uuid.UUID(job_id)))


async def _sweep() -> None:
    async with AsyncSessionLocal() as session:
        resubmit, repoll = await job_service.stale_jobs(session)
    for job_id in resubmit:
        enqueue_submit(job_id)
    for job_id in repoll:
        enqueue_poll(job_id)
    if resubmit or repoll:
        logger.info("ai sweep: %d resubmitted, %d re-polled", len(resubmit), len(repoll))


@celery_app.task(name="ai.sweep")
def sweep() -> None:
    _run(_sweep)
