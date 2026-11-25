import asyncio
import os
import shutil
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from filelock import FileLock, Timeout
from sqlalchemy.exc import OperationalError

from jxd_leads.backup import backup_database, restore_database, run_backup, verify
from jxd_leads.db import (
    APPROVED_DATA_DIR_ENV,
    DIRECTORY_MARKER,
    Database,
    resolve_data_dir,
    resolve_runtime_data_dir,
    verify_directory_identity,
    write_directory_identity,
)
from jxd_leads.errors import BusinessError
from jxd_leads.security import Vault
from jxd_leads.web import create_app


@pytest.mark.parametrize(
    ("configured", "code"),
    [
        (None, "DATA_DIR_REQUIRED"),
        ("", "DATA_DIR_REQUIRED"),
        ("   ", "DATA_DIR_REQUIRED"),
        ("relative/synthetic", "DATA_DIR_NOT_ABSOLUTE"),
    ],
)
def test_data_directory_requires_explicit_absolute_path(configured, code):
    with pytest.raises(BusinessError) as error:
        resolve_data_dir(configured)
    assert error.value.code == code


def test_data_directory_rejects_existing_file(tmp_path):
    target = tmp_path / "not-a-directory"
    target.write_text("synthetic")
    with pytest.raises(BusinessError) as error:
        resolve_data_dir(target)
    assert error.value.code == "DATA_DIR_INVALID"


def test_database_path_is_absolute_and_initialization_is_explicit(tmp_path, monkeypatch):
    with pytest.raises(BusinessError) as error:
        Database(Path("relative.db"))
    assert error.value.code == "DATABASE_PATH_NOT_ABSOLUTE"

    database = Database(tmp_path / "nested" / "leads.db")
    with pytest.raises(BusinessError) as error:
        database.assert_initialized()
    assert error.value.code == "DATA_NOT_INITIALIZED"
    assert not database.path.parent.exists()

    database.migrate()
    database.assert_initialized()

    monkeypatch.setattr(sys, "argv", ["jxd-leads", "serve"])
    from jxd_leads import cli

    with pytest.raises(BusinessError) as error:
        cli._main()
    assert error.value.code == "DATA_DIR_REQUIRED"


def test_copied_database_without_directory_binding_is_rejected(tmp_path):
    approved = Database(tmp_path / "approved" / "leads.db")
    approved.migrate()
    copied_dir = tmp_path / "different"
    copied_dir.mkdir()
    shutil.copy2(approved.path, copied_dir / "leads.db")
    copied = Database(copied_dir / "leads.db")
    with pytest.raises(BusinessError) as error:
        copied.assert_initialized()
    assert error.value.code == "DATA_DIRECTORY_MISMATCH"


def test_replaced_database_in_bound_directory_is_rejected(tmp_path):
    approved = Database(tmp_path / "approved" / "leads.db")
    approved.migrate()
    other = Database(tmp_path / "other" / "leads.db")
    other.migrate()
    replacement = approved.path.with_suffix(".replacement.db")
    shutil.copy2(other.path, replacement)
    os.replace(replacement, approved.path)
    with pytest.raises(BusinessError) as error:
        approved.assert_initialized()
    assert error.value.code == "DATA_DIRECTORY_MISMATCH"


def test_blank_directory_marker_is_rejected(tmp_path):
    database = Database(tmp_path / "approved" / "leads.db")
    database.migrate()
    (database.path.parent / DIRECTORY_MARKER).write_text("", encoding="utf-8")

    with pytest.raises(BusinessError) as error:
        database.assert_initialized()
    assert error.value.code == "DATA_DIRECTORY_MISMATCH"


def test_dangling_directory_marker_stops_before_database_creation(tmp_path):
    target = tmp_path / "dangling" / "leads.db"
    target.parent.mkdir()
    marker = target.parent / DIRECTORY_MARKER
    marker.symlink_to(tmp_path / "missing-marker.json")

    with pytest.raises(BusinessError) as error:
        Database(target).migrate()
    assert error.value.code == "DATA_DIRECTORY_MISMATCH"
    assert not target.exists()
    assert marker.is_symlink()


