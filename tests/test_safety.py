import csv
import io
import json
import re
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select
from test_core import candidate

from jxd_leads.backup import backup_database, restore_database
from jxd_leads.db import Database
from jxd_leads.imports import preview_import, safe_csv
from jxd_leads.models import Audit
from jxd_leads.schemas import CandidateInput, ContactInput, FollowupInput, OfferInput, RequirementsInput
from jxd_leads.service import BusinessError, Service
from jxd_leads.web import create_app


def project(svc):
    r = svc.submit_candidates(None, [candidate()], actor="owner")
    return svc.review_candidate(r["items"][0]["id"], "accept")["project_id"]


def test_contact_shared_and_refusal_survives_linking(svc):
    pid = project(svc)
    r = svc.submit_candidates(
        None, [candidate().model_copy(update={"project": "第二车库", "address": "测试路二号"})], actor="owner"
    )
    pid2 = svc.review_candidate(r["items"][0]["id"], "accept")["project_id"]
    data = ContactInput(name="测试甲", channel="13800000000", role="采购")
    c = svc.add_contact(pid, data)
    assert svc.add_contact(pid2, data)["id"] == c["id"]
    svc.record_followup(pid2, FollowupInput(summary="合成测试", next_action="回访", due_date="2026-11-01"))
    svc.suppress_contact(c["id"], "明确拒绝")
    assert svc.add_contact(pid2, data)["blocked"]
    assert all(x["status"] == "cancelled" for x in svc.project_context(pid2)["tasks"])
    with pytest.raises(BusinessError):
        svc.record_followup(pid2, FollowupInput(summary="再次联系"))
    assert "13800000000" not in json.dumps(svc.project_context(pid), ensure_ascii=False)
    assert b"13800000000" not in svc.db.path.read_bytes()


def test_agent_cannot_supply_confirmation_fields(svc):
    with pytest.raises(ValidationError):
        CandidateInput(**dict(candidate().model_dump(), confirmed=True))
    with pytest.raises(ValidationError):
        FollowupInput(summary="x", stage="采购")
    pid = project(svc)
    with pytest.raises(BusinessError):
        svc.update_requirements(pid, RequirementsInput(version=1, confirmed=True), actor="agent")
    with pytest.raises(BusinessError):
        svc.set_stage(pid, "采购")
    svc.update_requirements(
        pid, RequirementsInput(version=1, role="采购", authority="本人有采购权", demand="补货", confirmed=True)
    )
    with pytest.raises(BusinessError):
        svc.update_requirements(pid, RequirementsInput(version=1))
    svc.set_stage(pid, "确认需求")
    offer = svc.add_offer(pid, OfferInput(kind="试样", product="合成测试型号", quantity=2, due_date="2026-11-01"))
    svc.update_offer(offer["id"], "已反馈", "测试反馈")
    assert svc.project_context(pid)["offers"][0]["status"] == "已反馈"


def test_contact_rejected_for_suppressed_and_merged_projects(svc):
    pid = project(svc)
    other = svc.submit_candidates(
        None, [candidate().model_copy(update={"project": "另一项目", "address": "测试路9号"})], actor="owner"
    )["items"][0]
    target = svc.review_candidate(other["id"], "accept")["project_id"]
    data = ContactInput(name="测试乙", channel="13900000000", role="采购")
    svc.suppress_project(target, "明确拒绝联系")
    with pytest.raises(BusinessError) as suppressed:
        svc.add_contact(target, data)
    assert suppressed.value.code == "SUPPRESSED"
    svc.merge_projects(pid, target, "同一公司重复项目")
    with pytest.raises(BusinessError) as merged:
        svc.add_contact(pid, data)
    assert merged.value.code == "VERSION_CONFLICT"


