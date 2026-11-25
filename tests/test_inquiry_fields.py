import re

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from jxd_leads.errors import BusinessError
from jxd_leads.web import create_app


def inquiry():
    return {
        "platform": "抖音",
        "account_id": "owner-account",
        "message_id": "synthetic-1",
        "body": "成都停车场想了解灯具替换方案",
        "occurred_at": "2026-11-15T10:00:00+08:00",
    }


def test_inquiry_fields_need_owner_review_and_do_not_become_approved_drafts(svc):
    iid = svc.receive_inquiry(inquiry(), "incoming-1")["id"]
    fields = {"region": "成都", "scene": "停车场", "demand": "了解灯具替换方案"}
    proposal = svc.propose_inquiry_fields(iid, fields, "客户原话提到成都停车场及替换方案", "fields-1")
    assert proposal["status"] == "pending"
    assert svc.propose_inquiry_fields(iid, fields, "客户原话提到成都停车场及替换方案", "fields-1")["id"] == proposal["id"]
    before = svc.inquiry_context(iid)
    assert before["region"] is None and before["scene"] is None
    assert before["approved_drafts"] == []

    svc.review_update(
        proposal["id"],
        True,
        edited={"fields": {"region": "成都武侯区", "scene": ""}},
    )
    after = svc.inquiry_context(iid)
    assert after["region"] == "成都武侯区"
    assert after["scene"] is None
    assert after["demand"] is None
    assert after["version"] == before["version"] + 1
    assert after["approved_drafts"] == []


def test_inquiry_fields_reject_invalid_input_and_conflicting_request_id(svc):
    iid = svc.receive_inquiry(inquiry(), "incoming-2")["id"]
    with pytest.raises(ValidationError):
        svc.propose_inquiry_fields(iid, {"status": "done"}, "客户原话", "bad-status")
    with pytest.raises(ValidationError):
        svc.propose_inquiry_fields(iid, {}, "客户原话", "empty-fields")
    first = svc.propose_inquiry_fields(iid, {"region": "成都"}, "客户原话提到成都", "fields-2")
    with pytest.raises(BusinessError):
        svc.review_update(first["id"], True, edited={"fields": None})
    with pytest.raises(BusinessError) as error:
        svc.propose_inquiry_fields(iid, {"region": "重庆"}, "客户原话提到重庆", "fields-2")
    assert error.value.code == "IDEMPOTENCY_CONFLICT"
    assert svc.review_update(first["id"], False)["status"] == "rejected"
    assert svc.inquiry_context(iid)["region"] is None


def test_inquiry_fields_stale_or_suppressed_suggestion_cannot_be_confirmed(svc):
    iid = svc.receive_inquiry(inquiry(), "incoming-3")["id"]
    stale = svc.propose_inquiry_fields(iid, {"region": "成都"}, "客户原话提到成都", "fields-3")
    svc.update_inquiry(iid, 1, {"region": "乐山"})
    with pytest.raises(BusinessError) as error:
        svc.review_update(stale["id"], True)
    assert error.value.code == "VERSION_CONFLICT"
    assert svc.inquiry_context(iid)["region"] == "乐山"

    current = svc.propose_inquiry_fields(iid, {"scene": "停车场"}, "客户原话提到停车场", "fields-4")
    svc.request_suppression("请不要联系", "客户消息", "2026-11-15T10:05:00+08:00", "refusal-1", inquiry_id=iid)
    assert svc.review_update(current["id"], True)["status"] == "rejected"
    assert svc.inquiry_context(iid)["scene"] is None


def test_inquiry_fields_can_be_reviewed_in_owner_page(svc, tmp_path):
    iid = svc.receive_inquiry(inquiry(), "incoming-4")["id"]
    proposal = svc.propose_inquiry_fields(iid, {"region": "成都"}, "客户原话提到成都", "fields-5")
    with TestClient(create_app(svc, tmp_path / "browser", testing=True)) as client:
        html = client.get("/inbox/" + iid).text
        assert "客户原话提到成都" in html
        assert "咨询字段建议" in html
        csrf = re.search('name="csrf-token" content="([^"]+)"', html)[1]
        response = client.post(
            "/actions/suggestion_review",
            data={
                "csrf": csrf,
                "operation_id": "review-fields-1",
                "id": proposal["id"],
                "kind": "inquiry_fields",
                "decision": "confirm",
                "region": "成都高新区",
                "evidence": "本人对照原话核实",
            },
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200
        assert svc.inquiry_context(iid)["region"] == "成都高新区"


def test_confirmed_inquiry_field_does_not_expose_phone_number(svc):
    iid = svc.receive_inquiry(inquiry(), "incoming-5")["id"]
    proposal = svc.propose_inquiry_fields(
        iid, {"demand": "请联系 13800001111 讨论灯具"}, "合成测试中的号码", "fields-6"
    )
    svc.review_update(proposal["id"], True)
    assert "13800001111" not in svc.inquiry_context(iid)["demand"]