def test_directory_marker_private_temporary_rejects_raced_symlink(tmp_path, monkeypatch):
    database = Database(tmp_path / "marker-race" / "leads.db")
    database.path.parent.mkdir(parents=True)
    database.path.write_bytes(b"synthetic database identity holder")
    victim = tmp_path / "synthetic-victim.json"
    victim.write_text("unchanged", encoding="utf-8")
    original_open = os.open

    def race_open(path, flags, mode=0o777):
        path = Path(path)
        if (
            path.parent == database.path.parent
            and path.name.startswith(DIRECTORY_MARKER + ".")
            and path.name.endswith(".tmp")
        ):
            path.symlink_to(victim)
        return original_open(path, flags, mode)

    monkeypatch.setattr(os, "open", race_open)

    with pytest.raises(FileExistsError):
        write_directory_identity(database.path)

    assert victim.read_text(encoding="utf-8") == "unchanged"
    assert not (database.path.parent / DIRECTORY_MARKER).exists()


def test_directory_marker_publication_does_not_replace_a_raced_foreign_file(tmp_path, monkeypatch):
    from jxd_leads import db as db_module

    database = Database(tmp_path / "marker-publication-race" / "leads.db")
    database.path.parent.mkdir(parents=True)
    database.path.write_bytes(b"synthetic database identity holder")
    marker = database.path.parent / DIRECTORY_MARKER
    foreign = b'{"foreign": true}\n'
    original_link = os.link

    def race_link(source, destination):
        if Path(destination) == marker:
            Path(destination).write_bytes(foreign)
        return original_link(source, destination)

    monkeypatch.setattr(db_module.os, "link", race_link)
    with pytest.raises(BusinessError) as error:
        write_directory_identity(database.path)
    assert error.value.code == "DATA_DIRECTORY_MISMATCH"
    assert marker.read_bytes() == foreign


def test_directory_identity_rejects_marker_replaced_by_symlink_before_read(tmp_path, monkeypatch):
    database = Database(tmp_path / "marker-read-race" / "leads.db")
    database.migrate()
    marker = database.path.parent / DIRECTORY_MARKER
    victim = tmp_path / "victim-marker.json"
    victim.write_text('{"victim": true}\n', encoding="utf-8")
    original_is_file = Path.is_file
    swapped = False

    def race_is_file(path):
        nonlocal swapped
        result = original_is_file(path)
        if path == marker and result and not swapped:
            swapped = True
            marker.unlink()
            marker.symlink_to(victim)
        return result

    monkeypatch.setattr(Path, "is_file", race_is_file)
    with pytest.raises(BusinessError) as error:
        verify_directory_identity(database.path)
    assert error.value.code == "DATA_DIRECTORY_MISMATCH"
    assert victim.read_text(encoding="utf-8") == '{"victim": true}\n'


def test_initialization_marker_rejects_raced_symlink(tmp_path, monkeypatch):
    database = Database(tmp_path / "initialization-race" / "leads.db")
    victim = tmp_path / "synthetic-victim.txt"
    victim.write_text("unchanged", encoding="utf-8")
    original_open = os.open

    def race_open(path, flags, mode=0o777):
        path = Path(path)
        if path.name == ".leads.db.initializing" and flags & os.O_CREAT:
            path.symlink_to(victim)
        return original_open(path, flags, mode)

    monkeypatch.setattr(os, "open", race_open)

    with pytest.raises(FileExistsError):
        database.migrate()

    assert victim.read_text(encoding="utf-8") == "unchanged"