def test_offer_terminal_closes_todo_and_version_lock(svc):
    pid = project(svc)
    svc.update_requirements(
        pid,
        RequirementsInput(version=1, role="采购", authority="本人有采购权", demand="补货", confirmed=True),
        actor="owner",
    )
    svc.set_stage(pid, "确认需求")
    offer = svc.add_offer(pid, OfferInput(kind="报价", product="合成型号", quantity=1, due_date="2026-12-01"))
    oid = offer["opportunity_id"]
    version = svc.opportunity_context(oid)["version"]
    with pytest.raises(BusinessError) as stale:
        svc.update_offer(offer["id"], "已采购", "", expected_version=version + 9)
    assert stale.value.code == "VERSION_CONFLICT"
    assert svc.project_context(pid)["offers"][0]["status"] == "待确认"
    svc.update_offer(offer["id"], "已采购", "客户确认", expected_version=version)
    context = svc.opportunity_context(oid)
    assert all(t["status"] != "open" for t in context["tasks"])
    assert svc.project_context(pid)["offers"][0]["status"] == "已采购"


def test_concurrent_retry_and_conflicting_request_id(svc):
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: svc.submit_candidates(None, [candidate()], actor="agent"), range(2)))
    assert sum(r["created"] for r in results) == 1
    pid = project(svc)
    svc.propose_followup(pid, FollowupInput(summary="A"), "req-1")
    with pytest.raises(BusinessError):
        svc.propose_followup(pid, FollowupInput(summary="B"), "req-1")


def test_safe_output_never_redacts_internal_ids_as_phone_numbers(svc):
    synthetic_id = "13812345678"
    result = svc.safe_output(
        {
            "id": synthetic_id,
            "inquiry_id": synthetic_id,
            "identity_key": synthetic_id,
            "payload_hash": synthetic_id,
            "items": [{"contact_id": synthetic_id, "channel": synthetic_id}],
        }
    )

    assert result["id"] == synthetic_id
    assert result["inquiry_id"] == synthetic_id
    assert result["identity_key"] == synthetic_id
    assert result["payload_hash"] == synthetic_id
    assert result["items"][0]["contact_id"] == synthetic_id
    assert result["items"][0]["channel"] == "[手机号已隐藏]"


def test_safe_output_redacts_contact_name_landline_and_variant_numbers(svc):
    pid = project(svc)
    svc.add_contact(pid, ContactInput(name="张小明", channel="028-88888888", role="采购"))
    source = {
        "name": "张小明",
        "summary": "张小明说座机 028-8888 8888，手机 138 0000 0000 | 备用 (028) 6666 6666",
        "source_url": "https://example.org/tender/12345678",
        "due_date": "2026-11-23",
        "created_at": "2026-11-23T10:30:00+08:00",
    }

    result = svc.safe_output(source)

    assert result["name"] == "[联系方式已隐藏]"
    assert "张小明" not in result["summary"]
    assert not re.search(r"\d{7,}", re.sub(r"\D", "", result["summary"]))
    assert result["source_url"] == source["source_url"]
    assert result["due_date"] == "2026-11-23"
    assert result["created_at"] == source["created_at"]


def test_live_wal_backup_and_isolated_restore(svc, tmp_path):
    pid = project(svc)
    svc.add_contact(pid, ContactInput(name="测试乙", channel="13900000000"))
    svc.record_followup(pid, FollowupInput(summary="已提交记录"))
    with sqlite3.connect(svc.db.path) as pending:
        pending.execute("BEGIN IMMEDIATE")
        pending.execute("INSERT INTO settings(key,value) VALUES ('uncommitted','not-visible')")
        backup = backup_database(svc.db.path, tmp_path / "backups")
        pending.rollback()
    dest = restore_database(backup, tmp_path / "recovery" / "leads.db", svc.vault)
    assert not Path(str(backup) + "-wal").exists()
    assert not Path(str(backup) + "-shm").exists()
    assert not Path(str(dest) + "-wal").exists()
    assert not Path(str(dest) + "-shm").exists()
    restored = Service(Database(dest), svc.vault)
    assert restored.project_context(pid)["followups"][0]["summary"] == "已提交记录"
    with sqlite3.connect(dest) as c:
        assert not c.execute("SELECT * FROM settings WHERE key='uncommitted'").fetchall()
    with pytest.raises(ValueError):
        restore_database(backup, svc.db.path, svc.vault)
    restored.record_followup(pid, FollowupInput(summary="恢复后可写"))


