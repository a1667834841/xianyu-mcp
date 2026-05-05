"""
HTTP MCP 客户端集成测试
验证 SSE 连接和工具调用
"""

import requests
import json
import os
import pytest
import time
import subprocess
import sys
from pathlib import Path

from starlette.testclient import TestClient


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_build_app_exposes_streamable_http_mcp_route():
    """确保 FastMCP streamable HTTP 入口实际挂载到 Starlette 应用。"""
    from mcp_server.http_server import build_app

    paths = [getattr(route, "path", None) for route in build_app().routes]

    assert "/mcp" in paths


def test_streamable_http_mcp_route_handles_initialize(monkeypatch):
    """确保 /mcp 不只是存在路由，还初始化了 streamable HTTP session manager。"""
    from mcp_server import http_server

    async def noop_manager():
        return None

    monkeypatch.setattr(http_server, "initialize_manager", noop_manager)
    monkeypatch.setattr(http_server, "shutdown_manager", noop_manager)

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "clientInfo": {"name": "test-client", "version": "1.0"},
            "capabilities": {},
        },
    }

    with TestClient(http_server.build_app(), base_url="http://127.0.0.1:8080") as client:
        resp = client.post(
            "/mcp",
            json=payload,
            headers={"Accept": "application/json, text/event-stream"},
        )

    assert resp.status_code == 200
    assert resp.headers.get("mcp-session-id")
    assert '"method":"initialize"' not in resp.text
    assert '"result"' in resp.text


def _call_mcp_dev(*args):
    last_error = None
    for _ in range(10):
        result = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "scripts" / "mcp-dev"), "call", *args],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            try:
                return json.loads(result.stdout)
            except json.JSONDecodeError as exc:
                last_error = exc
        else:
            last_error = subprocess.CalledProcessError(
                result.returncode,
                result.args,
                output=result.stdout,
                stderr=result.stderr,
            )
        time.sleep(1)

    raise last_error


def test_sse_connection():
    """测试 SSE 连接建立"""
    try:
        resp = requests.get("http://localhost:8080/sse", stream=True, timeout=5)
    except requests.RequestException as exc:
        pytest.skip(f"MCP Server 未运行或无法连接: {exc}")
    assert resp.status_code == 200

    session_id = None
    for line in resp.iter_lines(decode_unicode=True):
        if line and "session_id=" in line:
            session_id = line.split("session_id=")[1]
            break

    assert session_id is not None
    print(f"✓ SSE 连接成功，session_id: {session_id}")
    return session_id


def test_initialize(session_id):
    """测试 MCP initialize 流程"""
    post_url = f"http://localhost:8080/messages/?session_id={session_id}"

    init_request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "clientInfo": {"name": "test-client", "version": "1.0"},
            "capabilities": {},
        },
    }

    resp = requests.post(post_url, json=init_request, timeout=3)
    assert resp.status_code == 202
    print(f"✓ initialize 请求发送成功")


def test_tools_list(session_id):
    """测试 tools/list 调用"""
    post_url = f"http://localhost:8080/messages/?session_id={session_id}"

    request = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}

    resp = requests.post(post_url, json=request, timeout=3)
    assert resp.status_code == 202
    print(f"✓ tools/list 请求发送成功")


def test_xianyu_check_session(session_id):
    """测试 xianyu_check_session 工具"""
    post_url = f"http://localhost:8080/messages/?session_id={session_id}"

    request = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {"name": "xianyu_check_session", "arguments": {}},
    }

    resp = requests.post(post_url, json=request, timeout=5)
    assert resp.status_code == 202
    print(f"✓ xianyu_check_session 调用请求发送成功")


def test_xianyu_ws_send_real_message_with_image():
    """真实发送带图片消息。需要显式设置环境变量，避免误发。"""
    target_id = os.environ.get("XIANYU_REAL_SEND_TARGET_ID")
    content = os.environ.get("XIANYU_REAL_SEND_CONTENT")
    image_url = os.environ.get("XIANYU_REAL_SEND_IMAGE_URL")
    conversation_id = os.environ.get("XIANYU_REAL_SEND_CONVERSATION_ID", "")

    if not target_id or not content or not image_url:
        pytest.skip(
            "set XIANYU_REAL_SEND_TARGET_ID, XIANYU_REAL_SEND_CONTENT, "
            "and XIANYU_REAL_SEND_IMAGE_URL to send a real message"
        )

    payload = _call_mcp_dev(
        "xianyu_ws_send",
        "--target-id",
        target_id,
        "--content",
        content,
        "--image-url",
        image_url,
        "--conversation-id",
        conversation_id,
    )

    assert payload["success"] is True


if __name__ == "__main__":
    print("=" * 50)
    print("HTTP MCP 客户端集成测试")
    print("=" * 50)

    session_id = test_sse_connection()
    test_initialize(session_id)
    time.sleep(1)
    test_tools_list(session_id)
    time.sleep(1)
    test_xianyu_check_session(session_id)

    print("=" * 50)
    print("所有测试通过！")
    print("=" * 50)
