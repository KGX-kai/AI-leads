import json
from datetime import date, timedelta
from html.parser import HTMLParser

from fastapi.testclient import TestClient

from jxd_leads.dashboard_model import build_dashboard_model
from jxd_leads.models import (
    Company,
    Notification,
    Opportunity,
    Project,
    ReviewSuggestion,
    SourceEvidence,
    SuppressionEvent,
    Todo,
)
from jxd_leads.schemas import CandidateInput, FollowupInput, QualificationInput
from jxd_leads.web import create_app


def candidate(index=1, **overrides):
    values = {
        "company": f"合成主体{index}",
        "project": f"合成项目{index}",
        "region": "合成地区",
        "address": f"合成地址{index}",
        "source_url": f"https://example.org/project/{index}",
        "evidence": "公开页面说明项目存在，采购需求仍待人工核实。",
        "discovered_at": date(2026, 11, 20),
    }
    values.update(overrides)
    return CandidateInput(**values)


def dashboard_model(svc):
    return build_dashboard_model(
        svc.dashboard_snapshot(),
        svc.list_candidates(page=1, page_size=20),
        svc.search_projects(page=1, page_size=100),
        svc.dashboard_opportunities(),
        svc.today_queue(page=1, page_size=100, kind="todo"),
        svc.notifications(),
    )


class DashboardBootParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.boot = None
        self.view_count = 0
        self.default_view = ""

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "section" and values.get("data-view"):
            self.view_count += 1
        if values.get("id") == "dashboardRoot":
            self.boot = json.loads(values["data-boot"])
        if values.get("id") == "appShell":
            self.default_view = values.get("data-default-view", "")


def parse_dashboard(response):
    parser = DashboardBootParser()
    parser.feed(response.text)
    return parser


def test_dashboard_snapshot_empty(svc):
    data = svc.dashboard_snapshot()
    assert data["counts"]["candidates"] == 0
    assert data["counts"]["projects"] == 0
    assert data["counts"]["pending"] == 0
    assert len(data["funnel"]) == 5
    assert data["total_conversion"] == 0
    assert all(source["count"] == 0 for source in data["sources"])


def test_dashboard_snapshot_counts_and_public_shape(svc):
    submitted_candidate = CandidateInput(
        company="测试物业",
        project="测试车库",
        region="成都",
        address="测试路 1 号",
        source_url="https://example.org/project",
        evidence="公开页面说明物业运营该项目，采购需求未知。",
    )
    submitted = svc.submit_candidates(None, [submitted_candidate], actor="owner")
    cid = submitted["items"][0]["id"]
    pending = svc.dashboard_snapshot()
    assert pending["counts"]["pending"] == 1
    assert pending["candidates"][0]["project"] == "测试车库"
    assert "source_url" not in pending["candidates"][0]

    pid = svc.review_candidate(cid, "accept", actor="owner")["project_id"]
    svc.record_followup(
        pid,
        FollowupInput(
            summary="确认由工程负责人牵头，下一步补齐数量。",
            result="有效沟通",
            next_action="补齐采购数量",
            due_date=date(2026, 11, 20),
        ),
    )

    data = svc.dashboard_snapshot()
    assert data["counts"]["candidates"] == 1
    assert data["counts"]["pending"] == 0
    assert data["counts"]["projects"] == 1
    assert data["counts"]["communications"] == 1
    assert data["counts"]["tasks"] == 1
    assert data["funnel"][0]["value"] == 1
    assert data["funnel"][1]["value"] == 1
    assert data["projects"][0]["missing"]
    assert "requirements" not in data["projects"][0]


def test_dashboard_model_empty_uses_unknown_rates_and_no_records(svc):
    model = dashboard_model(svc)

    assert model["meta"]["candidateTotal"] == 0
    assert model["meta"]["candidatePages"] == 0
    assert model["meta"]["taskTotal"] == 0
    assert model["leads"] == []
    assert model["projects"] == []
    assert model["opportunities"] == []
    assert model["tasks"] == []
    assert model["reports"] == []
    assert model["notifications"] == []
    assert model["overview"]["totalConversion"] is None
    assert model["overview"]["hasSourceData"] is False
    assert all(item["rate"] is None for item in model["overview"]["funnel"])
    assert all(item["rate"] is None for item in model["overview"]["quality"])