def test_isolated_restore_preserves_evidence_approval_and_suppression(svc, tmp_path):
    candidate_row = svc.submit_candidates(None, [candidate()], actor="owner")["items"][0]
    pid = svc.review_candidate(candidate_row["id"], "accept")["project_id"]
    contact = svc.add_contact(pid, ContactInput(name="恢复验证联系人", channel="13900000001"))
    event = svc.request_suppression(
        "请不要再联系",
        "本人录入合成证据",
        "2026-11-21T10:00:00+08:00",
        "restore-suppression",
        project_id=pid,
        actor="owner",
        origin="web",
    )
    svc.review_suppression(event["id"], "本人核对合成项目后确认停联")

    second = svc.submit_candidates(
        None,
        [candidate().model_copy(update={"project": "恢复审批验证项目", "address": "测试路三号"})],
        actor="owner",
    )["items"][0]
    second_pid = svc.review_candidate(second["id"], "accept")["project_id"]
    proposal = svc.propose_followup(second_pid, FollowupInput(summary="待恢复审批建议"), "restore-proposal")

    backup = backup_database(svc.db.path, tmp_path / "backup-source", vault=svc.vault)
    dest = restore_database(backup, tmp_path / "recovery" / "leads.db", svc.vault)
    restored = Service(Database(dest), svc.vault)

    restored_candidate = restored.candidate_context(candidate_row["id"])
    assert restored_candidate["evidence"] == candidate_row["evidence"]
    assert restored_candidate["status"] == "suppressed"
    assert restored.project_context(pid)["stage"] == "停止联系"
    # Project suppression blocks follow-up through the project stage; it does not
    # silently turn every historical contact into an individually blocked contact.
    assert restored.project_context(pid)["contacts"][0]["blocked"] is False
    assert restored.project_context(pid)["contacts"][0]["id"] == contact["id"]
    saved_event = next(item for item in restored.suppression_events() if item["id"] == event["id"])
    assert saved_event["status"] == "confirmed"
    assert saved_event["evidence"] == "请不要再联系"
    assert any(
        item["id"] == proposal["id"] and item["project_id"] == second_pid
        for item in restored.pending_followup_proposals()
    )
    with pytest.raises(BusinessError):
        restored.record_followup(pid, FollowupInput(summary="恢复后不得绕过停联"))
    svc.project_context(pid)


def test_import_preview_and_csv_injection():
    data = "公司,项目,地区,来源类型,证据\n测试物业,车库,成都,已有关系,测试介绍\n错误行,,,,\n".encode()
    result = preview_import(data, "test.csv")
    assert len(result["items"]) == 1 and result["errors"][0]["row"] == 3
    exported = safe_csv([['=HYPERLINK("bad")', " normal"]])
    assert next(csv.reader(io.StringIO(exported.lstrip("\ufeff"))))[0].startswith("'")


def test_csv_export_requires_post_csrf_and_audits(svc):
    project(svc)
    with TestClient(create_app(svc, testing=True)) as client:
        home = client.get("/")
        csrf = re.search('name="csrf-token" content="([^"]+)"', home.text).group(1)
        assert client.get("/exports/projects.csv").status_code == 405
        denied = client.post("/exports/projects.csv", data={"csrf": "wrong"})
        assert "会话已失效" in denied.text
        exported = client.post("/exports/projects.csv", data={"csrf": csrf})
        assert exported.status_code == 200
        assert exported.headers["content-type"].startswith("text/csv")
        assert "公司,项目,地区,地址,阶段" in exported.text
        with svc.db.read_session() as s:
            audit = s.scalar(select(Audit).where(Audit.action == "export.csv"))
        assert audit and audit.entity_id == "projects" and audit.detail.endswith("行")


