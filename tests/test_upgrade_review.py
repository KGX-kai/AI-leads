import asyncio
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_upgrade import project

from jxd_leads.errors import BusinessError
from jxd_leads.mcp_server import create_mcp
from jxd_leads.models import Audit, Followup, Inquiry, SuppressionEvent
from jxd_leads.schemas import FollowupInput, RequirementsInput
from jxd_leads.security import Vault
from jxd_leads.service import Service
from jxd_leads.web import create_app


def incoming(**changes):
    data = {
        "platform": "抖音",
        "account_id": "acct",
        "message_id": "m1",
        "user_id": "u1",
        "body": "请给方案",
        "occurred_at": "2026-10-30T10:00:00+08:00",
    }
    data.update(changes)
    return data


def test_old_stage_cannot_use_stale_requirement_card(svc):
    pid = project(svc)
    svc.update_requirements(
        pid, RequirementsInput(version=1, role="采购", authority="确认有权限", demand="补货", confirmed=True)
    )
    o = svc.opportunities(pid)[0]
    svc.update_opportunity(o["id"], o["version"], requirements={"confirmed": False})
    with pytest.raises(BusinessError):
        svc.set_stage(pid, "采购")
    assert svc.opportunities(pid)[0]["stage"] == "待核实"


def test_new_requirements_invalidates_old_project_version(svc):
    pid = project(svc)
    o = svc.opportunities(pid)[0]
    svc.update_opportunity(o["id"], 1, requirements={"demand": "新需求"})
    with pytest.raises(BusinessError):
        svc.update_requirements(pid, RequirementsInput(version=1, demand="旧需求"))
    assert svc.opportunities(pid)[0]["requirements"]["demand"] == "新需求"


def test_inquiry_suppression_is_scoped_to_stable_account_user(svc):
    i = svc.receive_inquiry(incoming(body="请不要再联系，谢谢"), "r1")
    svc.request_suppression(
        "请不要再联系", "咨询原文", "2026-10-30T10:00:00+08:00", "block", inquiry_id=i["id"]
    )
    other = svc.receive_inquiry(incoming() | {"message_id": "m2"}, "r2")
    assert other["status"] == "blocked"
    with pytest.raises(BusinessError):
        svc.propose_inquiry_reply(other["id"], "再次联系", "reply")
    assert svc.receive_inquiry(incoming() | {"message_id": "m3", "user_id": "u2"}, "r3")["status"] == "new"
    assert svc.receive_inquiry(incoming() | {"message_id": "m2", "account_id": "acct2"}, "r4")["status"] == "new"


@pytest.mark.parametrize(
    ("body", "evidence", "paused"),
    [
        ("本人明确表示：请不要再联系", "请不要再联系", True),
        ("请不要犹豫，尽快联系我，采购50盏灯", "不要犹豫", False),
        ("我并没有说不要联系你们", "不要联系", False),
        ("我没有建议你们不要联系", "不要联系", False),
        ("我不是要你们不要联系", "不要联系", False),
        ("客服说不要联系，我并不认同", "不要联系", False),
        ("如果价格太高，就不要联系", "不要联系", False),
        ("只要价格超过1000元，就不要联系", "不要联系", False),
        ("若价格不合适就不要联系", "不要联系", False),
        ("价格不合适的话就不要联系", "不要联系", False),
        ("不是不要联系，只是希望换个时间沟通", "不要联系", False),
        ("如果今天不方便请先回复；但无论如何，请不要再联系", "请不要再联系", True),
        ("如果价格合适就联系，现在请不要再联系", "请不要再联系", True),
        ("不要再打听价格，直接报价", "不要再打听", False),
        ("你们应该不要联系吗", "不要联系", False),
        ("请不要联系任何销售人员，请转技术", "不要联系", False),
        ("请不要联系张三，请直接联系我", "不要联系", False),
        ("请不要联系我们公司销售，请联系我", "不要联系", False),
        ("请不要再联系我以外的人，只联系我", "不要再联系", False),
        ("不要再联系我助理", "不要再联系", False),
        ("请别再打扰我们了", "别再打扰", True),
        ("请不要再给我打电话", "不要再给我打电话", True),
        ("别联系我了", "别联系", True),
        ("无需再联系", "无需再联系", True),
        ("请不要再和我联系", "请不要再和我联系", True),
        ("不要再给我们打电话", "不要再给我们打电话", True),
        ("请不要再打电话联系我", "请不要再打电话联系我", True),
        ("不要回复", "不要回复", True),
        ("无需回复", "无需回复", True),
        ("不必回复", "不必回复", True),
        ("请勿回复", "请勿回复", True),
        ("如果价格合适就联系但请不要再联系", "请不要再联系", True),
        ("我听客服说不要联系我，但我想继续沟通", "不要联系我", False),
        ("不要联系我们的经销商，请联系我", "不要联系我们的经销商，请联系我", False),
        ("不要再给我打电话，我们微信联系", "不要再给我打电话", False),
        ("不要再联系我，除非价格降到1000元内", "不要再联系我，除非价格降到1000元内", False),
        ("暂不需要，请不要联系", "暂不需要", False),
    ],
)
def test_inquiry_strong_match_requires_explicit_refusal(svc, body, evidence, paused):
    inquiry = svc.receive_inquiry(incoming(body=body), "strong-match")
    event = svc.request_suppression(
        evidence,
        "咨询原文",
        "2026-10-30T10:00:00+08:00",
        "strong-match-request",
        inquiry_id=inquiry["id"],
        actor="agent",
        origin="mcp",
    )
    assert event["paused"] is paused
    assert event["match"] == ("stable" if paused else "weak")
    assert svc.inquiry_context(inquiry["id"])["status"] == ("blocked" if paused else "new")