def test_dashboard_model_maps_pagination_real_ids_stages_and_task_targets(svc):
    submitted = svc.submit_candidates(None, [candidate(index) for index in range(25)], actor="owner")
    accepted = submitted["items"][0]
    project_id = svc.review_candidate(accepted["id"], "accept", actor="owner")["project_id"]
    opportunity = svc.dashboard_opportunities()[0]
    svc.update_opportunity(
        opportunity["id"],
        opportunity["version"],
        requirements={"role": "合成负责人", "authority": "有采购权限", "demand": "明确需求", "confirmed": True},
        actor="owner",
    )
    svc.set_stage(project_id, "确认需求", actor="owner")
    opportunity_id = svc.dashboard_opportunities()[0]["id"]

    with svc.db.session() as session:
        for index in range(105):
            session.add(
                Todo(
                    project_id=project_id,
                    opportunity_id=opportunity_id,
                    action=f"合成任务 {index}",
                    due_date=(date(2026, 11, 24) - timedelta(days=1 if index == 0 else -index)).isoformat(),
                )
            )
        session.add(
            Notification(
                event_key="dashboard-contract-notification",
                kind="due",
                title="合成到期提醒",
                count=2,
                target=f"/opportunities/{opportunity_id}",
            )
        )

    first_page = svc.list_candidates(page=1, page_size=20)
    second_page = svc.list_candidates(page=2, page_size=20)
    tasks = svc.today_queue(page=1, page_size=100, kind="todo")
    model = build_dashboard_model(
        svc.dashboard_snapshot(),
        first_page,
        svc.search_projects(page=1, page_size=100),
        svc.dashboard_opportunities(),
        tasks,
        svc.notifications(),
    )

    assert model["meta"]["candidateTotal"] == 25
    assert model["meta"]["candidatePage"] == 1
    assert model["meta"]["candidatePages"] == 2
    assert len(model["leads"]) == 20
    assert len(second_page["items"]) == 5
    assert model["meta"]["projectTotal"] == 1
    assert model["meta"]["taskTotal"] == 105
    assert model["meta"]["taskLoaded"] == 100
    assert model["meta"]["taskTruncated"] is True
    assert len(model["tasks"]) == 100
    assert model["projects"][0]["rawStage"] == "确认需求"
    assert model["projects"][0]["stage"] == "需求确认"
    assert model["projects"][0]["stageIndex"] == 2
    assert model["projects"][0]["href"] == f"/projects/{project_id}"
    assert model["opportunities"][0]["href"] == f"/opportunities/{opportunity_id}"
    assert model["tasks"][0]["href"].startswith("/opportunities/")
    assert model["notifications"][0]["href"] == f"/opportunities/{opportunity_id}"


def test_dashboard_model_stage_groups_and_unsafe_links(svc):
    snapshot = svc.dashboard_snapshot()
    projects = {
        "total": 1,
        "items": [
            {
                "id": "project / 1",
                "name": "合成项目",
                "company": "合成主体",
                "region": "合成地区",
                "stage": "报价或试样",
                "requirements": {"role": "未知"},
            }
        ],
    }
    opportunities = [
        {
            "id": "opp / 1",
            "project_id": "project / 1",
            "project_name": "合成项目",
            "name": "合成机会",
            "stage": "补货跟进",
            "requirements": {"lamps": "100 套"},
        }
    ]
    tasks = {
        "total": 1,
        "items": [{"id": "task", "kind": "todo", "title": "恶意链接", "due": "2026-11-24", "target": "javascript:alert(1)"}],
    }
    notifications = [
        {
            "id": "notice",
            "title": "恶意链接",
            "count": 1,
            "kind": "due",
            "target": "https://evil.example",
            "read_at": None,
        }
    ]
    model = build_dashboard_model(snapshot, {"items": [], "total": 0}, projects, opportunities, tasks, notifications)

    assert model["projects"][0]["stage"] == "报价 / 试样"
    assert model["projects"][0]["stageIndex"] == 3
    assert model["projects"][0]["href"] == "/projects/project%20%2F%201"
    assert model["opportunities"][0]["stageGroup"] == "采购 / 复购"
    assert model["opportunities"][0]["href"] == "/opportunities/opp%20%2F%201"
    assert model["tasks"][0]["href"] == "/opportunities"
    assert model["notifications"][0]["href"] == "/notifications"