def test_migration_holds_directory_lock_while_binding_identity(tmp_path, monkeypatch):
    from jxd_leads import db as db_module

    database = Database(tmp_path / "migration-lock" / "leads.db")
    original = db_module.write_directory_identity
    observed = []

    def probe_lock(path):
        def acquire_from_other_thread():
            lock = FileLock(path.parent / ".migration.lock", timeout=0)
            try:
                lock.acquire()
            except Timeout:
                return False
            lock.release()
            return True

        with ThreadPoolExecutor(max_workers=1) as pool:
            observed.append(pool.submit(acquire_from_other_thread).result())
        return original(path)

    monkeypatch.setattr(db_module, "write_directory_identity", probe_lock)
    database.migrate()

    assert observed == [False]


def test_independent_approval_rejects_another_valid_initialized_directory(tmp_path):
    approved = Database(tmp_path / "approved" / "leads.db")
    approved.migrate()
    other = Database(tmp_path / "other" / "leads.db")
    other.migrate()
    other.assert_initialized()

    with pytest.raises(BusinessError) as error:
        resolve_runtime_data_dir(other.path.parent, approved.path.parent)
    assert error.value.code == "DATA_DIRECTORY_MISMATCH"
    with pytest.raises(BusinessError) as error:
        Database(other.path, approved_directory=approved.path.parent).assert_initialized()
    assert error.value.code == "DATA_DIRECTORY_MISMATCH"
    approved.assert_initialized()
    other.assert_initialized()


def test_mcp_entrypoint_requires_explicit_directory(monkeypatch):
    from jxd_leads import mcp_server

    monkeypatch.delenv("JXD_DATA_DIR", raising=False)
    with pytest.raises(BusinessError) as error:
        mcp_server.main()
    assert error.value.code == "DATA_DIR_REQUIRED"


def test_cli_mcp_forwards_only_explicit_absolute_directory(tmp_path, monkeypatch):
    from jxd_leads import cli, mcp_server

    selected = tmp_path / "cli mcp data"
    seen = {}
    monkeypatch.setenv("JXD_DATA_DIR", "synthetic-before")
    monkeypatch.setattr(
        sys,
        "argv",
        ["jxd-leads", "mcp", "--data-dir", str(selected), "--approved-data-dir", str(selected)],
    )
    monkeypatch.setattr(
        mcp_server,
        "main",
        lambda: seen.update(
            directory=os.environ.get("JXD_DATA_DIR"),
            approved=os.environ.get(APPROVED_DATA_DIR_ENV),
        ),
    )
    cli._main()
    assert seen["directory"] == str(selected.resolve())
    assert seen["approved"] == str(selected.resolve())


def test_mcp_entrypoint_requires_independent_approval(tmp_path, monkeypatch):
    from jxd_leads import mcp_server

    selected = tmp_path / "synthetic-data"
    monkeypatch.setenv("JXD_DATA_DIR", str(selected))
    monkeypatch.delenv(APPROVED_DATA_DIR_ENV, raising=False)
    with pytest.raises(BusinessError) as error:
        mcp_server.main()
    assert error.value.code == "DATA_DIR_REQUIRED"


def test_corrupt_same_day_backup_is_quarantined_after_verified_replacement(svc, tmp_path):
    folder = tmp_path / "backups"
    valid = backup_database(svc.db.path, folder)
    earlier = folder / "leads-2026-11-20.sqlite3"
    shutil.copy2(valid, earlier)
    valid.write_bytes(b"synthetic corrupt backup")

    replacement = backup_database(svc.db.path, folder, force=True)
    verify(replacement)
    verify(earlier)
    quarantined = list(folder.glob("leads-*.corrupt-*.sqlite3"))
    assert len(quarantined) == 1
    assert quarantined[0].read_bytes() == b"synthetic corrupt backup"


def test_same_day_symlink_to_active_database_is_not_an_independent_backup(svc, tmp_path):
    folder = tmp_path / "backups"
    folder.mkdir()
    target = folder / f"leads-{datetime.now().strftime('%Y-%m-%d')}.sqlite3"
    target.symlink_to(svc.db.path)

    replacement = backup_database(svc.db.path, folder, vault=svc.vault)

    assert not replacement.is_symlink()
    assert replacement.resolve() != svc.db.path.resolve()
    verify(replacement, svc.vault)
    svc.db.assert_initialized()
    quarantined = list(folder.glob("leads-*.corrupt-*.sqlite3"))
    assert len(quarantined) == 1 and quarantined[0].is_symlink()


