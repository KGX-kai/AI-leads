"""Exercise the unchanged stdin protocol against an isolated MCP subprocess probe."""

import json
import shutil
import subprocess
import sys

import pytest
from mcp.client.stdio import get_default_environment

from jxd_leads.db import APPROVED_DATA_DIR_ENV, ROOT


@pytest.fixture
def fallback(tmp_path):
    script = tmp_path / "scripts/agent-call.py"
    script.parent.mkdir()
    shutil.copy2(ROOT / "scripts/agent-call.py", script)
    executable = tmp_path / ".venv/bin/python"
    executable.parent.mkdir(parents=True)
    executable.write_text(f"#!{sys.executable}\n" + '''
import os
from pathlib import Path
from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, TextContent

Path(__file__).resolve().parents[2].joinpath("child-started").touch()
mcp = FastMCP("synthetic directory probe")

@mcp.tool()
def get_capabilities() -> CallToolResult:
    return CallToolResult(content=[], structuredContent={
        "schema_version": "1.3", "ok": True, "request_id": None, "error": None,
        "data": {"data_dir": os.environ.get("JXD_DATA_DIR"),
                 "approved_data_dir": os.environ.get("JXD_APPROVED_DATA_DIR"),
                 "unrelated_forwarded": "UNRELATED_TEST_FLAG" in os.environ},
    })

@mcp.tool()
def get_research_task(task_id: str) -> CallToolResult:
    if task_id == "legacy-missing":
        return CallToolResult(content=[TextContent(type="text", text="synthetic legacy not found")], isError=True)
    return CallToolResult(content=[TextContent(type="text", text="synthetic not found")], isError=True,
        structuredContent={"schema_version": "1.3", "ok": False, "request_id": None, "data": None,
                           "error": {"code": "NOT_FOUND", "message": "synthetic", "retryable": False}})

mcp.run(transport="stdio")
''')
    executable.chmod(0o700)

    def call(payload, data_dir=None, approved_dir=None):
        environment = {**get_default_environment(), "PYTHONPATH": str(ROOT / "src"),
                       "PYTHONDONTWRITEBYTECODE": "1", "UNRELATED_TEST_FLAG": "synthetic"}
        if data_dir is not None:
            environment["JXD_DATA_DIR"] = data_dir
        if approved_dir is not None:
            environment[APPROVED_DATA_DIR_ENV] = approved_dir
        return subprocess.run(
            [sys.executable, str(script)], input=json.dumps(payload),
            text=True, capture_output=True, cwd=tmp_path, env=environment, timeout=15, check=False,
        )

    return call, tmp_path


def test_fallback_preserves_directory_selection_and_does_not_forward_unrelated_env(fallback):
    call, folder = fallback
    selected = str(folder / "approved synthetic data")
    result = call({"tool": "get_capabilities", "arguments": {}}, selected, selected)
    assert result.returncode == 0, result.stderr
    receipt = json.loads(result.stdout)
    assert set(receipt) == {"schema_version", "ok", "request_id", "data", "error"}
    assert receipt["schema_version"] == "1.3" and receipt["ok"]
    assert receipt["data"] == {
        "data_dir": selected,
        "approved_data_dir": selected,
        "unrelated_forwarded": False,
    }


@pytest.mark.parametrize("invalid", [None, "", "   ", "relative/synthetic"])
def test_fallback_rejects_missing_blank_or_relative_directory_before_starting_child(fallback, invalid):
    call, folder = fallback
    result = call({"tool": "get_capabilities", "arguments": {}}, invalid, invalid)
    receipt = json.loads(result.stdout)
    assert result.returncode == 2 and receipt["ok"] is False
    assert "数据目录" in receipt["error"]
    assert "工具或输入格式不正确" not in receipt["error"]
    assert not (folder / "child-started").exists()


def test_fallback_reports_missing_virtual_environment_before_start(tmp_path):
    script = tmp_path / "missing-venv/scripts/agent-call.py"
    script.parent.mkdir(parents=True)
    shutil.copy2(ROOT / "scripts/agent-call.py", script)
    selected = str(tmp_path / "approved synthetic data")
    environment = {
        **get_default_environment(),
        "PYTHONPATH": str(ROOT / "src"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "JXD_DATA_DIR": selected,
        APPROVED_DATA_DIR_ENV: selected,
    }

    result = subprocess.run(
        [sys.executable, str(script)],
        input=json.dumps({"tool": "get_capabilities", "arguments": {}}),
        text=True,
        capture_output=True,
        cwd=script.parent,
        env=environment,
        timeout=15,
        check=False,
    )

    receipt = json.loads(result.stdout)
    assert result.returncode == 2 and receipt["ok"] is False
    assert "缺少 .venv/bin/python" in receipt["error"]
    assert not (tmp_path / "missing-venv/child-started").exists()


def test_fallback_requires_independent_approved_directory(fallback):
    call, folder = fallback
    selected = str(folder / "approved synthetic data")
    result = call({"tool": "get_capabilities", "arguments": {}}, selected)
    assert result.returncode == 2 and json.loads(result.stdout)["ok"] is False
    assert not (folder / "child-started").exists()


def test_fallback_rejects_another_valid_directory_configuration(fallback):
    call, folder = fallback
    approved = str(folder / "approved synthetic data")
    other = str(folder / "other synthetic data")
    result = call({"tool": "get_capabilities", "arguments": {}}, other, approved)
    assert result.returncode == 2 and json.loads(result.stdout)["ok"] is False
    assert not (folder / "child-started").exists()


@pytest.mark.parametrize("payload", [
    {"tool": "get_capabilities", "arguments": {}, "extra": True},
    {"tool": "unregistered", "arguments": {}},
])
def test_fallback_keeps_two_key_stdin_protocol(fallback, payload):
    call, folder = fallback
    result = call(payload)
    assert result.returncode == 2 and json.loads(result.stdout)["ok"] is False
    assert not (folder / "child-started").exists()


def test_fallback_preserves_mcp_business_error_and_exit_code(fallback):
    call, folder = fallback
    result = call(
        {"tool": "get_research_task", "arguments": {"task_id": "synthetic-missing"}},
        str(folder / "approved synthetic data"),
        str(folder / "approved synthetic data"),
    )
    receipt = json.loads(result.stdout)
    assert result.returncode == 1 and receipt["ok"] is False
    assert receipt["error"]["code"] == "NOT_FOUND" and receipt["schema_version"] == "1.3"


def test_fallback_legacy_error_uses_current_envelope(fallback):
    call, folder = fallback
    result = call(
        {"tool": "get_research_task", "arguments": {"task_id": "legacy-missing"}},
        str(folder / "approved synthetic data"),
        str(folder / "approved synthetic data"),
    )
    receipt = json.loads(result.stdout)
    assert result.returncode == 1 and receipt["ok"] is False
    assert set(receipt) == {"schema_version", "ok", "request_id", "data", "error"}
    assert receipt["schema_version"] == "1.3" and receipt["request_id"] is None
    assert receipt["error"]["code"] == "LEGACY_ERROR"