def test_dashboard_model_only_allows_registered_internal_hrefs(svc):
    snapshot = svc.dashboard_snapshot()
    tasks = {
        "total": 6,
        "items": [
            {"id": "root", "kind": "todo", "title": "根路径", "due": "2026-11-24", "target": "/"},
            {
                "id": "query",
                "kind": "todo",
                "title": "带查询参数",
                "due": "2026-11-24",
                "target": "/notifications?view=unread#latest",
            },
            {
                "id": "encoded-traversal",
                "kind": "todo",
                "title": "编码路径穿越",
                "due": "2026-11-24",
                "target": "/opportunities/%2e%2e/settings",
            },
            {
                "id": "unknown-root",
                "kind": "todo",
                "title": "未登记路由",
                "due": "2026-11-24",
                "target": "/admin",
            },
            {
                "id": "control",
                "kind": "todo",
                "title": "控制字符",
                "due": "2026-11-24",
                "target": "/projects/\nsettings",
            },
            {
                "id": "protocol-relative",
                "kind": "todo",
                "title": "协议相对链接",
                "due": "2026-11-24",
                "target": "//evil.example/projects",
            },
        ],
    }
    model = build_dashboard_model(
        snapshot,
        {"items": [], "total": 0},
        {"items": [], "total": 0},
        [],
        tasks,
        [],
    )

    hrefs = {item["id"]: item["href"] for item in model["tasks"]}
    assert hrefs["root"] == "/"
    assert hrefs["query"] == "/notifications?view=unread#latest"
    assert hrefs["encoded-traversal"] == "/opportunities"
    assert hrefs["unknown-root"] == "/opportunities"
    assert hrefs["control"] == "/opportunities"
    assert hrefs["protocol-relative"] == "/opportunities"


def test_dashboard_model_maps_candidate_priority_and_keeps_raw_value(svc):
    priorities = ["优先核实", "常规核实", "暂缓", "建议排除", "停止联系"]
    leads = {
        "total": len(priorities),
        "page": 1,
        "page_size": 20,
        "items": [
            {
                "id": f"candidate-{index}",
                "project": f"合成项目{index}",
                "company": f"合成主体{index}",
                "region": "合成地区",
                "source_type": "公开网络",
                "status": "pending",
                "priority": priority,
            }
            for index, priority in enumerate(priorities)
        ],
    }
    model = build_dashboard_model(
        svc.dashboard_snapshot(),
        leads,
        {"items": [], "total": 0},
        [],
        {"items": [], "total": 0},
        [],
    )

    assert [item["priority"] for item in model["leads"]] == ["High", "Medium", "Low", "Low", "Critical"]
    assert [item["priorityRaw"] for item in model["leads"]] == priorities


def test_dashboard_opportunities_exclude_historical_and_merged_projects(svc):
    with svc.db.session() as session:
        session.add(Company(id="company", name="合成主体", region="合成地区", identity_key="company"))
        session.flush()
        session.add_all(
            [
                Project(
                    id="active-project",
                    company_id="company",
                    name="有效项目",
                    region="合成地区",
                    address="合成地址 1",
                    identity_key="active-project",
                ),
                Project(
                    id="target-project",
                    company_id="company",
                    name="合并目标",
                    region="合成地区",
                    address="合成地址 2",
                    identity_key="target-project",
                ),
                Project(
                    id="merged-project",
                    company_id="company",
                    name="已合并项目",
                    region="合成地区",
                    address="合成地址 3",
                    identity_key="merged-project",
                    merged_into_id="target-project",
                ),
            ]
        )
        session.flush()
        session.add_all(
            [
                Opportunity(id="active-opp", project_id="active-project", name="有效机会"),
                Opportunity(
                    id="historical-opp",
                    project_id="active-project",
                    name="历史机会",
                    historical=True,
                ),
                Opportunity(id="merged-project-opp", project_id="merged-project", name="合并项目机会"),
            ]
        )

    opportunities = svc.dashboard_opportunities()
    projects = svc.search_projects(page=1, page_size=100)

    assert [item["id"] for item in opportunities] == ["active-opp"]
    assert {item["id"] for item in projects["items"]} == {"active-project", "target-project"}


def test_dashboard_web_displays_raw_priority_with_mapped_priority_class(svc, tmp_path):
    candidate_id = svc.submit_candidates(None, [candidate()], actor="owner")["items"][0]["id"]
    svc.confirm_qualification(
        QualificationInput(
            fit="符合",
            need="明确需求",
            role="已核实采购角色",
            timing="已明确日期/窗口",
            confidence="原文已核对",
            priority="优先核实",
            evidence="合成核验：四项条件均有原文依据。",
        ),
        candidate_id=candidate_id,
    )
    app = create_app(svc, tmp_path / "dashboard-priority", testing=True)

    with TestClient(app) as client:
        response = client.get("/dashboard-v2")

    assert response.status_code == 200
    assert 'class="priority-tag priority-high">优先核实</span>' in response.text


