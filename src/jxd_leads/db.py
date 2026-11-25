import json
import os
import sqlite3
import sys
import sysconfig
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from filelock import FileLock
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import Session

from .errors import BusinessError

ROOT = Path(__file__).resolve().parents[2]
DIRECTORY_MARKER = ".jxd-leads-directory.json"
APPROVED_DATA_DIR_ENV = "JXD_APPROVED_DATA_DIR"
# Identifies only the historical migration seed; never used as business defaults.
LEGACY_TAG_SEED = {"物业", "地下停车场", "补货", "批量换灯", "型号待核实", "采购权待核实", "试样中"}
# Owner-editable settings seeded by 20261124_marketing_fields. A fresh-initialization check may
# ignore these exact rows; any changed value means the owner already used the database.
MIGRATION_SETTING_SEED = {
    "source_channels": ["招投标", "物业协会", "抖音同城", "CABEP", "展会", "名单池", "竞品客户", "转介绍"],
    "stall_days": {"EMC": 30, "买断": 7, "未定": 14},
}


def migration_resource_root():
    """Locate Alembic resources in a source checkout or an installed wheel."""
    data_root = sysconfig.get_path("data")
    candidates = [ROOT]
    if data_root:
        candidates.append(Path(data_root) / "share" / "jxd-leads")
    candidates.append(Path(sys.prefix) / "share" / "jxd-leads")
    for candidate in dict.fromkeys(candidates):
        if (candidate / "alembic.ini").is_file() and (candidate / "migrations").is_dir():
            return candidate
    raise RuntimeError("安装包缺少数据库迁移资源")


def resolve_data_dir(configured):
    """Require one explicit absolute directory for every database entrypoint."""
    if configured is None or not str(configured).strip():
        raise BusinessError("必须显式指定数据目录，未配置时不会打开或创建数据库", "DATA_DIR_REQUIRED")
    path = Path(str(configured).strip()).expanduser()
    if not path.is_absolute():
        raise BusinessError("数据目录必须使用绝对路径", "DATA_DIR_NOT_ABSOLUTE")
    if path.exists() and not path.is_dir():
        raise BusinessError("数据目录路径已存在但不是目录", "DATA_DIR_INVALID")
    return path.resolve()


def resolve_runtime_data_dir(configured, approved):
    """Require an actual directory and an independently supplied approved directory."""
    actual = resolve_data_dir(configured)
    expected = resolve_data_dir(approved)
    if actual != expected:
        raise BusinessError(
            "当前数据目录与维护者批准的目录不一致，已停止打开",
            "DATA_DIRECTORY_MISMATCH",
        )
    return actual


def _directory_identity(path):
    path = Path(path).resolve()
    stat = path.stat()
    return {
        "application": "JXD-LEADS-001",
        "database": str(path),
        "device": stat.st_dev,
        "inode": stat.st_ino,
    }


def _read_private_text(path):
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(descriptor, "r", encoding="utf-8") as handle:
        return handle.read()


def _write_private_text(path, value):
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            descriptor = -1
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _same_private_file(path, other):
    try:
        left = Path(path).lstat()
        right = Path(other).lstat()
    except OSError:
        return False
    return (left.st_dev, left.st_ino) == (right.st_dev, right.st_ino)


