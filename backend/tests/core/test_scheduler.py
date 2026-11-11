"""The job scheduler: failures are contained and reported, never fatal."""

from __future__ import annotations

import asyncio
import json
import os
import time

from app.commands import scheduler
from app.commands.scheduler import Job, run_once


def _lines(capsys) -> list[dict]:
    return [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.strip()]


async def test_a_successful_job_is_logged_ok(capsys):
    async def work():
        return 3

    await run_once(Job("demo", 60, 5, work))

    (line,) = _lines(capsys)
    assert line["job"] == "demo" and line["status"] == "ok" and line["result"] == 3


async def test_an_exception_is_contained_and_logged(capsys):
    async def boom():
        raise RuntimeError("database went away")

    await run_once(Job("demo", 60, 5, boom))  # must not raise

    (line,) = _lines(capsys)
    assert line["status"] == "failed"
    assert line["error"] == "RuntimeError"
    assert "database went away" in line["detail"]


async def test_a_slow_job_times_out(capsys):
    async def slow():
        await asyncio.sleep(5)

    await run_once(Job("demo", 60, 0.05, slow))

    (line,) = _lines(capsys)
    assert line["status"] == "failed" and line["error"] == "timeout"


async def test_a_partial_failure_is_reported(capsys):
    async def partial():
        return False

    await run_once(Job("demo", 60, 5, partial))

    assert _lines(capsys)[0]["status"] == "failed"


def test_the_healthcheck_follows_the_heartbeat(tmp_path, monkeypatch):
    beat = tmp_path / "beat"
    monkeypatch.setattr(scheduler, "HEARTBEAT", beat)
    assert scheduler.check() == 1  # never started

    beat.touch()
    assert scheduler.check() == 0

    old = time.time() - scheduler.STALE_AFTER_SECONDS - 10
    os.utime(beat, (old, old))
    assert scheduler.check() == 1  # loop stuck


def test_every_command_job_is_scheduled():
    from app.brands.platform_system import EXPECTED_JOBS

    jobs = {job.name: job.every_seconds for job in scheduler._jobs()}
    assert set(jobs) == {"disk-space", "order-sheets", "expire-orders", "shipment-sync", "expire-carts", "review-requests"}
    assert jobs == EXPECTED_JOBS  # the operator console knows every job