def test_same_day_hardlink_to_older_backup_is_replaced_as_independent_copy(svc, tmp_path):
    folder = tmp_path / "backups"
    valid = backup_database(svc.db.path, folder)
    earlier = folder / "leads-2026-11-20.sqlite3"
    os.link(valid, earlier)

    replacement = backup_database(svc.db.path, folder, vault=svc.vault)

    assert replacement.lstat().st_nlink == 1
    assert not replacement.samefile(earlier)
    verify(replacement, svc.vault)
    earlier.write_bytes(b"synthetic mutation through the older hardlink")
    verify(replacement, svc.vault)


def test_same_day_backup_with_live_wal_is_not_accepted_as_self_contained(svc, tmp_path):
    source = backup_database(svc.db.path, tmp_path / "source")
    folder = tmp_path / "backups"
    folder.mkdir()
    target = folder / f"leads-{datetime.now().strftime('%Y-%m-%d')}.sqlite3"
    shutil.copy2(source, target)
    staged = tmp_path / "live-wal" / "leads.sqlite3"
    staged.parent.mkdir()

    with sqlite3.connect(target) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA wal_autocheckpoint=0")
        connection.execute("INSERT OR REPLACE INTO settings(key,value) VALUES ('live-wal','pending')")
        connection.commit()
        wal = Path(str(target) + "-wal")
        assert wal.exists()
        shutil.copy2(target, staged)
        shutil.copy2(wal, Path(str(staged) + "-wal"))

    shutil.copy2(staged, target)
    shutil.copy2(Path(str(staged) + "-wal"), Path(str(target) + "-wal"))
    verify(target, svc.vault)

    replacement = backup_database(svc.db.path, folder, vault=svc.vault)

    verify(replacement, svc.vault)
    assert not Path(str(replacement) + "-wal").exists()
    quarantined = list(folder.glob("leads-*.corrupt-*.sqlite3"))
    assert len(quarantined) == 1
    assert Path(str(quarantined[0]) + "-wal").exists()


def test_corrupt_same_day_backup_moves_wal_and_shm_with_main_file(svc, tmp_path):
    folder = tmp_path / "backups"
    valid = backup_database(svc.db.path, folder)
    corrupt = b"synthetic corrupt backup with sidecars"
    valid.write_bytes(corrupt)
    for suffix, content in (("-wal", b"synthetic wal"), ("-shm", b"synthetic shm")):
        Path(str(valid) + suffix).write_bytes(content)

    replacement = backup_database(svc.db.path, folder, vault=svc.vault)

    verify(replacement, svc.vault)
    assert not valid.with_name(valid.name + "-wal").exists()
    assert not valid.with_name(valid.name + "-shm").exists()
    quarantined = list(folder.glob("leads-*.corrupt-*.sqlite3"))
    assert len(quarantined) == 1 and quarantined[0].read_bytes() == corrupt
    assert Path(str(quarantined[0]) + "-wal").read_bytes() == b"synthetic wal"
    assert Path(str(quarantined[0]) + "-shm").read_bytes() == b"synthetic shm"


def test_backup_verification_rejects_empty_old_schema_and_wrong_key(svc, tmp_path):
    valid = backup_database(svc.db.path, tmp_path / "valid", vault=svc.vault)
    empty = tmp_path / "empty.sqlite3"
    sqlite3.connect(empty).close()
    with pytest.raises(ValueError, match="必需表"):
        verify(empty, svc.vault)

    old = tmp_path / "old.sqlite3"
    shutil.copy2(valid, old)
    with sqlite3.connect(old) as connection:
        connection.execute("UPDATE alembic_version SET version_num='20261030_project_aliases'")
    with pytest.raises(ValueError, match="迁移版本"):
        verify(old, svc.vault)

    with pytest.raises(BusinessError, match="密钥"):
        verify(valid, Vault.ephemeral())


