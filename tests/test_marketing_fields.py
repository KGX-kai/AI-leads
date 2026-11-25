"""0.5.0 R12: business profile, source channel, bid deadline, stall warning and follow-up pace."""

import json
import sqlite3
from datetime import UTC, date, datetime, timedelta

import pytest
from alembic import command
from alembic.config import Config
from pydantic import ValidationError
from sqlalchemy import inspect

from jxd_leads.db import Database, migration_resource_root
from jxd_leads.errors import BusinessError
from jxd_leads.models import Opportunity, Setting
from jxd_leads.schemas import CandidateInput
from jxd_leads.workflows import TZ

TODAY = datetime.now(TZ).date()


def candidate(**extra):
    data = {
        "company": "合成物业公司",
        "project": "合成园区公区照明",
        "region": "合成地区",
        "source_url": "https://example.com/notice/1",
        "evidence": "公告原文写明公区照明节能改造",
        "published_at": str(TODAY - timedelta(days=2)),
    }
    data.update(extra)
    return CandidateInput(**data)


def accepted_opportunity(svc, **extra):
    cid = svc.submit_candidates(None, [candidate(**extra)], actor="owner")["items"][0]["id"]
    pid = svc.review_candidate(cid, "accept")["project_id"]
    return cid, svc.opportunities(pid)[0]


def test_old_calls_without_new_fields_keep_working(svc):
    cid, opp = accepted_opportunity(svc)
    item = svc.list_candidates()["items"][0]
    assert item["id"] == cid and item["source_channel"] == "" and item["bid_deadline"] is None
    assert opp["bid_deadline"] is None and opp["source_channel"] == ""
    suggestion = svc.propose_update(opp["id"], {"summary": "电话沟通", "result": "有效沟通"}, "old-1")
    svc.review_update(suggestion["id"], True)
    requirements = svc.opportunity_context(opp["id"])["requirements"]
    assert "business_mode" not in requirements


def test_capabilities_expose_version_and_owner_lists(svc):
    caps = svc.capabilities()
    assert caps["version"] == "0.5.0" and caps["schema_version"] == "1.3"
    assert caps["source_channels"][0] == "招投标" and len(caps["source_channels"]) == 8
    assert "annual_power_cost" in caps["inquiry_suggestion_fields"]
    svc.save_source_channels(["自定义渠道", "自定义渠道", " "])
    assert svc.capabilities()["source_channels"] == ["自定义渠道"]


