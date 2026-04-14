"""
HTTP MCP 客户端集成测试
验证 SSE 连接和工具调用
"""

import requests
import json
import time
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


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


def _pick_debug_user_id():
    payload = _call_mcp_dev("xianyu_list_users")
    assert payload["success"] is True
    users = payload.get("users") or []
    assert users, "expected at least one registered user"
    return users[0]["user_id"]


def test_sse_connection():
    """测试 SSE 连接建立"""
    resp = requests.get("http://localhost:8080/sse", stream=True, timeout=5)
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


def test_xianyu_debug_snapshot_uploads_real_screenshot():
    """测试 xianyu_debug_snapshot 真实截图并上传到 R2"""
    user_id = _pick_debug_user_id()

    overview = _call_mcp_dev("xianyu_browser_overview", "--user-id", user_id)
    assert overview["success"] is True

    payload = _call_mcp_dev("xianyu_debug_snapshot", "--user-id", user_id)

    assert payload["success"] is True
    assert payload["user_id"] == user_id
    assert payload["screenshot"]["uploaded"] is True
    assert payload["screenshot"]["public_url"].startswith("https://img.ggball.top/")
    assert payload["page"]["url"]


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
