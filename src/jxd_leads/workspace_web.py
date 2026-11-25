"""Local owner pages. No owner action below is registered as an MCP tool."""

from urllib.parse import urlencode

from fastapi import Request

from .errors import BusinessError, envelope
from .schemas import INQUIRY_SUGGESTION_FIELDS, OpportunityUpdate, QualificationInput
from .workflows import OPPORTUNITY_STAGES


def safe_return(value, default):
    return value if value.startswith("/") and not value.startswith("//") and "\\" not in value else default


def register_workspace(app, service, render, desktop):
    @app.get("/opportunities/{oid}")
    def opportunity(request: Request, oid: str, n: int = 1, sop: str = "", received_at: str = ""):
        o = service.opportunity_context(oid, page=n)
        return render(
            request,
            "opportunity.html",
            page="projects",
            o=o,
            snapshot=service.opportunity_followup_snapshot(oid),
            tags=service.tags(),
            opportunity_stages=OPPORTUNITY_STAGES,
            sop=service.sop(sop, received_at or None) if sop else None,
            stall=next((item for item in service.stalled_opportunities() if item["id"] == oid), None),
            pace=None if o.get("suppressed") else service.followup_suggestion(oid),
        )

    @app.get("/candidates/{cid}")
    def candidate(request: Request, cid: str, return_to: str = ""):
        return render(
            request,
            "candidate.html",
            page="candidates",
            c=service.candidate_context(cid),
            tags=service.tags(),
            projects=service.projects(),
            return_to=safe_return(return_to, "/candidates"),
        )

    @app.get("/inbox")
    def inbox(request: Request, status: str = "", q: str = "", n: int = 1):
        return render(
            request, "inbox.html", page="inbox", data=service.inquiries(status, q, n), status=status, q=q, preview=None
        )

    @app.get("/inbox/{iid}")
    def inquiry(request: Request, iid: str):
        options = []
        for p in service.projects():
            options.extend(dict(o, project=p["name"]) for o in service.opportunities(p["id"]))
        return render(request, "inquiry.html", page="inbox", i=service.inquiry_context(iid), opportunities=options)

    @app.get("/reviews")
    def reviews(request: Request):
        return render(
            request,
            "reviews.html",
            page="reviews",
            suggestions=service.suggestions(),
            followup_proposals=service.pending_followup_proposals(),
            refusals=service.suppression_events(),
            tags=service.tags(),
        )

    @app.get("/notifications")
    def notifications(request: Request):
        return render(
            request, "notifications.html", page="notifications", items=service.notifications(), desktop=desktop.status()
        )

    @app.get("/notifications/summary")
    def summary(request: Request):
        return render(request, "notification_badge.html", count=len(service.notifications(unread_only=True)))

    @app.get("/api/v1/capabilities")
    def capabilities():
        return envelope(data=service.capabilities())

    @app.get("/api/v1/queue")
    def queue(page: int = 1, page_size: int = 20, kind: str = ""):
        return envelope(data=service.today_queue(page, page_size, kind))

    @app.get("/api/v1/opportunities/{oid}")
    def context(oid: str):
        return envelope(data=service.opportunity_context(oid))

    def extra(action, data):
        if action == "opportunity_new":
            o = service.create_opportunity(data["project_id"], data["kind"], data["name"])
            return "/opportunities/" + o["id"]
        if action == "opportunity_requirements":
            fields = {k: data.get(k, "未知") for k in ["role", "authority", "lamps", "demand", "purchase_time"]}
            fields["confirmed"] = data.get("confirmed") == "on"
            current = service.opportunity_context(data["id"])["requirements"] or {}
            for key, fallback in (("business_mode", "未定"), ("annual_power_cost", "未知")):
                fields[key] = data.get(key) or current.get(key) or fallback
            managed = data.get("managed_projects", "").strip() if "managed_projects" in data else None
            fields["managed_projects"] = (
                int(managed) if managed else None
            ) if managed is not None else current.get("managed_projects")
            service.update_opportunity(data["id"], int(data["version"]), requirements=fields)
            return "/opportunities/" + data["id"]
        if action == "opportunity_stage":
            service.update_opportunity(data["id"], int(data["version"]), stage=data["stage"])
            return "/opportunities/" + data["id"]
        if action == "suggestion_review":
            edited = None
            if data.get("kind") == "inquiry_reply":
                edited = {"draft": data.get("draft", "")}
            elif data.get("kind") == "inquiry_fields":
                edited = {"fields": {key: data[key] for key in INQUIRY_SUGGESTION_FIELDS if key in data}}
            elif data.get("kind") == "opportunity":
                fields = {
                    k: data.get(k, "") for k in ["summary", "result", "stage", "draft", "next_action", "evidence"]
                }
                fields.update(
                    due_date=data.get("due_date") or None,
                    minutes=int(data["minutes"]) if data.get("minutes") else None,
                    tag_ids=data.get("tag_ids", []),
                )
                edited = OpportunityUpdate(**fields).model_dump(mode="json")
            service.review_update(
                data["id"],
                data["decision"] == "confirm",
                version=int(data["version"]) if data.get("version") else None,
                edited=edited,
            )
            return data.get("back", "/reviews")
        if action == "qualification":
            data["tag_ids"] = data.get("tag_ids", [])
            cid, oid = data.pop("candidate_id", None), data.pop("opportunity_id", None)
            expected = int(data.pop("expected_version", 0))
            service.confirm_qualification(QualificationInput(**data), cid, oid, expected_version=expected)
            return "/candidates/" + cid if cid else "/opportunities/" + oid
        if action == "source_verify":
            service.verify_source(
                data["id"],
                data.get("publisher", ""),
                data.get("published_at", ""),
                data["location_kind"],
                data["project_state"],
                data["status"],
                data.get("note", ""),
                source_url=data.get("source_url", ""),
                claim=data.get("claim", ""),
            )
            destination = "/candidates/" + data["id"]
            back = safe_return(data.get("context_back", ""), "")
            return destination + (("?" + urlencode({"return_to": back})) if back else "")
        if action == "tag_new":
            service.add_tag(data["name"])
            return "/settings"
        if action == "inquiry_new":
            request_id = data.pop("request_id")
            result = service.receive_inquiry(data, request_id)
            return "/inbox/" + result["id"]
        if action == "inquiry_update":
            iid, version, oid = data.pop("id"), data.pop("version"), data.pop("opportunity_id", None)
            service.update_inquiry(iid, int(version), data, oid or None)
            return "/inbox/" + iid
        if action == "inquiry_draft":
            service.propose_inquiry_reply(data["id"], data["draft"], data["request_id"])
            return "/inbox/" + data["id"]
        if action == "refusal":
            targets = {k: data.get(k) or None for k in ["project_id", "contact_id", "inquiry_id"]}
            service.request_suppression(
                data["evidence"],
                data["source"],
                data["occurred_at"],
                data["request_id"],
                actor="owner",
                origin="web",
                **targets,
            )
            return "/reviews"
        if action == "refusal_correct":
            service.correct_suppression(data["id"], data["reason"])
            return "/reviews"
        if action == "refusal_review":
            service.review_suppression(data["id"], data["note"])
            return "/reviews"
        if action == "notification_read":
            service.read_notification(data["id"])
            return "/notifications"
        if action == "save_view":
            service.save_view(data["name"], data.get("kind", ""), data.get("date_from", ""), data.get("date_to", ""))
            return "/"
        if action == "opportunity_profile":
            service.update_opportunity_profile(
                data["id"], int(data["version"]), data.get("source_channel", ""), data.get("bid_deadline") or None
            )
            return "/opportunities/" + data["id"]
        if action == "channel_settings":
            service.save_source_channels(data.get("channels", "").splitlines())
            return "/settings"
        if action == "stall_settings":
            service.save_stall_days({k: int(data[k]) for k in ["EMC", "买断", "未定"]})
            return "/settings"
        if action == "sop_settings":
            service.save_sop({k: int(data[k]) for k in ["inquiry", "quote", "sample", "replenish", "paused"]})
            return "/settings"
        if action == "todo_reschedule":
            service.reschedule_task(data["id"], data["due_at"], data["reason"])
            return "/"
        if action == "project_correct":
            service.correct_project(
                data["id"], int(data["version"]), data["name"], data["region"], data["address"], data["reason"]
            )
            return "/projects/" + data["id"]
        if action == "project_merge":
            service.merge_projects(data["id"], data["target_id"], data["reason"])
            return "/projects/" + data["target_id"]
        raise BusinessError("不支持的操作")

    return extra
