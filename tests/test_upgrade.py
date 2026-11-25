import asyncio
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from test_core import candidate

from jxd_leads.backup import restore_database, run_backup, verify
from jxd_leads.db import Database
from jxd_leads.models import Followup, Todo
from jxd_leads.schemas import ContactInput, FollowupInput
from jxd_leads.security import Vault
from jxd_leads.service import BusinessError, Service
from jxd_leads.web import create_app


def project(svc):
    item = svc.submit_candidates(None, [candidate()])["items"][0]
    return svc.review_candidate(item["id"], "accept")["project_id"]


def test_wrong_vault_rejected_at_startup(svc):
    with pytest.raises(BusinessError, match="密钥"):
        Service(svc.db, Vault.ephemeral())


def test_existing_database_detects_initialized_schema(tmp_path):
    from jxd_leads.cli import _existing_database

    database = Database(tmp_path / "leads.db")
    assert _existing_database(database) is False
    database.migrate()
    assert _existing_database(database) is True


def _legacy_11_database(tmp_path):
    """Synthetic schema-1.1 database with candidate, alias, review and suppression rows."""
    from alembic import command
    from alembic.config import Config

    from jxd_leads.db import ROOT

    data_dir = tmp_path / "legacy"
    database = Database(data_dir / "leads.db")
    database.path.parent.mkdir(parents=True, exist_ok=True)
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database.path}")
    command.upgrade(config, "20261030_project_aliases")
    vault = Vault.ephemeral()
    with sqlite3.connect(database.path) as connection:
        connection.execute(
            "INSERT INTO key_metadata (id, version, key_ref, sentinel) VALUES (1, 1, 'synthetic', ?)",
            (vault.encrypt({"application": "JXD-LEADS-001", "version": 1}),),
        )
        connection.execute(
            "INSERT INTO companies (name, region, identity_key, id, created_at) VALUES "
            "('合成公司', '合成地区', 'company-key', 'company-1', '2026-11-01')"
        )
        connection.execute(
            "INSERT INTO projects (company_id, name, region, address, identity_key, stage, "
            "requirements, version, id, created_at) VALUES "
            "('company-1', '合成项目', '合成地区', '合成地址', 'project-key', '待核实', '{}', 1, "
            "'project-1', '2026-11-01')"
        )
        connection.execute(
            "INSERT INTO candidates (research_id, company, project, region, address, source_url, "
            "source_type, evidence, discovered_at, reason, demand_evidence, identity_key, "
            "submission_key, status, review_reason, project_id, id, created_at) VALUES "
            "(NULL, '合成公司', '合成项目', '合成地区', '合成地址', 'https://example.invalid/1', "
            "'公开网络', '合成证据', '2026-11-01', '', '', 'candidate-key', 'submission-key', "
            "'pending', '', 'project-1', 'candidate-1', '2026-11-01')"
        )
        connection.execute(
            "INSERT INTO project_aliases (id, created_at, identity_key, project_id) VALUES "
            "('alias-1', '2026-11-01', 'alias-key', 'project-1')"
        )
        connection.execute(
            "INSERT INTO review_suggestions (kind, candidate_id, encrypted, status, request_id, "
            "payload_hash, id, created_at) VALUES "
            "('accept', 'candidate-1', ?, 'pending', 'request-1', 'hash-1', 'suggestion-1', "
            "'2026-11-01')",
            (vault.encrypt({"note": "合成审核关系"}),),
        )
        connection.execute(
            "INSERT INTO suppression_events (project_id, encrypted, source, occurred_at, status, "
            "review_note, id, created_at) VALUES "
            "('project-1', ?, 'manual', '2026-11-01', 'approved', '', 'suppression-1', '2026-11-01')",
            (vault.encrypt({"reason": "合成停联"}),),
        )
    return database, vault


def _run_cli_migrate(monkeypatch, data_dir, vault):
    from jxd_leads import cli

    monkeypatch.setattr(cli.Vault, "macos", classmethod(lambda cls, *args, **kwargs: vault))
    monkeypatch.setattr(
        "sys.argv",
        ["jxd-leads", "migrate", "--data-dir", str(data_dir), "--approved-data-dir", str(data_dir)],
    )
    return cli.main()