def test_inquiry_suppression_increments_version_once(svc):
    inquiry = svc.receive_inquiry(incoming(body="本人明确表示：请不要再联系"), "version-once")
    with svc.db.read_session() as session:
        before = session.get(Inquiry, inquiry["id"]).version
    event = svc.request_suppression(
        "请不要再联系",
        "咨询原文",
        "2026-10-30T10:00:00+08:00",
        "version-once-request",
        inquiry_id=inquiry["id"],
        actor="agent",
        origin="mcp",
    )
    assert event["paused"] is True
    with svc.db.read_session() as session:
        after = session.get(Inquiry, inquiry["id"]).version
    assert after == before + 1


def test_web_and_mcp_suppression_have_trusted_actor_and_stable_scope(svc, tmp_path):
    web_project = project(svc)
    with TestClient(create_app(svc, tmp_path / "b", testing=True)) as client:
        html = client.get("/reviews").text
        csrf = re.search('name="csrf-token" content="([^"]+)"', html)[1]
        response = client.post(
            "/actions/refusal",
            data={
                "csrf": csrf,
                "operation_id": "web-refusal",
                "request_id": "web-refusal",
                "evidence": "本人核实原话：请不要再联系",
                "source": "网页本人录入",
                "occurred_at": "2026-11-21T10:00:00+08:00",
                "project_id": web_project,
            },
            headers={"HX-Request": "true"},
        )
    assert response.status_code == 200
    assert svc.project_context(web_project)["stage"] == "停止联系"

    inquiry = svc.receive_inquiry(incoming(body="本人明确表示：请不要再联系", message_id="mcp-refusal"), "in")
    same_user = svc.receive_inquiry(
        incoming(body="后续咨询", message_id="same-user", comment_id="same-user"), "same-user"
    )
    other_user = svc.receive_inquiry(
        incoming(body="另一个用户", message_id="other", user_id="u2"), "other-user"
    )
    result = asyncio.run(
        create_mcp(svc).call_tool(
            "request_suppression",
            {
                "evidence": "请不要再联系",
                "source": "咨询原文",
                "occurred_at": "2026-10-30T10:00:00+08:00",
                "request_id": "mcp-stable",
                "inquiry_id": inquiry["id"],
            },
        )
    )
    assert result.structuredContent["ok"] is True
    assert result.structuredContent["data"]["paused"] is True
    assert svc.inquiry_context(inquiry["id"])["status"] == "blocked"
    assert svc.inquiry_context(same_user["id"])["status"] == "blocked"
    assert svc.inquiry_context(other_user["id"])["status"] == "new"
    with svc.db.read_session() as session:
        requests = list(
            session.scalars(
                select(Audit)
                .where(Audit.action == "suppression.request")
                .order_by(Audit.created_at)
            )
        )
    assert [(item.actor, item.detail) for item in requests] == [
        ("owner", "origin=web"),
        ("agent", "origin=mcp"),
    ]


