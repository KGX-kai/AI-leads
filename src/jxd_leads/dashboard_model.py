"""Build the read-only model consumed by the v0.4.0 dashboard design (app 0.5.0)."""

from datetime import date, datetime
from math import ceil
from urllib.parse import quote, unquote, urlsplit

SOURCE_TONES = {"公开网络": "orange", "已有关系": "green", "抖音": "gold", "公开招标公告": "orange"}
PRIORITY_LABELS = {
    "优先核实": "High",
    "常规核实": "Medium",
    "暂缓": "Low",
    "建议排除": "Low",
    "停止联系": "Critical",
    "High": "High",
    "Medium": "Medium",
    "Low": "Low",
    "Critical": "Critical",
}
STATUS_LABELS = {
    "pending": "待核实",
    "accepted": "已建档",
    "rejected": "已排除",
    "watch": "暂缓",
    "suppressed": "停止联系",
}
PROJECT_STAGE_LABELS = {
    "待核实": "待核实",
    "确认需求": "需求确认",
    "报价或试样": "报价 / 试样",
    "采购": "采购 / 复购",
    "补货跟进": "采购 / 复购",
    "暂缓": "暂缓",
    "停止联系": "停止联系",
}
PROJECT_STAGE_INDEX = {
    "待核实": 1,
    "确认需求": 2,
    "报价或试样": 3,
    "采购": 4,
    "补货跟进": 4,
    "暂缓": 2,
    "停止联系": 2,
}
OPPORTUNITY_STAGE_GROUP = {
    "待核实": "待核实",
    "确认需求": "需求确认",
    "需求确认": "需求确认",
    "报价或试样": "报价 / 试样",
    "报价 / 试样": "报价 / 试样",
    "采购": "采购 / 复购",
    "补货跟进": "采购 / 复购",
    "暂缓": "暂缓 / 关闭",
    "停止联系": "暂缓 / 关闭",
    "关闭": "暂缓 / 关闭",
}
OPPORTUNITY_STAGES = ["待核实", "需求确认", "报价 / 试样", "采购 / 复购", "暂缓 / 关闭", "未知"]
TASK_KIND_META = {
    "refusal": ("停联事件待本人复核", "alert", "orange"),
    "inquiry": ("客户咨询待核实身份与需求", "inbox", "blue"),
    "suggestion": ("AI 建议待本人核实", "pending", "gold"),
    "proposal": ("跟进建议待本人审核", "message", "gold"),
    "watch": ("暂缓候选已到期，等待复核", "clock", "orange"),
    "candidate": ("候选仍待核实来源与需求", "inbox", "blue"),
    "bid_deadline": ("投标截止 7 天内，核对报名与资格材料", "alert", "orange"),
}
INTERNAL_HREF_ROOTS = frozenset(
    {
        "",
        "candidates",
        "dashboard-v2",
        "exports",
        "health",
        "import",
        "inbox",
        "insights",
        "notifications",
        "opportunities",
        "projects",
        "research",
        "reviews",
        "settings",
    }
)


def _text(value, fallback=""):
    text = str(value).strip() if value is not None else ""
    return text or fallback


def _date_only(value):
    if not value:
        return ""
    text = str(value)
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        try:
            return date.fromisoformat(text[:10]).isoformat()
        except ValueError:
            return ""
    try:
        return datetime.fromisoformat(text).date().isoformat()
    except ValueError:
        return ""


def _safe_internal_href(value, fallback):
    text = _text(value)
    if not text.startswith("/") or text.startswith("//") or "\\" in text or any(ord(char) < 32 for char in text):
        return fallback
    parsed = urlsplit(text)
    decoded_path = unquote(parsed.path)
    segments = decoded_path.split("/")[1:]
    if parsed.scheme or parsed.netloc or any(segment in {".", ".."} for segment in segments):
        return fallback
    if segments and segments[-1].casefold() in {"none", "null", "undefined"}:
        return fallback
    root = segments[0] if segments else ""
    if root not in INTERNAL_HREF_ROOTS:
        return fallback
    return text


def _record_href(prefix, identifier, fallback):
    value = _text(identifier)
    return f"{prefix}/{quote(value, safe='')}" if value else fallback


def _candidate_next(candidate):
    status = candidate.get("status", "")
    if status == "watch":
        review_date = _date_only(candidate.get("next_review_at"))
        return ("等待复核", review_date) if review_date else ("复核日期未知", "")
    return {
        "pending": ("审核来源与需求", ""),
        "accepted": ("进入项目跟进", ""),
        "rejected": ("已排除，无需跟进", ""),
        "suppressed": ("停止联系，禁止外发", ""),
    }.get(status, ("核对当前状态", ""))


