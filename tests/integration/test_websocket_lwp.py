"""WebSocket LWP 协议集成测试"""
import asyncio
import pytest
import json
import os
from pathlib import Path

from src.api.http_client import HttpClient
from src.api.websocket_client import WebSocketClient


def get_auth_path() -> Path:
    """获取 auth.json 路径"""
    data_dir = os.environ.get("XIANYU_DATA_DIR", "/root/.claude/xianyu-tokens")
    return Path(data_dir) / "auth.json"


@pytest.mark.asyncio
async def test_websocket_lwp_full():
    """完整测试 WebSocket LWP 协议：连接、对话列表、消息历史、缓存"""
    auth_path = get_auth_path()
    if not auth_path.exists():
        pytest.skip("auth.json 不存在，需要先登录")
    
    with open(auth_path) as f:
        auth = json.load(f)
    
    cookies = auth.get("cookies", {})
    device_id = auth.get("device_id", "web_" + cookies.get("unb", "default"))
    
    if not cookies:
        pytest.skip("cookies 为空")
    
    http = HttpClient(cookies=cookies, device_id=device_id)
    
    # 先测试 accessToken 是否可用
    token = await http.get_access_token()
    if not token:
        pytest.skip("accessToken API 被限流，跳过测试（请等待 10 分钟后重试）")
    
    ws = WebSocketClient(http)
    
    try:
        # 1. 测试连接
        print("\n=== 1. 测试 WebSocket 连接 ===")
        connected = await ws.connect()
        assert connected is True, "WebSocket 连接失败"
        print("✓ 连接成功")
        
        await asyncio.sleep(3)
        assert ws.is_connected is True, "WebSocket 未完成初始化"
        print("✓ 初始化完成")
        
        # 2. 测试获取对话列表（最新 10 个）
        print("\n=== 2. 测试获取对话列表（最新 10 个）===")
        result = await ws.get_conversation_list(page_size=10)
        assert result.get("success") is True, f"获取对话列表失败: {result.get('error', '')}"
        
        conversations = result.get("conversations", [])
        assert len(conversations) > 0, "对话列表为空"
        print(f"✓ 成功获取 {len(conversations)} 个对话")
        
        for i, conv in enumerate(conversations, 1):
            print(f"  {i}. {conv.get('peer_user_name', '未知')}: {conv.get('last_message', '')[:50]}")
            assert "cid" in conv, "对话缺少 cid"
            assert conv["cid"], "对话 cid 为空"
        
        # 3. 测试对话列表缓存
        print("\n=== 3. 测试对话列表缓存 ===")
        cached_convs = ws.cache.get_conversations(limit=10)
        assert len(cached_convs) == len(conversations), "缓存数量不匹配"
        print(f"✓ 缓存 {len(cached_convs)} 个对话")
        
        for conv in cached_convs:
            assert conv.conversation_id, "缓存对话缺少 conversation_id"
        
        # 4. 测试获取消息历史
        print("\n=== 4. 测试获取消息历史 ===")
        chat_id = conversations[0]["cid"]
        msg_result = await ws.get_message_history(chat_id=chat_id, count=20)
        assert msg_result.get("success") is True, f"获取消息历史失败: {msg_result.get('error', '')}"
        
        messages = msg_result.get("messages", [])
        print(f"✓ 成功获取 {len(messages)} 条消息")
        
        if messages:
            for msg in messages[:3]:
                print(f"  - {msg.get('sender_name', '未知')}: {msg.get('content', '')[:50]}")
        
        # 5. 测试消息历史缓存
        print("\n=== 5. 测试消息历史缓存 ===")
        cached_msgs = ws.cache.get_messages(chat_id, limit=20)
        assert len(cached_msgs) == len(messages), "缓存消息数量不匹配"
        print(f"✓ 缓存 {len(cached_msgs)} 条消息")
        
        print("\n=== 所有测试通过 ✓ ===")
        
    finally:
        await ws.stop()


@pytest.mark.asyncio
async def test_conversation_list_10():
    """专门测试获取最新 10 个对话"""
    auth_path = get_auth_path()
    if not auth_path.exists():
        pytest.skip("auth.json 不存在")
    
    with open(auth_path) as f:
        auth = json.load(f)
    
    cookies = auth.get("cookies", {})
    device_id = auth.get("device_id", "web_" + cookies.get("unb", "default"))
    
    if not cookies:
        pytest.skip("cookies 为空")
    
    http = HttpClient(cookies=cookies, device_id=device_id)
    
    # 先测试 accessToken
    token = await http.get_access_token()
    if not token:
        pytest.skip("accessToken API 被限流")
    
    ws = WebSocketClient(http)
    
    try:
        connected = await ws.connect()
        assert connected is True
        
        await asyncio.sleep(3)
        assert ws.is_connected is True
        
        result = await ws.get_conversation_list(page_size=10)
        assert result.get("success") is True
        
        conversations = result.get("conversations", [])
        print(f"\n最新 {len(conversations)} 个对话:")
        for i, c in enumerate(conversations, 1):
            name = c.get("peer_user_name", "未知")
            msg = c.get("last_message", "")[:50]
            unread = c.get("unread_count", 0)
            print(f"{i}. {name} (未读:{unread}) - {msg}")
        
        assert len(conversations) > 0, "必须至少有 1 个对话"
        
    finally:
        await ws.stop()