def test_mcp_weak_project_match_is_pending_until_owner_review(svc, tmp_path):
    pid = project(svc)
    args = {
        "evidence": "合成来源显示请不要再联系",
        "source": "受限 Agent 提交",
        "occurred_at": "2026-11-21T10:00:00+08:00",
        "request_id": "mcp-weak",
        "project_id": pid,
    }
    first = asyncio.run(create_mcp(svc).call_tool("request_suppression", args))
    repeated = asyncio.run(create_mcp(svc).call_tool("request_suppression", args))
    assert first.structuredContent["data"] == repeated.structuredContent["data"]
    assert first.structuredContent["data"]["paused"] is False
    assert first.structuredContent["data"]["match"] == "weak"
    assert svc.project_context(pid)["stage"] != "停止联系"
    event_id = first.structuredContent["data"]["id"]
    with TestClient(create_app(svc, tmp_path / "b", testing=True)) as client:
        assert "尚未停联" in client.get("/reviews").text
    with pytest.raises(BusinessError) as error:
        svc.review_suppression(event_id, "本人已核对", actor="agent")
    assert error.value.code == "SCOPE_VIOLATION"
    svc.review_suppression(event_id, "本人核对来源后确认执行")
    assert svc.project_context(pid)["stage"] == "停止联系"
    svc.review_suppression(event_id, "重复确认")

    with svc.db.read_session() as session:
        events = list(session.scalars(select(SuppressionEvent)))
        audits = list(session.scalars(select(Audit).where(Audit.entity_id == pid)))
    assert len(events) == 1 and events[0].status == "confirmed"
    assert [(item.actor, item.action) for item in audits].count(("owner", "project.suppress")) == 1
    conflict = asyncio.run(
        create_mcp(svc).call_tool(
            "request_suppression",
            {**args, "evidence": "同一编号的不同内容"},
        )
    )
    assert conflict.structuredContent["ok"] is False
    assert conflict.structuredContent["error"]["code"] == "IDEMPOTENCY_CONFLICT"


def test_mcp_inquiry_without_matching_identity_or_quote_stays_pending(svc):
    inquiry = svc.receive_inquiry(
        incoming(user_id="", body="暂不需要，请不要联系", message_id="weak-inquiry"),
        "weak-inquiry",
    )
    result = asyncio.run(
        create_mcp(svc).call_tool(
            "request_suppression",
            {
                "evidence": "暂不需要",
                "source": "咨询原文",
                "occurred_at": "2026-10-30T10:00:00+08:00",
                "request_id": "mcp-weak-inquiry",
                "inquiry_id": inquiry["id"],
            },
        )
    )
    assert result.structuredContent["data"]["paused"] is False
    assert svc.inquiry_context(inquiry["id"])["status"] == "new"
    svc.review_suppression(result.structuredContent["data"]["id"], "本人核对原话后确认停联")
    assert svc.inquiry_context(inquiry["id"])["status"] == "blocked"


def test_weak_suppression_review_rejects_changed_target(svc):
    pid = project(svc)
    result = asyncio.run(
        create_mcp(svc).call_tool(
            "request_suppression",
            {
                "evidence": "待本人核实的拒绝原话",
                "source": "受限 Agent 提交",
                "occurred_at": "2026-11-21T10:00:00+08:00",
                "request_id": "mcp-weak-changed",
                "project_id": pid,
            },
        )
    )
    current = svc.project_context(pid)
    svc.correct_project(pid, current["version"], current["name"], current["region"], current["address"], "本人核实项目资料已更新")
    with pytest.raises(BusinessError) as error:
        svc.review_suppression(result.structuredContent["data"]["id"], "本人核对后确认")
    assert error.value.code == "VERSION_CONFLICT"
    assert svc.project_context(pid)["stage"] != "停止联系"


def test_project_suppression_invalidates_inquiry_draft(svc):
    pid = project(svc)
    i = svc.receive_inquiry(incoming(), "r1")
    svc.update_inquiry(i["id"], 1, {}, svc.opportunities(pid)[0]["id"])
    r = svc.propose_inquiry_reply(i["id"], "建议回复", "draft")
    svc.suppress_project(pid, "不要联系")
    assert svc.review_update(r["id"], True)["status"] == "rejected"
    assert svc.inquiry_context(i["id"])["approved_drafts"] == []