def _map_candidate(candidate):
    next_action, next_date = _candidate_next(candidate)
    status = _text(candidate.get("status"))
    discovered = _date_only(candidate.get("discovered_at"))
    created = _date_only(candidate.get("created_at"))
    identifier = candidate.get("id", "")
    priority_raw = _text(candidate.get("priority"), "常规核实")
    return {
        "id": identifier,
        "name": _text(candidate.get("project"), "项目名称待核实"),
        "org": _text(candidate.get("company") or candidate.get("region"), "主体待核实"),
        "source": _text(candidate.get("source_type"), "来源未知"),
        "status": status,
        "stage": STATUS_LABELS.get(status, status or "状态未知"),
        "priority": PRIORITY_LABELS.get(priority_raw, "Medium"),
        "priorityRaw": priority_raw,
        "next": next_action,
        "nextMeta": f"登记 {discovered}" if discovered else "登记日期未知",
        "nextDate": next_date,
        "owner": "本人",
        "updated": created or "日期未知",
        "tone": SOURCE_TONES.get(candidate.get("source_type"), "blue"),
        "projectId": candidate.get("project_id") or "",
        "evidence": "来源证据已保留" if candidate.get("source_url") else "来源待补",
        "note": "进入线索详情核对来源、需求与未知项。",
        "href": _record_href("/candidates", identifier, "/candidates"),
    }


def _map_project(project):
    raw_stage = _text(project.get("stage"), "待核实")
    stage = PROJECT_STAGE_LABELS.get(raw_stage, raw_stage)
    requirements = project.get("requirements") or {}
    missing = [
        label
        for key, label in (
            ("role", "采购角色"),
            ("authority", "采购权限"),
            ("lamps", "灯具情况"),
            ("demand", "实际需求"),
            ("purchase_time", "采购时间"),
        )
        if requirements.get(key, "未知") in ("", "未知")
    ]
    identifier = project.get("id", "")
    return {
        "id": identifier,
        "name": _text(project.get("name"), "项目名称待核实"),
        "client": _text(project.get("company"), "主体待核实"),
        "scene": _text(project.get("region"), "地区待核实"),
        "rawStage": raw_stage,
        "stage": stage,
        "stageIndex": PROJECT_STAGE_INDEX.get(raw_stage),
        "owner": "本人",
        "leads": None,
        "next": "进入项目页核对需求与下一步",
        "nextDate": "",
        "risk": "、".join(missing) if missing else "需求字段已填写，仍须人工核实",
        "tone": "muted" if raw_stage in ("暂缓", "停止联系") else "orange",
        "note": "看板只显示安全摘要；阶段推进和跟进请进入项目页。",
        "href": _record_href("/projects", identifier, "/projects"),
    }


def _map_opportunity(opportunity, stalled=None, today=""):
    requirements = opportunity.get("requirements") or {}
    stall = (stalled or {}).get(opportunity.get("id", ""))
    deadline = _date_only(opportunity.get("bid_deadline"))
    if stall:
        risk = f"本阶段已停留 {stall['days']} 天，超过阈值 {stall['threshold']} 天"
    elif deadline:
        risk = ("投标已截止 " if today and deadline < today else "投标截止 ") + deadline
    else:
        risk = "需求、预算或时间可能仍未知"
    raw_stage = _text(opportunity.get("stage"), "待核实")
    identifier = opportunity.get("id", "")
    project_id = opportunity.get("project_id") or ""
    project_name = _text(opportunity.get("project_name") or opportunity.get("region"), "地区待核实")
    return {
        "id": identifier,
        "projectId": project_id,
        "projectHref": _record_href("/projects", project_id, "/projects"),
        "name": _text(opportunity.get("name"), f"{project_name}采购机会"),
        "place": project_name,
        "stage": raw_stage,
        "stageGroup": OPPORTUNITY_STAGE_GROUP.get(raw_stage, "未知"),
        "qty": _text(requirements.get("quantity") or requirements.get("lamps"), "未知"),
        "qtyNote": "仅显示已记录字段",
        "role": _text(requirements.get("role"), "采购角色待核实"),
        "owner": "本人",
        "next": "进入机会页核对需求与跟进",
        "nextMeta": raw_stage,
        "risk": risk,
        "stalled": bool(stall),
        "stallDays": stall["days"] if stall else None,
        "bidDeadline": deadline or None,
        "businessMode": _text(requirements.get("business_mode"), "未定"),
        "powerCost": _text(requirements.get("annual_power_cost"), "未知"),
        "sourceChannel": _text(opportunity.get("source_channel"), "未标注"),
        "ai": "",
        "href": _record_href("/opportunities", identifier, "/reviews"),
    }