def test_dashboard_web_renders_real_data_assets_and_safe_text(svc, tmp_path):
    malicious = candidate(
        1,
        company="<img src=x onerror=alert(1)>",
        project="</script><script>alert(2)</script>",
        region="<svg onload=alert(3)>",
    )
    svc.submit_candidates(None, [malicious], actor="owner")
    app = create_app(svc, tmp_path / "dashboard-backups", testing=True)

    with TestClient(app) as client:
        response = client.get("/dashboard-v2")
        css = client.get("/static/dashboard_v2.css")
        script = client.get("/static/dashboard_v2.js")

    assert response.status_code == 200
    assert css.status_code == 200
    assert script.status_code == 200
    parser = parse_dashboard(response)
    assert parser.view_count == 9
    assert parser.boot["meta"]["candidateTotal"] == 1
    assert parser.boot["leads"][0]["href"].startswith("/candidates/")
    assert "data-view=\"system\"" not in response.text
    assert "example-tag" not in response.text
    assert "示例数据" not in response.text
    assert "演示" not in response.text
    assert "downloadSample" not in response.text
    assert "<script>" not in response.text
    assert " style=" not in response.text
    assert "javascript:" not in response.text
    assert "<img src=x" not in response.text
    assert "&lt;img src=x" in response.text
    assert "\\u003cimg src=x" in response.text


def test_dashboard_web_server_filters_and_paginates(svc, tmp_path):
    svc.submit_candidates(None, [candidate(index) for index in range(21)], actor="owner")
    app = create_app(svc, tmp_path / "dashboard-pages", testing=True)

    with TestClient(app) as client:
        second = client.get("/dashboard-v2?candidate_page=2")
        filtered = client.get("/dashboard-v2?candidate_q=合成项目20&candidate_status=pending")

    second_parser = parse_dashboard(second)
    assert second.status_code == 200
    assert second_parser.boot["meta"]["candidatePage"] == 2
    assert second_parser.boot["meta"]["candidateTotal"] == 21
    assert second_parser.boot["meta"]["candidatePages"] == 2
    assert len(second_parser.boot["leads"]) == 1
    assert "candidate_page=1#leads" in second.text

    filtered_parser = parse_dashboard(filtered)
    assert filtered.status_code == 200
    assert filtered_parser.boot["meta"]["candidateTotal"] == 1
    assert filtered_parser.boot["leads"][0]["name"] == "合成项目20"


def test_dashboard_web_queue_includes_stop_review_and_pending_suggestions(svc, tmp_path):
    with svc.db.session() as session:
        session.add(
            SuppressionEvent(
                encrypted="synthetic",
                source="合成咨询原文",
                occurred_at="2026-11-24T09:00:00+08:00",
                status="pending",
            )
        )
        session.add(
            ReviewSuggestion(
                kind="qualification",
                encrypted="synthetic",
                request_id="dashboard-queue-suggestion",
                payload_hash="synthetic",
                target_version=0,
            )
        )
    app = create_app(svc, tmp_path / "dashboard-queue", testing=True)

    with TestClient(app) as client:
        response = client.get("/dashboard-v2")

    parser = parse_dashboard(response)
    assert response.status_code == 200
    assert parser.boot["meta"]["taskTotal"] == 2
    assert {item["kind"] for item in parser.boot["tasks"]} == {"refusal", "suggestion"}
    assert {item["note"] for item in parser.boot["tasks"]} == {
        "停联事件待本人复核",
        "AI 建议待本人核实",
    }
    assert "停止联系待复核" in response.text
    assert "AI建议待本人核实" in response.text
    assert "没有待处理事项" not in response.text