def test_migrate_backs_up_legacy_database_and_keeps_relations(tmp_path, monkeypatch):
    database, vault = _legacy_11_database(tmp_path)
    data_dir = database.path.parent

    _run_cli_migrate(monkeypatch, data_dir, vault)

    verify(database.path, vault)
    with sqlite3.connect(database.path) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "20261124_marketing_fields",
        )
        assert connection.execute("SELECT company FROM candidates WHERE id = 'candidate-1'").fetchone() == (
            "合成公司",
        )
        assert connection.execute(
            "SELECT project_id FROM project_aliases WHERE id = 'alias-1'"
        ).fetchone() == ("project-1",)
        assert connection.execute(
            "SELECT candidate_id FROM review_suggestions WHERE id = 'suggestion-1'"
        ).fetchone() == ("candidate-1",)
        suppression = connection.execute(
            "SELECT status, encrypted FROM suppression_events WHERE id = 'suppression-1'"
        ).fetchone()
        assert suppression[0] == "approved"
        assert vault.decrypt(suppression[1]) == {"reason": "合成停联"}

    backups = sorted((data_dir / "backups").glob("leads-????-??-??.sqlite3"))
    assert len(backups) == 1
    pre_migration = backups[0]
    verify(pre_migration, vault, before_migration=True)
    with sqlite3.connect(pre_migration) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "20261030_project_aliases",
        )
        assert connection.execute("SELECT count(*) FROM candidates").fetchone() == (1,)

    # Restore remains head-only: the 1.1 snapshot is rejected by the candidate.
    with pytest.raises(ValueError, match="迁移版本"):
        restore_database(pre_migration, tmp_path / "strict-restore" / "leads.db", vault)

    # The same snapshot is restorable by the version that created it (0.3.0 head).
    monkeypatch.setattr("jxd_leads.backup.expected_head", lambda: "20261030_project_aliases")
    legacy_target = tmp_path / "legacy-restore" / "leads.db"
    restore_database(pre_migration, legacy_target, vault)
    with sqlite3.connect(legacy_target) as connection:
        assert connection.execute("SELECT company FROM candidates WHERE id = 'candidate-1'").fetchone() == (
            "合成公司",
        )


def test_migrate_wrong_key_leaves_no_backup_and_no_schema_change(tmp_path, monkeypatch):
    database, _ = _legacy_11_database(tmp_path)
    data_dir = database.path.parent

    with pytest.raises(SystemExit) as stopped:
        _run_cli_migrate(monkeypatch, data_dir, Vault.ephemeral())
    assert stopped.value.code == 1

    assert not list((data_dir / "backups").glob("leads-????-??-??.sqlite3"))
    with sqlite3.connect(database.path) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "20261030_project_aliases",
        )
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "candidate_review_events" not in tables


def test_daily_backup_keeps_strict_head_check_after_migration(tmp_path, monkeypatch):
    database, vault = _legacy_11_database(tmp_path)
    data_dir = database.path.parent
    legacy_copy = tmp_path / "legacy-copy.sqlite3"
    with sqlite3.connect(database.path) as source, sqlite3.connect(legacy_copy) as target:
        source.backup(target)
    with pytest.raises(ValueError, match="迁移版本"):
        verify(legacy_copy, vault)

    # Default daily backup (no before_migration) must still reject an old head.
    with pytest.raises(BusinessError) as error:
        run_backup(database, tmp_path / "legacy-backups", force=True, vault=vault)
    assert error.value.code == "BACKUP_FAILED"
    assert not list((tmp_path / "legacy-backups").glob("leads-????-??-??.sqlite3"))

    _run_cli_migrate(monkeypatch, data_dir, vault)
    backup = run_backup(database, tmp_path / "current-backups", force=True, vault=vault)
    verify(backup, vault)
    with sqlite3.connect(backup) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "20261124_marketing_fields",
        )


def test_migrate_stops_when_key_unavailable(tmp_path, monkeypatch):
    """存量库迁移前必须先过密钥预检；预检失败时不得继续升级，也不得留下备份。"""
    from jxd_leads import cli

    database = Database(tmp_path / "leads.db")
    database.migrate()

    def unavailable(*args, **kwargs):
        raise BusinessError(
            "原密钥不可用。已停止打开数据；请恢复本应用钥匙串密钥，不要重新生成。", "KEY_UNAVAILABLE"
        )

    monkeypatch.setattr(cli.Vault, "macos", classmethod(lambda cls, *args, **kwargs: unavailable()))
    monkeypatch.setattr(
        "sys.argv",
        ["jxd-leads", "migrate", "--data-dir", str(tmp_path), "--approved-data-dir", str(tmp_path)],
    )
    with pytest.raises(SystemExit) as stopped:
        cli.main()
    assert stopped.value.code == 1
    assert not (tmp_path / "backups").exists()


def test_retry_command_atomic_and_conflicting_content(svc):
    pid = project(svc)
    data = FollowupInput(summary="已沟通", next_action="回访", due_date="2026-11-03", minutes=7)
    def run():
        return svc.record_followup(pid, data)

    a = svc.execute_once("owner", "followup", "stable-1", data.model_dump(mode="json"), run)
    b = svc.execute_once("owner", "followup", "stable-1", data.model_dump(mode="json"), run)
    assert a == b
    with svc.db.session() as s:
        assert s.scalar(select(func.count()).select_from(Followup)) == 1
        assert s.scalar(select(func.count()).select_from(Todo)) == 1
    with pytest.raises(BusinessError) as e:
        svc.execute_once("owner", "followup", "stable-1", {"changed": True}, run)
    assert e.value.code == "IDEMPOTENCY_CONFLICT"


