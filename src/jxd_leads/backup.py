import json
import os
import sqlite3
import stat
import traceback
from contextlib import closing
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from alembic.config import Config
from alembic.script import ScriptDirectory
from filelock import FileLock

from .db import (
    DIRECTORY_MARKER,
    Database,
    _read_private_text,
    migration_resource_root,
    write_directory_identity,
)
from .errors import BusinessError
from .models import BackupRun

REQUIRED_TABLES = {
    "alembic_version",
    "candidates",
    "inquiries",
    "key_metadata",
    "projects",
    "settings",
    "suppression_events",
}


def expected_head():
    resources = migration_resource_root()
    config = Config(str(resources / "alembic.ini"))
    config.set_main_option("script_location", str(resources / "migrations"))
    return ScriptDirectory.from_config(config).get_current_head()


def _sidecars(path):
    return [Path(str(path) + suffix) for suffix in ("-wal", "-shm")]


def _entry_exists(path):
    return path.exists() or path.is_symlink()


def _same_file(left, right):
    try:
        return Path(left).samefile(right)
    except OSError:
        return False


def _private_identity(path):
    info = Path(path).lstat()
    if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise OSError("路径不是普通文件")
    return info.st_dev, info.st_ino


def _matches_private_identity(path, identity):
    try:
        return _private_identity(path) == tuple(identity)
    except OSError:
        return False


def _valid_existing_backup(path, source, vault, before_migration=False):
    path = Path(path)
    try:
        before = path.lstat()
        single_link = stat.S_ISREG(before.st_mode) and before.st_nlink == 1
    except OSError:
        single_link = False
    if path.is_symlink() or not path.is_file() or not single_link or _same_file(path, source):
        return False
    if any(_entry_exists(sidecar) for sidecar in _sidecars(path)):
        return False
    try:
        verify(path, vault, before_migration=before_migration)
    except (sqlite3.Error, ValueError):
        return False
    try:
        after = path.lstat()
    except OSError:
        return False
    return (
        stat.S_ISREG(after.st_mode)
        and not stat.S_ISLNK(after.st_mode)
        and after.st_nlink == 1
        and (after.st_dev, after.st_ino) == (before.st_dev, before.st_ino)
        and not any(_entry_exists(sidecar) for sidecar in _sidecars(path))
    )


def _restore_entries(moved):
    for original, saved in reversed(moved):
        if _entry_exists(saved) and not _entry_exists(original):
            saved.replace(original)


def _quarantine_entries(target):
    quarantined = target.with_name(f"{target.stem}.corrupt-{uuid4().hex}.sqlite3")
    moved = []
    try:
        for original, saved in [
            (target, quarantined),
            *[
                (sidecar, Path(str(quarantined) + sidecar.name[len(target.name):]))
                for sidecar in _sidecars(target)
            ],
        ]:
            if _entry_exists(original):
                original.replace(saved)
                moved.append((original, saved))
    except BaseException:
        _restore_entries(moved)
        raise
    return quarantined, moved


def _finalize_copy(connection, path):
    """Make a copied database self-contained before verification or rename."""
    connection.commit()
    mode = connection.execute("PRAGMA journal_mode=DELETE").fetchone()
    if not mode or str(mode[0]).casefold() != "delete":
        raise sqlite3.OperationalError("无法退出 WAL 模式，备份未完成")
    connection.close()
    for sidecar in _sidecars(path):
        sidecar.unlink(missing_ok=True)


def _create_private_database(path):
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    os.close(descriptor)


def _remove_own_directory_marker(target, expected_identity, database_path):
    marker = target.parent / DIRECTORY_MARKER
    if not _entry_exists(marker):
        return False
    try:
        before = marker.lstat()
        content = json.loads(_read_private_text(marker))
    except (OSError, ValueError, TypeError):
        return False
    if not stat.S_ISREG(before.st_mode) or stat.S_ISLNK(before.st_mode):
        return False
    expected = {
        "application": "JXD-LEADS-001",
        "database": database_path,
        "device": expected_identity[0],
        "inode": expected_identity[1],
    }
    if content != expected:
        return False
    try:
        after = marker.lstat()
    except OSError:
        return False
    if (after.st_dev, after.st_ino) != (before.st_dev, before.st_ino):
        return False
    marker.unlink(missing_ok=True)
    return True


