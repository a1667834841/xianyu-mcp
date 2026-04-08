"""
HTTP MCP 客户端集成测试
验证 SSE 连接和工具调用
"""

import requests
import json
import time


def test_sse_connection():
    """测试 SSE 连接建立"""
    resp = requests.get('http://localhost:8080/sse', stream=True, timeout=5)
    assert resp.status_code == 200

    session_id = None
    for line in resp.iter_lines(decode_unicode=True):
        if line and 'session_id=' in line:
            session_id = line.split('session_id=')[1]
            break

    assert session_id is not None
    print(f"✓ SSE 连接成功，session_id: {session_id}")
    return session_id


def test_initialize(session_id):
    """测试 MCP initialize 流程"""
    post_url = f'http://localhost:8080/messages/?session_id={session_id}'

    init_request = {
        'jsonrpc': '2.0',
        'id': 1,
        'method': 'initialize',
        'params': {
            'protocolVersion': '2024-11-05',
            'clientInfo': {'name': 'test-client', 'version': '1.0'},
            'capabilities': {}
        }
    }

    resp = requests.post(post_url, json=init_request, timeout=3)
    assert resp.status_code == 202
    print(f"✓ initialize 请求发送成功")


def test_tools_list(session_id):
    """测试 tools/list 调用"""
    post_url = f'http://localhost:8080/messages/?session_id={session_id}'

    request = {
        'jsonrpc': '2.0',
        'id': 2,
        'method': 'tools/list',
        'params': {}
    }

    resp = requests.post(post_url, json=request, timeout=3)
    assert resp.status_code == 202
    print(f"✓ tools/list 请求发送成功")


def test_xianyu_check_session(session_id):
    """测试 xianyu_check_session 工具"""
    post_url = f'http://localhost:8080/messages/?session_id={session_id}'

    request = {
        'jsonrpc': '2.0',
        'id': 3,
        'method': 'tools/call',
        'params': {
            'name': 'xianyu_check_session',
            'arguments': {}
        }
    }

    resp = requests.post(post_url, json=request, timeout=5)
    assert resp.status_code == 202
    print(f"✓ xianyu_check_session 调用请求发送成功")


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