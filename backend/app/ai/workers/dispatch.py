"""Hand work to the Celery worker. A broker outage never fails the API call:
the job stays queued and the periodic sweep submits it later."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable

logger = logging.getLogger(__name__)

# Tests replace this to observe (and run) dispatched work without a broker.
_sender: Callable[[str, uuid.UUID, float], None] | None = None


def set_sender(sender: Callable[[str, uuid.UUID, float], None] | None) -> None:
    global _sender
    _sender = sender


def _send(task: str, job_id: uuid.UUID, countdown: float = 0) -> None:
    if _sender is not None:
        _sender(task, job_id, countdown)
        return
    try:
        from app.ai.celery_app import celery_app

        celery_app.send_task(task, args=[str(job_id)], countdown=countdown or None)
    except Exception:
        logger.warning("ai: could not enqueue %s for job %s; the sweep will retry", task, job_id)


def enqueue_submit(job_id: uuid.UUID, countdown: float = 0) -> None:
    _send("ai.submit", job_id, countdown)


def enqueue_poll(job_id: uuid.UUID, countdown: float = 0) -> None:
    _send("ai.poll", job_id, countdown)
