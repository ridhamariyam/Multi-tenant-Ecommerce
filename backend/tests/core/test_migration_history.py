"""A database built only from the migration history matches the models, both ways."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import pytest_asyncio
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy.ext.asyncio import create_async_engine

BACKEND_DIR = Path(__file__).resolve().parents[2]
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")


def _with_database(url: str, name: str) -> str:
    return urlunsplit(urlsplit(url)._replace(path=f"/{name}"))


MIGRATIONS_DATABASE = f"{urlsplit(TEST_DATABASE_URL).path.lstrip('/')}_migrations"
MIGRATIONS_URL = _with_database(TEST_DATABASE_URL, MIGRATIONS_DATABASE)


async def _admin(statement: str) -> None:
    engine = create_async_engine(
        _with_database(TEST_DATABASE_URL, "postgres"), isolation_level="AUTOCOMMIT"
    )
    async with engine.connect() as connection:
        await connection.exec_driver_sql(statement)
    await engine.dispose()


@pytest_asyncio.fixture(loop_scope="session")
async def migrations_database():
    await _admin(f'DROP DATABASE IF EXISTS "{MIGRATIONS_DATABASE}" WITH (FORCE)')
    await _admin(f'CREATE DATABASE "{MIGRATIONS_DATABASE}"')
    yield MIGRATIONS_URL
    await _admin(f'DROP DATABASE IF EXISTS "{MIGRATIONS_DATABASE}" WITH (FORCE)')


def _alembic(url: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        env={**os.environ, "DATABASE_URL": url},
        capture_output=True,
        text=True,
    )


def _one_step_back() -> list[str]:
    """Targets for `downgrade -1`, which alembic cannot resolve at a merge.

    At a merge head, stepping into one parent undoes the merge and the
    branches only the other parents hold. Some migrations refuse to go back
    (financial records), so each parent is a candidate; a refused attempt
    rolls back in its transaction and the next is tried.
    """
    script = ScriptDirectory.from_config(Config(str(BACKEND_DIR / "alembic.ini")))
    parents = script.get_revision(script.get_current_head()).down_revision
    return list(parents) if isinstance(parents, tuple) else ["-1"]


def _step_back(url: str) -> subprocess.CompletedProcess:
    for target in _one_step_back():
        result = _alembic(url, "downgrade", target)
        if result.returncode == 0:
            break
    return result


async def test_the_history_upgrades_to_the_models_and_back(migrations_database):
    for step in (("upgrade", "head"), ("check",), ("downgrade",), ("upgrade", "head")):
        if step == ("downgrade",):
            result = _step_back(migrations_database)
        else:
            result = _alembic(migrations_database, *step)
        assert result.returncode == 0, f"alembic {' '.join(step)}:\n{result.stderr}"

    final = _alembic(migrations_database, "check")
    assert final.returncode == 0, final.stderr