def _map_task(todo, today):
    due = _text(todo.get("due") or todo.get("due_date"))
    due_date = _date_only(due)
    time = due[11:16] if len(due) >= 16 and due[10] in "T " else "全天"
    priority_value = _text(todo.get("priority"), "9")
    href = _safe_internal_href(todo.get("target"), "/opportunities")
    kind = _text(todo.get("kind"), "todo")
    overdue = kind in {"todo", "bid_deadline"} and bool(due_date and today and due_date < today)
    note, icon, tone = TASK_KIND_META.get(
        kind,
        ("逾期未完成事项" if overdue else "未完成跟进事项", "calendar", "orange" if overdue else "blue"),
    )
    if kind == "bid_deadline":
        if overdue:
            note = "投标已截止"
        elif due_date and today:
            remaining = (date.fromisoformat(due_date) - date.fromisoformat(today)).days
            note = "投标今天截止" if remaining == 0 else f"投标截止剩余 {remaining} 天"
        else:
            note = "投标截止日期待核对"
    return {
        "id": todo.get("id", ""),
        "kind": kind,
        "title": _text(todo.get("title") or todo.get("action"), "未命名任务"),
        "projectId": todo.get("project_id") or "",
        "date": due_date,
        "time": time,
        "owner": "本人",
        "priority": "High" if priority_value in {"0", "1"} else "Medium",
        "overdue": overdue,
        "note": note,
        "icon": icon,
        "tone": tone,
        "href": href,
    }


def _map_notification(notification):
    title = _text(notification.get("title"), "待处理提醒")
    count = int(notification.get("count") or 0)
    return {
        "id": notification.get("id", ""),
        "title": title,
        "body": f"{count} 项待处理" if count > 1 else "需要本人复核处理",
        "time": _date_only(notification.get("created_at")) or "时间未知",
        "icon": "alert" if notification.get("kind") in ("overdue", "due") else "bell",
        "tone": "orange" if notification.get("kind") in ("overdue", "due") else "gold",
        "unread": not bool(notification.get("read_at") or notification.get("read")),
        "href": _safe_internal_href(notification.get("target"), "/notifications"),
    }


def _map_candidate_detail(detail):
    if not detail:
        return {}
    unknowns = detail.get("open_unknowns")
    return {
        "id": _text(detail.get("id")),
        "project": _text(detail.get("project"), "项目名称待核实"),
        "company": _text(detail.get("company"), "主体待核实"),
        "region": _text(detail.get("region"), "地区待核实"),
        "status": STATUS_LABELS.get(_text(detail.get("status")), _text(detail.get("status"), "状态未知")),
        "discovered_at": _date_only(detail.get("discovered_at")) or "日期未知",
        "source_type": _text(detail.get("source_type"), "来源未知"),
        "evidence": _text(detail.get("evidence"), "来源证据待补"),
        "open_unknowns": [str(item)[:100] for item in unknowns[:20]] if isinstance(unknowns, list) else [],
    }


def _normalize_trend(value):
    result = {}
    for key in ("6m", "8w"):
        item = value.get(key, {}) if isinstance(value, dict) else {}
        labels = [str(label) for label in item.get("labels", [])] if isinstance(item, dict) else []
        raw_values = item.get("values", []) if isinstance(item, dict) else []
        values = []
        for raw in raw_values[: len(labels)]:
            try:
                values.append(max(0, int(raw)))
            except (TypeError, ValueError):
                values.append(0)
        if len(values) < len(labels):
            values.extend([0] * (len(labels) - len(values)))
        result[key] = {"labels": labels, "values": values}
    return result


def _quality_summary(quality):
    return [
        {
            "key": key,
            "label": label,
            "numerator": int((quality.get(key) or {}).get("numerator") or 0),
            "denominator": int((quality.get(key) or {}).get("denominator") or 0),
            "rate": (quality.get(key) or {}).get("rate"),
        }
        for key, label in (
            ("source_verified", "来源核实"),
            ("human_accepted", "人工接受"),
            ("demand_confirmed", "需求确认"),
            ("followup_on_time", "按时跟进"),
        )
    ]