def test_web_pages_and_csrf(svc, tmp_path):
    app = create_app(svc, tmp_path / "backups", testing=True)
    with TestClient(app) as client:
        assert client.get("/api/v1/overview").status_code == 401
        home = client.get("/")
        assert home.status_code == 200
        csrf = re.search('name="csrf-token" content="([^"]+)"', home.text).group(1)
        assert client.post("/api/v1/research-tasks", json={}).status_code == 403
        assert client.post(
            "/api/v1/research-tasks", json={},
            headers={"X-CSRF-Token": csrf, "Idempotency-Key": "missing-scope"},
        ).status_code == 422
        assert (
            client.post(
                "/api/v1/research-tasks",
                json={"region": "合成地区", "scene": "合成设备更新"},
                headers={"X-CSRF-Token": csrf, "Idempotency-Key": "api-test"},
            ).status_code
            == 200
        )
        assert client.get("/", headers={"host": "attacker.invalid"}).status_code == 400
        assert client.get("/api/v1/overview", headers={"origin": "http://evil.invalid"}).status_code == 403
        assert client.get("/", headers={"sec-fetch-site": "cross-site"}).status_code == 403
        pid = project(svc)
        for path in [
            "/research",
            "/candidates",
            "/projects",
            f"/projects/{pid}",
            "/insights",
            "/settings",
            "/import",
        ]:
            response = client.get(path)
            assert response.status_code == 200, path
        assert client.get("/exports/projects.csv").status_code == 405
        research_page = client.get("/research").text
        assert "复制获客任务指令" in research_page
        assert "复制给 WorkBuddy" not in research_page
        assert client.post("/actions/candidate", data={"csrf": csrf, "company": "x"}).status_code == 200
        assert "操作未保存" in client.post("/actions/candidate", data={"csrf": csrf, "company": "x"}).text
        assert "frame-ancestors 'none'" in home.headers["content-security-policy"]


def test_web_escapes_source_content(svc, tmp_path):
    malicious = candidate().model_copy(update={"evidence": "<script>alert(1)</script>"})
    svc.submit_candidates(None, [malicious], actor="agent")
    with TestClient(create_app(svc, tmp_path / "b", testing=True)) as c:
        html = c.get("/candidates").text
        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;" in html


def test_country_code_blocking_and_late_link(svc):
    first = project(svc)
    contact = svc.add_contact(first, ContactInput(name="测试", channel="13800000000"))
    svc.suppress_contact(contact["id"], "拒绝")
    row = svc.submit_candidates(
        None, [candidate().model_copy(update={"project": "后关联车库", "region": "德阳"})], actor="owner"
    )
    second = svc.review_candidate(row["items"][0]["id"], "accept")["project_id"]
    svc.record_followup(second, FollowupInput(summary="测试", next_action="回访", due_date="2026-11-01"))
    svc.propose_followup(second, FollowupInput(summary="提议"), "late-proposal")
    linked = svc.add_contact(second, ContactInput(name="测试", channel="+86 13800000000"))
    assert linked["id"] == contact["id"] and linked["blocked"]
    ctx = svc.project_context(second)
    assert ctx["tasks"][0]["status"] == "cancelled"
    assert ctx["proposals"][0]["status"] == "rejected"
    assert ctx["company_id"] == svc.project_context(first)["company_id"]


def test_phone_redaction_variants():
    from jxd_leads.security import redact

    for value in ["13800000000", "+8613800000000", "+86 138 0000 0000", "0086-138-0000-0000"]:
        assert "0000" not in redact(value)
    for value in ["028-88888888", "(028) 8888 8888", "028.8888.8888", "400 123 4567", "138 000 0000"]:
        assert not re.search(r"\d{7,}", re.sub(r"\D", "", redact(value)))
    assert redact("2026-11-23") == "2026-11-23"
    assert redact("2026-11-23T10:30:00+08:00") == "2026-11-23T10:30:00+08:00"
    assert redact("https://example.org/?phone=13800000000") == "https://example.org/?phone=[手机号已隐藏]"


def test_filtered_htmx_review_returns_navigation(svc, tmp_path):
    row = svc.submit_candidates(None, [candidate()], actor="owner")["items"][0]
    with TestClient(create_app(svc, tmp_path / "b", testing=True)) as client:
        home = client.get("/")
        csrf = re.search('name="csrf-token" content="([^"]+)"', home.text).group(1)
        fragment = client.get("/candidates?q=车库", headers={"HX-Request": "true"})
        assert "接受并建档" in fragment.text
        response = client.post(
            "/actions/review",
            data={"csrf": csrf, "operation_id": "review-test", "id": row["id"], "decision": "accept"},
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200
        assert response.headers["HX-Location"].startswith("/projects/")
        page = client.get(response.headers["HX-Location"], headers={"HX-Request": "true"})
        assert "需求确认卡" in page.text
