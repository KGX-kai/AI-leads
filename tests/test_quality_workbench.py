import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from jxd_leads.errors import BusinessError
from jxd_leads.schemas import CandidateInput, FollowupInput, QualificationInput, ResearchInput
from jxd_leads.web import create_app


def candidate(**changes):
    data = {
        "company": "成都示例物业有限公司",
        "project": "示例停车场照明维护",
        "region": "成都市",
        "source_url": "https://example.org/project",
        "evidence": "公开公告提到停车场照明维护，具体采购需求待核实",
    }
    data.update(changes)
    return CandidateInput(**data)


def test_watch_due_returns_to_queue_without_changing_identity_or_suppression(svc):
    item = svc.submit_candidates(None, [candidate()], actor="owner")["items"][0]
    cid = item["id"]
    due = str(date.today())
    watched = svc.review_candidate(cid, "watch", reason="项目时间未明确", next_review_at=due, reason_code="timing")
    assert watched["id"] == cid
    assert watched["status"] == "watch"
    assert watched["next_review_at"] == due
    assert cid in {row["id"] for row in svc.today_queue(kind="watch")["items"]}
    resumed = svc.review_candidate(cid, "resume", reason="重新核实时间")
    assert resumed["id"] == cid
    assert resumed["status"] == "pending"
    assert resumed["next_review_at"] is None
    assert cid in {row["id"] for row in svc.today_queue(kind="candidate")["items"]}


def test_watch_is_owner_only_and_rejected_candidate_stays_blocked(svc):
    cid = svc.submit_candidates(None, [candidate()], actor="owner")["items"][0]["id"]
    with pytest.raises(BusinessError):
        svc.review_candidate(cid, "watch", actor="agent", reason="待观察", next_review_at=str(date.today()))
    svc.review_candidate(cid, "reject", reason="不在服务范围")
    with pytest.raises(BusinessError):
        svc.review_candidate(cid, "watch", reason="尝试恢复", next_review_at=str(date.today()))


def test_future_watch_not_due_and_candidate_metadata_roundtrip(svc):
    item = svc.submit_candidates(
        None,
        [candidate(org_phone="028-12345678", unknowns=["采购角色", "预计时间"])],
        actor="owner",
    )["items"][0]
    cid = item["id"]
    assert item["org_phone"] == "028-12345678"
    assert item["unknowns"] == ["采购角色", "预计时间"]
    svc.review_candidate(cid, "watch", reason="等待公开更新", next_review_at=str(date.today() + timedelta(days=5)))
    assert cid not in {row["id"] for row in svc.today_queue(kind="watch")["items"]}


def test_evidence_claims_keep_separate_sources(svc):
    cid = svc.submit_candidates(None, [candidate()], actor="owner")["items"][0]["id"]
    svc.verify_source(
        cid, "业主官网", "", "项目位置", "在管物业", "已核对", "核对照明场景",
        source_url="https://example.org/owner", claim="停车场位置",
    )
    svc.verify_source(
        cid, "采购平台", "", "未知", "未知", "存在冲突", "采购时间冲突",
        source_url="https://example.org/tender", claim="采购时间",
    )
    sources = svc.candidate_context(cid)["verification"]
    assert {x["source_url"] for x in sources} >= {"https://example.org/owner", "https://example.org/tender"}
    assert len({x["id"] for x in sources}) == len(sources)


def test_new_source_does_not_auto_merge_or_reactivate_excluded_project(svc):
    first = svc.submit_candidates(None, [candidate()], actor="owner")["items"][0]
    retry = svc.submit_candidates(None, [candidate()], actor="owner")
    assert retry["duplicates"] == 1 and retry["items"][0]["id"] == first["id"]
    second = svc.submit_candidates(
        None, [candidate(source_url="https://example.org/another")], actor="owner"
    )["items"][0]
    assert second["id"] != first["id"] and second["project_id"] is None
    svc.review_candidate(first["id"], "reject", reason="来源核对后排除")
    assert svc.list_candidates(status="suppressed")["total"] == 1
    third = svc.submit_candidates(
        None, [candidate(source_url="https://example.org/third")], actor="owner"
    )["items"][0]
    assert third["status"] == "suppressed"