def test_contact_handle_not_leaked_in_context(svc):
    pid = project(svc)
    svc.add_contact(pid, ContactInput(name="测试", channel="test_wechat_8391"))
    svc.record_followup(pid, FollowupInput(summary="请通过 test_wechat_8391 联系"))
    assert "test_wechat_8391" not in json.dumps(svc.project_context(pid))


def test_command_receipt_rolls_back_with_failed_operation(svc):
    pid = project(svc)

    def fail():
        svc.record_followup(pid, FollowupInput(summary="不应保留"))
        raise BusinessError("失败")

    with pytest.raises(BusinessError):
        svc.execute_once("owner", "followup", "rollback", {}, fail)
    assert not svc.project_context(pid)["followups"]


def test_mcp_business_error_uses_protocol_error(svc):
    import asyncio

    from mcp.types import CallToolResult

    from jxd_leads.mcp_server import create_mcp

    result = asyncio.run(create_mcp(svc).call_tool("get_project_context", {"project_id": "missing"}))
    assert isinstance(result, CallToolResult)
    assert result.isError and result.structuredContent["ok"] is False
    assert result.structuredContent["error"]["code"] == "NOT_FOUND"


def test_mcp_unlisted_error_still_returns_envelope(svc, capsys):
    from mcp.types import CallToolResult

    from jxd_leads.mcp_server import create_mcp

    pid = project(svc)
    with svc.db.session() as s:
        s.add(Followup(project_id=pid, summary="not-a-fernet-token", result="待跟进", minutes=None))

    result = asyncio.run(create_mcp(svc).call_tool("get_project_context", {"project_id": pid}))

    assert isinstance(result, CallToolResult)
    receipt = result.structuredContent
    assert set(receipt) == {"schema_version", "ok", "request_id", "data", "error"}
    assert receipt["ok"] is False and receipt["data"] is None
    assert receipt["error"]["code"] == "INTERNAL_ERROR"
    assert receipt["error"]["retryable"] is False
    assert result.isError
    assert "InvalidToken" in capsys.readouterr().err


def test_backup_failure_is_persisted(svc, tmp_path):
    from jxd_leads.models import BackupRun

    folder = tmp_path / "file"
    folder.write_text("not a directory")
    with pytest.raises(BusinessError) as error:
        run_backup(svc.db, folder, force=True)
    assert error.value.code == "BACKUP_FAILED"
    with svc.db.session() as s:
        assert s.scalar(select(BackupRun)).status == "failed"


def test_backup_failure_survives_a_broken_failure_record(tmp_path):
    class BrokenDatabase:
        path = tmp_path / "missing.sqlite3"

        def session(self):
            raise RuntimeError("synthetic failure record unavailable")

    with pytest.raises(BusinessError) as error:
        run_backup(BrokenDatabase(), tmp_path / "backups", force=True)
    assert error.value.code == "BACKUP_FAILED"


def test_background_refresh_survives_unlisted_exception_and_health_reports_it(
    svc, tmp_path, monkeypatch
):
    app = create_app(svc, tmp_path / "health-backups", testing=True)

    def fail(*args, **kwargs):
        raise RuntimeError("synthetic unlisted failure")

    monkeypatch.setattr("jxd_leads.web.run_backup", fail)
    monkeypatch.setattr(svc, "check_reminders", fail)
    asyncio.run(app.state.refresh_backup())
    asyncio.run(app.state.refresh_reminders())

    assert "自动备份" in app.state.backup_error
    assert "提醒检查" in app.state.reminder_error
    with TestClient(app) as client:
        failed = client.get("/health").json()
    assert failed["backup_error"] and failed["reminder_error"]
    assert failed["last_backup_ok_at"] is None
    assert failed["last_reminder_ok_at"] is None

    monkeypatch.setattr("jxd_leads.web.run_backup", lambda *args, **kwargs: tmp_path / "leads.sqlite3")
    monkeypatch.setattr(svc, "check_reminders", lambda: None)
    asyncio.run(app.state.refresh_backup())
    asyncio.run(app.state.refresh_reminders())

    with TestClient(app) as client:
        recovered = client.get("/health").json()
    assert recovered["backup_error"] is None
    assert recovered["reminder_error"] is None
    assert recovered["last_backup_ok_at"]
    assert recovered["last_reminder_ok_at"]
