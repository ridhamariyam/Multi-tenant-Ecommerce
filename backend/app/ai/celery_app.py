"""Celery for AI generation. Broker and result backend: Redis.

Run the worker (with its periodic sweep) as its own container:
    celery -A app.ai.celery_app worker -B --loglevel=INFO --concurrency=4
"""

from __future__ import annotations

from celery import Celery

from app.core.config import get_settings

settings = get_settings()
broker = settings.celery_broker_url or settings.redis_url

celery_app = Celery("cliq_ai", broker=broker, backend=None, include=["app.ai.workers.generation_worker"])
celery_app.conf.update(
    task_always_eager=settings.celery_task_always_eager,
    task_acks_late=True,  # a worker that dies mid-task leaves it for another
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_default_queue="ai",
    task_ignore_result=True,
    broker_connection_retry_on_startup=True,
    beat_schedule={
        "ai-sweep": {"task": "ai.sweep", "schedule": 30.0},
    },
    timezone="UTC",
)
