"""集成测试 - WebSocket 自动更新缓存"""
import asyncio
import pytest
from src.api.http_client import HttpClient, load_local_auth
from src.api.websocket_client import WebSocketClient
from src.api.message_codec import MessageSegment, TextContent
from src.api.types import Conversation, ChatMessage


@pytest.mark.asyncio
async def test_websocket_auto_update_cache():
    """测试 WebSocket 自动更新缓存"""
    cookies = load_local_auth()
    if not cookies:
        pytest.skip("未找到 cookies，请先登录")
    
    http_client = HttpClient(cookies=cookies, device_id='')
    ws_client = WebSocketClient(http_client)
    
    # 模拟收到消息
    event = {
        "cid": "test_conv_1",
        "sender_id": "test_user_1",
        "sender_name": "测试用户1",
        "timestamp": 1000.0,
        "segments": [{"content": {"type": "text", "text": "测试消息1"}}]
    }
    
    segments = [MessageSegment(content=TextContent(text="测试消息1"))]
    
    # 直接调用缓存更新方法
    ws_client._update_cache_from_event(event, segments)
    
    # 验证缓存已更新 - 对话列表
    conversations = ws_client.cache.get_conversations()
    assert len(conversations) == 1
    assert conversations[0].conversation_id == "test_conv_1"
    assert conversations[0].user_id == "test_user_1"
    assert conversations[0].user_nick == "测试用户1"
    assert conversations[0].last_message == "测试消息1"
    
    # 验证缓存已更新 - 消息列表
    messages = ws_client.cache.get_messages("test_conv_1")
    assert len(messages) == 1
    assert messages[0].conversation_id == "test_conv_1"
    assert messages[0].sender_id == "test_user_1"
    assert messages[0].content.text == "测试消息1"


@pytest.mark.asyncio
async def test_cache_multiple_messages():
    """测试缓存多条消息"""
    cookies = load_local_auth()
    if not cookies:
        pytest.skip("未找到 cookies，请先登录")
    
    http_client = HttpClient(cookies=cookies, device_id='')
    ws_client = WebSocketClient(http_client)
    
    # 模拟同一对话的多条消息
    for i in range(3):
        event = {
            "cid": "test_conv_2",
            "sender_id": "test_user_2",
            "sender_name": "测试用户2",
            "timestamp": 1000.0 + i,
            "segments": [{"content": {"type": "text", "text": f"消息{i+1}"}}]
        }
        segments = [MessageSegment(content=TextContent(text=f"消息{i+1}"))]
        ws_client._update_cache_from_event(event, segments)
    
    # 验证对话列表只有1个对话
    conversations = ws_client.cache.get_conversations()
    assert len(conversations) == 1
    assert conversations[0].conversation_id == "test_conv_2"
    
    # 验证消息列表有3条消息
    messages = ws_client.cache.get_messages("test_conv_2")
    assert len(messages) == 3


@pytest.mark.asyncio
async def test_cache_multiple_conversations():
    """测试缓存多个对话"""
    cookies = load_local_auth()
    if not cookies:
        pytest.skip("未找到 cookies，请先登录")
    
    http_client = HttpClient(cookies=cookies, device_id='')
    ws_client = WebSocketClient(http_client)
    
    # 模拟多个对话的消息
    for i in range(3):
        event = {
            "cid": f"test_conv_{i+3}",
            "sender_id": f"test_user_{i+3}",
            "sender_name": f"测试用户{i+3}",
            "timestamp": 1000.0 + i,
            "segments": [{"content": {"type": "text", "text": f"对话{i+3}的消息"}}]
        }
        segments = [MessageSegment(content=TextContent(text=f"对话{i+3}的消息"))]
        ws_client._update_cache_from_event(event, segments)
    
    # 验证对话列表有3个对话
    conversations = ws_client.cache.get_conversations()
    assert len(conversations) == 3
    
    # 验证每个对话都有消息
    for i in range(3):
        messages = ws_client.cache.get_messages(f"test_conv_{i+3}")
        assert len(messages) == 1


@pytest.mark.asyncio
async def test_cache_clear():
    """测试清空缓存"""
    cookies = load_local_auth()
    if not cookies:
        pytest.skip("未找到 cookies，请先登录")
    
    http_client = HttpClient(cookies=cookies, device_id='')
    ws_client = WebSocketClient(http_client)
    
    # 添加一些消息
    event = {
        "cid": "test_conv_clear",
        "sender_id": "test_user_clear",
        "sender_name": "清空测试用户",
        "timestamp": 1000.0,
        "segments": [{"content": {"type": "text", "text": "将被清空的消息"}}]
    }
    segments = [MessageSegment(content=TextContent(text="将被清空的消息"))]
    ws_client._update_cache_from_event(event, segments)
    
    # 验证缓存有数据
    conversations = ws_client.cache.get_conversations()
    assert len(conversations) == 1
    
    # 清空缓存
    ws_client.cache.clear()
    
    # 验证缓存已清空
    conversations = ws_client.cache.get_conversations()
    assert len(conversations) == 0
    
    messages = ws_client.cache.get_messages("test_conv_clear")
    assert len(messages) == 0