"""Bring the database schema up to this release (the `migrate` service).

    python -m app.commands.migrate

Runs `alembic upgrade head`, with one exception: the database is already at a
revision this code does not know. That only happens on a rollback, after a
newer release migrated it. Migrations are additive, so the older code runs on
the newer schema. Exiting with an error instead would keep the rolled-back
`api` from starting at all, because it waits for `migrate` to succeed. Any
other failure still exits non-zero.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


async def database_revision() -> str | None:
    """The revision stamped in the database; None for a fresh database."""
    from app.core.database import AsyncSessionLocal, dispose_engine

    try:
        async with AsyncSessionLocal() as session:
            try:
                return await session.scalar(text("select version_num from alembic_version"))
            except ProgrammingError:  # no alembic_version table yet
                return None
    finally:
        await dispose_engine()


def is_known(script: ScriptDirectory, revision: str) -> bool:
    try:
        return script.get_revision(revision) is not None
    except Exception:  # alembic raises ResolutionError / CommandError subclasses
        return False


def main() -> int:
    config = Config(str(ALEMBIC_INI))
    script = ScriptDirectory.from_config(config)
    current = asyncio.run(database_revision())
    if current is not None and not is_known(script, current):
        print(
            json.dumps(
                {
                    "logger": "migrate",
                    "status": "skipped",
                    "reason": "database is at a newer revision than this release (rollback)",
                    "database_revision": current,
                    "code_head": script.get_current_head(),
                }
            ),
            flush=True,
        )
        return 0
    command.upgrade(config, "head")
    return 0


if __name__ == "__main__":
    sys.exit(main())
