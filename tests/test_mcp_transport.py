import json
import sys

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from jxd_leads.db import ROOT
from jxd_leads.mcp_server import TOOL_NAMES

ENVELOPE_KEYS = {"schema_version", "ok", "request_id", "data", "error"}


def envelope(result):
    data = result.structuredContent or json.loads(result.content[0].text)
    assert set(data) == ENVELOPE_KEYS
    assert data["schema_version"] == "1.3"
    assert data["ok"] is (not bool(result.isError))
    if data["ok"]:
        assert data["error"] is None
    else:
        assert data["data"] is None
        assert {"code", "message", "retryable"} == set(data["error"])
    return data


async def test_registered_tools_over_real_stdio(tmp_path):
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(ROOT / "tests/mcp_fixture.py"), str(tmp_path)],
        cwd=str(ROOT),
        env={"PYTHONPATH": str(ROOT / "src"), "PYTHONDONTWRITEBYTECODE": "1"},
    )
    with anyio.fail_after(30):
        async with stdio_client(params) as (reader, writer), ClientSession(reader, writer) as session:
            await session.initialize()
            tools = {tool.name: tool for tool in (await session.list_tools()).tools}
            assert set(tools) == set(TOOL_NAMES)
            assert len(tools) == 18
            assert "实际 task_id" in tools["get_research_task"].description
            assert "待人工审核" in tools["submit_candidates"].description

            capabilities = envelope(await session.call_tool("get_capabilities", {}))
            data = capabilities["data"]
            assert capabilities["request_id"] is None
            assert data["application"] == "JXD-LEADS-001"
            assert data["version"] == "0.5.0"
            assert data["schema_version"] == "1.3"
            assert data["tools"] == list(TOOL_NAMES)
            assert data["send_messages"] is False
            assert data["live_receiver"] is False
            assert data["auto_receive"] is False

            inquiries = envelope(await session.call_tool("list_inquiries", {}))["data"]["items"]
            inquiry = inquiries[0]
            inquiry_queue = envelope(
                await session.call_tool("get_today_queue", {"kind": "inquiry"})
            )["data"]
            assert inquiry_queue["page_size"] == 20
            assert inquiry["id"] in {item["id"] for item in inquiry_queue["items"]}

            missing = await session.call_tool("get_project_context", {"project_id": "missing"})
            missing_envelope = envelope(missing)
            assert missing_envelope["error"]["code"] == "NOT_FOUND"

            proposed_fields = envelope(
                await session.call_tool(
                    "propose_inquiry_fields",
                    {
                        "inquiry_id": inquiry["id"],
                        "fields": {"region": "成都", "scene": "停车场"},
                        "evidence": "合成咨询原文提到成都停车场",
                        "request_id": "synthetic-fields-1",
                    },
                )
            )
            assert proposed_fields["data"]["status"] == "pending"
            inquiry_context = envelope(
                await session.call_tool("get_inquiry_context", {"inquiry_id": inquiry["id"]})
            )["data"]
            assert inquiry_context["region"] is None
            assert inquiry_context["scene"] is None

            invalid_fields = await session.call_tool(
                "propose_inquiry_fields",
                {
                    "inquiry_id": inquiry["id"],
                    "fields": {"status": "done", "demand": "请拨打 13800001111"},
                    "evidence": "越权字段不应写入",
                    "request_id": "synthetic-fields-invalid",
                },
            )
            invalid_fields_envelope = envelope(invalid_fields)
            assert invalid_fields_envelope["error"]["code"] == "VALIDATION_ERROR"
            assert "13800001111" not in json.dumps(invalid_fields.structuredContent, ensure_ascii=False)

            missing_scope = await session.call_tool(
                "create_research_task", {"request_id": "scope-missing"}
            )
            missing_scope_envelope = envelope(missing_scope)
            assert missing_scope_envelope["request_id"] == "scope-missing"
            assert missing_scope_envelope["error"]["code"] == "VALIDATION_ERROR"

            research_args = {
                "request_id": "research-once",
                "region": "合成地区",
                "scene": "合成设备更新",
                "target": 1,
            }
            created = envelope(await session.call_tool("create_research_task", research_args))
            retried = envelope(await session.call_tool("create_research_task", research_args))
            task_id = created["data"]["id"]
            assert task_id == retried["data"]["id"]
            assert created["request_id"] == "research-once"

            conflict = await session.call_tool(
                "create_research_task",
                {**research_args, "region": "另一地区"},
            )
            assert envelope(conflict)["error"]["code"] == "IDEMPOTENCY_CONFLICT"

            task = envelope(await session.call_tool("get_research_task", {"task_id": task_id}))["data"]
            assert task["id"] == task_id
            assert task["region"] == "合成地区"
            assert task["scene"] == "合成设备更新"
            assert task["target"] == 1
            assert task["status"] == "researching"
            assert "先调用 get_capabilities" in task["brief"]
            assert "schema_version" in task["brief"]
            assert all(status in task["brief"] for status in ("completed", "partial", "failed"))
            assert "人工审核" in task["brief"]

            for status in ("completed", "partial", "failed"):
                request_id = f"empty-{status}"
                empty_task = envelope(
                    await session.call_tool(
                        "create_research_task",
                        {
                            "request_id": request_id,
                            "region": "合成地区",
                            "scene": f"空结果{status}",
                            "target": 1,
                        },
                    )
                )["data"]
                empty_result = envelope(
                    await session.call_tool(
                        "submit_candidates",
                        {
                            "task_id": empty_task["id"],
                            "candidates": [],
                            "status": status,
                            "note": f"{status} 合成回执：来源不可达",
                        },
                    )
                )["data"]
                assert empty_result == {"created": 0, "duplicates": 0, "items": []}
                empty_state = envelope(
                    await session.call_tool("get_research_task", {"task_id": empty_task["id"]})
                )["data"]
                assert empty_state["status"] == status
                assert f"{status} 合成回执" in empty_state["note"]

            candidate_args = {
                "task_id": task_id,
                "candidates": [
                    {
                        "company": "合成物业",
                        "project": "合成车库",
                        "region": "成都",
                        "source_url": "https://example.org/test",
                        "evidence": "合成测试证据，无真实客户",
                    }
                ],
                "status": "completed",
                "note": "合成链路完成",
            }
            first = envelope(await session.call_tool("submit_candidates", candidate_args))
            again = envelope(await session.call_tool("submit_candidates", candidate_args))
            assert first["data"]["created"] == 1
            assert again["data"]["duplicates"] == 1
            candidate_id = first["data"]["items"][0]["id"]
            assert again["data"]["items"][0]["id"] == candidate_id
            assert first["data"]["items"][0]["status"] == "pending"

            completed_task = envelope(
                await session.call_tool("get_research_task", {"task_id": task_id})
            )["data"]
            assert completed_task["status"] == "completed"
            assert completed_task["note"] == "合成链路完成"

            candidate_list = envelope(
                await session.call_tool("list_candidates", {"status": "pending", "page_size": 20})
            )["data"]
            assert candidate_id in {item["id"] for item in candidate_list["items"]}
            candidate_queue = envelope(
                await session.call_tool("get_today_queue", {"kind": "candidate"})
            )["data"]
            assert candidate_id in {item["id"] for item in candidate_queue["items"]}

            project_before = envelope(
                await session.call_tool("get_project_context", {"project_id": "test-project"})
            )["data"]
            followup_args = {
                "project_id": "test-project",
                "suggestion": {
                    "summary": "合成摘要",
                    "draft": "合成草稿",
                    "next_action": "合成下一步",
                    "due_date": "2026-11-20",
                },
                "request_id": "test-proposal",
            }
            proposal = envelope(await session.call_tool("propose_followup", followup_args))
            repeated = envelope(await session.call_tool("propose_followup", followup_args))
            assert proposal["data"]["status"] == "pending"
            assert proposal["data"]["id"] == repeated["data"]["id"]
            project_after = envelope(
                await session.call_tool("get_project_context", {"project_id": "test-project"})
            )["data"]
            assert project_after["stage"] == project_before["stage"]
            assert project_after["opportunities"][0]["stage"] == project_before["opportunities"][0]["stage"]
            assert project_after["followups"] == []
            assert project_after["proposals"][0]["status"] == "pending"

            followup_conflict = await session.call_tool(
                "propose_followup",
                {**followup_args, "suggestion": {**followup_args["suggestion"], "summary": "换了内容"}},
            )
            followup_conflict_envelope = envelope(followup_conflict)
            assert followup_conflict_envelope["ok"] is False
            assert followup_conflict_envelope["error"]["code"] in {
                "VALIDATION_ERROR",
                "IDEMPOTENCY_CONFLICT",
            }

            followup_overreach = await session.call_tool(
                "propose_followup",
                {
                    "project_id": "test-project",
                    "suggestion": {"summary": "越权建议", "confirmed": True},
                    "request_id": "followup-invalid",
                },
            )
            assert bool(followup_overreach.isError) is True

            candidate_overreach = await session.call_tool(
                "submit_candidates",
                {
                    **candidate_args,
                    "candidates": [
                        {
                            **candidate_args["candidates"][0],
                            "confirmed": True,
                        }
                    ],
                },
            )
            assert bool(candidate_overreach.isError) is True
