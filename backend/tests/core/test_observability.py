"""Logs, error reporting, alerts and the operator's system-health view."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.brands.platform_system import JOB_STATUS_KEY, job_health
from app.commands.scheduler import Job, run_once
from app.core import cache, observability
from app.core.config import get_settings
from app.core.request_context import set_request_id


def _record(msg="hello", **extra) -> logging.LogRecord:
    record = logging.makeLogRecord({"name": "app.test", "levelname": "INFO", "msg": msg})
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_json_logs_carry_the_request_id_and_extra_fields():
    set_request_id("req-123")
    try:
        line = json.loads(observability.JsonFormatter().format(_record(path="/x", status=200)))
    finally:
        set_request_id("-")

    assert line["msg"] == "hello" and line["level"] == "info"
    assert line["request_id"] == "req-123"
    assert line["path"] == "/x" and line["status"] == 200


def test_json_logs_include_the_traceback():
    try:
        raise ValueError("bad")
    except ValueError:
        import sys

        record = _record(exc_info=sys.exc_info())
    line = json.loads(observability.JsonFormatter().format(record))
    assert "ValueError: bad" in line["exc"]


def test_error_reports_never_carry_secrets_or_bodies():
    event = {
        "request": {
            "headers": {"Authorization": "Bearer x", "Cookie": "a=b", "X-Cart-Token": "t", "Accept": "json"},
            "cookies": {"a": "b"},
            "data": {"password": "p"},
        }
    }
    scrubbed = observability._scrub(event)["request"]
    assert scrubbed["headers"] == {
        "Authorization": "[filtered]", "Cookie": "[filtered]", "X-Cart-Token": "[filtered]", "Accept": "json"
    }
    assert "data" not in scrubbed and "cookies" not in scrubbed


def test_without_a_dsn_errors_are_only_logged():
    assert observability.init_error_reporting(dsn=None, environment="test", release=None) is False


@pytest.fixture
def webhook(monkeypatch):
    sent: list[dict] = []
    real = httpx.AsyncClient

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(200)

    monkeypatch.setattr(
        observability.httpx, "AsyncClient",
        lambda **kw: real(transport=httpx.MockTransport(handler), **kw),
    )
    monkeypatch.setattr(get_settings(), "alert_webhook_url", "https://hooks.example.test/x")
    return sent


async def test_an_alert_is_sent_once_per_window(webhook):
    key = f"test:{datetime.now().timestamp()}"
    assert await observability.send_alert(key, "Disk almost full") is True
    assert await observability.send_alert(key, "Disk almost full") is False
    assert len(webhook) == 1
    assert "Disk almost full" in webhook[0]["text"] and webhook[0]["content"] == webhook[0]["text"]


async def test_no_webhook_means_no_alert(monkeypatch):
    monkeypatch.setattr(get_settings(), "alert_webhook_url", None)
    assert await observability.send_alert("x", "y") is False


async def test_a_failing_job_is_recorded_and_alerts(webhook, capsys):
    redis = cache.get_redis()
    await redis.delete(JOB_STATUS_KEY)
    name = f"demo-{datetime.now().timestamp()}"

    async def ok():
        return 1

    async def boom():
        raise RuntimeError("db down")

    await run_once(Job(name, 60, 5, ok))
    await run_once(Job(name, 60, 5, boom))

    entry = json.loads(await redis.hget(JOB_STATUS_KEY, name))
    assert entry["status"] == "failed" and entry["error"] == "RuntimeError: db down"
    assert entry["last_ok_at"] is not None  # kept from the earlier success
    assert len(webhook) == 1 and name in webhook[0]["text"]
    await redis.delete(JOB_STATUS_KEY)


def test_job_health_flags_a_job_that_stopped_running():
    now = datetime.now(timezone.utc)
    fresh = json.dumps({"status": "ok", "at": now.isoformat(), "every_seconds": 60, "timeout_seconds": 60, "last_ok_at": now.isoformat()})
    old_at = (now - timedelta(hours=1)).isoformat()
    old = json.dumps({"status": "ok", "at": old_at, "every_seconds": 60, "timeout_seconds": 60, "last_ok_at": old_at})

    assert job_health("a", fresh, 60, now).status == "ok"
    assert job_health("a", old, 60, now).status == "stale"
    assert job_health("a", None, 60, now).status == "never_ran"


async def test_a_nearly_full_disk_fails_the_disk_job(monkeypatch):
    import shutil
    from collections import namedtuple

    from app.commands import scheduler

    Usage = namedtuple("Usage", "total used free")
    monkeypatch.setattr(shutil, "disk_usage", lambda _p: Usage(100 * 2**30, 95 * 2**30, 5 * 2**30))
    with pytest.raises(RuntimeError, match="5.0% disk free"):
        await scheduler.check_disk_space()

    monkeypatch.setattr(shutil, "disk_usage", lambda _p: Usage(100 * 2**30, 50 * 2**30, 50 * 2**30))
    assert await scheduler.check_disk_space() == {"free_percent": 50.0}