def test_retry_after_version_change_and_edited_reply(svc):
    pid = project(svc)
    oid = svc.opportunities(pid)[0]["id"]
    a = svc.propose_update(oid, {"summary": "候选待核实"}, "retry")
    svc.update_opportunity(oid, 1, stage="暂缓")
    assert svc.propose_update(oid, {"summary": "候选待核实"}, "retry")["id"] == a["id"]
    i = svc.receive_inquiry(incoming(), "in")
    r = svc.propose_inquiry_reply(i["id"], "原始草稿", "draft")
    svc.review_update(r["id"], True, edited={"draft": "人工修改稿"})
    assert svc.inquiry_context(i["id"])["approved_drafts"][0]["draft"] == "人工修改稿"


def test_mixed_key_rejected_even_when_sentinel_valid(svc):
    pid = project(svc)
    with svc.db.session() as s:
        s.add(
            Followup(project_id=pid, summary=Vault.ephemeral().encrypt({"text": "bad"}), result="待跟进", minutes=None)
        )
    with pytest.raises(BusinessError) as e:
        Service(svc.db, svc.vault)
    assert e.value.code == "KEY_UNAVAILABLE"


def test_web_inquiry_owner_flow_repeat_does_not_duplicate(svc, tmp_path):
    with TestClient(create_app(svc, tmp_path / "b", testing=True)) as client:
        html = client.get("/inbox").text
        csrf = re.search('name="csrf-token" content="([^"]+)"', html)[1]
        data = {"csrf": csrf, "operation_id": "web-1", "request_id": "web-r1", **incoming()}
        first = client.post("/actions/inquiry_new", data=data, headers={"HX-Request": "true"})
        second = client.post("/actions/inquiry_new", data=data, headers={"HX-Request": "true"})
        assert first.headers["HX-Location"] == second.headers["HX-Location"]
        assert svc.inquiries()["total"] == 1
        assert "请给方案" in client.get(first.headers["HX-Location"]).text
        assert "项目待核实" in client.get(first.headers["HX-Location"]).text
        for url in ["/reviews", "/notifications", "/api/v1/capabilities", "/api/v1/queue"]:
            assert client.get(url).status_code == 200


def test_web_joint_review_and_offer_retries(svc, tmp_path):
    pid = project(svc)
    o = svc.opportunities(pid)[0]
    svc.update_opportunity(
        o["id"], 1, requirements={"role": "采购", "authority": "本人有权", "demand": "补货", "confirmed": True}
    )
    with TestClient(create_app(svc, tmp_path / "b", testing=True)) as client:
        html = client.get("/opportunities/" + o["id"]).text
        assert "本次采购需求卡" in html
        csrf = re.search('name="csrf-token" content="([^"]+)"', html)[1]
        data = {
            "csrf": csrf,
            "operation_id": "offer-one",
            "project_id": pid,
            "opportunity_id": o["id"],
            "kind": "试样",
            "product": "合成型号",
            "quantity": "2",
            "amount": "",
            "due_date": "2026-11-02",
        }
        for _ in range(2):
            response = client.post("/actions/offer", data=data, headers={"HX-Request": "true"})
            assert "HX-Location" in response.headers
        assert len(svc.opportunity_context(o["id"])["offers"]) == 1
        assert len(svc.opportunity_context(o["id"])["tasks"]) == 1


def test_overnight_reminder_is_not_replayed_per_missed_day(svc):
    pid = project(svc)
    svc.record_followup(pid, FollowupInput(summary="跟进", next_action="回访", due_date="2026-10-01"))
    current = datetime(2026, 10, 30, 10, tzinfo=ZoneInfo("Asia/Shanghai"))
    svc.check_reminders(current)
    svc.check_reminders(current)
    assert len(svc.notifications()) == 1


