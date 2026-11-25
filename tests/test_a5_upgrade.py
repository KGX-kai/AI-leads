"""Synthetic migration and restore checks. Never opens a production database or Keychain."""

import pytest
from sqlalchemy import select

from jxd_leads.db import Database
from jxd_leads.models import Research, Tag
from jxd_leads.security import Vault
from jxd_leads.service import Service


@pytest.mark.parametrize("precreated", [False, True])
def test_new_database_has_no_inherited_test_scope_and_preserves_later_tags(tmp_path, precreated):
    database = Database(tmp_path / "fresh" / "leads.db")
    if precreated:
        database.path.parent.mkdir(parents=True)
        database.path.touch()
    database.migrate()
    service = Service(database, Vault.ephemeral())
    assert service.tags() == []
    tag = service.add_tag("本人指定的合成分类")
    database.migrate()
    assert service.tags() == [tag]


def test_existing_database_tags_are_not_cleaned_on_startup(svc):
    with svc.db.session() as session:
        session.add(Tag(id="synthetic-existing-tag", name="物业"))
    svc.db.migrate()
    assert any(tag["id"] == "synthetic-existing-tag" for tag in svc.tags())


@pytest.mark.parametrize("interrupted_revision", ["bbad41c2a094", "head"])
def test_interrupted_fresh_initialization_resumes_cleanup(tmp_path, monkeypatch, interrupted_revision):
    from jxd_leads.db import command

    database = Database(tmp_path / "interrupted.db")
    upgrade = command.upgrade

    def fail_after_migration(config, target):
        upgrade(config, interrupted_revision)
        raise RuntimeError("synthetic interruption before initialization cleanup")

    monkeypatch.setattr(command, "upgrade", fail_after_migration)
    with pytest.raises(RuntimeError, match="synthetic interruption"):
        database.migrate()
    monkeypatch.setattr(command, "upgrade", upgrade)
    database.migrate()
    assert Service(database, Vault.ephemeral()).tags() == []


@pytest.mark.parametrize("new_data", ["tag", "business"])
def test_interrupted_initialization_keeps_new_data_for_manual_recovery(tmp_path, monkeypatch, new_data):
    from jxd_leads.db import command

    database = Database(tmp_path / "interrupted-with-data.db")
    upgrade = command.upgrade

    def fail_after_migration(config, target):
        upgrade(config, target)
        raise RuntimeError("synthetic interruption")

    monkeypatch.setattr(command, "upgrade", fail_after_migration)
    with pytest.raises(RuntimeError, match="synthetic interruption"):
        database.migrate()
    with database.session() as session:
        if new_data == "tag":
            session.add(Tag(id="keep-user-tag", name="本人新增的合成分类"))
        else:
            session.add(Research(id="keep-research", region="合成地区", scene="合成场景"))
    with database.read_session() as session:
        before = set(session.execute(select(Tag.id, Tag.name)).all())
    monkeypatch.setattr(command, "upgrade", upgrade)
    with pytest.raises(RuntimeError, match="已有新增数据"):
        database.migrate()
    with database.read_session() as session:
        if new_data == "tag":
            assert session.get(Tag, "keep-user-tag").name == "本人新增的合成分类"
        else:
            assert session.get(Research, "keep-research").region == "合成地区"
        assert set(session.execute(select(Tag.id, Tag.name)).all()) == before


@pytest.mark.parametrize("mismatch", ["content", "database_identity"])
def test_initialization_marker_mismatch_stops_before_migration(tmp_path, monkeypatch, mismatch):
    from jxd_leads.db import command

    database = Database(tmp_path / "marker.db")
    upgrade = command.upgrade

    def fail_after_migration(config, target):
        upgrade(config, target)
        raise RuntimeError("synthetic interruption")

    monkeypatch.setattr(command, "upgrade", fail_after_migration)
    with pytest.raises(RuntimeError, match="synthetic interruption"):
        database.migrate()
    database.engine.dispose()
    marker = database.path.with_name("." + database.path.name + ".initializing")
    if mismatch == "content":
        marker.write_text("synthetic mismatched marker")
    else:
        replacement = tmp_path / "replacement.db"
        replacement.write_bytes(database.path.read_bytes())
        replacement.replace(database.path)

    def forbidden_upgrade(*args):
        pytest.fail("Marker mismatch must be checked before migration")

    monkeypatch.setattr(command, "upgrade", forbidden_upgrade)
    with database.read_session() as session:
        before = set(session.execute(select(Tag.id, Tag.name)).all())
    with pytest.raises(RuntimeError, match="标记与数据库不匹配"):
        database.migrate()
    with database.read_session() as session:
        assert set(session.execute(select(Tag.id, Tag.name)).all()) == before
