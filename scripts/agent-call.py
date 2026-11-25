#!/usr/bin/env python3
"""Project-local MCP transport fallback; accepts only the registered restricted tools."""

import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from jxd_leads.db import APPROVED_DATA_DIR_ENV, resolve_runtime_data_dir
from jxd_leads.errors import BusinessError
from jxd_leads.mcp_server import TOOL_NAMES

ALLOWED = set(TOOL_NAMES)
ROOT = Path(__file__).resolve().parents[1]


async def call(payload):
    if (
        set(payload) != {"tool", "arguments"}
        or payload["tool"] not in ALLOWED
        or not isinstance(payload["arguments"], dict)
    ):
        raise ValueError("只允许已注册的 MCP 工具及其结构化参数")
    data_dir = str(
        resolve_runtime_data_dir(os.environ.get("JXD_DATA_DIR"), os.environ.get(APPROVED_DATA_DIR_ENV))
    )
    interpreter = ROOT / ".venv/bin/python"
    if not interpreter.is_file():
        raise BusinessError(
            "候选目录缺少 .venv/bin/python；请按切换清单建立虚拟环境后再启动备用入口",
            "MCP_PYTHON_MISSING",
        )
    params = StdioServerParameters(
        command=str(interpreter), args=["-m", "jxd_leads.mcp_server"], cwd=str(ROOT),
        env={"JXD_DATA_DIR": data_dir, APPROVED_DATA_DIR_ENV: data_dir},
    )
    async with stdio_client(params) as (reader, writer), ClientSession(reader, writer) as session:
        await session.initialize()
        response = await session.call_tool(payload["tool"], payload["arguments"])
        if response.structuredContent is not None:
            data = response.structuredContent
        else:
            texts = [item.text for item in response.content if item.type == "text"]
            try:
                data = json.loads(texts[0]) if len(texts) == 1 else texts
            except json.JSONDecodeError:
                data = texts
        if isinstance(data, dict) and "schema_version" in data:
            if response.isError:
                data["ok"] = False
            return data
        failed = response.isError or (isinstance(data, dict) and (bool(data.get("error")) or data.get("ok") is False))
        return {
            "schema_version": "1.3",
            "ok": not failed,
            "request_id": None,
            "data": None if failed else data,
            "error": {"code": "LEGACY_ERROR", "message": "MCP调用失败，请检查参数与连接", "retryable": False}
            if failed
            else None,
        }


if __name__ == "__main__":
    raw = sys.stdin.buffer.read(512 * 1024 + 1)
    if len(raw) > 512 * 1024:
        raise SystemExit("输入超过限制")
    try:
        result = asyncio.run(call(json.loads(raw)))
    except BusinessError as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        raise SystemExit(2) from None
    except (ValueError, TypeError, KeyError):
        print(json.dumps({"ok": False, "error": "工具或输入格式不正确"}, ensure_ascii=False))
        raise SystemExit(2)
    print(json.dumps(result, ensure_ascii=False))

    raise SystemExit(0 if result.get("ok") else 1)
