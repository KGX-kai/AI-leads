import asyncio
import contextlib
import secrets
import sqlite3
import traceback
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode, urlparse
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from itsdangerous import BadSignature, URLSafeTimedSerializer
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from starlette.middleware.sessions import SessionMiddleware

from . import __version__
from .backup import run_backup
from .dashboard_model import build_dashboard_model
from .desktop import DesktopNotifications
from .errors import envelope
from .imports import preview_import, safe_csv
from .schemas import (
    BUSINESS_MODES,
    POWER_COST_BANDS,
    REJECT_REASON_CODES,
    CandidateInput,
    ContactInput,
    FollowupInput,
    InquiryInput,
    OfferInput,
    RequirementsInput,
    ResearchInput,
)
from .service import STAGES, STATUS, BusinessError, Service
from .workspace_web import register_workspace

PACKAGE = Path(__file__).parent
TZ = ZoneInfo("Asia/Shanghai")


def queue_item_view(item, back_url):
    kind = item["kind"]
    reason = {
        "refusal": "客户明确拒绝联系，需先核对原话、对象和停联范围",
        "inquiry": "新咨询的身份、场景和实际需求尚未核实",
        "suggestion": "AI 判断或回复建议尚未由本人确认",
        "proposal": "AI 跟进建议尚未由本人确认",
        "watch": "暂缓观察已到复核日期",
    }.get(kind)
    next_action = {
        "refusal": "核对后保持停联，或记录误匹配依据",
        "inquiry": "核对原文，补齐可获得的事实后再处理",
        "suggestion": "查看依据后确认、编辑或拒绝建议",
        "proposal": "进入项目核对上次沟通与下一步",
        "watch": "复核来源与时间，返回待审或重新暂缓",
        "candidate": "查看来源证据、冲突和未知项后审核",
    }.get(kind, "打开待处理对象并完成本次动作")
    if kind == "todo":
        reason = "跟进已逾期，需要完成、改期或记录原因" if item["priority"] == 1 else "已安排下一动作"
        next_action = "打开采购机会处理该项跟进"
    elif kind == "candidate":
        reason = "优先候选仍缺关键证据" if item["priority"] == 5 else "普通候选尚待人工核实"
    date_label = {
        "refusal": "进入时间",
        "inquiry": "收到时间",
        "suggestion": "生成时间",
        "proposal": "生成时间",
        "watch": "复核日期",
        "candidate": "进入时间",
    }.get(kind, "截止时间")
    target = item["target"]
    separator = "&" if "?" in target else "?"
    return {
        **item,
        "reason": reason,
        "next_action": next_action,
        "date_label": date_label,
        "target": target + separator + urlencode({"return_to": back_url}),
    }


