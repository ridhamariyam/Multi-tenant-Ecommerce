"""The migrate service lets a rollback start on a schema a newer release migrated."""

from __future__ import annotations

from alembic.config import Config
from alembic.script import ScriptDirectory

from app.commands import migrate


def _script() -> ScriptDirectory:
    return ScriptDirectory.from_config(Config(str(migrate.ALEMBIC_INI)))


def test_every_revision_in_this_release_is_known():
    script = _script()
    for revision in script.walk_revisions():
        assert migrate.is_known(script, revision.revision)


def test_a_revision_from_a_newer_release_is_not_known():
    assert not migrate.is_known(_script(), "ffff0000future")


def test_a_newer_database_is_skipped_not_failed(monkeypatch, capsys):
    async def newer():
        return "ffff0000future"

    upgraded = []
    monkeypatch.setattr(migrate, "database_revision", newer)
    monkeypatch.setattr(migrate.command, "upgrade", lambda *a, **k: upgraded.append(a))

    assert migrate.main() == 0
    assert upgraded == []
    assert '"status": "skipped"' in capsys.readouterr().out


def test_a_known_or_fresh_database_is_upgraded(monkeypatch):
    head = _script().get_current_head()
    for current in (None, head):

        async def revision(value=current):
            return value

        upgraded = []
        monkeypatch.setattr(migrate, "database_revision", revision)
        monkeypatch.setattr(migrate.command, "upgrade", lambda config, target: upgraded.append(target))

        assert migrate.main() == 0
        assert upgraded == ["head"]
