from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from jxd_leads.dashboard_model import SOURCE_TONES
from jxd_leads.schemas import CandidateInput, FollowupInput, ResearchInput
from jxd_leads.service import BusinessError


def candidate(**kw):
    return CandidateInput(
        **dict(
            company="测试物业",
            project="测试车库",
            region="成都",
            address="测试路1号",
            source_url="https://example.org/project",
            evidence="公开页面说明物业运营该项目，采购需求未知。",
            **kw,
        )
    )


def test_candidate_retries_and_human_review(svc):
    task = svc.create_research(ResearchInput(region="合成地区", scene="合成设备更新"))
    one = svc.submit_candidates(task["id"], [candidate()], actor="agent")
    two = svc.submit_candidates(task["id"], [candidate()], actor="agent")
    assert one["created"] == 1 and two["duplicates"] == 1
    cid = one["items"][0]["id"]
    with pytest.raises(BusinessError):
        svc.review_candidate(cid, "accept", actor="agent")
    result = svc.review_candidate(cid, "accept", actor="owner")
    assert result["project_id"]
    assert svc.project_context(result["project_id"])["stage"] == "待核实"
    assert svc.review_candidate(cid, "accept", actor="owner")["project_id"] == result["project_id"]


@pytest.mark.parametrize(
    ("source", "age", "expected"),
    [("公开招标公告", 45, 0), ("公开招标公告", 7, 0), ("公开招标公告", 6, 1),
     ("公开招标公告", 5, 1), ("公开网络", 45, 1)],
)
def test_notice_window_and_source_statistics(svc, source, age, expected):
    today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    task = svc.create_research(ResearchInput(region="合成地区", scene="合成场景"))
    item = candidate(source_type=source, published_at=today - timedelta(days=age), org_phone="028-12345678")
    result = svc.submit_candidates(task["id"], [item], note="本批已核对")
    assert result["created"] == len(svc.candidates()) == expected
    note = svc.research_task(task["id"])["note"]
    assert "本批已核对" in note
    if not expected:
        assert "跳过" in note and "超过六日窗口" in note
        assert result["note"] == note
    else:
        assert result["items"][0]["org_phone"] == item.org_phone
    assert next(row["candidates"] for row in svc.overview()["sources"] if row["source"] == source) == expected
    assert next(row["count"] for row in svc.dashboard_snapshot()["sources"] if row["name"] == source) == expected
    assert SOURCE_TONES["公开招标公告"] == "orange"


def test_same_company_different_projects_and_block_reimport(svc):
    a = candidate()
    b = a.model_copy(update={"project": "另一车库", "address": "测试路2号"})
    r = svc.submit_candidates(None, [a, b], actor="owner")
    p1 = svc.review_candidate(r["items"][0]["id"], "accept", actor="owner")["project_id"]
    p2 = svc.review_candidate(r["items"][1]["id"], "accept", actor="owner")["project_id"]
    assert p1 != p2
    svc.suppress_project(p1, "明确拒绝联系")
    result = svc.submit_candidates(
        None, [a.model_copy(update={"source_url": "https://example.org/other"})], actor="agent"
    )
    assert result["items"][0]["status"] == "suppressed"
    assert svc.project_context(p2)["stage"] != "停止联系"


def test_agent_proposal_needs_owner_and_task_is_atomic(svc):
    r = svc.submit_candidates(None, [candidate()], actor="owner")
    pid = svc.review_candidate(r["items"][0]["id"], "accept", actor="owner")["project_id"]
    draft = svc.propose_followup(
        pid,
        FollowupInput(summary="客户可能需要灯管", next_action="核实采购权限", due_date="2026-11-01"),
        "test-request-1",
    )
    again = svc.propose_followup(
        pid,
        FollowupInput(summary="客户可能需要灯管", next_action="核实采购权限", due_date="2026-11-01"),
        "test-request-1",
    )
    assert draft["id"] == again["id"]
    assert not svc.project_context(pid)["followups"]
    svc.confirm_proposal(draft["id"])
    svc.confirm_proposal(draft["id"])
    context = svc.project_context(pid)
    assert len(context["followups"]) == 1 and len(context["tasks"]) == 1
    svc.suppress_project(pid, "不再联系")
    with pytest.raises(BusinessError):
        svc.propose_followup(pid, FollowupInput(summary="再次联系"), "test-request-2")


def test_research_limit_empty_failure_and_retry(svc):
    task = svc.create_research(ResearchInput(region="合成地区", scene="合成设备更新", target=1))
    svc.submit_candidates(task["id"], [], status="failed", note="来源不可达")
    assert svc.research_task(task["id"])["status"] == "failed"
    svc.submit_candidates(task["id"], [candidate()])
    assert svc.submit_candidates(task["id"], [candidate()])["duplicates"] == 1
    with pytest.raises(BusinessError):
        svc.submit_candidates(task["id"], [candidate().model_copy(update={"project": "超量项目"})])
    assert len(svc.candidates()) == 1


def test_submit_candidates_request_id_idempotency(svc):
    task = svc.create_research(ResearchInput(region="合成地区", scene="合成场景"))
    first = svc.submit_candidates(task["id"], [candidate()], note="首次提交", request_id="batch-1")
    replay = svc.submit_candidates(task["id"], [candidate()], note="首次提交", request_id="batch-1")
    assert replay == first
    assert len(svc.candidates()) == 1
    with pytest.raises(BusinessError) as conflict:
        svc.submit_candidates(task["id"], [candidate()], note="改写备注", request_id="batch-1")
    assert conflict.value.code == "IDEMPOTENCY_CONFLICT"
    saved = svc.research_task(task["id"])
    assert saved["status"] == "completed" and saved["note"] == "首次提交"