def write_directory_identity(path, expected_identity=None):
    path = Path(path).resolve()
    marker = path.parent / DIRECTORY_MARKER
    if marker.exists() or marker.is_symlink():
        verify_directory_identity(path)
        return marker
    content = _directory_identity(path)
    if expected_identity is not None and (
        content["device"], content["inode"]
    ) != tuple(expected_identity):
        raise BusinessError(
            "数据库路径在目录绑定前发生变化，已停止打开",
            "DATA_DIRECTORY_MISMATCH",
        )
    temporary = marker.with_name(f"{marker.name}.{uuid4().hex}.tmp")
    created = False
    try:
        _write_private_text(
            temporary,
            json.dumps(content, ensure_ascii=False, sort_keys=True) + "\n",
        )
        try:
            # A hard link publishes without replacing a marker created by
            # another process after the existence check.
            os.link(temporary, marker)
            created = True
        except FileExistsError:
            verify_directory_identity(path)
            return marker
        current = _directory_identity(path)
        if (current["device"], current["inode"]) != (
            content["device"],
            content["inode"],
        ):
            if created and _same_private_file(marker, temporary):
                marker.unlink(missing_ok=True)
            raise BusinessError(
                "数据库路径在目录绑定过程中发生变化，已停止打开",
                "DATA_DIRECTORY_MISMATCH",
            )
    finally:
        temporary.unlink(missing_ok=True)
    return marker


def verify_directory_identity(path, approved_directory=None):
    path = Path(path).resolve()
    marker = path.parent / DIRECTORY_MARKER
    if marker.is_symlink() or not marker.is_file():
        raise BusinessError(
            "数据目录尚未通过显式 migrate 绑定，未打开数据库",
            "DATA_DIRECTORY_MISMATCH",
        )
    try:
        content = json.loads(_read_private_text(marker))
        current = _directory_identity(path)
    except (OSError, ValueError, TypeError):
        raise BusinessError(
            "数据目录绑定不可读取或已损坏，已停止打开；请核对批准路径",
            "DATA_DIRECTORY_MISMATCH",
        ) from None
    expected = {
        "application": "JXD-LEADS-001",
        "database": str(path),
        "device": current["device"],
        "inode": current["inode"],
    }
    if not isinstance(content, dict) or content != expected:
        raise BusinessError(
            "数据目录绑定与当前数据库不一致，已停止打开；请核对批准路径",
            "DATA_DIRECTORY_MISMATCH",
        )
    if approved_directory is not None and str(Path(approved_directory).expanduser().resolve()) != str(path.parent):
        raise BusinessError(
            "当前数据目录与维护者批准的目录不一致，已停止打开",
            "DATA_DIRECTORY_MISMATCH",
        )
    return marker


def has_business_data(connection):
    """True when any table holds rows beyond migration seeds (tags are checked separately)."""
    tables = inspect(connection).get_table_names()
    for table in set(tables) - {"tags", "alembic_version", "settings"}:
        quoted = connection.dialect.identifier_preparer.quote(table)
        if connection.exec_driver_sql(f"SELECT 1 FROM {quoted} LIMIT 1").first():
            return True
    if "settings" in tables:
        for key, value in connection.exec_driver_sql("SELECT key, value FROM settings").all():
            try:
                seeded = key in MIGRATION_SETTING_SEED and json.loads(value) == MIGRATION_SETTING_SEED[key]
            except (TypeError, ValueError):
                seeded = False
            if not seeded:
                return True
    return False


def _check_unfinished_initialization(connection):
    tables = inspect(connection).get_table_names()
    if has_business_data(connection):
        raise RuntimeError("初始化中断后已有新增数据，请人工核对，禁止自动清理")
    if "tags" not in tables:
        return []
    tags = connection.exec_driver_sql("SELECT id, name, created_at FROM tags").all()
    if tags and ({row.name for row in tags} != LEGACY_TAG_SEED or len({row.created_at for row in tags}) != 1):
        raise RuntimeError("初始化中断后已有新增数据或标签变化，请人工核对，禁止自动清理")
    return [row.id for row in tags]