def test_quality_metrics_share_window_and_show_unknown_denominator(svc):
    empty = svc.dashboard_snapshot()["quality"]
    assert empty["source_verified"]["rate"] is None
    assert empty["human_accepted"]["rate"] is None
    cid = svc.submit_candidates(None, [candidate()], actor="owner")["items"][0]["id"]
    svc.verify_source(cid, "业主官网", "", "项目位置", "在管物业", "已核对", "现场核对",
                      source_url="https://example.org/owner", claim="项目位置")
    pending = svc.dashboard_snapshot()["quality"]
    assert pending["source_verified"] == {"numerator": 1, "denominator": 1, "rate": 100.0}
    assert pending["human_accepted"]["rate"] is None
    svc.verify_source(cid, "另一公开来源", "", "未知", "未知", "存在冲突", "项目时间与原来源不一致",
                      source_url="https://example.org/conflict", claim="项目时间")
    assert svc.dashboard_snapshot()["quality"]["source_verified"]["rate"] == 0.0
    svc.review_candidate(cid, "accept")
    accepted = svc.dashboard_snapshot()["quality"]
    assert accepted["human_accepted"] == {"numerator": 1, "denominator": 1, "rate": 100.0}
    assert accepted["demand_confirmed"] == {"numerator": 0, "denominator": 1, "rate": 0.0}


def test_confirmed_opportunity_counts_as_confirmed_demand(svc):
    cid = svc.submit_candidates(None, [candidate()], actor="owner")["items"][0]["id"]
    pid = svc.review_candidate(cid, "accept")["project_id"]
    opportunity = svc.opportunities(pid)[0]
    svc.update_opportunity(
        opportunity["id"], opportunity["version"],
        requirements={
            "role": "合成项目负责人", "authority": "合成采购负责人", "demand": "合成需求",
            "confirmed": True,
        },
    )
    data = svc.dashboard_snapshot()
    assert data["quality"]["demand_confirmed"] == {"numerator": 1, "denominator": 1, "rate": 100.0}
    assert data["funnel"][2]["value"] == 1
    assert data["funnel"][2]["rate"] == 100.0


def test_conflict_cleared_for_same_source_and_claim_restores_verification(svc):
    cid = svc.submit_candidates(None, [candidate()], actor="owner")["items"][0]["id"]
    svc.verify_source(cid, "甲方", "", "项目位置", "未知", "已核对", "位置已核对",
                      source_url="https://example.org/location", claim="项目位置")
    svc.verify_source(cid, "乙方", "", "未知", "未知", "存在冲突", "时间冲突",
                      source_url="https://example.org/timing", claim="项目时间")
    svc.verify_source(cid, "丙方", "", "未知", "未知", "已核对", "另一事项已核对",
                      source_url="https://example.org/other", claim="项目主体")
    assert svc.dashboard_snapshot()["quality"]["source_verified"]["rate"] == 0.0
    svc.verify_source(cid, "乙方", "", "未知", "历史公告", "已核对", "对照原文核清时间",
                      source_url="https://example.org/timing", claim="项目时间")
    assert svc.dashboard_snapshot()["quality"]["source_verified"] == {
        "numerator": 1, "denominator": 1, "rate": 100.0,
    }


def test_research_scope_must_be_explicit_and_brief_uses_selected_scope(svc):
    with pytest.raises(ValidationError):
        ResearchInput()
    task = svc.create_research(ResearchInput(region="试验地区", scene="合成设备更新", target=1))
    brief = svc.research_task(task["id"])["brief"]
    assert "试验地区" in brief and "合成设备更新" in brief
    assert "物业" not in brief and "照明" not in brief
    assert "先调用 get_capabilities" in brief
    assert "schema_version" in brief
    assert "人工审核" in brief
    assert "scripts/agent-call.py" not in brief


def test_research_page_uses_neutral_copy_instruction_and_codex_handoff(svc):
    svc.create_research(ResearchInput(region="试验地区", scene="合成设备更新", target=1))
    with TestClient(create_app(svc, testing=True)) as client:
        html = client.get("/research").text
    assert "由你发起，由 Codex 按任务检索" in html
    assert "复制获客任务指令" in html
    assert "复制给 WorkBuddy" not in html
    assert "先调用 get_capabilities" in html
    assert "候选和建议仍需本人确认" in html