def test_migration_seeds_settings_and_round_trips(tmp_path):
    import importlib.util

    from jxd_leads.db import MIGRATION_SETTING_SEED

    spec = importlib.util.spec_from_file_location(
        "marketing_migration", migration_resource_root() / "migrations/versions/20261124_marketing_fields.py"
    )
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert MIGRATION_SETTING_SEED == {
        "source_channels": migration.DEFAULT_SOURCE_CHANNELS, "stall_days": migration.DEFAULT_STALL_DAYS
    }

    database = Database(tmp_path / "migration" / "leads.db")
    database.migrate()
    resources = migration_resource_root()
    config = Config(str(resources / "alembic.ini"))
    config.set_main_option("script_location", str(resources / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database.path}")

    with sqlite3.connect(database.path) as connection:
        values = dict(connection.execute("SELECT key, value FROM settings").fetchall())
    assert json.loads(values["source_channels"]) == [
        "招投标", "物业协会", "抖音同城", "CABEP", "展会", "名单池", "竞品客户", "转介绍"
    ]
    assert json.loads(values["stall_days"]) == {"EMC": 30, "买断": 7, "未定": 14}

    database.engine.dispose()
    command.downgrade(config, "20261117_candidate_quality")
    with sqlite3.connect(database.path) as connection:
        assert "source_channel" not in {
            row[1] for row in connection.execute("PRAGMA table_info(candidates)")
        }
        assert not set(connection.execute("SELECT key FROM settings").fetchall()) & {
            ("source_channels",), ("stall_days",)
        }

    command.upgrade(config, "head")
    database.engine.dispose()
    with database.read_session() as session:
        assert json.loads(session.get(Setting, "source_channels").value)[0] == "招投标"
        columns = {column["name"] for column in inspect(database.engine).get_columns("candidates")}
    assert {"source_channel", "bid_deadline"} <= columns


def test_source_channel_must_come_from_owner_list(svc):
    svc.submit_candidates(None, [candidate(source_channel="招投标")], actor="agent")
    with pytest.raises(BusinessError, match="来源渠道"):
        svc.submit_candidates(None, [candidate(project="另一项目", source_channel="未登记渠道")], actor="agent")
    svc.save_source_channels(["只剩这个"])
    with pytest.raises(BusinessError):
        svc.submit_candidates(None, [candidate(project="第三项目", source_channel="招投标")], actor="agent")


def test_bid_deadline_validation_and_queue(svc):
    with pytest.raises(BusinessError, match="早于公告"):
        svc.submit_candidates(
            None, [candidate(bid_deadline=str(TODAY - timedelta(days=5)))], actor="agent"
        )
    soon = svc.submit_candidates(
        None, [candidate(project="近期截止", bid_deadline=str(TODAY + timedelta(days=3)))], actor="agent"
    )["items"][0]["id"]
    later = svc.submit_candidates(
        None, [candidate(project="远期截止", bid_deadline=str(TODAY + timedelta(days=20)))], actor="agent"
    )["items"][0]["id"]
    ids = {item["id"] for item in svc.today_queue(kind="bid_deadline")["items"]}
    assert soon in ids and later not in ids
    pid = svc.review_candidate(soon, "accept")["project_id"]
    opp = svc.opportunities(pid)[0]
    assert opp["bid_deadline"] == str(TODAY + timedelta(days=3))
    queue = {item["id"]: item for item in svc.today_queue(kind="bid_deadline")["items"]}
    assert opp["id"] in queue and soon not in queue
    svc.update_opportunity(opp["id"], opp["version"], stage="关闭")
    assert opp["id"] not in {item["id"] for item in svc.today_queue(kind="bid_deadline")["items"]}


def test_business_profile_is_suggested_then_confirmed(svc):
    _, opp = accepted_opportunity(svc)
    with pytest.raises(ValidationError):
        svc.propose_update(opp["id"], {"summary": "x", "business_mode": "租赁"}, "bad-mode")
    suggestion = svc.propose_update(
        opp["id"],
        {"summary": "客户说明为集团物业", "business_mode": "EMC", "annual_power_cost": "≥30万", "managed_projects": 8},
        "profile-1",
    )
    assert "business_mode" not in svc.opportunity_context(opp["id"])["requirements"]
    svc.review_update(suggestion["id"], True)
    requirements = svc.opportunity_context(opp["id"])["requirements"]
    assert requirements["business_mode"] == "EMC"
    assert requirements["annual_power_cost"] == "≥30万" and requirements["managed_projects"] == 8


def test_inquiry_power_cost_field_is_reviewed(svc):
    iid = svc.receive_inquiry(
        {"platform": "手工", "account_id": "owner", "message_id": "m-1", "body": "电费一年四十多万",
         "occurred_at": "2026-11-20T10:00:00+08:00"},
        "inq-1",
    )["id"]
    with pytest.raises(ValidationError):
        svc.propose_inquiry_fields(iid, {"annual_power_cost": "四十万"}, "原话提到电费", "inq-bad")
    suggestion = svc.propose_inquiry_fields(iid, {"annual_power_cost": "≥30万"}, "原话提到一年四十多万", "inq-ok")
    assert svc.inquiry_context(iid)["annual_power_cost"] is None
    svc.review_update(suggestion["id"], True)
    assert svc.inquiry_context(iid)["annual_power_cost"] == "≥30万"


def test_inquiry_source_channel_is_validated_and_saved(svc):
    data = {
        "platform": "手工",
        "account_id": "owner",
        "message_id": "channel-inquiry",
        "body": "咨询公区照明改造",
        "occurred_at": "2026-11-20T10:00:00+08:00",
    }
    legacy = svc.receive_inquiry(data, "legacy-source-channel")["id"]
    assert svc.inquiry_context(legacy)["source_channel"] == ""
    current = svc.receive_inquiry({**data, "message_id": "channel-inquiry-2",
                                   "source_channel": "物业协会"}, "current-source-channel")["id"]
    assert svc.inquiry_context(current)["source_channel"] == "物业协会"
    with pytest.raises(BusinessError, match="来源渠道"):
        svc.receive_inquiry({**data, "message_id": "channel-inquiry-3",
                             "source_channel": "未登记渠道"}, "bad-source-channel")


def test_stall_warning_uses_mode_threshold_and_resets_on_stage_change(svc):
    _, opp = accepted_opportunity(svc)
    old = (datetime.now(UTC) - timedelta(days=20)).isoformat()
    with svc.db.session() as s:
        row = s.get(Opportunity, opp["id"])
        row.stage_entered_at = old
        row.requirements = {**row.requirements, "business_mode": "EMC"}
    assert svc.stalled_opportunities() == []
    svc.save_stall_days({"EMC": 10, "买断": 7, "未定": 14})
    stalled = svc.stalled_opportunities()
    assert stalled[0]["id"] == opp["id"] and stalled[0]["threshold"] == 10 and stalled[0]["days"] >= 20
    with pytest.raises(BusinessError):
        svc.save_stall_days({"EMC": 0, "买断": 7, "未定": 14})
    svc.update_opportunity(opp["id"], svc.opportunity_context(opp["id"])["version"], stage="暂缓")
    assert svc.stalled_opportunities() == []


def test_reject_reason_codes(svc):
    first = svc.submit_candidates(None, [candidate()], actor="owner")["items"][0]["id"]
    with pytest.raises(BusinessError, match="排除原因类型"):
        svc.review_candidate(first, "reject", reason="经销商询价", reason_code="unknown")
    result = svc.review_candidate(first, "reject", reason="经销商询价", reason_code="channel_dealer")
    assert result["review_reason_code"] == "channel_dealer"


def test_followup_pace_is_only_a_suggestion(svc):
    _, opp = accepted_opportunity(svc)
    at = datetime(2026, 11, 24, 9, tzinfo=TZ)
    pace = svc.followup_suggestion(opp["id"], at=at)
    assert pace == {"due_date": "2026-11-25", "basis": "未定 · 待核实", "requires_confirmation": True}
    assert svc.opportunity_context(opp["id"])["tasks"] == []
    assert date.fromisoformat(pace["due_date"])


def test_owner_pages_save_profile_channels_and_thresholds(svc, tmp_path):
    import re

    from fastapi.testclient import TestClient

    from jxd_leads.web import create_app

    _, opp = accepted_opportunity(svc)
    with TestClient(create_app(svc, tmp_path / "browser", testing=True)) as client:
        html = client.get("/opportunities/" + opp["id"]).text
        assert "来源与截止" in html and "商务模式" in html and "建议下次跟进" in html
        csrf = re.search('name="csrf-token" content="([^"]+)"', html)[1]

        def post(action, op, **data):
            response = client.post(
                "/actions/" + action, data={"csrf": csrf, "operation_id": op, **data}, headers={"HX-Request": "true"}
            )
            assert response.status_code == 200, response.text
            return response

        version = svc.opportunity_context(opp["id"])["version"]
        post("opportunity_profile", "op-1", id=opp["id"], version=str(version),
             source_channel="物业协会", bid_deadline=str(TODAY + timedelta(days=2)))
        version = svc.opportunity_context(opp["id"])["version"]
        post("opportunity_requirements", "op-2", id=opp["id"], version=str(version),
             business_mode="买断", annual_power_cost="5–30万", managed_projects="3")
        context = svc.opportunity_context(opp["id"])
        assert context["source_channel"] == "物业协会"
        assert context["requirements"]["business_mode"] == "买断"
        assert context["requirements"]["managed_projects"] == 3

        settings = client.get("/settings").text
        assert "来源渠道" in settings and "阶段停滞阈值" in settings
        post("channel_settings", "op-3", channels="渠道甲\n渠道乙")
        assert svc.source_channels() == ["渠道甲", "渠道乙"]
        post("stall_settings", "op-4", EMC="20", 买断="5", 未定="9")
        assert svc.stall_days() == {"EMC": 20, "买断": 5, "未定": 9}


def test_dashboard_shows_deadline_stall_and_channels(svc, tmp_path):
    from fastapi.testclient import TestClient

    from jxd_leads.web import create_app

    _, opp = accepted_opportunity(svc, source_channel="招投标", bid_deadline=str(TODAY + timedelta(days=4)))
    with svc.db.session() as s:
        s.get(Opportunity, opp["id"]).stage_entered_at = (datetime.now(UTC) - timedelta(days=40)).isoformat()
    with TestClient(create_app(svc, tmp_path / "browser", testing=True)) as client:
        html = client.get("/dashboard-v2").text
    assert "投标截止" in html
    assert "超过阈值 14 天" in html
    assert "来源渠道" in html and "招投标" in html and "未标注" in html
    snapshot = svc.dashboard_snapshot()
    row = next(item for item in snapshot["channels"] if item["name"] == "招投标")
    assert row == {"name": "招投标", "candidates": 1, "inquiries": 0, "opportunities": 1}


def test_dashboard_keeps_historical_channel_after_settings_change(svc):
    accepted_opportunity(svc, source_channel="招投标")
    inquiry = svc.receive_inquiry(
        {
            "platform": "手工",
            "account_id": "owner",
            "message_id": "historical-channel",
            "source_channel": "招投标",
            "body": "咨询投标项目",
            "occurred_at": "2026-11-20T10:00:00+08:00",
        },
        "historical-channel",
    )
    assert inquiry["source_channel"] == "招投标"
    svc.save_source_channels(["物业协会"])
    snapshot = svc.dashboard_snapshot()
    rows = {item["name"]: item for item in snapshot["channels"]}
    assert rows["招投标"] == {"name": "招投标", "candidates": 1, "inquiries": 1, "opportunities": 1}
    assert rows["物业协会"] == {"name": "物业协会", "candidates": 0, "inquiries": 0, "opportunities": 0}
    assert rows["未标注"]["candidates"] == 0


def test_dashboard_marks_expired_bid_deadline_as_overdue(svc, tmp_path):
    from fastapi.testclient import TestClient
    from test_dashboard import parse_dashboard

    from jxd_leads.web import create_app

    _, opp = accepted_opportunity(
        svc,
        published_at=str(TODAY - timedelta(days=10)),
        bid_deadline=str(TODAY - timedelta(days=1)),
    )
    with TestClient(create_app(svc, tmp_path / "browser", testing=True)) as client:
        boot = parse_dashboard(client.get("/dashboard-v2")).boot
    task = next(item for item in boot["tasks"] if item["id"] == opp["id"])
    assert task["kind"] == "bid_deadline"
    assert task["overdue"] is True
    assert task["note"] == "投标已截止"
    assert boot["overview"]["counts"]["overdue"] == 1