def test_verify_wal_database_creates_no_sidecars(svc, tmp_path):
    source = backup_database(svc.db.path, tmp_path / "source", vault=svc.vault)
    folder = tmp_path / "wal-backup"
    folder.mkdir()
    target = folder / "leads.sqlite3"
    shutil.copy2(source, target)
    connection = sqlite3.connect(target)
    try:
        assert connection.execute("PRAGMA journal_mode=WAL").fetchone() == ("wal",)
    finally:
        connection.close()
    assert {path.name for path in folder.iterdir()} == {target.name}

    verify(target, svc.vault)

    assert {path.name for path in folder.iterdir()} == {target.name}


def test_default_backup_repairs_corrupt_same_day_file_and_is_idempotent(svc, tmp_path):
    folder = tmp_path / "backups"
    valid = backup_database(svc.db.path, folder)
    earlier = folder / "leads-2026-11-20.sqlite3"
    shutil.copy2(valid, earlier)
    corrupt = b"synthetic corrupt backup"
    valid.write_bytes(corrupt)

    replacement = run_backup(svc.db, folder)
    verify(replacement)
    verify(earlier)
    quarantined = list(folder.glob("leads-*.corrupt-*.sqlite3"))
    assert len(quarantined) == 1 and quarantined[0].read_bytes() == corrupt

    again = run_backup(svc.db, folder)
    assert again == replacement
    assert len(list(folder.glob("leads-*.corrupt-*.sqlite3"))) == 1


def test_same_day_backup_rejects_hardlink_added_after_verification(svc, tmp_path, monkeypatch):
    import jxd_leads.backup as backup_module

    folder = tmp_path / "backups"
    valid = backup_database(svc.db.path, folder)
    extra = folder / "unexpected-extra-link.sqlite3"
    original_verify = backup_module.verify

    def verify_then_add_link(path, vault=None, **kwargs):
        result = original_verify(path, vault)
        if Path(path) == valid and not extra.exists():
            os.link(valid, extra)
        return result

    monkeypatch.setattr(backup_module, "verify", verify_then_add_link)
    assert backup_module._valid_existing_backup(valid, svc.db.path, None) is False


def test_failed_replacement_keeps_older_valid_backup_and_recovers_target(svc, tmp_path, monkeypatch):
    folder = tmp_path / "backups"
    valid = backup_database(svc.db.path, folder)
    earlier = folder / "leads-2026-11-20.sqlite3"
    shutil.copy2(valid, earlier)
    corrupt = b"synthetic corrupt same-day backup"
    valid.write_bytes(corrupt)
    same_day = valid
    sidecars = {suffix: f"synthetic {suffix}".encode() for suffix in ("-wal", "-shm")}
    for suffix, content in sidecars.items():
        Path(str(same_day) + suffix).write_bytes(content)
    original_replace = Path.replace

    def fail_temporary_replace(source, destination):
        if source.suffix == ".tmp" and Path(destination) == same_day:
            raise OSError("synthetic replacement failure")
        return original_replace(source, destination)

    monkeypatch.setattr(Path, "replace", fail_temporary_replace)
    with pytest.raises(OSError, match="synthetic replacement failure"):
        backup_database(svc.db.path, folder, force=True)

    assert same_day.read_bytes() == corrupt
    for suffix, content in sidecars.items():
        assert Path(str(same_day) + suffix).read_bytes() == content
    verify(earlier)
    assert not list(folder.glob("leads-*.corrupt-*.sqlite3"))
    assert not list(folder.glob("*.tmp*"))


