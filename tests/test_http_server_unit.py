"""
Unit tests for MCP server HTTP/SSE wiring.
"""

from __future__ import annotations

import json
import logging
import sys
import types

import pytest


def _install_fake_mcp(monkeypatch):
    """
    The real `mcp` dependency isn't available in this execution environment.
    These unit tests only need to import the HTTP/SSE server entrypoint, so we
    install a minimal FastMCP stub.
    """

    sys.modules.pop("mcp_server.http_server", None)

    mcp_mod = types.ModuleType("mcp")
    mcp_server_mod = types.ModuleType("mcp.server")
    mcp_server_fastmcp_mod = types.ModuleType("mcp.server.fastmcp")

    class FastMCP:
        def __init__(self, *args, **kwargs):
            return None

        def tool(self):
            def deco(fn):
                return fn

            return deco

    mcp_server_fastmcp_mod.FastMCP = FastMCP

    # Wire module hierarchy (attributes + sys.modules)
    mcp_mod.server = mcp_server_mod
    mcp_server_mod.fastmcp = mcp_server_fastmcp_mod

    for name, module in (
        ("mcp", mcp_mod),
        ("mcp.server", mcp_server_mod),
        ("mcp.server.fastmcp", mcp_server_fastmcp_mod),
    ):
        monkeypatch.setitem(sys.modules, name, module)


def test_install_fake_mcp_clears_cached_http_server_module(monkeypatch):
    cached_module = types.ModuleType("mcp_server.http_server")
    cached_module.cached_only = True
    monkeypatch.setitem(sys.modules, "mcp_server.http_server", cached_module)

    _install_fake_mcp(monkeypatch)

    import mcp_server.http_server as http_server

    assert http_server is not cached_module
    assert hasattr(http_server, "xianyu_login")