def create_app(service: Service, backup_dir=None, testing=False):
    backup_dir = Path(backup_dir or service.db.backup_dir)

    desktop = DesktopNotifications(service.db)

    async def refresh_reminders():
        try:
            await asyncio.to_thread(service.check_reminders)
            await asyncio.to_thread(desktop.dispatch)
        except (OSError, ValueError, sqlite3.Error, SQLAlchemyError):
            app.state.reminder_error = "提醒检查失败；现有提醒保留，系统将在下一轮自动重试"
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            app.state.reminder_error = "提醒检查异常；现有提醒保留，系统将在下一轮自动重试"
        else:
            app.state.reminder_error = None
            app.state.last_reminder_ok_at = datetime.now(TZ).isoformat(timespec="seconds")

    async def reminder_loop():
        while True:
            await refresh_reminders()
            await asyncio.sleep(60)

    async def refresh_backup():
        try:
            await asyncio.to_thread(run_backup, service.db, backup_dir, vault=service.vault)
            app.state.backup_error = None
        except (OSError, sqlite3.Error, ValueError, SQLAlchemyError):
            app.state.backup_error = "自动备份失败，请检查存储空间和目录权限"
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            app.state.backup_error = "自动备份异常；请检查存储空间和目录权限，下一轮自动重试"
        else:
            app.state.last_backup_ok_at = datetime.now(TZ).isoformat(timespec="seconds")

    async def backup_loop():
        while True:
            await refresh_backup()
            await asyncio.sleep(3600)

    @contextlib.asynccontextmanager
    async def lifespan(app):
        tasks = [asyncio.create_task(backup_loop()), asyncio.create_task(reminder_loop())] if not testing else []
        yield
        for task in tasks:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    app = FastAPI(
        title="京小电获客平台", version=__version__, lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None
    )
    app.state.backup_error = None
    app.state.last_backup_ok_at = None
    app.state.refresh_backup = refresh_backup
    app.state.reminder_error = None
    app.state.last_reminder_ok_at = None
    app.state.refresh_reminders = refresh_reminders
    signer = URLSafeTimedSerializer(secrets.token_hex(32), salt="import-preview")
    templates = Jinja2Templates(directory=PACKAGE / "templates")
    templates.env.globals["operation_id"] = lambda: str(uuid4())
    templates.env.globals["reject_reasons"] = REJECT_REASON_CODES
    templates.env.globals["business_modes"] = BUSINESS_MODES
    templates.env.globals["power_cost_bands"] = POWER_COST_BANDS
    templates.env.globals["source_channels"] = service.source_channels
    templates.env.filters["status"] = lambda value: STATUS.get(value, value)
    templates.env.filters["money"] = lambda value: "待确认" if value is None else f"¥{value / 100:,.2f}"
    templates.env.filters["local_time"] = lambda value: (
        datetime.fromisoformat(value).astimezone(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M")
    )

    def render(request, name, **context):
        return templates.TemplateResponse(
            request=request,
            name=name,
            context={
                "today": str(datetime.now(TZ).date()),
                "isolated_preview": testing,
                "csrf": request.session.get("csrf", ""),
                "stages": STAGES,
                "backup_error": app.state.backup_error,
                "reminder_error": app.state.reminder_error,
                **context,
            },
        )

    extra_action = register_workspace(app, service, render, desktop)

    @app.middleware("http")
    async def local_guard(request, call_next):
        host = request.headers.get("host", "").split(":")[0]
        allowed = {"127.0.0.1", "localhost"} | ({"testserver"} if testing else set())
        if host not in allowed:
            return JSONResponse({"error": "只允许本机访问"}, 400)
        origin = request.headers.get("origin")
        if origin and (urlparse(origin).netloc != request.headers.get("host") or urlparse(origin).scheme != "http"):
            return JSONResponse({"error": "来源校验失败"}, 403)
        if request.headers.get("sec-fetch-site") == "cross-site":
            return JSONResponse({"error": "不允许跨站请求"}, 403)
        length = request.headers.get("content-length", "0")
        if not length.isdigit() or int(length) > 3 * 1024 * 1024:
            return JSONResponse({"error": "请求过大"}, 413)
        if request.url.path.startswith("/api/"):
            if not request.session.get("csrf"):
                return JSONResponse({"error": "请先打开工作台"}, 401)
            if request.method not in {"GET", "HEAD"} and not secrets.compare_digest(
                request.headers.get("x-csrf-token", ""), request.session["csrf"]
            ):
                return JSONResponse({"error": "会话校验失败，请刷新页面"}, 403)
        elif request.method == "GET" and not request.url.path.startswith("/static/"):
            if not request.session.get("csrf"):
                request.session["csrf"] = secrets.token_urlsafe(32)
        response = await call_next(request)
        response.headers.update(
            {
                "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "no-referrer",
                "Cache-Control": "no-store",
            }
        )
        return response

    # Outermost middleware so local_guard can read signed, HttpOnly sessions.
    app.add_middleware(
        SessionMiddleware,
        secret_key=secrets.token_hex(32),
        same_site="strict",
        https_only=False,
        max_age=12 * 3600,
        session_cookie="jxd_session",
    )
    app.mount("/static", StaticFiles(directory=PACKAGE / "static"), name="static")

    @app.exception_handler(BusinessError)
    async def business_error(request, exc):
        if request.url.path.startswith("/api/"):
            return JSONResponse(envelope(error=exc), 409)
        return render(request, "error.html", page="error", message=str(exc))

    @app.exception_handler(SQLAlchemyError)
    async def storage_error(request, exc):
        error = BusinessError("数据暂时无法保存，请检查磁盘空间或稍后用相同操作编号重试", "TEMPORARY_UNAVAILABLE", True)
        if request.url.path.startswith("/api/"):
            return JSONResponse(envelope(error=error), 503)
        return render(request, "error.html", page="error", message=str(error))

    @app.get("/", response_class=HTMLResponse)
    def home(
        request: Request,
        n: int = 1,
        kind: str = "",
        date_from: str = "",
        date_to: str = "",
        reminder_due: int | None = None,
        reminder_new: int | None = None,
    ):
        queue_sections = [
            (key, label, service.today_queue(1, 1, key)["total"])
            for key, label in [
                ("inquiry", "新咨询"), ("refusal", "拒绝待复核"),
                ("overdue", "逾期跟进"), ("suggestion", "建议待审"),
                ("watch", "到期复核"), ("proposal", "跟进建议"), ("candidate", "候选核实"),
            ]
        ]
        back_url = request.url.path + (("?" + request.url.query) if request.url.query else "")
        queue_data = service.today_queue(n, 20, kind, date_from, date_to)
        queue_data["items"] = [queue_item_view(item, back_url) for item in queue_data["items"]]
        return render(
            request,
            "dashboard.html",
            page="home",
            data=service.overview(),
            queue=queue_data,
            date_from=date_from,
            date_to=date_to,
            views=service.saved_views(),
            queue_sections=queue_sections,
            kind=kind,
            reminder_result=(
                {"due": reminder_due, "new": reminder_new, "already": max(reminder_due - reminder_new, 0)}
                if reminder_due is not None and reminder_new is not None
                else None
            ),
        )

    @app.get("/health")
    def health():
        return {
            "app": "JXD-LEADS-001",
            "version": __version__,
            "last_backup_ok_at": app.state.last_backup_ok_at,
            "last_reminder_ok_at": app.state.last_reminder_ok_at,
            "backup_error": app.state.backup_error,
            "reminder_error": app.state.reminder_error,
        }

    @app.get("/dashboard-v2", response_class=HTMLResponse)
    def dashboard_v2(
        request: Request,
        candidate_status: str = "",
        candidate_q: str = "",
        candidate_page: int = 1,
        candidate_id: str = "",
        project_page: int = 1,
    ):
        snapshot = service.dashboard_snapshot()
        leads = service.list_candidates(
            status=candidate_status,
            q=candidate_q,
            page=candidate_page,
            page_size=20,
        )
        projects = service.search_projects(page=project_page, page_size=100)
        boot = build_dashboard_model(
            snapshot,
            leads,
            projects,
            service.dashboard_opportunities(),
            service.today_queue(page=1, page_size=100),
            service.notifications(),
            service.dashboard_candidate_detail(candidate_id) if candidate_id else None,
        )
        return render(
            request,
            "dashboard_v2.html",
            page="home",
            boot=boot,
            candidate_status=candidate_status,
            candidate_q=candidate_q,
            project_page=project_page,
        )

    @app.get("/research", response_class=HTMLResponse)
    def research(request: Request):
        data = service.overview()
        for r in data["research"]:
            r["brief"] = service.research_task(r["id"])["brief"]
        return render(request, "research.html", page="research", data=data)

    @app.get("/candidates", response_class=HTMLResponse)
    def candidates(request: Request, status: str = "", q: str = "", n: int = 1, tag_id: str = ""):
        listing = service.list_candidates(status, q, n, tag_id=tag_id or None)
        name = "candidate_rows.html" if request.headers.get("hx-request") == "true" else "candidates.html"
        return render(
            request,
            name,
            page="candidates",
            rows=listing["items"],
            tags=service.tags(),
            tag_id=tag_id,
            listing=listing,
            projects=service.projects(),
            status=status,
            q=q,
        )

    @app.get("/projects", response_class=HTMLResponse)
    def projects(request: Request, q: str = "", n: int = 1):
        listing = service.search_projects(q, n)
        return render(request, "projects.html", page="projects", rows=listing["items"], listing=listing, q=q)

    @app.get("/projects/{pid}", response_class=HTMLResponse)
    def project(request: Request, pid: str):
        return render(
            request, "project.html", page="projects", p=service.project_context(pid), merge_targets=service.projects()
        )

    @app.get("/insights", response_class=HTMLResponse)
    def insights(request: Request):
        return render(
            request, "insights.html", page="insights", data=service.overview(),
            quality=service.dashboard_snapshot()["quality"],
        )

    @app.get("/settings", response_class=HTMLResponse)
    def settings(request: Request):
        return render(
            request,
            "settings.html",
            page="settings",
            data=service.overview(),
            desktop=desktop.status(),
            sop_settings=service.get_sop_settings(),
            stall_days=service.stall_days(),
            backup_history=service.backup_history(),
            tags=service.tags(),
            backups=[x.name for x in sorted(backup_dir.glob("leads-*.sqlite3"), reverse=True)],
        )

    @app.get("/import", response_class=HTMLResponse)
    def importer(request: Request):
        return render(request, "import.html", page="candidates", preview=None)

    async def form(request):
        raw = await request.form()
        data = dict(raw)
        if "tag_ids" in raw:
            data["tag_ids"] = raw.getlist("tag_ids")
        csrf = str(data.pop("csrf", ""))
        if not request.session.get("csrf") or not secrets.compare_digest(csrf, request.session["csrf"]):
            raise BusinessError("会话已失效，请刷新页面重试")
        return data

    @app.post("/actions/{action}")
    async def action(request: Request, action: str):
        data = await form(request)
        destination = data.pop("return_to", "/")
        if not destination.startswith("/") or destination.startswith("//") or "\\" in destination:
            destination = "/"
        operation = data.pop("operation_id", "")
        try:
            if action == "desktop_enable":
                state = await asyncio.to_thread(desktop.configure, data.get("enabled") == "yes")
                if state.get("error") or (
                    data.get("enabled") == "yes" and state.get("authorization") not in {"authorized", "provisional"}
                ):
                    raise BusinessError(
                        "系统通知尚未获授权；站内提醒继续可用。请在macOS系统设置的通知中检查京小电获客提醒。"
                    )
                return RedirectResponse("/notifications", status_code=303)
            if action == "inquiry_import_preview":
                upload = data["file"]
                mapping = {
                    "平台": "platform",
                    "企业账号ID": "account_id",
                    "消息ID": "message_id",
                    "评论ID": "comment_id",
                    "视频ID": "video_id",
                    "事件类型": "event_type",
                    "用户ID": "user_id",
                    "昵称": "nickname",
                    "原文": "body",
                    "来源链接": "source_url",
                    "发生时间": "occurred_at",
                }
                preview = preview_import(
                    await upload.read(2 * 1024 * 1024 + 1), upload.filename or "", model=InquiryInput, headers=mapping
                )
                signed = signer.dumps(
                    {
                        "session": request.session["csrf"],
                        "encrypted": service.vault.encrypt(preview["items"]),
                        "batch": str(uuid4()),
                    }
                )
                return render(
                    request,
                    "inbox.html",
                    page="inbox",
                    data=service.inquiries(),
                    status="",
                    q="",
                    preview=service.safe_output(preview),
                    signed=signed,
                )
            if action == "import_preview":
                upload = data["file"]
                preview = preview_import(await upload.read(2 * 1024 * 1024 + 1), upload.filename or "")
                signed = signer.dumps({"session": request.session["csrf"], "items": preview["items"]})
                return render(request, "import.html", page="candidates", preview=preview, signed=signed)

            def apply_action():
                nonlocal destination
                if action == "research":
                    service.create_research(ResearchInput(**data))
                    destination = "/research"
                elif action == "candidate":
                    data["unknowns"] = [value.strip() for value in data.pop("unknowns", "").splitlines() if value.strip()]
                    data["bid_deadline"] = data.get("bid_deadline") or None
                    service.submit_candidates(None, [CandidateInput(**data)], actor="owner")
                    destination = "/candidates"
                elif action == "review":
                    result = service.review_candidate(
                        data["id"],
                        data["decision"],
                        reason=data.get("reason", ""),
                        merge_project_id=data.get("merge_project_id") or None,
                        next_review_at=data.get("next_review_at") or None,
                        reason_code=data.get("reason_code") or "other",
                    )
                    if result.get("project_id"):
                        destination = "/projects/" + result["project_id"]
                elif action == "check_reminders":
                    result = service.check_reminders()
                    destination = "/?" + urlencode({"reminder_due": result["due"], "reminder_new": result["new"]})
                elif action == "requirements":
                    pid = data.pop("project_id")
                    data["confirmed"] = data.get("confirmed") == "on"
                    service.update_requirements(pid, RequirementsInput(**data))
                elif action == "stage":
                    service.set_stage(data["project_id"], data["stage"])
                elif action == "contact":
                    pid = data.pop("project_id")
                    service.add_contact(pid, ContactInput(**data))
                elif action == "followup":
                    pid = data.pop("project_id")
                    data["due_date"] = data.get("due_date") or None
                    oid = data.pop("opportunity_id", None) or None
                    data["minutes"] = int(data["minutes"]) if data.get("minutes") else None
                    service.record_followup(pid, FollowupInput(**data), oid)
                elif action == "proposal":
                    service.confirm_proposal(data["id"], data["decision"] == "confirm")
                elif action == "todo":
                    service.complete_task(data["id"])
                elif action == "suppress":
                    service.suppress_project(data["project_id"], data["reason"])
                elif action == "suppress_contact":
                    service.suppress_contact(data["id"], "联系人明确拒绝联系")
                elif action == "offer":
                    pid = data.pop("project_id")
                    data["due_date"] = data.get("due_date") or None
                    from decimal import Decimal, InvalidOperation

                    amount = data.pop("amount", "")
                    try:
                        value = Decimal(amount) if amount else None
                        if value is not None and (
                            not value.is_finite() or value < 0 or value > 100000000 or value.as_tuple().exponent < -2
                        ):
                            raise BusinessError("金额需要为非负数，最多两位小数且不超过一亿元")
                        data["amount_cents"] = int(value * 100) if value is not None else None
                    except InvalidOperation:
                        raise BusinessError("金额格式不正确")
                    oid = data.pop("opportunity_id", None) or None
                    service.add_offer(pid, OfferInput(**data), oid)
                elif action == "offer_update":
                    service.update_offer(
                        data["id"],
                        data["status"],
                        data.get("feedback", ""),
                        expected_version=int(data["version"]) if data.get("version") else None,
                    )
                elif action == "backup":
                    run_backup(service.db, backup_dir, force=True, vault=service.vault)
                    destination = "/settings"
                elif action == "import_confirm":
                    try:
                        payload = signer.loads(data["preview"], max_age=1800)
                    except BadSignature:
                        raise BusinessError("导入预览已过期，请重新上传")
                    if payload["session"] != request.session["csrf"]:
                        raise BusinessError("导入会话不匹配")
                    service.submit_candidates(None, [CandidateInput(**r) for r in payload["items"]], actor="owner")
                    destination = "/candidates"
                elif action == "inquiry_import_confirm":
                    try:
                        payload = signer.loads(data["preview"], max_age=1800)
                    except BadSignature:
                        raise BusinessError("导入预览已过期，请重新上传")
                    if payload["session"] != request.session["csrf"]:
                        raise BusinessError("导入会话不匹配")
                    for index, item in enumerate(service.vault.decrypt(payload["encrypted"])):
                        service.receive_inquiry(item, payload["batch"] + ":" + str(index))
                    destination = "/inbox"
                else:
                    destination = extra_action(action, data)
                return {"destination": destination}

            if action == "backup":
                apply_action()
            else:
                outcome = service.execute_once("owner", action, operation, dict(data), apply_action)
                destination = outcome["destination"]
        except (ValidationError, ValueError, KeyError) as exc:
            message = (
                str(exc) if isinstance(exc, BusinessError) else "输入格式不正确，请检查必填字段、日期、数字和文件格式"
            )
            return render(request, "error.html", page="error", message=message)
        if not destination.startswith("/") or destination.startswith("//") or "\\" in destination:
            destination = "/"
        if request.headers.get("hx-request") == "true":
            return Response(status_code=200, headers={"HX-Location": destination})
        return RedirectResponse(destination, status_code=303)

    @app.get("/api/v1/overview")
    def api_overview():
        return service.overview()

    @app.get("/api/v1/candidates")
    def api_candidates(status: str = "", q: str = ""):
        return service.candidates(status, q)

    @app.get("/api/v1/projects/{pid}")
    def api_context(pid: str):
        return service.project_context(pid)

    @app.post("/api/v1/research-tasks")
    def api_research(request: Request, data: ResearchInput):
        rid = request.headers.get("Idempotency-Key", "")
        return envelope(
            data=service.execute_once(
                "owner", "api.research", rid, data.model_dump(mode="json"), lambda: service.create_research(data)
            ),
            request_id=rid,
        )

    @app.post("/api/v1/candidates")
    def api_candidate(request: Request, data: CandidateInput):
        rid = request.headers.get("Idempotency-Key", "")
        return envelope(
            data=service.execute_once(
                "owner",
                "api.candidate",
                rid,
                data.model_dump(mode="json"),
                lambda: service.submit_candidates(None, [data], actor="owner"),
            ),
            request_id=rid,
        )

    @app.post("/api/v1/contacts/{cid}/reveal")
    def api_reveal(cid: str):
        return service.reveal_contact(cid)

    export_kinds = {"inquiry-template", "inquiries", "template", "projects", "candidates"}

    @app.post("/exports/{kind}.csv")
    async def export(request: Request, kind: str):
        if kind not in export_kinds:
            raise BusinessError("导出类型不正确")
        await form(request)
        if kind == "inquiry-template":
            rows = [
                [
                    "平台",
                    "企业账号ID",
                    "消息ID",
                    "评论ID",
                    "视频ID",
                    "事件类型",
                    "用户ID",
                    "昵称",
                    "原文",
                    "来源链接",
                    "发生时间",
                ]
            ]
        elif kind == "inquiries":
            rows = [["编号", "平台", "原文（脱敏）", "发生时间", "状态", "地区", "项目"]]
            page = 1
            while True:
                batch = service.inquiries(page=page, page_size=100)
                rows.extend(
                    [
                        [i[k] for k in ["id", "platform", "body", "occurred_at", "status", "region", "project_name"]]
                        for i in batch["items"]
                    ]
                )
                if page * 100 >= batch["total"]:
                    break
                page += 1
        elif kind == "template":
            rows = [
                ["公司", "项目", "地区", "地址", "来源链接", "来源类型", "证据", "匹配理由", "需求证据", "发现日期"]
            ]
        elif kind == "projects":
            rows = [["项目编号", "公司", "项目", "地区", "地址", "阶段"]] + [
                [p[k] for k in ["id", "company", "name", "region", "address", "stage"]] for p in service.projects()
            ]
        elif kind == "candidates":
            rows = [["公司", "项目", "地区", "来源链接", "证据", "状态"]] + [
                [p[k] for k in ["company", "project", "region", "source_url", "evidence", "status"]]
                for p in service.candidates()
            ]
        service.record_export(kind, len(rows) - 1)
        return Response(
            safe_csv(rows),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="jxd-{kind}.csv"'},
        )

    return app
