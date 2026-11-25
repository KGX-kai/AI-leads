import argparse
import os
from pathlib import Path

from .backup import restore_database, run_backup, verify
from .db import APPROVED_DATA_DIR_ENV, Database, resolve_runtime_data_dir
from .security import Vault
from .service import Service


def _existing_database(db):
    """存量库（已建表）才做迁移前密钥预检与强制备份；新库或空库直接迁移。"""
    import sqlite3

    if not db.path.is_file():
        return False
    try:
        with sqlite3.connect(f"file:{db.path}?mode=ro", uri=True) as connection:
            return bool(
                connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' LIMIT 1"
                ).fetchone()
            )
    except sqlite3.Error:
        return False


def _main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description="京小电获客平台")
    parser.add_argument("command", choices=["serve", "migrate", "backup", "restore", "mcp"])
    parser.add_argument("--data-dir")
    parser.add_argument("--approved-data-dir")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--target", type=Path)
    args = parser.parse_args()
    if args.command == "restore":
        if not args.source or not args.target:
            parser.error("restore 需要 --source 和 --target")
        restore_database(args.source, args.target, Vault.macos_existing())
        print("恢复成功：完整性与关系检查通过。密钥仍由本机钥匙串管理。")
        return
    data_dir = resolve_runtime_data_dir(args.data_dir, args.approved_data_dir)
    if args.command == "mcp":
        os.environ["JXD_DATA_DIR"] = str(data_dir)
        os.environ[APPROVED_DATA_DIR_ENV] = str(data_dir)
        from .mcp_server import main as run

        run()
        return
    db = Database(data_dir / "leads.db", approved_directory=data_dir)
    if args.command == "migrate":
        vault = None
        if _existing_database(db):
            vault = Vault.macos(db=db, before_migration=True)
            run_backup(db, force=True, vault=vault, before_migration=True)
        db.migrate()
        verify(db.path, vault)
        print("数据库迁移完成，迁移后校验通过")
        return
    db.assert_initialized()
    vault = Vault.macos(db=db, before_migration=True) if args.command in {"serve", "backup"} else None
    if args.command == "backup":
        run_backup(db, force=True, vault=vault)
        print("备份完成并通过完整性检查")
        return
    import uvicorn

    from .web import create_app

    app = create_app(Service(db, vault))
    print(f"京小电获客平台：http://127.0.0.1:{args.port}（仅本机）", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False)


def main():
    import sys

    from .errors import BusinessError

    try:
        _main()
    except BusinessError as error:
        print(f"{error.code}: {error}", file=sys.stderr)
        raise SystemExit(1) from None