def test_refusal_misidentification_owner_correction_is_audited(svc):
    i = svc.receive_inquiry(incoming(), "initial")
    event = svc.request_suppression(
        "不要联系了", "人工误选对象", "2026-10-30T10:00:00+08:00", "refuse", inquiry_id=i["id"]
    )
    with pytest.raises(BusinessError):
        svc.correct_suppression(event["id"], "已核对为误匹配", actor="agent")
    svc.correct_suppression(event["id"], "已比对原文和稳定用户ID，确认选错对象")
    assert svc.inquiry_context(i["id"])["status"] == "new"
    assert svc.receive_inquiry(incoming() | {"message_id": "m2"}, "again")["status"] == "new"
    with pytest.raises(BusinessError) as error:
        svc.review_suppression(event["id"], "旧页面迟到的复核请求")
    assert error.value.code == "VERSION_CONFLICT"
    with svc.db.read_session() as session:
        saved = session.get(SuppressionEvent, event["id"])
        confirmations = list(
            session.scalars(
                select(Audit).where(Audit.action == "suppression.confirm", Audit.entity_id == event["id"])
            )
        )
    assert saved.status == "mistaken"
    assert confirmations == []


def test_refusal_correction_reopens_later_inquiries_inheriting_same_block(svc):
    first = svc.receive_inquiry(incoming(body="本人明确表示：请不要再联系"), "first")
    event = svc.request_suppression(
        "请不要再联系",
        "咨询原文",
        "2026-10-30T10:00:00+08:00",
        "correct-inherited",
        inquiry_id=first["id"],
    )
    later = svc.receive_inquiry(
        incoming(body="后续新咨询", message_id="later", comment_id="later"), "later"
    )
    assert later["status"] == "blocked"

    result = svc.correct_suppression(event["id"], "已比对原话和同一稳定用户ID，确认此前选错了对象")

    assert result["status"] == "mistaken"
    assert svc.inquiry_context(first["id"])["status"] == "new"
    assert svc.inquiry_context(later["id"])["status"] == "new"
    with svc.db.read_session() as session:
        saved = session.get(SuppressionEvent, event["id"])
        payload = svc.vault.decrypt(saved.encrypted)
        audit = session.scalar(
            select(Audit)
            .where(Audit.action == "suppression.correct", Audit.entity_id == event["id"])
        )
    assert f"inquiries:{later['id']}" in payload["prior"]["changes"]
    assert "restored_objects=2" in audit.detail and "inherited_after_event=1" in audit.detail


def test_refusal_correction_keeps_a_later_independent_stop_in_force(svc):
    first = svc.receive_inquiry(incoming(body="本人明确表示：请不要再联系"), "first-stop")
    first_event = svc.request_suppression(
        "请不要再联系",
        "咨询原文",
        "2026-10-30T10:00:00+08:00",
        "first-stop-event",
        inquiry_id=first["id"],
        actor="agent",
        origin="mcp",
    )
    second = svc.receive_inquiry(
        incoming(body="后续咨询，本人再次明确：请不要再联系", message_id="second-stop"),
        "second-stop",
    )
    second_event = svc.request_suppression(
        "请不要再联系",
        "咨询原文",
        "2026-10-30T10:00:00+08:00",
        "second-stop-event",
        inquiry_id=second["id"],
        actor="agent",
        origin="mcp",
    )
    assert first_event["paused"] is True and second_event["paused"] is True

    with pytest.raises(BusinessError) as error:
        svc.correct_suppression(first_event["id"], "已核对原文和稳定身份，确认第一次事件误匹配")

    assert error.value.code == "VERSION_CONFLICT"
    assert svc.inquiry_context(first["id"])["status"] == "blocked"
    assert svc.inquiry_context(second["id"])["status"] == "blocked"
    assert svc.receive_inquiry(
        incoming(body="第三次新咨询", message_id="third-stop", comment_id="third-stop"),
        "third-stop",
    )["status"] == "blocked"
    svc.review_suppression(second_event["id"], "本人确认后续独立停联仍有效")
    assert svc.inquiry_context(second["id"])["status"] == "blocked"