def test_agent_candidate_is_reviewed_through_owner_web(svc, tmp_path):
    task = svc.create_research(ResearchInput(region="试验地区", scene="合成设备更新", target=1))
    item = svc.submit_candidates(task["id"], [candidate()], actor="agent")["items"][0]
    assert item["status"] == "pending"
    with TestClient(create_app(svc, tmp_path / "review-browser", testing=True)) as client:
        html = client.get("/candidates").text
        assert item["id"] in html
        assert "接受并建档" in html
        csrf = re.search('name="csrf-token" content="([^"]+)"', html)[1]
        response = client.post(
            "/actions/review",
            data={
                "csrf": csrf,
                "operation_id": "review-candidate-web-1",
                "id": item["id"],
                "decision": "accept",
            },
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200
        accepted = next(row for row in svc.candidates() if row["id"] == item["id"])
        assert accepted["status"] == "accepted"
        assert accepted["project_id"]
        assert response.headers["HX-Location"] == f"/projects/{accepted['project_id']}"

        proposal = svc.propose_followup(
            accepted["project_id"],
            FollowupInput(summary="A1 合成跟进建议"),
            "review-proposal-web-1",
        )
        project_html = client.get(f"/projects/{accepted['project_id']}").text
        assert "AI 建议 · 待审" in project_html
        assert "A1 合成跟进建议" in project_html
        csrf = re.search('name="csrf-token" content="([^"]+)"', project_html)[1]
        reviewed = client.post(
            "/actions/proposal",
            data={
                "csrf": csrf,
                "operation_id": "accept-proposal-web-1",
                "id": proposal["id"],
                "decision": "confirm",
            },
            headers={"HX-Request": "true"},
        )
    assert reviewed.status_code == 200
    project = svc.project_context(accepted["project_id"])
    assert len(project["followups"]) == 1
    assert project["stage"] == "待核实"


def test_public_tender_brief_uses_seven_calendar_dates_and_original_publish_date(svc):
    task = svc.create_research(ResearchInput(region="合成地区", scene="合成项目采购", target=1))
    today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    start = today - timedelta(days=6)
    brief = svc.research_task(task["id"])["brief"]
    assert f"{start} 至 {today}" in brief
    assert "公告原文发布日期" in brief
    assert "发现日期不能代替发布日期" in brief
    assert "日期不明或超出窗口" in brief
    assert "非招标来源" in brief


def test_a4_candidate_context_exposes_latest_claim_and_folded_history(svc):
    cid = svc.submit_candidates(
        None,
        [candidate(
            reason="合成 AI 匹配建议",
            demand_evidence="尚待核实的需求证据",
            unknowns=["采购角色", "预计时间"],
        )],
        actor="owner",
    )["items"][0]["id"]
    for index in range(21):
        svc.verify_source(
            cid,
            "公开来源",
            "",
            "项目位置",
            "未知",
            "已核对",
            f"第 {index + 1} 次核对位置",
            source_url="https://example.org/project?utm_source=test",
            claim="项目位置",
        )
    svc.verify_source(
        cid,
        "另一公开来源",
        "",
        "未知",
        "未知",
        "存在冲突",
        "采购时间与原来源不一致",
        source_url="https://example.org/timing",
        claim="采购时间",
    )

    context = svc.candidate_context(cid)
    latest = {
        (item["source_url"], item["claim"]): item
        for item in context["verification_latest"]
    }
    assert latest[("https://example.org/project?utm_source=test", "项目位置")]["history_count"] == 21
    assert context["verification_summary"] == {
        "status": "conflict",
        "label": "存在未清冲突",
        "claim_count": 3,
        "source_count": 2,
        "conflict_count": 1,
        "verified_count": 1,
    }
    assert context["verification_history_count"] == 23
    assert len(context["verification"]) == 20


def test_a4_verify_source_requires_a_specific_claim(svc):
    cid = svc.submit_candidates(None, [candidate()], actor="owner")["items"][0]["id"]
    with pytest.raises(BusinessError, match="事实主张"):
        svc.verify_source(cid, "公开来源", "", "未知", "未知", "已核对", "未说明具体主张", claim="  ")


@pytest.mark.parametrize("latest_status", ["已核对", "存在冲突"])
def test_source_status_tied_timestamp_matches_card_and_metrics(svc, latest_status):
    from jxd_leads.models import SourceEvidence

    cid = svc.submit_candidates(None, [candidate()], actor="owner")["items"][0]["id"]
    previous_status = "存在冲突" if latest_status == "已核对" else "已核对"
    records = [
        svc.verify_source(
            cid, "合成来源", "", "项目位置", "未知", status, "合成核验",
            source_url="https://example.org/project", claim="项目位置",
        )
        for status in (previous_status, latest_status)
    ]
    tied_at = datetime.now().isoformat()
    with svc.db.session() as session:
        for index, record in enumerate(records):
            evidence = session.get(SourceEvidence, record["id"])
            evidence.id = f"tied-{index}"
            evidence.created_at = tied_at
    card = svc.candidate_context(cid)
    verified = svc.dashboard_snapshot()["quality"]["source_verified"]["numerator"]
    assert card["verification_latest"][0]["status"] == latest_status
    assert card["verification_summary"]["conflict_count"] == int(latest_status == "存在冲突")
    assert verified == int(latest_status == "已核对")


def test_a4_confirmed_qualification_moves_matching_unknowns_out_of_current_list(svc):
    cid = svc.submit_candidates(
        None,
        [candidate(unknowns=["采购角色", "预计采购时间", "设备数量"])],
        actor="owner",
    )["items"][0]["id"]
    svc.confirm_qualification(
        QualificationInput(
            fit="符合",
            need="有问题但采购未定",
            role="可影响/可引荐",
            timing="未知",
            confidence="原文已核对",
            priority="常规核实",
            evidence="合成核验：角色已确认，时间仍未知。",
        ),
        candidate_id=cid,
    )
    context = svc.candidate_context(cid)
    assert context["resolved_unknowns"] == ["采购角色"]
    assert context["open_unknowns"] == ["预计采购时间", "设备数量"]


def test_a4_candidate_page_layers_evidence_and_reviews_in_place(svc, tmp_path):
    cid = svc.submit_candidates(
        None,
        [candidate(
            reason="合成 AI 匹配建议",
            demand_evidence="尚待核实的需求证据",
            unknowns=["采购角色", "预计时间"],
        )],
        actor="agent",
    )["items"][0]["id"]
    svc.verify_source(
        cid,
        "采购平台",
        "",
        "未知",
        "未知",
        "存在冲突",
        "采购时间与原来源不一致",
        source_url="https://example.org/timing",
        claim="采购时间",
    )
    return_to = "/?kind=candidate"
    with TestClient(create_app(svc, tmp_path / "a4-candidate", testing=True)) as client:
        response = client.get(f"/candidates/{cid}", params={"return_to": return_to})
        assert response.status_code == 200
        html = response.text
        assert "来源证据" in html
        assert "AI 建议 · 待核实" in html
        assert "本人尚未确认" in html
        assert "未知项" in html
        assert "存在未清冲突" in html
        assert "采购时间" in html
        assert "暂缓观察" in html
        assert "接受并建档" in html
        assert 'name="return_to" value="/?kind=candidate"' in html
        csrf = re.search('name="csrf-token" content="([^"]+)"', html)[1]
        reviewed = client.post(
            "/actions/review",
            data={
                "csrf": csrf,
                "operation_id": "a4-candidate-watch",
                "return_to": return_to,
                "id": cid,
                "decision": "watch",
                "reason": "合成证据仍不足",
                "next_review_at": str(date.today()),
                "reason_code": "missing_evidence",
            },
            headers={"HX-Request": "true"},
        )
        assert reviewed.status_code == 200
        assert reviewed.headers["HX-Location"] == return_to
    assert svc.candidate_context(cid)["status"] == "watch"


def test_a4_quality_panel_uses_unknown_instead_of_zero_percent(svc, tmp_path):
    with TestClient(create_app(svc, tmp_path / "a4-quality", testing=True)) as client:
        html = client.get("/insights").text
    assert "近 30 天线索质量" in html
    assert "暂无数据" in html
    assert "0 / 0" in html


def test_a4_quality_window_uses_shanghai_calendar_date(svc, monkeypatch):
    from jxd_leads import service as service_module

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            fixed = datetime(2026, 11, 20, 16, 30, tzinfo=ZoneInfo("UTC"))
            return fixed.astimezone(tz) if tz else fixed

    monkeypatch.setattr(service_module, "datetime", FixedDateTime)
    quality = svc.dashboard_snapshot()["quality"]
    assert quality["window_end"] == "2026-11-21"
    assert quality["window_start"] == "2026-10-23"


def test_a4_dashboard_queue_shows_reason_next_step_and_safe_return(svc, tmp_path):
    cid = svc.submit_candidates(None, [candidate()], actor="owner")["items"][0]["id"]
    with TestClient(create_app(svc, tmp_path / "a4-queue", testing=True)) as client:
        html = client.get("/").text
    assert "排队原因" in html
    assert "下一步" in html
    assert "查看来源证据、冲突和未知项后审核" in html
    assert f"/candidates/{cid}" in html
    assert "return_to=" in html


def test_a4_opportunity_snapshot_connects_last_result_and_next_action(svc, tmp_path):
    cid = svc.submit_candidates(None, [candidate()], actor="owner")["items"][0]["id"]
    pid = svc.review_candidate(cid, "accept")["project_id"]
    opportunity = svc.opportunities(pid)[0]
    svc.record_followup(
        pid,
        FollowupInput(
            summary="合成上次沟通结果",
            result="有效沟通",
            next_action="合成下一动作",
            due_date=date.today() + timedelta(days=1),
        ),
        opportunity["id"],
    )
    with TestClient(create_app(svc, tmp_path / "a4-followup", testing=True)) as client:
        html = client.get(f"/opportunities/{opportunity['id']}").text
    assert "上次结果" in html
    assert "合成上次沟通结果" in html
    assert "当前触发" in html
    assert "下一动作" in html
    assert "合成下一动作" in html


@pytest.mark.parametrize("page", [2, 99])
def test_opportunity_current_summary_stays_latest_on_history_pages(svc, tmp_path, page):
    cid = svc.submit_candidates(None, [candidate()], actor="owner")["items"][0]["id"]
    pid = svc.review_candidate(cid, "accept")["project_id"]
    oid = svc.opportunities(pid)[0]["id"]
    for index in range(11):
        svc.record_followup(
            pid, FollowupInput(summary=f"合成历史沟通第{index}次", result="有效沟通"), oid,
        )
    with TestClient(create_app(svc, tmp_path / "history-summary", testing=True)) as client:
        response = client.get(f"/opportunities/{oid}", params={"n": page})
    assert response.status_code == 200
    snapshot = re.search(r'<section class="panel followup-snapshot">(.*?)</section>', response.text, re.DOTALL)[1]
    assert "合成历史沟通第10次" in snapshot
    assert "尚无沟通记录" not in snapshot
    history = svc.opportunity_context(oid, page=page)
    assert len(history["followups"]) == (1 if page == 2 else 0)


def test_opportunity_next_action_not_hidden_by_completed_task_limit(svc, tmp_path):
    from jxd_leads.models import Todo

    cid = svc.submit_candidates(None, [candidate()], actor="owner")["items"][0]["id"]
    pid = svc.review_candidate(cid, "accept")["project_id"]
    oid = svc.opportunities(pid)[0]["id"]
    with svc.db.session() as session:
        session.add_all([
            Todo(project_id=pid, opportunity_id=oid, action="合成已完成旧动作", due_date="2026-01-01", status="done")
            for _ in range(100)
        ])
        session.add(Todo(project_id=pid, opportunity_id=oid, action="合成当前开放动作", due_date="2026-12-01"))
    with TestClient(create_app(svc, tmp_path / "open-task-summary", testing=True)) as client:
        response = client.get(f"/opportunities/{oid}")
    assert response.status_code == 200
    snapshot = re.search(r'<section class="panel followup-snapshot">(.*?)</section>', response.text, re.DOTALL)[1]
    assert "合成当前开放动作" in snapshot
    assert "待安排" not in snapshot
    assert len(svc.opportunity_context(oid)["tasks"]) == 100


def test_a4_research_page_labels_recent_receipt_without_inventing_history(svc):
    task = svc.create_research(ResearchInput(region="合成地区", scene="合成项目采购", target=1))
    svc.submit_candidates(
        task["id"],
        [],
        actor="agent",
        status="partial",
        note="来源 A 成功；来源 B 超时，未提交候选。",
    )
    with TestClient(create_app(svc, testing=True)) as client:
        html = client.get("/research").text
    assert "最近批次回执" in html
    assert "来源 A 成功；来源 B 超时" in html
    assert "首次和重试计数未单独保存" in html


def test_a4_owner_can_check_reminders_and_see_hit_summary(svc, tmp_path):
    cid = svc.submit_candidates(None, [candidate()], actor="owner")["items"][0]["id"]
    pid = svc.review_candidate(cid, "accept")["project_id"]
    svc.record_followup(
        pid,
        FollowupInput(
            summary="合成到期跟进",
            next_action="合成回访",
            due_date=date.today() - timedelta(days=1),
        ),
    )
    with TestClient(create_app(svc, tmp_path / "a4-reminder", testing=True)) as client:
        home = client.get("/")
        csrf = re.search('name="csrf-token" content="([^"]+)"', home.text)[1]
        response = client.post(
            "/actions/check_reminders",
            data={"csrf": csrf, "operation_id": "a4-reminder-check", "return_to": "/"},
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200
        assert "reminder_due=1" in response.headers["HX-Location"]
        checked = client.get(response.headers["HX-Location"]).text
    assert "提醒检查完成" in checked
    assert "命中 1 项" in checked