def build_dashboard_model(
    snapshot,
    leads_listing,
    projects_listing,
    opportunities,
    tasks,
    notifications,
    detail=None,
):
    """Return only display data; callers must not pass credentials or contact secrets."""
    today = _date_only(snapshot.get("today"))
    counts = snapshot.get("counts") or {}
    funnel = []
    previous = None
    for item in snapshot.get("funnel", []):
        try:
            value = max(0, int(item.get("value") or 0))
        except (TypeError, ValueError):
            value = 0
        rate = round(value / previous * 100, 1) if previous not in (None, 0) else None
        funnel.append({**item, "value": value, "rate": rate})
        previous = value

    source_rows = []
    for item in snapshot.get("sources", []):
        try:
            count = max(0, int(item.get("count") or 0))
            projects = max(0, int(item.get("projects") or 0))
        except (TypeError, ValueError):
            count, projects = 0, 0
        source_rows.append(
            {
                "name": _text(item.get("name"), "来源未知"),
                "count": count,
                "projects": projects,
                "percent": item.get("percent") if item.get("percent") is not None else None,
            }
        )

    candidate_total = int(leads_listing.get("total") or 0)
    candidate_page = max(1, int(leads_listing.get("page") or 1))
    candidate_page_size = max(0, int(leads_listing.get("page_size") or 0))
    stalled = {item.get("id"): item for item in snapshot.get("stalled", [])}
    channel_rows = [
        {
            "name": _text(item.get("name"), "未标注"),
            "candidates": max(0, int(item.get("candidates") or 0)),
            "inquiries": max(0, int(item.get("inquiries") or 0)),
            "opportunities": max(0, int(item.get("opportunities") or 0)),
        }
        for item in snapshot.get("channels", [])
    ]
    task_total = int(tasks.get("total") or 0)
    task_loaded = len(tasks.get("items", []))
    project_total = int(projects_listing.get("total") or 0)
    project_loaded = len(projects_listing.get("items", []))
    project_page = max(1, int(projects_listing.get("page") or 1))
    project_page_size = max(0, int(projects_listing.get("page_size") or 0))
    total_conversion = snapshot.get("total_conversion") if counts.get("candidates") else None
    mapped_tasks = [_map_task(todo, today) for todo in tasks.get("items", [])]
    mapped_tasks.sort(key=lambda item: (item["date"] or "9999-12-31", item["time"] == "全天", item["time"]))

    return {
        "today": today,
        "meta": {
            "designRevision": "rev-f47cfd6a90e5",
            "themeRevision": "rev-9b78fa9d5d99",
            "schemaVersion": "1.3",
            "appVersion": "0.5.0",
            "candidatePage": candidate_page,
            "candidatePageSize": candidate_page_size,
            "candidateTotal": candidate_total,
            "candidatePages": ceil(candidate_total / candidate_page_size) if candidate_page_size else 0,
            "projectTotal": project_total,
            "projectPage": project_page,
            "projectPageSize": project_page_size,
            "projectPages": ceil(project_total / project_page_size) if project_page_size else 0,
            "projectLoaded": project_loaded,
            "projectTruncated": project_loaded < project_total,
            "opportunityTotal": len(opportunities),
            "opportunityLoaded": len(opportunities),
            "taskTotal": task_total,
            "taskLoaded": task_loaded,
            "taskTruncated": task_loaded < task_total,
            "notificationLoaded": len(notifications),
            "notificationLimited": len(notifications) >= 100,
            "opportunityStages": OPPORTUNITY_STAGES,
        },
        "overview": {
            "counts": counts,
            "channels": channel_rows,
            "stalledCount": len(stalled),
            "kpis": [
                {
                    "key": "pending",
                    "label": "待核实线索",
                    "value": counts.get("pending", 0),
                    "unit": "leads",
                    "foot": "进入线索池审核",
                    "href": "/candidates?status=pending",
                    "tone": "orange",
                },
                {
                    "key": "projects",
                    "label": "客户项目",
                    "value": counts.get("projects", 0),
                    "unit": "projects",
                    "foot": "核对需求与下一步",
                    "href": "/projects",
                    "tone": "green",
                },
                {
                    "key": "communications",
                    "label": "有效沟通",
                    "value": counts.get("communications", 0),
                    "unit": "conversations",
                    "foot": "累计人工记录",
                    "href": "/insights",
                    "tone": "blue",
                },
                {
                    "key": "opportunities",
                    "label": "采购机会",
                    "value": counts.get("opportunities", 0),
                    "unit": "opportunities",
                    "foot": "进入机会页核对",
                    "href": "/projects",
                    "tone": "gold",
                },
            ],
            "funnel": funnel,
            "sources": source_rows,
            "trend": _normalize_trend(snapshot.get("trend")),
            "totalConversion": total_conversion,
            "quality": _quality_summary(snapshot.get("quality") or {}),
            "hasSourceData": any(item["count"] or item["projects"] for item in source_rows),
        },
        "leads": [_map_candidate(item) for item in leads_listing.get("items", [])],
        "projects": [_map_project(item) for item in projects_listing.get("items", [])],
        "opportunities": [_map_opportunity(item, stalled, today) for item in opportunities],
        "tasks": mapped_tasks,
        "reports": [],
        "notifications": [_map_notification(item) for item in notifications],
        "detail": _map_candidate_detail(detail),
    }