class Database:
    def __init__(self, path: Path, approved_directory=None):
        path = Path(path)
        if not path.is_absolute():
            raise BusinessError("数据库路径必须使用绝对路径", "DATABASE_PATH_NOT_ABSOLUTE")
        self.path = path.resolve()
        self.approved_directory = (
            Path(approved_directory).expanduser().resolve() if approved_directory is not None else None
        )
        if self.approved_directory is not None and self.approved_directory != self.path.parent:
            raise BusinessError(
                "当前数据目录与维护者批准的目录不一致，已停止打开",
                "DATA_DIRECTORY_MISMATCH",
            )
        self._active = ContextVar("jxd_transaction", default=None)
        self.engine = create_engine(f"sqlite:///{self.path}", connect_args={"check_same_thread": False, "timeout": 15})

        @event.listens_for(self.engine, "connect")
        def configure(dbapi, _):
            dbapi.execute("PRAGMA foreign_keys=ON")
            dbapi.execute("PRAGMA journal_mode=WAL")
            dbapi.execute("PRAGMA busy_timeout=15000")

    def migrate(self):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        resources = migration_resource_root()
        config = Config(str(resources / "alembic.ini"))
        config.set_main_option("script_location", str(resources / "migrations"))
        config.set_main_option("sqlalchemy.url", f"sqlite:///{self.path}")
        with FileLock(self.path.parent / ".migration.lock", timeout=30):
            directory_marker = self.path.parent / DIRECTORY_MARKER
            if directory_marker.exists() or directory_marker.is_symlink():
                verify_directory_identity(self.path, self.approved_directory)
            fresh = not inspect(self.engine).get_table_names()
            marker = self.path.with_name("." + self.path.name + ".initializing")
            file = self.path.stat()
            identity = f"jxd-leads-fresh-v1:{file.st_dev}:{file.st_ino}:{self.path}\n"
            if marker.is_symlink() or (
                marker.exists() and _read_private_text(marker) != identity
            ):
                raise RuntimeError("新库初始化标记与数据库不匹配，请先核对，禁止自动清理")
            if fresh and not marker.exists():
                _write_private_text(marker, identity)
            if marker.exists():
                with self.engine.connect() as connection:
                    _check_unfinished_initialization(connection)
            command.upgrade(config, "head")
            if marker.exists():
                # Historical migrations seed test-scope examples. Only a schema-less
                # new database (or its interrupted initialization) may discard them.
                with self.session() as session:
                    ids = _check_unfinished_initialization(session.connection())
                    if ids:
                        session.execute(text("DELETE FROM tags WHERE id IN (" + ",".join(
                            f":id{i}" for i in range(len(ids))
                        ) + ")"), {f"id{i}": tag_id for i, tag_id in enumerate(ids)})
                marker.unlink()
            self.path.chmod(0o600)
            write_directory_identity(self.path)

    def assert_initialized(self):
        """Fail closed unless an explicit initialization step reached the candidate head."""
        if not self.path.is_file():
            raise BusinessError(
                "数据库尚未初始化，请先显式运行 migrate 并核对数据目录",
                "DATA_NOT_INITIALIZED",
            )
        verify_directory_identity(self.path, self.approved_directory)
        resources = migration_resource_root()
        config = Config(str(resources / "alembic.ini"))
        config.set_main_option("script_location", str(resources / "migrations"))
        expected = ScriptDirectory.from_config(config).get_current_head()
        try:
            with sqlite3.connect(f"file:{self.path}?mode=ro", uri=True) as connection:
                row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
        except sqlite3.Error:
            row = None
        if not row or row[0] != expected:
            raise BusinessError(
                "数据库未处于候选要求的迁移版本，请先备份并显式运行 migrate",
                "DATA_NOT_INITIALIZED",
            )

    @property
    def backup_dir(self):
        return self.path.parent / "backups"

    @contextmanager
    def session(self):
        active = self._active.get()
        if active is not None:
            yield active
            return
        with Session(self.engine, expire_on_commit=False) as s:
            # Serialize writes across web/MCP; avoids read-then-write duplicate races.
            s.connection().exec_driver_sql("BEGIN IMMEDIATE")
            token = self._active.set(s)
            try:
                yield s
                s.commit()
            except BaseException:
                s.rollback()
                raise

            finally:
                self._active.reset(token)

    @contextmanager
    def read_session(self):
        active = self._active.get()
        if active is not None:
            yield active
        else:
            with Session(self.engine, expire_on_commit=False) as s:
                yield s