def test_dashboard_candidate_detail_query_is_explicit_read_only_view(svc, tmp_path):
    item = svc.submit_candidates(None, [candidate()], actor="owner")["items"][0]
    sensitive_url = "https://example.org/private?signature=do-not-expose"
    sensitive_suggestion = "合成建议正文不应进入浏览器"
    with svc.db.session() as session:
        session.add(
            SourceEvidence(
                candidate_id=item["id"],
                publisher="合成发布方",
                published_at=None,
                location_kind="项目位置",
                project_state="待核实",
                status="已核对",
                note="合成来源核验",
                verified_at="2026-11-24T10:00:00+08:00",
                actor="owner",
                source_url=sensitive_url,
                claim="合成项目存在",
            )
        )
    svc.propose_qualification(
        {
            "fit": "符合",
            "need": "明确需求",
            "role": "已核实采购角色",
            "timing": "未知",
            "confidence": "原文已核对",
            "priority": "优先核实",
            "evidence": sensitive_suggestion,
        },
        "dashboard-detail-suggestion",
        candidate_id=item["id"],
    )
    app = create_app(svc, tmp_path / "dashboard-detail", testing=True)

    with TestClient(app) as client:
        response = client.get(f"/dashboard-v2?candidate_id={item['id']}")

    parser = parse_dashboard(response)
    assert response.status_code == 200
    assert parser.default_view == "detail"
    assert parser.boot["detail"]["id"] == item["id"]
    assert set(parser.boot["detail"]) == {
        "id",
        "project",
        "company",
        "region",
        "status",
        "discovered_at",
        "source_type",
        "evidence",
        "open_unknowns",
    }
    assert sensitive_suggestion not in response.text
    assert "signature=do-not-expose" not in response.text
    assert f"/candidates/{item['id']}" in response.text


def test_dashboard_zero_denominator_renders_unknown_not_zero(svc, tmp_path):
    app = create_app(svc, tmp_path / "dashboard-empty-web", testing=True)
    with TestClient(app) as client:
        response = client.get("/dashboard-v2")

    assert response.status_code == 200
    assert "<strong>—</strong>" in response.text
    assert "<strong>0%</strong>" not in response.text
    assert "暂无来源数据" in response.text


def test_dashboard_theme_assets_external_script_order_and_light_overrides(svc, tmp_path):
    class ScriptParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.scripts = []
            self.inline_bodies = []
            self._capture_inline = False

        def handle_starttag(self, tag, attrs):
            if tag != "script":
                return
            values = dict(attrs)
            self.scripts.append(values)
            self._capture_inline = not values.get("src") and values.get("type") != "application/json"

        def handle_data(self, data):
            if self._capture_inline and data.strip():
                self.inline_bodies.append(data.strip())

        def handle_endtag(self, tag):
            if tag == "script":
                self._capture_inline = False

    app = create_app(svc, tmp_path / "dashboard-theme", testing=True)
    with TestClient(app) as client:
        response = client.get("/dashboard-v2")
        theme_css = client.get("/static/theme-light.css")
        theme_js = client.get("/static/theme.js")
        theme_init = client.get("/static/theme-init.js")

    assert response.status_code == 200
    assert theme_css.status_code == 200
    assert theme_js.status_code == 200
    assert theme_init.status_code == 200

    parser = ScriptParser()
    parser.feed(response.text)
    assert parser.inline_bodies == []
    assert [script.get("src") for script in parser.scripts] == [
        "/static/theme-init.js",
        "/static/dashboard_v2.js",
        "/static/theme.js",
    ]
    assert "defer" not in parser.scripts[0]
    assert "defer" in parser.scripts[1]
    assert "defer" in parser.scripts[2]
    assert all(
        script.get("src") or script.get("type") == "application/json"
        for script in parser.scripts
    )

    references = [
        "/static/theme-init.js",
        "/static/dashboard_v2.css",
        "/static/theme-light.css",
        "/static/dashboard_v2.js",
        "/static/theme.js",
    ]
    positions = [response.text.index(reference) for reference in references]
    assert positions == sorted(positions)

    assert ':root[data-theme="light"]' in theme_css.text
    assert '[data-theme="light"] .data-table thead th' in theme_css.text
    assert '[data-theme="light"] .funnel-row > strong' in theme_css.text
    assert '[data-theme="light"] .project-card h3' in theme_css.text
    assert '[data-theme="light"] .opp-card h4' in theme_css.text
    assert '[data-theme="light"] .agenda-copy strong' in theme_css.text
    assert '[data-theme="light"] .quality-row strong' in theme_css.text
    assert '[data-theme="light"] .opp-risk' in theme_css.text
    assert '[data-theme="light"] .agenda-item.is-overdue .agenda-time' in theme_css.text
    for obsolete_selector in ("lead-table", "lead-meta", "funnel-meta", "section-title"):
        assert f".{obsolete_selector}" not in theme_css.text
    assert 'localStorage.getItem("jxd-theme")' in theme_init.text
    assert 'localStorage.setItem(STORAGE_KEY, theme)' in theme_js.text
