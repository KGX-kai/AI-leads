"""TEMP verification probe: web + real MCP stdio process writing one new temp DB."""

import asyncio
import json
import os
import re
import sys
import tempfile
import threading
import time
from pathlib import Path

if __name__ == "__main__" and "--worker" in sys.argv:
    from jxd_leads.db import Database
    from jxd_leads.mcp_server import create_mcp
    from jxd_leads.security import Vault
    from jxd_leads.service import Service

    directory = Path(sys.argv[sys.argv.index("--worker") + 1])
    db = Database(directory / "leads.db", approved_directory=directory)
    create_mcp(Service(db, Vault(os.environ["JX_PROBE_KEY"].encode()))).run(transport="stdio")
    raise SystemExit(0)

import httpx
import uvicorn
from cryptography.fernet import Fernet
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from jxd_leads.db import Database
from jxd_leads.schemas import ResearchInput
from jxd_leads.security import Vault
from jxd_leads.service import Service
from jxd_leads.web import create_app


def candidate(index):
    return {
        "company": f"并发合成公司{index}",
        "project": f"并发合成项目{index}",
        "region": "四川成都",
        "address": f"合成路{index}号",
        "source_url": f"https://example.org/probe/{index}",
        "source_type": "公开网络",
        "evidence": "并发探针合成证据，无真实客户。",
    }


async def main():
    root = Path(tempfile.mkdtemp(prefix="jxd-concurrency-"))
    db = Database(root / "leads.db", approved_directory=root)
    db.migrate()
    key = Fernet.generate_key()
    service = Service(db, Vault(key))
    task = service.create_research(ResearchInput(region="四川成都", scene="公共建筑", target=30))
    app = create_app(service, testing=True)
    config = uvicorn.Config(app, host="127.0.0.1", port=8799, log_level="error")
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        if server.started:
            break
        await asyncio.sleep(0.05)
    assert server.started, "probe web did not start"

    params = StdioServerParameters(
        command=sys.executable,
        args=[__file__, "--worker", str(root)],
        env={**os.environ, "PYTHONPATH": str(Path(__file__).parents[4] / "src"), "JX_PROBE_KEY": key.decode()},
    )
    rounds = []
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8799") as client:
        html = (await client.get("/")).text
        csrf = re.search('name="csrf-token" content="([^"]+)"', html).group(1)
        async with stdio_client(params) as (reader, writer), ClientSession(reader, writer) as session:
            await session.initialize()
            for index in range(1, 11):
                async def web_call():
                    started = time.perf_counter()
                    try:
                        response = await client.post(
                            "/api/v1/candidates",
                            json=candidate(index),
                            headers={"X-CSRF-Token": csrf, "Idempotency-Key": f"probe-web-{index}"},
                        )
                        return {
                            "status": response.status_code,
                            "ms": round((time.perf_counter() - started) * 1000, 1),
                            "body": response.text[:300],
                        }
                    except Exception as error:  # noqa: BLE001
                        return {"status": 0, "ms": round((time.perf_counter() - started) * 1000, 1), "error": repr(error)}

                async def mcp_call():
                    started = time.perf_counter()
                    try:
                        result = await session.call_tool(
                            "submit_candidates",
                            {
                                "task_id": task["id"],
                                "candidates": [candidate(index + 100)],
                                "request_id": f"probe-mcp-{index}",
                            },
                        )
                        payload = result.structuredContent or json.loads(result.content[0].text)
                        return {
                            "ok": payload["ok"],
                            "code": (payload["error"] or {}).get("code"),
                            "ms": round((time.perf_counter() - started) * 1000, 1),
                        }
                    except Exception as error:  # noqa: BLE001
                        return {"ok": False, "error": repr(error), "ms": round((time.perf_counter() - started) * 1000, 1)}

                mcp_result, web_result = await asyncio.gather(mcp_call(), web_call())
                rounds.append({"round": index, "mcp": mcp_result, "web": web_result})
    server.should_exit = True
    serialized = json.dumps(rounds, ensure_ascii=False)
    summary = {
        "rounds": rounds,
        "web_503": sum(r["web"].get("status") == 503 for r in rounds),
        "lock_timeouts": serialized.count("database is locked") + serialized.count("TEMPORARY_UNAVAILABLE"),
        "mcp_failures": sum(not r["mcp"].get("ok") for r in rounds),
        "web_failures": sum(r["web"].get("status") != 200 for r in rounds),
        "max_ms": max(max(r["mcp"]["ms"], r["web"]["ms"]) for r in rounds),
        "candidate_rows": len(service.candidates()),
        "temp_db": str(root / "leads.db"),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