def test_suppression_retry_reports_current_status_without_new_side_effects(svc):
    stable = svc.receive_inquiry(incoming(body="本人明确表示：请不要再联系"), "stable-retry")
    stable_args = {
        "evidence": "请不要再联系",
        "source": "咨询原文",
        "occurred_at": "2026-10-30T10:00:00+08:00",
        "request_id": "stable-retry-request",
        "inquiry_id": stable["id"],
        "actor": "agent",
        "origin": "mcp",
    }
    first = svc.request_suppression(**stable_args)
    assert first["paused"] is True and first["status"] == "pending"
    svc.correct_suppression(first["id"], "已核对原话和稳定身份，确认此前事件误匹配")
    retried = svc.request_suppression(**stable_args)
    assert retried["id"] == first["id"]
    assert retried["status"] == "mistaken" and retried["paused"] is False

    weak = svc.receive_inquiry(
        incoming(body="暂不需要，请不要联系", message_id="weak-retry"),
        "weak-retry",
    )
    weak_args = {
        "evidence": "暂不需要",
        "source": "咨询原文",
        "occurred_at": "2026-10-30T10:00:00+08:00",
        "request_id": "weak-retry-request",
        "inquiry_id": weak["id"],
        "actor": "agent",
        "origin": "mcp",
    }
    pending = svc.request_suppression(**weak_args)
    assert pending["paused"] is False and pending["status"] == "pending"
    svc.review_suppression(pending["id"], "本人核对原话后确认停联")
    confirmed = svc.request_suppression(**weak_args)
    assert confirmed["id"] == pending["id"]
    assert confirmed["status"] == "confirmed" and confirmed["paused"] is True


def test_suppression_review_rejects_a_confirmed_event_whose_effect_disappeared(svc):
    inquiry = svc.receive_inquiry(incoming(body="本人明确表示：请不要再联系"), "effect-loss")
    event = svc.request_suppression(
        "请不要再联系",
        "咨询原文",
        "2026-10-30T10:00:00+08:00",
        "effect-loss-request",
        inquiry_id=inquiry["id"],
        actor="owner",
    )
    svc.review_suppression(event["id"], "本人确认先保持停联")
    with svc.db.session() as session:
        from jxd_leads.models import Suppression

        block = session.scalar(select(Suppression).where(Suppression.kind == "platform_user"))
        saved_inquiry = session.get(Inquiry, inquiry["id"])
        session.delete(block)
        saved_inquiry.status = "new"
        saved_inquiry.version += 1

    with pytest.raises(BusinessError) as error:
        svc.review_suppression(event["id"], "页面上的迟到确认")

    assert error.value.code == "VERSION_CONFLICT"
    assert svc.inquiry_context(inquiry["id"])["status"] == "new"


def test_suppression_review_rejects_a_lost_platform_block_even_if_inquiry_is_blocked(svc):
    inquiry = svc.receive_inquiry(incoming(body="本人明确表示：请不要再联系"), "lost-block")
    event = svc.request_suppression(
        "请不要再联系",
        "咨询原文",
        "2026-10-30T10:00:00+08:00",
        "lost-block-request",
        inquiry_id=inquiry["id"],
        actor="owner",
    )
    svc.review_suppression(event["id"], "本人确认先保持停联")
    with svc.db.session() as session:
        from jxd_leads.models import Suppression

        block = session.scalar(select(Suppression).where(Suppression.kind == "platform_user"))
        session.delete(block)

    assert svc.inquiry_context(inquiry["id"])["status"] == "blocked"
    with pytest.raises(BusinessError) as error:
        svc.review_suppression(event["id"], "页面上的迟到确认")
    assert error.value.code == "VERSION_CONFLICT"


def test_legacy_suppression_payload_uses_event_columns_for_retry_and_review(svc):
    inquiry = svc.receive_inquiry(incoming(body="本人明确表示：请不要再联系"), "legacy-payload")
    args = {
        "evidence": "请不要再联系",
        "source": "咨询原文",
        "occurred_at": "2026-10-30T10:00:00+08:00",
        "request_id": "legacy-payload-request",
        "inquiry_id": inquiry["id"],
        "actor": "agent",
        "origin": "mcp",
    }
    event = svc.request_suppression(**args)
    with svc.db.session() as session:
        saved = session.get(SuppressionEvent, event["id"])
        payload = svc.vault.decrypt(saved.encrypted)
        payload.pop("target")
        payload.pop("match")
        saved.encrypted = svc.vault.encrypt(payload)

    retried = svc.request_suppression(**args)
    assert retried["id"] == event["id"]
    assert retried["paused"] is True
    assert retried["match"] == "stable"
    assert svc.review_suppression(event["id"], "本人核对旧版回执后确认")["status"] == "confirmed"


