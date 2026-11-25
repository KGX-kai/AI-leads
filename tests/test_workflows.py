from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from test_upgrade import project

from jxd_leads.errors import BusinessError
from jxd_leads.schemas import FollowupInput


def test_multiple_opportunities_require_explicit_binding(svc):
    pid = project(svc)
    assert len(svc.opportunities(pid)) == 1
    second = svc.create_opportunity(pid, "补货", "第二次采购")
    with pytest.raises(BusinessError) as error:
        svc.record_followup(pid, FollowupInput(summary="未指定"))
    assert error.value.code == "AMBIGUOUS_OPPORTUNITY"
    svc.record_followup(pid, FollowupInput(summary="第二次跟进"), opportunity_id=second["id"])
    assert len(svc.opportunity_context(second["id"])["followups"]) == 1


def test_inquiry_unknown_identity_dedup_and_conflict(svc):
    data = {
        "platform": "抖音",
        "account_id": "owned-enterprise",
        "message_id": "comment-1",
        "body": "怎么联系，想了解车库方案",
        "source_url": "https://www.douyin.com/video/1",
        "occurred_at": "2026-10-30T10:00:00+08:00",
    }
    one = svc.receive_inquiry(data, "in-1")
    again = svc.receive_inquiry(data, "in-2")
    assert one["id"] == again["id"]
    assert one["project_id"] is None and svc.projects() == []
    with pytest.raises(BusinessError):
        svc.receive_inquiry(dict(data, body="不同内容"), "in-3")
    other = svc.receive_inquiry(dict(data, account_id="other-account"), "in-4")
    assert other["id"] != one["id"]
    assert b"owned-enterprise" not in svc.db.path.read_bytes()


def test_refusal_pauses_known_target_but_not_similar_name(svc):
    pid = project(svc)
    svc.record_followup(pid, FollowupInput(summary="客户沟通", next_action="回访", due_date="2026-11-01"))
    event = svc.request_suppression(
        project_id=pid,
        evidence="请不要再联系",
        source="用户录入",
        occurred_at="2026-10-30T10:00:00+08:00",
        request_id="refusal-1",
    )
    assert event["status"] == "pending"
    assert svc.project_context(pid)["tasks"][0]["status"] == "cancelled"
    with pytest.raises(BusinessError):
        svc.propose_followup(pid, FollowupInput(summary="重试"), "bad")


def test_joint_review_rolls_back_invalid_stage(svc):
    pid = project(svc)
    oid = svc.opportunities(pid)[0]["id"]
    suggestion = svc.propose_update(
        oid, {"summary": "客户咨询", "stage": "采购", "next_action": "回访", "due_date": "2026-11-01"}, "joint-1"
    )
    with pytest.raises(BusinessError):
        svc.review_update(suggestion["id"], True, version=1)
    assert svc.opportunity_context(oid)["followups"] == []
    assert svc.opportunity_context(oid)["stage"] == "待核实"


def test_notifications_once_and_done_no_repeat(svc):
    pid = project(svc)
    svc.record_followup(pid, FollowupInput(summary="沟通", next_action="回访", due_date="2026-11-01"))
    before = datetime(2026, 11, 1, 8, 59, tzinfo=ZoneInfo("Asia/Shanghai"))
    after = datetime(2026, 11, 1, 9, 1, tzinfo=ZoneInfo("Asia/Shanghai"))
    svc.check_reminders(before)
    assert svc.notifications() == []
    svc.check_reminders(after)
    svc.check_reminders(after)
    assert len(svc.notifications()) == 1
    svc.complete_task(svc.project_context(pid)["tasks"][0]["id"])
    svc.check_reminders(datetime(2026, 11, 2, 10, tzinfo=ZoneInfo("Asia/Shanghai")))
    assert len(svc.notifications()) == 1