def test_restore_rejects_same_directory_and_bound_directory(svc, tmp_path):
    marker = svc.db.path.parent / DIRECTORY_MARKER
    before = marker.read_bytes()
    backup = backup_database(svc.db.path, tmp_path / "backup-source")

    with pytest.raises(BusinessError) as error:
        restore_database(backup, svc.db.path.with_name("recovered.db"), svc.vault)
    assert error.value.code == "RESTORE_TARGET_NOT_ISOLATED"
    assert marker.read_bytes() == before
    Database(svc.db.path).assert_initialized()

    bound = Database(tmp_path / "already-bound" / "leads.db")
    bound.migrate()
    bound_marker = bound.path.parent / DIRECTORY_MARKER
    bound_before = bound_marker.read_bytes()
    with pytest.raises(BusinessError) as error:
        restore_database(backup, bound.path.with_name("new-name.db"), svc.vault)
    assert error.value.code == "RESTORE_TARGET_NOT_ISOLATED"
    assert bound_marker.read_bytes() == bound_before
    bound.assert_initialized()


def test_restore_wrong_key_leaves_no_target_or_marker(svc, tmp_path):
    backup = backup_database(svc.db.path, tmp_path / "backup-source", vault=svc.vault)
    target = tmp_path / "wrong-key-recovery" / "leads.db"

    with pytest.raises(BusinessError, match="密钥"):
        restore_database(backup, target, Vault.ephemeral())
    assert not target.parent.exists()
    assert not target.exists()


def test_restore_failure_removes_new_target_and_binding(svc, tmp_path, monkeypatch):
    import jxd_leads.backup as backup_module

    backup = backup_database(svc.db.path, tmp_path / "backup-source", vault=svc.vault)
    target = tmp_path / "failed-recovery" / "leads.db"
    marker = target.parent / DIRECTORY_MARKER
    write_identity = backup_module.write_directory_identity

    def fail_after_binding(path, expected_identity=None):
        write_identity(path, expected_identity=expected_identity)
        raise OSError("synthetic post-bind failure")

    monkeypatch.setattr(backup_module, "write_directory_identity", fail_after_binding)
    with pytest.raises(OSError, match="synthetic post-bind failure"):
        restore_database(backup, target, svc.vault)
    assert target.parent.is_dir()
    assert not target.exists()
    assert not marker.exists() and not marker.is_symlink()
    assert not Path(str(target) + "-wal").exists()
    assert not Path(str(target) + "-shm").exists()


def test_restore_never_follows_symlink_created_before_final_link(svc, tmp_path, monkeypatch):
    backup = backup_database(svc.db.path, tmp_path / "backup-source", vault=svc.vault)
    victim = Database(tmp_path / "victim" / "leads.db")
    victim.migrate()
    victim_before = victim.path.read_bytes()
    target = tmp_path / "recovery-race" / "leads.db"
    target.parent.mkdir()
    original_link = os.link

    def race_link(source, destination):
        Path(destination).symlink_to(victim.path)
        return original_link(source, destination)

    monkeypatch.setattr(os, "link", race_link)
    with pytest.raises(FileExistsError):
        restore_database(backup, target, svc.vault)

    assert target.is_symlink()
    assert victim.path.read_bytes() == victim_before
    victim.assert_initialized()


def test_restore_rejects_target_replaced_after_publish_without_deleting_it(svc, tmp_path, monkeypatch):
    import jxd_leads.backup as backup_module

    backup = backup_database(svc.db.path, tmp_path / "backup-source", vault=svc.vault)
    target = tmp_path / "post-link-symlink" / "leads.db"
    victim = Database(tmp_path / "post-link-victim" / "leads.db")
    victim.migrate()
    victim_before = victim.path.read_bytes()
    original_link = os.link

    def race_link(source, destination):
        result = original_link(source, destination)
        if Path(destination) == target:
            Path(destination).unlink()
            Path(destination).symlink_to(victim.path)
        return result

    monkeypatch.setattr(backup_module.os, "link", race_link)
    with pytest.raises(OSError, match="发布后"):
        restore_database(backup, target, svc.vault)

    assert target.is_symlink()
    assert victim.path.read_bytes() == victim_before
    victim.assert_initialized()
    assert not (target.parent / DIRECTORY_MARKER).exists()
    assert list(target.parent.glob(".restore-*/leads.db"))