@pytest.mark.asyncio
async def test_xianyu_search_returns_requested_and_stop_reason(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.http_server as http_server

    class FakeClient:
        async def search(self, keyword, rows=30, min_price=None, max_price=None, free_ship=False, sort_field="", sort_order=""):
            return {
                "success": True,
                "user_id": "user-001",
                "slot_id": "slot-1",
                "requested": rows,
                "total": 1,
                "stop_reason": "stale_limit",
                "stale_pages": 3,
                "items": [],
                "engine_used": "http_api",
                "fallback_reason": None,
                "pages_fetched": 1,
            }

    monkeypatch.setattr(http_server, "get_client", lambda: FakeClient())

    payload = json.loads(await http_server.xianyu_search(keyword="键盘", rows=100))

    assert payload["requested"] == 100
    assert payload["total"] == 1
    assert payload["stop_reason"] == "stale_limit"
    assert payload["stale_pages"] == 3


@pytest.mark.asyncio
async def test_xianyu_search_returns_engine_metadata(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.http_server as http_server

    class FakeClient:
        async def search(self, keyword, user_id=None, **options):
            return {
                "success": True,
                "user_id": "user-001",
                "slot_id": "slot-1",
                "requested": 10,
                "total": 1,
                "stop_reason": "target_reached",
                "stale_pages": 0,
                "items": [],
                "engine_used": "page_api",
                "fallback_reason": None,
                "pages_fetched": 1,
            }

    monkeypatch.setattr(http_server, "get_client", lambda: FakeClient())

    payload = json.loads(await http_server.xianyu_search(keyword="泡泡玛特", rows=10))

    assert payload["engine_used"] == "page_api"
    assert payload["fallback_reason"] is None
    assert payload["pages_fetched"] == 1


@pytest.mark.asyncio
async def test_xianyu_check_session_returns_formatted_last_updated_at(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.http_server as http_server

    class FakeClient:
        async def check_session(self):
            return {
                "valid": True,
                "last_updated_at": "2026-04-09 15:16:17",
            }

    monkeypatch.setattr(http_server, "get_client", lambda: FakeClient())

    payload = json.loads(await http_server.xianyu_check_session(user_id="user-001"))

    assert payload["valid"] is True
    assert payload["last_updated_at"] == "2026-04-09 15:16:17"


@pytest.mark.asyncio
async def test_xianyu_check_session_returns_null_when_last_updated_missing(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.http_server as http_server

    class FakeClient:
        async def check_session(self):
            return {"valid": False, "last_updated_at": None}

    monkeypatch.setattr(http_server, "get_client", lambda: FakeClient())

    payload = json.loads(await http_server.xianyu_check_session(user_id="user-001"))

    assert payload["valid"] is False
    assert payload["last_updated_at"] is None


@pytest.mark.asyncio
async def test_xianyu_suggest_keywords_returns_manager_payload(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.http_server as http_server

    class FakeHttpClient:
        async def suggest_keywords(self, input_words="x"):
            return {
                "success": True,
                "user_id": "user-001",
                "slot_id": "slot-1",
                "input_words": input_words,
                "keywords": ["显卡"],
                "raw": {},
            }

    class FakeClient:
        http_client = FakeHttpClient()

    monkeypatch.setattr(http_server, "get_client", lambda: FakeClient())

    payload = json.loads(await http_server.xianyu_suggest_keywords(input_words="x"))

    assert payload["success"] is True
    assert payload["user_id"] == "user-001"
    assert payload["keywords"] == ["显卡"]


@pytest.mark.asyncio
async def test_http_xianyu_publish_maps_public_params_to_core_options(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.http_server as http_server

    captured = {}

    class FakeClient:
        async def publish(self, **kwargs):
            captured.update(kwargs)
            return {"success": True, "item_id": "item-001"}

    monkeypatch.setattr(http_server, "get_client", lambda: FakeClient())

    payload = json.loads(
        await http_server.xianyu_publish(
            images_paths="/tmp/a.jpg",
            title="新标题",
            current_price=88.0,
            original_price=128.0,
            shipping="包邮",
        )
    )

    assert payload["success"] is True
    assert captured == {
        "images_paths": ["/tmp/a.jpg"],
        "title": "新标题",
        "price": {"current_price": 88.0, "original_price": 128.0},
        "shipping": "包邮",
        "self_pickup": False,
        "post_price": 0,
    }


@pytest.mark.asyncio
async def test_http_xianyu_publish_from_item_url_delegates_to_client(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.http_server as http_server

    class FakeClient:
        async def publish_from_item_url(self, item_url: str):
            assert item_url == "https://www.goofish.com/item?id=1047155930582"
            return {
                "success": True,
                "source_platform": "xianyu",
                "source_item_url": item_url,
                "published_item_id": "item-001",
                "published_item_url": "https://www.goofish.com/item?id=item-001",
                "selected_price": 88.0,
                "logs": [],
            }

    monkeypatch.setattr(http_server, "get_client", lambda: FakeClient())

    payload = json.loads(
        await http_server.xianyu_publish_from_item_url(
            item_url="https://www.goofish.com/item?id=1047155930582"
        )
    )

    assert payload == {
        "success": True,
        "source_platform": "xianyu",
        "source_item_url": "https://www.goofish.com/item?id=1047155930582",
        "published_item_id": "item-001",
        "published_item_url": "https://www.goofish.com/item?id=item-001",
        "selected_price": 88.0,
        "logs": [],
    }


@pytest.mark.asyncio
async def test_http_create_conversation_success(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.http_server as http_server

    class FakeClient:
        async def create_conversation(self, item_url):
            assert item_url == "https://www.goofish.com/item?id=1047155930582"
            return {
                "success": True,
                "conversation_id": "conv-123",
                "item_id": "1047155930582",
                "message": "对话已创建并已发送问候语",
            }

    monkeypatch.setattr(http_server, "get_client", lambda: FakeClient())

    payload = json.loads(
        await http_server.xianyu_create_conversation(
            item_url="https://www.goofish.com/item?id=1047155930582"
        )
    )

    assert payload == {
        "success": True,
        "conversation_id": "conv-123",
        "item_id": "1047155930582",
        "message": "对话已创建并已发送问候语",
    }


@pytest.mark.asyncio
async def test_http_create_conversation_returns_greeting_send_failure(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.http_server as http_server

    class FakeClient:
        async def create_conversation(self, item_url):
            assert item_url == "https://www.goofish.com/item?id=1047155930582"
            return {
                "success": False,
                "error_code": "GREETING_SEND_FAILED",
                "conversation_id": "conv-123",
                "item_id": "1047155930582",
                "message": "默认问候语发送失败: 发送失败",
            }

    monkeypatch.setattr(http_server, "get_client", lambda: FakeClient())

    payload = json.loads(
        await http_server.xianyu_create_conversation(
            item_url="https://www.goofish.com/item?id=1047155930582"
        )
    )

    assert payload == {
        "success": False,
        "error_code": "GREETING_SEND_FAILED",
        "conversation_id": "conv-123",
        "item_id": "1047155930582",
        "message": "默认问候语发送失败: 发送失败",
    }


@pytest.mark.asyncio
async def test_http_create_conversation_returns_business_error_for_invalid_url(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.http_server as http_server

    payload = json.loads(await http_server.xianyu_create_conversation(item_url="https://example.com/no-item"))

    assert payload == {
        "success": False,
        "error_code": "INVALID_ITEM_URL",
        "message": "无法从 item_url 提取 item_id",
    }


@pytest.mark.asyncio
async def test_http_create_conversation_accepts_query_id_item_url(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.http_server as http_server

    class FakeClient:
        async def create_conversation(self, item_url):
            assert item_url == "https://www.goofish.com/item?spm=a21ybx.home.feedsCnxh.4.44c43da6SeefKI&id=1046723628406&categoryId=126856275"
            return {
                "success": True,
                "conversation_id": "conv-456",
                "item_id": "1046723628406",
                "message": "对话已创建并已发送问候语",
            }

    monkeypatch.setattr(http_server, "get_client", lambda: FakeClient())

    payload = json.loads(
        await http_server.xianyu_create_conversation(
            item_url="https://www.goofish.com/item?spm=a21ybx.home.feedsCnxh.4.44c43da6SeefKI&id=1046723628406&categoryId=126856275"
        )
    )

    assert payload == {
        "success": True,
        "conversation_id": "conv-456",
        "item_id": "1046723628406",
        "message": "对话已创建并已发送问候语",
    }


@pytest.mark.asyncio
async def test_http_ws_status_returns_detailed_status(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.http_server as http_server

    class FakeClient:
        def get_ws_status(self):
            return {
                "connected": False,
                "status": "failed",
                "last_error": "token failed",
                "started_at": "2026-05-03T01:02:03",
            }

    monkeypatch.setattr(http_server, "get_client", lambda: FakeClient())

    payload = json.loads(await http_server.xianyu_ws_status())

    assert payload["connected"] is False
    assert payload["status"] == "failed"
    assert payload["last_error"] == "token failed"


@pytest.mark.asyncio
async def test_get_access_token_returns_failure_when_empty(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.http_server as http_server

    class FakeHttpClient:
        async def get_access_token(self):
            return ""

    class FakeClient:
        http_client = FakeHttpClient()

    monkeypatch.setattr(http_server, "get_client", lambda: FakeClient())

    payload = json.loads(await http_server.xianyu_get_access_token())

    assert payload == {
        "success": False,
        "error_code": "ACCESS_TOKEN_UNAVAILABLE",
        "message": "accessToken 获取失败",
    }


@pytest.mark.asyncio
async def test_get_access_token_returns_structured_failure_on_exception(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.http_server as http_server

    class FakeHttpClient:
        async def get_access_token(self):
            raise RuntimeError("token endpoint failed")

    class FakeClient:
        http_client = FakeHttpClient()

    monkeypatch.setattr(http_server, "get_client", lambda: FakeClient())

    payload = json.loads(await http_server.xianyu_get_access_token())

    assert payload == {
        "success": False,
        "error_code": "ACCESS_TOKEN_ERROR",
        "message": "accessToken 获取异常",
    }


@pytest.mark.asyncio
async def test_initialize_manager_starts_ws_when_cookie_valid(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.http_server as http_server

    calls = []

    class FakeClient:
        async def check_session(self):
            return {"valid": True}

        async def ensure_ws_started(self, reason):
            calls.append(reason)
            return {"success": True, "status": "starting", "reason": reason}

    monkeypatch.setattr(http_server, "get_client", lambda: FakeClient())

    await http_server.initialize_manager()

    assert calls == ["service_start"]


@pytest.mark.asyncio
async def test_initialize_manager_skips_ws_when_cookie_invalid(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.http_server as http_server

    calls = []

    class FakeClient:
        async def check_session(self):
            return {"valid": False}

        async def ensure_ws_started(self, reason):
            calls.append(reason)
            return {"success": True, "status": "starting", "reason": reason}

    monkeypatch.setattr(http_server, "get_client", lambda: FakeClient())

    await http_server.initialize_manager()

    assert calls == []


@pytest.mark.asyncio
async def test_initialize_manager_handles_check_session_exception(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.http_server as http_server

    class FakeClient:
        async def check_session(self):
            raise RuntimeError("network error")

    monkeypatch.setattr(http_server, "get_client", lambda: FakeClient())

    await http_server.initialize_manager()


@pytest.mark.asyncio
async def test_initialize_manager_handles_ensure_ws_exception(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.http_server as http_server

    class FakeClient:
        async def check_session(self):
            return {"valid": True}

        async def ensure_ws_started(self, reason):
            raise RuntimeError("ws failed")

    monkeypatch.setattr(http_server, "get_client", lambda: FakeClient())

    await http_server.initialize_manager()


@pytest.mark.asyncio
async def test_shutdown_manager_stops_ws_listener(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.http_server as http_server

    calls = []

    class FakeClient:
        async def stop_ws_listener(self):
            calls.append("stop")
            return {"success": True}

    monkeypatch.setattr(http_server, "get_client", lambda: FakeClient())

    await http_server.shutdown_manager()

    assert calls == ["stop"]


@pytest.mark.asyncio
async def test_rest_login_poll_auto_starts_ws_after_confirmed(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.http_server as http_server

    calls = []

    class FakeRequest:
        method = "POST"

        async def json(self):
            return {"t": "123", "ck": "abc"}

    class FakeClient:
        async def login_poll(self, t, ck):
            return {"success": True, "status": "CONFIRMED"}

        async def ensure_ws_started(self, reason):
            calls.append(reason)
            return {"success": True, "status": "starting", "reason": reason}

        def get_ws_status(self):
            return {"connected": False, "status": "starting", "last_error": None, "started_at": "2026-05-03T01:02:03"}

    monkeypatch.setattr(http_server, "get_client", lambda: FakeClient())

    response = await http_server.rest_login_poll(FakeRequest())
    payload = json.loads(response.body.decode())

    assert calls == ["login_confirmed"]
    assert payload["ws_auto_start"] is True
    assert payload["ws_status"]["status"] == "starting"


@pytest.mark.asyncio
async def test_xianyu_login_starts_background_poll_when_qr_returned(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.http_server as http_server

    calls = []

    class FakeClient:
        async def login(self):
            return {
                "success": True,
                "logged_in": False,
                "qr_code": {"public_url": "https://example.com/qr.png"},
                "t": "t-1",
                "ck": "ck-1",
            }

    def fake_poll(client, t, ck):
        calls.append((client, t, ck))
        async def noop():
            return None
        return noop()

    class FakeTask:
        def done(self):
            return False

        def cancel(self):
            calls.append("cancel")

        def close(self):
            calls.append("close")

    fake_client = FakeClient()
    monkeypatch.setattr(http_server, "get_client", lambda: fake_client)
    monkeypatch.setattr(http_server, "_auto_login_poll", fake_poll)
    def fake_create_task(coro):
        coro.close()
        return FakeTask()

    monkeypatch.setattr(http_server.asyncio, "create_task", fake_create_task)

    payload = json.loads(await http_server.xianyu_login())

    assert payload["success"] is True
    assert payload["auto_poll"] is True
    assert calls == [(fake_client, "t-1", "ck-1")]


@pytest.mark.asyncio
async def test_auto_login_poll_confirms_and_starts_websocket(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.http_server as http_server

    sleeps = []
    starts = []

    class FakeClient:
        def __init__(self):
            self.polls = 0

        async def login_poll(self, t, ck):
            self.polls += 1
            return {"success": True, "status": "CONFIRMED"}

        async def ensure_ws_started(self, reason):
            starts.append(reason)
            return {"success": True, "status": "starting"}

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    client = FakeClient()
    monkeypatch.setattr(http_server.asyncio, "sleep", fake_sleep)

    await http_server._auto_login_poll(client, "t-1", "ck-1", attempts=3, interval=1)

    assert client.polls == 1
    assert starts == ["login_confirmed"]
    assert sleeps == []


@pytest.mark.asyncio
async def test_auto_login_poll_logs_and_returns_when_login_poll_raises(monkeypatch, caplog):
    _install_fake_mcp(monkeypatch)
    import mcp_server.http_server as http_server

    class FakeClient:
        async def login_poll(self, t, ck):
            raise RuntimeError("poll failed")

        async def ensure_ws_started(self, reason):
            raise AssertionError("ensure_ws_started should not be called")

    async def fake_sleep(seconds):
        raise AssertionError("sleep should not be called after exception")

    monkeypatch.setattr(http_server.asyncio, "sleep", fake_sleep)

    with caplog.at_level(logging.WARNING):
        await http_server._auto_login_poll(FakeClient(), "t-1", "ck-1", attempts=3, interval=1)

    assert "登录轮询异常" in caplog.text
    assert "poll failed" in caplog.text


@pytest.mark.asyncio
async def test_auto_login_poll_logs_and_returns_when_ws_start_raises(monkeypatch, caplog):
    _install_fake_mcp(monkeypatch)
    import mcp_server.http_server as http_server

    class FakeClient:
        async def login_poll(self, t, ck):
            return {"success": True, "status": "CONFIRMED"}

        async def ensure_ws_started(self, reason):
            raise RuntimeError("ws start failed")

    async def fake_sleep(seconds):
        raise AssertionError("sleep should not be called after exception")

    monkeypatch.setattr(http_server.asyncio, "sleep", fake_sleep)

    with caplog.at_level(logging.WARNING):
        await http_server._auto_login_poll(FakeClient(), "t-1", "ck-1", attempts=3, interval=1)

    assert "登录轮询异常" in caplog.text
    assert "ws start failed" in caplog.text


@pytest.mark.asyncio
async def test_list_conversations_returns_starting_status(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.http_server as http_server

    class FakeClient:
        def get_ws_status(self):
            return {"connected": False, "status": "starting", "last_error": None, "started_at": "2026-05-03T01:02:03"}

        async def list_conversations(self, limit=20):
            raise AssertionError("list_conversations must not be called while WS is starting")

    monkeypatch.setattr(http_server, "get_client", lambda: FakeClient())

    payload = json.loads(await http_server.xianyu_list_conversations(limit=5))

    assert payload["success"] is False
    assert payload["status"] == "starting"


@pytest.mark.asyncio
async def test_list_conversations_returns_cache_when_ws_disconnected(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.http_server as http_server
    from src.api.types import Conversation

    class FakeCache:
        def get_conversations(self, limit):
            return [
                Conversation(
                    conversation_id="conv-1",
                    user_id="user-1",
                    user_nick="买家",
                    last_message="你好",
                    last_message_time=123.0,
                    unread_count=2,
                    item_id="item-1",
                )
            ]

    class FakeWsClient:
        cache = FakeCache()

    class FakeClient:
        ws_client = FakeWsClient()

        def get_ws_status(self):
            return {"connected": False, "status": "disconnected", "last_error": None}

    monkeypatch.setattr(http_server, "get_client", lambda: FakeClient())

    payload = json.loads(await http_server.xianyu_list_conversations(limit=5))

    assert payload["success"] is True
    assert payload["source"] == "cache"
    assert payload["count"] == 1
    assert payload["conversations"][0]["conversation_id"] == "conv-1"


@pytest.mark.asyncio
async def test_list_conversations_returns_failed_status(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.http_server as http_server

    class FakeClient:
        def get_ws_status(self):
            return {"connected": False, "status": "failed", "last_error": "token failed", "started_at": "2026-05-03T01:02:03"}

        async def list_conversations(self, limit=20):
            raise AssertionError("list_conversations must not be called when WS failed")

    monkeypatch.setattr(http_server, "get_client", lambda: FakeClient())

    payload = json.loads(await http_server.xianyu_list_conversations(limit=5))

    assert payload["success"] is False
    assert payload["status"] == "failed"
    assert payload["message"] == "token failed"


@pytest.mark.asyncio
async def test_get_messages_accepts_numeric_conversation_id(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.http_server as http_server

    captured = {}

    class FakeWsClient:
        async def get_message_history(self, chat_id, anchor=None, count=50):
            captured["chat_id"] = chat_id
            captured["count"] = count
            return {"success": True, "messages": [], "hasMore": False, "nextCursor": 0}

    class FakeClient:
        ws_client = FakeWsClient()

        def ws_is_connected(self):
            return True

    monkeypatch.setattr(http_server, "get_client", lambda: FakeClient())

    payload = json.loads(await http_server.xianyu_get_messages(conversation_id=60971615689, limit=5))

    assert payload["success"] is True
    assert captured == {"chat_id": "60971615689", "count": 5}


@pytest.mark.asyncio
async def test_get_messages_returns_cache_when_ws_disconnected(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.http_server as http_server
    from src.api.types import ChatMessage, TextContent

    captured = {}

    class FakeCache:
        def get_messages(self, conversation_id, limit):
            captured["conversation_id"] = conversation_id
            captured["limit"] = limit
            return [
                ChatMessage(
                    message_id="msg-1",
                    conversation_id=conversation_id,
                    sender_id="sender-1",
                    receiver_id="receiver-1",
                    content=TextContent(text="你好"),
                    timestamp=123.0,
                    is_read=True,
                )
            ]

    class FakeWsClient:
        cache = FakeCache()

    class FakeClient:
        ws_client = FakeWsClient()

        def ws_is_connected(self):
            return False

    monkeypatch.setattr(http_server, "get_client", lambda: FakeClient())

    payload = json.loads(await http_server.xianyu_get_messages(conversation_id=60971615689, limit=5))

    assert payload["success"] is True
    assert payload["source"] == "cache"
    assert payload["messages"][0]["content"] == "你好"
    assert captured == {"conversation_id": "60971615689", "limit": 5}


@pytest.mark.asyncio
async def test_http_publish_success_with_valid_public_args(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.http_server as http_server

    captured = {}

    class FakeClient:
        async def publish(self, **kwargs):
            captured.update(kwargs)
            return {"success": True, "item_id": "item-1", "method": "http"}

    monkeypatch.setattr(http_server, "get_client", lambda: FakeClient())

    payload = json.loads(
        await http_server.xianyu_publish(
            images_paths="/tmp/a.png,/tmp/b.png",
            title="测试商品",
            current_price=88.0,
            original_price=128.0,
            shipping="包邮",
        )
    )

    assert payload == {"success": True, "item_id": "item-1", "method": "http"}
    assert captured == {
        "images_paths": ["/tmp/a.png", "/tmp/b.png"],
        "title": "测试商品",
        "price": {"current_price": 88.0, "original_price": 128.0},
        "shipping": "包邮",
        "self_pickup": False,
        "post_price": 0,
    }


@pytest.mark.asyncio
async def test_http_ws_send_success_with_target_id(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.http_server as http_server

    captured = {}

    class FakeClient:
        async def ws_send_message(self, target_id, content, image_url, conversation_id):
            captured.update(
                {
                    "target_id": target_id,
                    "content": content,
                    "image_url": image_url,
                    "conversation_id": conversation_id,
                }
            )
            return {"success": True, "message": "消息已发送"}

    monkeypatch.setattr(http_server, "get_client", lambda: FakeClient())

    payload = json.loads(
        await http_server.xianyu_ws_send(
            target_id="user-1",
            content="你好",
            image_url="",
            conversation_id="conv-1",
        )
    )

    assert payload == {"success": True, "message": "消息已发送"}
    assert captured == {
        "target_id": "user-1",
        "content": "你好",
        "image_url": "",
        "conversation_id": "conv-1",
    }


@pytest.mark.asyncio
async def test_http_ws_status_reports_connected(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.http_server as http_server

    class FakeClient:
        def get_ws_status(self):
            return {
                "connected": True,
                "status": "connected",
                "last_error": None,
                "started_at": "2026-05-03T13:00:00",
            }

    monkeypatch.setattr(http_server, "get_client", lambda: FakeClient())

    payload = json.loads(await http_server.xianyu_ws_status())

    assert payload == {
        "connected": True,
        "status": "connected",
        "last_error": None,
        "started_at": "2026-05-03T13:00:00",
    }


@pytest.mark.asyncio
async def test_http_get_access_token_success_with_token(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.http_server as http_server

    class FakeHttpClient:
        async def get_access_token(self):
            return "oauth_k1:abcdefghijklmnopqrstuvwxyz"

    class FakeClient:
        http_client = FakeHttpClient()

    monkeypatch.setattr(http_server, "get_client", lambda: FakeClient())

    payload = json.loads(await http_server.xianyu_get_access_token())

    assert payload == {
        "success": True,
        "access_token": "oauth_k1:abcdefghijk...",
        "access_token_masked": "oauth_k1:abcdefghijk...",
    }
    assert "abcdefghijklmnopqrstuvwxyz" not in json.dumps(payload)


@pytest.mark.asyncio
async def test_get_access_token_falls_back_to_cached_token_when_live_fetch_empty(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.http_server as http_server

    class FakeHttpClient:
        _token = "oauth_k1:cachedtokenvalue123456"

        async def get_access_token(self):
            return ""

    class FakeClient:
        http_client = FakeHttpClient()

        def get_ws_status(self):
            return {"connected": True, "status": "connected", "last_error": None}

    monkeypatch.setattr(http_server, "get_client", lambda: FakeClient())

    payload = json.loads(await http_server.xianyu_get_access_token())

    assert payload == {
        "success": True,
        "access_token": "oauth_k1:cachedtoken...",
        "access_token_masked": "oauth_k1:cachedtoken...",
        "source": "cache",
    }


@pytest.mark.asyncio
async def test_list_conversations_returns_clear_failure_when_rpc_raises(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.http_server as http_server

    class FakeCache:
        def get_conversations(self, limit):
            return []

    class FakeWsClient:
        cache = FakeCache()

        async def get_conversation_list(self, max_sort_index=None, page_size=20):
            raise RuntimeError("rpc timeout")

    class FakeClient:
        ws_client = FakeWsClient()

        def get_ws_status(self):
            return {"connected": True, "status": "connected", "last_error": None}

    monkeypatch.setattr(http_server, "get_client", lambda: FakeClient())

    payload = json.loads(await http_server.xianyu_list_conversations(limit=5))

    assert payload == {
        "success": False,
        "source": "websocket",
        "message": "rpc timeout",
        "conversations": [],
        "count": 0,
    }


@pytest.mark.asyncio
async def test_list_conversations_returns_clear_failure_when_rpc_fails_without_cache(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.http_server as http_server

    class FakeCache:
        def get_conversations(self, limit):
            return []

    class FakeWsClient:
        cache = FakeCache()

        async def get_conversation_list(self, max_sort_index=None, page_size=20):
            return {"success": False, "error": "rpc failed"}

    class FakeClient:
        ws_client = FakeWsClient()

        def get_ws_status(self):
            return {"connected": True, "status": "connected", "last_error": None}

    monkeypatch.setattr(http_server, "get_client", lambda: FakeClient())

    payload = json.loads(await http_server.xianyu_list_conversations(limit=5))

    assert payload == {
        "success": False,
        "source": "websocket",
        "message": "rpc failed",
        "conversations": [],
        "count": 0,
    }


@pytest.mark.asyncio
async def test_http_list_conversations_success_from_websocket(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.http_server as http_server

    class FakeWsClient:
        async def get_conversation_list(self, max_sort_index=None, page_size=20):
            return {
                "success": True,
                "hasMore": False,
                "conversations": [
                    {
                        "cid": "conv-1",
                        "peer_user_name": "买家",
                        "last_message": "你好",
                        "last_message_time": 123456,
                        "unread_count": 1,
                        "item_id": "item-1",
                    }
                ],
            }

    class FakeClient:
        ws_client = FakeWsClient()

        def get_ws_status(self):
            return {"connected": True, "status": "connected", "last_error": None}

    monkeypatch.setattr(http_server, "get_client", lambda: FakeClient())

    payload = json.loads(await http_server.xianyu_list_conversations(limit=10))

    assert payload["success"] is True
    assert payload["source"] == "websocket"
    assert payload["count"] == 1
    assert payload["conversations"][0] == {
        "conversation_id": "conv-1",
        "user_id": "conv-1",
        "user_nick": "买家",
        "last_message": "你好",
        "last_message_time": 123456,
        "unread_count": 1,
        "item_id": "item-1",
    }


@pytest.mark.asyncio
async def test_http_get_messages_success_from_websocket(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.http_server as http_server

    class FakeWsClient:
        async def get_message_history(self, chat_id, anchor=None, count=50):
            return {
                "success": True,
                "hasMore": False,
                "nextCursor": 0,
                "messages": [
                    {
                        "message_id": "msg-1",
                        "sender_id": "sender-1",
                        "sender_name": "买家",
                        "content": "你好",
                        "content_type": 1,
                        "timestamp": 123456,
                        "read_status": 2,
                    }
                ],
            }

    class FakeClient:
        ws_client = FakeWsClient()

        def ws_is_connected(self):
            return True

    monkeypatch.setattr(http_server, "get_client", lambda: FakeClient())

    payload = json.loads(await http_server.xianyu_get_messages(conversation_id="conv-1", limit=3))

    assert payload["success"] is True
    assert payload["source"] == "websocket"
    assert payload["count"] == 1
    assert payload["messages"][0] == {
        "message_id": "msg-1",
        "sender_id": "sender-1",
        "sender_nick": "买家",
        "receiver_id": "",
        "receiver_nick": "",
        "content": "你好",
        "content_type": 1,
        "send_time": "1970-01-02 10:17:36",
        "read_status": 2,
    }


@pytest.mark.asyncio
async def test_get_messages_returns_business_error_without_conversation_id(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.http_server as http_server

    payload = json.loads(await http_server.xianyu_get_messages(conversation_id=""))

    assert payload == {
        "success": False,
        "error_code": "MISSING_CONVERSATION_ID",
        "message": "请提供 conversation_id（从 xianyu_list_conversations 获取）",
    }


@pytest.mark.asyncio
async def test_get_messages_returns_clear_failure_when_ws_disconnected_without_cache(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.http_server as http_server

    class FakeCache:
        def get_messages(self, conversation_id, limit):
            return []

    class FakeWsClient:
        cache = FakeCache()

    class FakeClient:
        ws_client = FakeWsClient()

        def ws_is_connected(self):
            return False

        def get_ws_status(self):
            return {"connected": False, "status": "failed", "last_error": "token failed"}

    monkeypatch.setattr(http_server, "get_client", lambda: FakeClient())

    payload = json.loads(await http_server.xianyu_get_messages(conversation_id="conv-1", limit=5))

    assert payload == {
        "success": False,
        "status": "failed",
        "message": "token failed",
        "messages": [],
        "count": 0,
    }


@pytest.mark.asyncio
async def test_get_messages_returns_clear_failure_when_rpc_raises_without_cache(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.http_server as http_server

    class FakeCache:
        def get_messages(self, conversation_id, limit):
            return []

    class FakeWsClient:
        cache = FakeCache()

        async def get_message_history(self, chat_id, anchor=None, count=50):
            raise RuntimeError("history timeout")

    class FakeClient:
        ws_client = FakeWsClient()

        def ws_is_connected(self):
            return True

    monkeypatch.setattr(http_server, "get_client", lambda: FakeClient())

    payload = json.loads(await http_server.xianyu_get_messages(conversation_id="conv-1", limit=5))

    assert payload == {
        "success": False,
        "source": "websocket",
        "message": "history timeout",
        "messages": [],
        "count": 0,
    }