def test_legacy_later_event_without_target_still_blocks_correction(svc):
    first = svc.receive_inquiry(incoming(body="本人明确表示：请不要再联系"), "legacy-first")
    first_event = svc.request_suppression(
        "请不要再联系",
        "咨询原文",
        "2026-10-30T10:00:00+08:00",
        "legacy-first-request",
        inquiry_id=first["id"],
        actor="owner",
    )
    second = svc.receive_inquiry(
        incoming(body="后续咨询，本人再次明确：请不要再联系", message_id="legacy-second"),
        "legacy-second",
    )
    second_event = svc.request_suppression(
        "请不要再联系",
        "咨询原文",
        "2026-10-30T10:00:00+08:00",
        "legacy-second-request",
        inquiry_id=second["id"],
        actor="owner",
    )
    with svc.db.session() as session:
        saved = session.get(SuppressionEvent, second_event["id"])
        payload = svc.vault.decrypt(saved.encrypted)
        payload.pop("target")
        saved.encrypted = svc.vault.encrypt(payload)

    with pytest.raises(BusinessError) as error:
        svc.correct_suppression(first_event["id"], "已核对原文和稳定身份，确认第一次事件误匹配")
    assert error.value.code == "VERSION_CONFLICT"
    assert svc.inquiry_context(first["id"])["status"] == "blocked"
    assert svc.inquiry_context(second["id"])["status"] == "blocked"


def test_suppression_correction_reports_only_blocks_actually_deleted(svc):
    inquiry = svc.receive_inquiry(incoming(body="本人明确表示：请不要再联系"), "deleted-count")
    event = svc.request_suppression(
        "请不要再联系",
        "咨询原文",
        "2026-10-30T10:00:00+08:00",
        "deleted-count-request",
        inquiry_id=inquiry["id"],
        actor="owner",
    )
    with svc.db.session() as session:
        from jxd_leads.models import Suppression

        block = session.scalar(select(Suppression).where(Suppression.kind == "platform_user"))
        session.delete(block)

    svc.correct_suppression(event["id"], "已核对原话和稳定身份，确认此前事件误匹配")
    with svc.db.read_session() as session:
        audit = session.scalar(
            select(Audit).where(
                Audit.action == "suppression.correct", Audit.entity_id == event["id"]
            )
        )
    assert "deleted_blocks=0" in audit.detail
    assert svc.inquiry_context(inquiry["id"])["status"] == "new"


def test_corrected_address_and_merge_preserve_refusal(svc):
    from test_core import candidate

    pid = project(svc)
    svc.suppress_project(pid, "明确拒绝")
    version = svc.project_context(pid)["version"]
    svc.correct_project(pid, version, "更正后的车库", "成都", "核实后的项目地址", "本人核对项目官网位置")
    result = svc.submit_candidates(
        None,
        [
            candidate().model_copy(
                update={
                    "project": "更正后的车库",
                    "address": "核实后的项目地址",
                    "source_url": "https://example.org/corrected",
                }
            )
        ],
    )
    assert result["items"][0]["status"] == "suppressed"


def test_stale_qualification_does_not_replace_new_owner_judgment(svc):
    pid = project(svc)
    oid = svc.opportunities(pid)[0]["id"]
    suggestion = svc.propose_qualification(
        {"fit": "符合", "evidence": "旧版待核实证据"}, "qual-stale", opportunity_id=oid
    )
    svc.confirm_qualification({"fit": "不符合", "evidence": "本人刚核实不符合服务地区"}, opportunity_id=oid)
    with pytest.raises(BusinessError) as error:
        svc.review_update(suggestion["id"], True)
    assert error.value.code == "VERSION_CONFLICT"


def test_overview_counts_new_pending_suggestions(svc):
    i = svc.receive_inquiry(incoming(), "dashboard-inquiry")
    svc.propose_inquiry_reply(i["id"], "待本人核对的回复", "dashboard-draft")
    assert svc.overview()["proposals"] == 1


def test_tracking_parameters_deduplicate_without_merging_distinct_page(svc):
    from test_core import candidate

    a = svc.submit_candidates(
        None, [candidate().model_copy(update={"source_url": "https://example.org/project?id=1&utm_source=douyin"})]
    )
    b = svc.submit_candidates(
        None, [candidate().model_copy(update={"source_url": "https://example.org/project?id=1&utm_source=wechat"})]
    )
    c = svc.submit_candidates(None, [candidate().model_copy(update={"source_url": "https://example.org/project?id=2"})])
    assert a["created"] == 1 and b["duplicates"] == 1 and c["created"] == 1
    assert "utm_source=douyin" in a["items"][0]["source_url"]