def test_restore_rejects_target_replaced_after_publish_without_deleting_foreign_file(
    svc, tmp_path, monkeypatch
):
    import jxd_leads.backup as backup_module

    backup = backup_database(svc.db.path, tmp_path / "backup-source", vault=svc.vault)
    target = tmp_path / "post-link-file" / "leads.db"
    foreign = b"foreign ordinary file"
    original_link = os.link

    def race_link(source, destination):
        result = original_link(source, destination)
        if Path(destination) == target:
            Path(destination).unlink()
            Path(destination).write_bytes(foreign)
        return result

    monkeypatch.setattr(backup_module.os, "link", race_link)
    with pytest.raises(OSError, match="发布后"):
        restore_database(backup, target, svc.vault)

    assert target.read_bytes() == foreign
    assert not (target.parent / DIRECTORY_MARKER).exists()
    assert list(target.parent.glob(".restore-*/leads.db"))


def test_restore_rechecks_target_after_writing_directory_binding(svc, tmp_path, monkeypatch):
    import jxd_leads.backup as backup_module

    backup = backup_database(svc.db.path, tmp_path / "backup-source", vault=svc.vault)
    target = tmp_path / "post-bind-symlink" / "leads.db"
    victim = Database(tmp_path / "post-bind-victim" / "leads.db")
    victim.migrate()
    victim_before = victim.path.read_bytes()
    original_write = backup_module.write_directory_identity

    def write_then_replace(path, expected_identity=None):
        marker = original_write(path, expected_identity=expected_identity)
        Path(path).unlink()
        Path(path).symlink_to(victim.path)
        return marker

    monkeypatch.setattr(backup_module, "write_directory_identity", write_then_replace)
    with pytest.raises(OSError, match="目录绑定后"):
        restore_database(backup, target, svc.vault)

    assert target.is_symlink()
    assert victim.path.read_bytes() == victim_before
    victim.assert_initialized()
    assert not (target.parent / DIRECTORY_MARKER).exists()
    assert list(target.parent.glob(".restore-*/leads.db"))


def test_web_backup_refresh_uses_default_background_path(svc, tmp_path):
    folder = tmp_path / "web-backups"
    valid = backup_database(svc.db.path, folder)
    earlier = folder / "leads-2026-11-20.sqlite3"
    shutil.copy2(valid, earlier)
    valid.write_bytes(b"synthetic corrupt web backup")
    app = create_app(svc, folder, testing=True)

    asyncio.run(app.state.refresh_backup())
    assert app.state.backup_error is None
    verify(valid)
    verify(earlier)
    assert len(list(folder.glob("leads-*.corrupt-*.sqlite3"))) == 1


def test_reminder_failure_is_visible_and_next_cycle_recovers(svc, tmp_path, monkeypatch):
    app = create_app(svc, tmp_path / "reminder-backups", testing=True)

    def fail():
        raise OperationalError("SELECT synthetic", {}, Exception("synthetic reminder failure"))

    original = svc.check_reminders
    monkeypatch.setattr(svc, "check_reminders", fail)
    asyncio.run(app.state.refresh_reminders())
    assert "下一轮自动重试" in app.state.reminder_error
    with TestClient(app) as client:
        failed_page = client.get("/").text
        failed_notifications = client.get("/notifications").text
    assert "提醒检查失败" in failed_page and "下一轮自动重试" in failed_page
    assert "提醒检查失败" in failed_notifications and "下一轮自动重试" in failed_notifications

    monkeypatch.setattr(svc, "check_reminders", original)
    asyncio.run(app.state.refresh_reminders())
    assert app.state.reminder_error is None
    with TestClient(app) as client:
        recovered_page = client.get("/").text
        recovered_notifications = client.get("/notifications").text
    assert "提醒检查失败" not in recovered_page
    assert "提醒检查失败" not in recovered_notifications
