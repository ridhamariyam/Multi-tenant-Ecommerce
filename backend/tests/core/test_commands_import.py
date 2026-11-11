"""Every command runs in its own process: its models must resolve on their own."""

from __future__ import annotations

import pkgutil
import subprocess
import sys

import pytest

import app.commands

COMMANDS = sorted(m.name for m in pkgutil.iter_modules(app.commands.__path__))


@pytest.mark.parametrize("name", COMMANDS)
def test_a_command_loads_with_every_foreign_key_resolvable(name):
    code = (
        f"import app.commands.{name}\n"
        "from sqlalchemy.orm import configure_mappers\n"
        "from app.models.base import Base\n"
        "configure_mappers()\n"
        "for table in Base.metadata.sorted_tables:\n"
        "    for fk in table.foreign_keys:\n"
        "        fk.column\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr[-2000:]