def verify(path, vault=None, *, before_migration=False):
    """Verify a backup copy.

    ``before_migration`` is only for the forced backup taken by ``migrate``:
    it still checks integrity, relations, required tables and key decryption,
    but accepts the database's current (older) migration head.  Every other
    caller keeps the strict head check.

    Self-contained copies use ``immutable=1`` so verification does not create
    WAL sidecars.  A live WAL database with sidecars still uses a normal
    read-only connection so its latest committed content remains visible.
    """
    resolved = Path(path).resolve()
    immutable = not any(_entry_exists(sidecar) for sidecar in _sidecars(resolved))
    uri = f"file:{resolved}?mode=ro" + ("&immutable=1" if immutable else "")
    with closing(sqlite3.connect(uri, uri=True)) as c:
        if (
            c.execute("PRAGMA integrity_check").fetchone()[0] != "ok"
            or c.execute("PRAGMA foreign_key_check").fetchall()
        ):
            raise ValueError("数据库完整性或关系检查失败")
        tables = {row[0] for row in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not REQUIRED_TABLES.issubset(tables):
            raise ValueError("数据库缺少工作台必需表")
        if not before_migration:
            version = c.execute("SELECT version_num FROM alembic_version").fetchone()
            if not version or version[0] != expected_head():
                raise ValueError("数据库迁移版本与候选不一致")
    if vault is not None:
        vault.preflight(Database(resolved), immutable=immutable)


def backup_database(source, folder, force=False, vault=None, before_migration=False):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    with FileLock(folder / ".backup.lock", timeout=15):
        return _backup_database(source, folder, force, vault, before_migration)


def _backup_database(source, folder, force=False, vault=None, before_migration=False):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    stamp = datetime.now().strftime("%Y-%m-%d")
    target = folder / f"leads-{stamp}.sqlite3"
    if _entry_exists(target) and not force and _valid_existing_backup(
        target, source, vault, before_migration
    ):
        return target
    temporary = folder / f".{stamp}-{uuid4().hex}.tmp"
    try:
        with (
            closing(sqlite3.connect(f"file:{Path(source).resolve()}?mode=ro", uri=True)) as src,
            closing(sqlite3.connect(temporary)) as dst,
        ):
            src.backup(dst)
            _finalize_copy(dst, temporary)
        try:
            verify(temporary, vault, before_migration=before_migration)
        except BusinessError as error:
            raise ValueError("备份副本密钥预检失败") from error
        temporary.chmod(0o600)
        moved = []
        if any(_entry_exists(path) for path in [target, *_sidecars(target)]) and not _valid_existing_backup(
            target, source, vault, before_migration
        ):
            _, moved = _quarantine_entries(target)
        try:
            temporary.replace(target)
        except BaseException:
            _restore_entries(moved)
            raise
        for sidecar in _sidecars(temporary):
            sidecar.unlink(missing_ok=True)
        # Only files generated by this application, after a successful verified backup.
        old = sorted(folder.glob("leads-????-??-??.sqlite3"), reverse=True)
        for item in old[7:]:
            item.unlink()
        return target
    finally:
        if temporary.exists():
            temporary.unlink()
        for sidecar in _sidecars(temporary):
            sidecar.unlink(missing_ok=True)


def restore_database(source, target, vault):
    target = Path(target)
    if target.exists() or target.is_symlink():
        raise ValueError("恢复目标已存在；必须选择新的隔离文件，禁止覆盖当前库")
    verify(source, vault)
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with FileLock(target.parent / ".migration.lock", timeout=30):
        marker = target.parent / DIRECTORY_MARKER
        if marker.exists() or marker.is_symlink():
            raise BusinessError(
                "恢复目标目录已绑定其他数据库；请选择新的未绑定隔离目录",
                "RESTORE_TARGET_NOT_ISOLATED",
            )
        if target.exists() or target.is_symlink():
            raise ValueError("恢复目标已存在；必须选择新的隔离文件，禁止覆盖当前库")
        staging_dir = target.parent / f".restore-{uuid4().hex}"
        staging_dir.mkdir(mode=0o700)
        staged = staging_dir / "leads.db"
        target_database = str(target.resolve())
        published = False
        committed = False
        staged_identity = None
        try:
            _create_private_database(staged)
            with (
                closing(sqlite3.connect(f"file:{Path(source).resolve()}?mode=ro", uri=True)) as src,
                closing(sqlite3.connect(staged)) as dst,
            ):
                src.backup(dst)
                _finalize_copy(dst, staged)
            staged.chmod(0o600)
            verify(staged, vault)
            staged_identity = _private_identity(staged)
            # Linking publishes without following a pre-existing symlink and
            # without overwriting a file created by another process.
            os.link(staged, target)
            published = True
            if not _matches_private_identity(target, staged_identity):
                raise OSError("恢复目标在发布后发生变化")
            write_directory_identity(target, expected_identity=staged_identity)
            if not _matches_private_identity(target, staged_identity):
                raise OSError("恢复目标在目录绑定后发生变化")
            committed = True
        except BaseException:
            if published:
                # Remove only a marker whose stored device/inode is this
                # restore's staged copy; a foreign target and marker stay put.
                _remove_own_directory_marker(target, staged_identity, target_database)
                if _matches_private_identity(target, staged_identity):
                    target.unlink(missing_ok=True)
            raise
        finally:
            # A failed post-publish restore keeps its verified private copy in
            # the isolated staging directory for owner inspection. Successful
            # and pre-publish paths remove only entries created here.
            if committed or not published:
                for sidecar in _sidecars(staged):
                    sidecar.unlink(missing_ok=True)
                staged.unlink(missing_ok=True)
                try:
                    staging_dir.rmdir()
                except OSError:
                    pass
    return target


def run_backup(db, folder=None, force=False, vault=None, before_migration=False):
    try:
        target = backup_database(
            db.path, folder or db.backup_dir, force, vault, before_migration
        )
    except (OSError, sqlite3.Error, ValueError, TimeoutError):
        message = "备份失败：请检查磁盘空间和目录权限后重试；上次成功备份保留。"
        try:
            with db.session() as s:
                s.add(BackupRun(status="failed", message=message))
        except Exception:  # noqa: BLE001
            traceback.print_exc()
        raise BusinessError(message, "BACKUP_FAILED", True) from None
    with db.session() as s:
        s.add(BackupRun(status="success", message="完整性与关系检查通过", filename=target.name))
    return target
