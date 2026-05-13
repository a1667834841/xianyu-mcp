"""
Unit tests for MCP server HTTP/SSE wiring.
"""

from __future__ import annotations

import json
import logging
import sys
import types
from datetime import datetime, timedelta, timezone

import pytest


def _patch_client(monkeypatch, mod, fake_client):
    """替换 get_client_manager 和 _resolve_user_id 以返回 fake_client。"""
    class FakeClientManager:
        def get_client(self, user_id):
            return fake_client
    monkeypatch.setattr(mod, "get_client_manager", lambda: FakeClientManager())
    monkeypatch.setattr(mod, "_resolve_user_id", lambda uid: uid or "default")


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


def test_access_token_tool_is_not_exposed(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.http_server as http_server

    assert not hasattr(http_server, "xianyu_get_access_token")


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

    _patch_client(monkeypatch, http_server, FakeClient())

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

    _patch_client(monkeypatch, http_server, FakeClient())

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

    _patch_client(monkeypatch, http_server, FakeClient())

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

    _patch_client(monkeypatch, http_server, FakeClient())

    payload = json.loads(await http_server.xianyu_check_session(user_id="user-001"))

    assert payload["valid"] is False
    assert payload["last_updated_at"] is None


@pytest.mark.asyncio
async def test_xianyu_check_session_batch_returns_all_users_with_status(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.http_server as http_server

    recorded = []

    class FakeUserManager:
        def list_users(self):
            return [
                {"user_id": "user-a", "username": "用户A", "status": "active"},
                {"user_id": "user-b", "username": "用户B", "status": "expired"},
                {"user_id": "user-c", "username": "已禁用C", "status": "disabled"},
            ]

    class FakeClientA:
        async def check_session(self):
            return {"valid": True, "message": "Cookie有效"}

    class FakeClientB:
        async def check_session(self):
            return {"valid": False, "message": "Cookie无效"}

    class FakeClientManager:
        def get_client(self, user_id):
            recorded.append(user_id)
            if user_id == "user-a":
                return FakeClientA()
            if user_id == "user-b":
                return FakeClientB()
            raise AssertionError(f"不应该为 user-c 调用 get_client")

    monkeypatch.setattr(http_server, "get_user_manager", lambda: FakeUserManager())
    monkeypatch.setattr(http_server, "get_client_manager", lambda: FakeClientManager())

    payload = json.loads(await http_server.xianyu_check_session())

    assert payload["success"] is True
    assert len(payload["sessions"]) == 3
    assert payload["sessions"][0] == {
        "user_id": "user-a",
        "username": "用户A",
        "status": "active",
        "valid": True,
        "message": "Cookie有效",
    }
    assert payload["sessions"][1] == {
        "user_id": "user-b",
        "username": "用户B",
        "status": "expired",
        "valid": False,
        "message": "Cookie无效",
    }
    assert payload["sessions"][2] == {
        "user_id": "user-c",
        "username": "已禁用C",
        "status": "disabled",
        "valid": False,
        "message": "用户已禁用，未执行会话检查",
    }
    assert recorded == ["user-a", "user-b"]


@pytest.mark.asyncio
async def test_xianyu_check_session_batch_syncs_user_status(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.http_server as http_server

    recorded = []

    class FakeUserManager:
        def list_users(self):
            return [
                {"user_id": "user-a", "username": "用户A", "status": "expired"},
                {"user_id": "user-b", "username": "用户B", "status": "active"},
            ]

        def update_user(self, user_id, **changes):
            recorded.append((user_id, changes))
            return {"user_id": user_id, **changes}

    class FakeClientA:
        async def check_session(self):
            return {"valid": True, "message": "Cookie有效"}

    class FakeClientB:
        async def check_session(self):
            return {"valid": False, "message": "Cookie无效"}

    class FakeClientManager:
        def get_client(self, user_id):
            if user_id == "user-a":
                return FakeClientA()
            if user_id == "user-b":
                return FakeClientB()
            raise AssertionError(f"unexpected user_id: {user_id}")

    monkeypatch.setattr(http_server, "get_user_manager", lambda: FakeUserManager())
    monkeypatch.setattr(http_server, "get_client_manager", lambda: FakeClientManager())

    payload = json.loads(await http_server.xianyu_check_session())

    assert payload["sessions"][0]["status"] == "active"
    assert payload["sessions"][1]["status"] == "expired"
    assert recorded == [
        ("user-a", {"status": "active"}),
        ("user-b", {"status": "expired"}),
    ]


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

    _patch_client(monkeypatch, http_server, FakeClient())

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

    _patch_client(monkeypatch, http_server, FakeClient())

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

    _patch_client(monkeypatch, http_server, FakeClient())

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

    _patch_client(monkeypatch, http_server, FakeClient())

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

    _patch_client(monkeypatch, http_server, FakeClient())

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

    monkeypatch.setattr(http_server, "_resolve_user_id", lambda uid: "default")

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

    _patch_client(monkeypatch, http_server, FakeClient())

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

    _patch_client(monkeypatch, http_server, FakeClient())

    payload = json.loads(await http_server.xianyu_ws_status())

    assert payload["connected"] is False
    assert payload["status"] == "failed"
    assert payload["last_error"] == "token failed"


@pytest.mark.asyncio
async def test_initialize_manager_starts_keepalive_and_ws_for_active_users(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.http_server as http_server

    class FakeKeepalive:
        interval_minutes = 240

    class FakeSettings:
        keepalive = FakeKeepalive()

    started_keepalive = []
    ws_started = []
    updated_users = {}
    get_user_calls = []

    class FakeClient:
        def __init__(self, user_id):
            self._user_id = user_id

        async def check_session(self):
            return {"valid": True}

        async def ensure_ws_started(self, reason):
            ws_started.append((self._user_id, reason))

        def get_ws_status(self):
            return {"status": "starting", "connected": False}

    class FakeClientManager:
        def get_client(self, user_id):
            return FakeClient(user_id)

        async def start_keepalive(self, user_id, interval_minutes):
            started_keepalive.append((user_id, interval_minutes))

    class FakeUserManager:
        def list_users(self):
            return [
                {"user_id": "user-1", "status": "active", "keepalive_enabled": True},
                {"user_id": "user-2", "status": "active", "keepalive_enabled": False},
                {"user_id": "user-3", "status": "disabled", "keepalive_enabled": True},
            ]

        def get_user(self, user_id):
            get_user_calls.append(user_id)
            return {
                "user_id": user_id,
                "status": "active",
                "keepalive_enabled": True,
            }

        def update_user(self, user_id, **changes):
            updated_users[user_id] = changes

    monkeypatch.setattr(http_server, "load_settings", lambda: FakeSettings())
    monkeypatch.setattr(http_server, "get_user_manager", lambda: FakeUserManager())
    monkeypatch.setattr(http_server, "get_client_manager", lambda: FakeClientManager())

    await http_server.initialize_manager()

    assert started_keepalive == [("user-1", 240)]
    assert ws_started == [("user-1", "service_start")]
    assert get_user_calls == ["user-1"]
    assert updated_users == {}


@pytest.mark.asyncio
async def test_initialize_manager_marks_user_expired_when_session_invalid(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.http_server as http_server

    class FakeKeepalive:
        interval_minutes = 240

    class FakeSettings:
        keepalive = FakeKeepalive()

    updated = {}

    class FakeClient:
        async def check_session(self):
            return {"valid": False}

    class FakeClientManager:
        def get_client(self, user_id):
            return FakeClient()

        async def start_keepalive(self, user_id, interval_minutes):
            pytest.fail("start_keepalive should not be called for expired session")

    class FakeUserManager:
        def list_users(self):
            return [{"user_id": "user-1", "status": "active", "keepalive_enabled": True}]

        def update_user(self, user_id, **changes):
            updated[user_id] = changes

    monkeypatch.setattr(http_server, "load_settings", lambda: FakeSettings())
    monkeypatch.setattr(http_server, "get_user_manager", lambda: FakeUserManager())
    monkeypatch.setattr(http_server, "get_client_manager", lambda: FakeClientManager())

    await http_server.initialize_manager()

    assert "user-1" in updated
    assert updated["user-1"]["status"] == "expired"


@pytest.mark.asyncio
async def test_initialize_manager_marks_user_error_when_check_session_raises(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.http_server as http_server

    class FakeKeepalive:
        interval_minutes = 240

    class FakeSettings:
        keepalive = FakeKeepalive()

    updated = {}

    class FakeClient:
        async def check_session(self):
            raise RuntimeError("network error")

    class FakeClientManager:
        def get_client(self, user_id):
            return FakeClient()

        async def start_keepalive(self, user_id, interval_minutes):
            pytest.fail("start_keepalive should not be called after check_session error")

    class FakeUserManager:
        def list_users(self):
            return [{"user_id": "user-1", "status": "active", "keepalive_enabled": True}]

        def update_user(self, user_id, **changes):
            updated[user_id] = changes

    monkeypatch.setattr(http_server, "load_settings", lambda: FakeSettings())
    monkeypatch.setattr(http_server, "get_user_manager", lambda: FakeUserManager())
    monkeypatch.setattr(http_server, "get_client_manager", lambda: FakeClientManager())

    await http_server.initialize_manager()

    assert "user-1" in updated
    assert updated["user-1"]["status"] == "error"


@pytest.mark.asyncio
async def test_initialize_manager_starts_keepalive_even_when_ws_fails(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.http_server as http_server

    class FakeKeepalive:
        interval_minutes = 240

    class FakeSettings:
        keepalive = FakeKeepalive()

    started_keepalive = []

    class FakeClient:
        async def check_session(self):
            return {"valid": True}

        async def ensure_ws_started(self, reason):
            raise RuntimeError("ws failed")

    class FakeClientManager:
        def get_client(self, user_id):
            return FakeClient()

        async def start_keepalive(self, user_id, interval_minutes):
            started_keepalive.append((user_id, interval_minutes))

    class FakeUserManager:
        def get_user(self, user_id):
            return {
                "user_id": user_id,
                "username": "user-1",
                "status": "active",
                "keepalive_enabled": True,
            }

        def list_users(self):
            return [{"user_id": "user-1", "status": "active", "keepalive_enabled": True}]

        def update_user(self, user_id, **changes):
            pass

    monkeypatch.setattr(http_server, "load_settings", lambda: FakeSettings())
    monkeypatch.setattr(http_server, "get_user_manager", lambda: FakeUserManager())
    monkeypatch.setattr(http_server, "get_client_manager", lambda: FakeClientManager())

    await http_server.initialize_manager()

    assert started_keepalive == [("user-1", 240)]


@pytest.mark.asyncio
async def test_shutdown_manager_stops_clients(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.http_server as http_server

    calls = []

    class FakeClientManager:
        async def shutdown(self):
            calls.append("shutdown")

    monkeypatch.setattr(http_server, "get_client_manager", lambda: FakeClientManager())
    monkeypatch.setattr(http_server, "_resolve_user_id", lambda uid: uid or "default")

    await http_server.shutdown_manager()

    assert calls == ["shutdown"]


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

    _patch_client(monkeypatch, http_server, FakeClient())

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
    class FakeClientManager:
        def get_client(self, user_id):
            return fake_client
    monkeypatch.setattr(http_server, "get_client_manager", lambda: FakeClientManager())
    monkeypatch.setattr(http_server, "_resolve_user_id", lambda uid: "default")
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
    activations = []

    class FakeClient:
        user_id = "poll-user"

        def __init__(self):
            self.polls = 0

        async def login_poll(self, t, ck):
            self.polls += 1
            return {"success": True, "status": "CONFIRMED"}

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    async def fake_activate_user_runtime(user_id, reason):
        activations.append({"user_id": user_id, "reason": reason})
        return {"ws_auto_start": True, "ws_status": {"status": "starting"}}

    client = FakeClient()
    monkeypatch.setattr(http_server.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(http_server, "_activate_user_runtime", fake_activate_user_runtime)

    await http_server._auto_login_poll(client, "t-1", "ck-1", attempts=3, interval=1)

    assert client.polls == 1
    assert activations == [{"user_id": "poll-user", "reason": "login_confirmed"}]
    assert sleeps == []


@pytest.mark.asyncio
async def test_auto_login_poll_logs_and_returns_when_login_poll_raises(monkeypatch, caplog):
    _install_fake_mcp(monkeypatch)
    import mcp_server.http_server as http_server

    class FakeClient:
        user_id = "poll-user"

        async def login_poll(self, t, ck):
            raise RuntimeError("poll failed")

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
        user_id = "poll-user"

        async def login_poll(self, t, ck):
            return {"success": True, "status": "CONFIRMED"}

    async def fake_activate_user_runtime(user_id, reason):
            raise RuntimeError("ws start failed")

    async def fake_sleep(seconds):
        raise AssertionError("sleep should not be called after exception")

    monkeypatch.setattr(http_server.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(http_server, "_activate_user_runtime", fake_activate_user_runtime)

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

    _patch_client(monkeypatch, http_server, FakeClient())

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

    _patch_client(monkeypatch, http_server, FakeClient())

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

    _patch_client(monkeypatch, http_server, FakeClient())

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

    _patch_client(monkeypatch, http_server, FakeClient())

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

    _patch_client(monkeypatch, http_server, FakeClient())

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

    _patch_client(monkeypatch, http_server, FakeClient())

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

    _patch_client(monkeypatch, http_server, FakeClient())

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

    _patch_client(monkeypatch, http_server, FakeClient())

    payload = json.loads(await http_server.xianyu_ws_status())

    assert payload == {
        "connected": True,
        "status": "connected",
        "last_error": None,
        "started_at": "2026-05-03 13:00:00",
    }


@pytest.mark.asyncio
async def test_xianyu_show_qrcode_creates_pending_session(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.http_server as http_server

    class FakeClient:
        async def show_qrcode(self):
            return {
                "success": True,
                "logged_in": False,
                "t": "token-123",
                "ck": "ck-123",
                "qr_code": {
                    "public_url": "https://example.com/qr.png",
                    "url": "https://passport.goofish.com/qrcodeCheck.htm?token=abc",
                },
                "qr_code_url": "https://example.com/qr.png",
            }

    class FakeClientManager:
        def get_client(self, user_id):
            assert user_id == http_server.PENDING_LOGIN_CLIENT_ID
            return FakeClient()

    captured = {}

    class FakePendingLoginManager:
        def create_session(self, t, ck, qr_code_url, expires_at):
            captured.update(
                {
                    "t": t,
                    "ck": ck,
                    "qr_code_url": qr_code_url,
                    "expires_at": expires_at,
                }
            )
            return {
                "t": t,
                "ck": ck,
                "qr_code_url": qr_code_url,
                "expires_at": expires_at.isoformat(),
                "phase": "login_required",
            }

    monkeypatch.setattr(http_server, "get_client_manager", lambda: FakeClientManager())
    monkeypatch.setattr(http_server, "get_pending_login_manager", lambda: FakePendingLoginManager())

    before = datetime.now(timezone.utc)
    payload = json.loads(await http_server.xianyu_show_qrcode())
    after = datetime.now(timezone.utc)

    assert payload["phase"] == "login_required"
    assert payload["qr_code"]["public_url"] == "https://example.com/qr.png"
    assert "url" not in payload["qr_code"]
    assert captured["t"] == "token-123"
    assert captured["ck"] == "ck-123"
    assert captured["qr_code_url"] == "https://example.com/qr.png"
    assert before + timedelta(minutes=5) <= captured["expires_at"] <= after + timedelta(minutes=5)


@pytest.mark.asyncio
async def test_xianyu_show_qrcode_uses_nested_public_url_for_pending_session(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.http_server as http_server

    class FakeClient:
        async def show_qrcode(self):
            return {
                "success": True,
                "logged_in": False,
                "t": "token-123",
                "ck": "ck-123",
                "qr_code": {
                    "public_url": "https://example.com/qr.png",
                    "url": "https://passport.goofish.com/qrcodeCheck.htm?token=abc",
                },
            }

    class FakeClientManager:
        def get_client(self, user_id):
            assert user_id == http_server.PENDING_LOGIN_CLIENT_ID
            return FakeClient()

    captured = {}

    class FakePendingLoginManager:
        def create_session(self, t, ck, qr_code_url, expires_at):
            captured.update(
                {
                    "t": t,
                    "ck": ck,
                    "qr_code_url": qr_code_url,
                    "expires_at": expires_at,
                }
            )

    monkeypatch.setattr(http_server, "get_client_manager", lambda: FakeClientManager())
    monkeypatch.setattr(http_server, "get_pending_login_manager", lambda: FakePendingLoginManager())

    payload = json.loads(await http_server.xianyu_show_qrcode())

    assert payload["phase"] == "login_required"
    assert payload["qr_code"]["public_url"] == "https://example.com/qr.png"
    assert captured["qr_code_url"] == "https://example.com/qr.png"


@pytest.mark.asyncio
async def test_xianyu_add_user_creates_user_after_confirmed_login(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.http_server as http_server

    recorded = {}

    class FakePendingLoginManager:
        def get_session(self, t, ck):
            recorded["session_lookup"] = {"t": t, "ck": ck}
            return {"t": t, "ck": ck}

        def delete_session(self, t, ck):
            recorded["deleted_session"] = {"t": t, "ck": ck}

    class FakeHttpClient:
        cookies = {"unb": "new-user", "cookie2": "new-cookie"}
        device_id = "web_new-user"

        def get_authenticated_user_identity(self):
            return {"user_id": "new-user", "username": "new-user"}

        async def fetch_user_nickname(self):
            return "真实昵称"

    class FakeClient:
        http_client = FakeHttpClient()

        async def login_poll(self, t, ck):
            recorded["login_poll"] = {"t": t, "ck": ck}
            return {"status": "CONFIRMED"}

        async def check_session(self):
            recorded["check_session"] = True
            return {"valid": True}

    class FakeClientManager:
        def __init__(self):
            self.pending_client = FakeClient()

            class TargetClient:
                async def initialize(self_inner, cookies, device_id):
                    return await fake_initialize(self_inner, cookies, device_id)

                async def ensure_ws_started(self_inner, reason):
                    recorded["ws_reason"] = reason
                    return {"success": True, "status": "starting", "reason": reason}

                def get_ws_status(self_inner):
                    return {
                        "connected": False,
                        "status": "starting",
                        "last_error": None,
                        "started_at": None,
                    }

            self.target_client = TargetClient()

        def get_client(self, user_id):
            recorded.setdefault("client_ids", []).append(user_id)
            if user_id == http_server.PENDING_LOGIN_CLIENT_ID:
                return self.pending_client
            if user_id == "new-user":
                return self.target_client
            raise AssertionError(f"unexpected user_id: {user_id}")

        async def start_keepalive(self, user_id, interval_minutes):
            recorded["runtime_activation"] = {
                "user_id": user_id,
                "reason": "login_confirmed",
                "interval_minutes": interval_minutes,
            }

    class FakeUserManager:
        def __init__(self):
            self.users = {}

        def get_user(self, user_id):
            try:
                return self.users[user_id]
            except KeyError as exc:
                raise ValueError(f"User '{user_id}' not found") from exc

        def add_user(self, user_id, username):
            recorded["added_user"] = {"user_id": user_id, "username": username}
            self.users[user_id] = {
                "user_id": user_id,
                "username": username,
                "status": "active",
            }
            return self.users[user_id]

        def update_user(self, user_id, **fields):
            recorded["updated_user"] = {"user_id": user_id, **fields}
            current = self.users.get(user_id, {"user_id": user_id})
            current.update(fields)
            self.users[user_id] = current
            return current

    async def fake_initialize(self, cookies, device_id):
        recorded["initialized"] = {"cookies": cookies, "device_id": device_id}

        class FakeTargetHttpClient:
            def _save_auth(self_inner, cookies):
                recorded["saved_cookies"] = cookies

        self.http_client = FakeTargetHttpClient()

    fake_client_manager = FakeClientManager()
    fake_user_manager = FakeUserManager()

    monkeypatch.setattr(http_server, "get_pending_login_manager", lambda: FakePendingLoginManager())
    monkeypatch.setattr(http_server, "get_client_manager", lambda: fake_client_manager)
    monkeypatch.setattr(http_server, "get_user_manager", lambda: fake_user_manager)
    monkeypatch.setattr(http_server.XianyuApiClient, "initialize", fake_initialize)

    payload = json.loads(await http_server.xianyu_add_user(t="token-123", ck="ck-123"))

    assert payload["success"] is True
    assert payload["phase"] == "completed"
    assert payload["user"]["user_id"] == "new-user"
    assert payload["user"]["username"] == "真实昵称"
    assert payload["user"]["status"] == "active"
    assert recorded["session_lookup"] == {"t": "token-123", "ck": "ck-123"}
    assert recorded["client_ids"] == [http_server.PENDING_LOGIN_CLIENT_ID, "new-user", "new-user"]
    assert recorded["login_poll"] == {"t": "token-123", "ck": "ck-123"}
    assert recorded["check_session"] is True
    assert recorded["added_user"] == {"user_id": "new-user", "username": "真实昵称"}
    assert recorded["initialized"] == {
        "cookies": {"unb": "new-user", "cookie2": "new-cookie"},
        "device_id": "web_new-user",
    }
    assert recorded["saved_cookies"] == {"unb": "new-user", "cookie2": "new-cookie"}
    assert recorded["updated_user"]["user_id"] == "new-user"
    assert isinstance(recorded["updated_user"]["last_login_at"], str)
    assert recorded["deleted_session"] == {"t": "token-123", "ck": "ck-123"}
    assert recorded["runtime_activation"] == {
        "user_id": "new-user",
        "reason": "login_confirmed",
        "interval_minutes": 240,
    }
    assert payload["ws_auto_start"] is True
    assert payload["ws_status"]["status"] == "starting"


@pytest.mark.asyncio
async def test_xianyu_add_user_returns_waiting_when_not_confirmed(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.http_server as http_server

    class FakePendingLoginManager:
        def get_session(self, t, ck):
            return {"t": t, "ck": ck}

    class FakeClient:
        async def login_poll(self, t, ck):
            return {"status": "NEW", "message": "等待扫码"}

    class FakeClientManager:
        def get_client(self, user_id):
            assert user_id == http_server.PENDING_LOGIN_CLIENT_ID
            return FakeClient()

    monkeypatch.setattr(http_server, "get_pending_login_manager", lambda: FakePendingLoginManager())
    monkeypatch.setattr(http_server, "get_client_manager", lambda: FakeClientManager())

    payload = json.loads(await http_server.xianyu_add_user(t="token-123", ck="ck-123"))

    assert payload["success"] is False
    assert payload["phase"] == "waiting_for_scan"
    assert payload["status"] == "NEW"


@pytest.mark.asyncio
async def test_xianyu_add_user_returns_expired_when_qrcode_expired(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.http_server as http_server

    recorded = {}

    class FakePendingLoginManager:
        def get_session(self, t, ck):
            return {"t": t, "ck": ck}

        def delete_session(self, t, ck):
            recorded["deleted_session"] = {"t": t, "ck": ck}

    class FakeClient:
        async def login_poll(self, t, ck):
            return {"status": "EXPIRED", "message": "二维码已过期"}

    class FakeClientManager:
        def get_client(self, user_id):
            assert user_id == http_server.PENDING_LOGIN_CLIENT_ID
            return FakeClient()

    monkeypatch.setattr(http_server, "get_pending_login_manager", lambda: FakePendingLoginManager())
    monkeypatch.setattr(http_server, "get_client_manager", lambda: FakeClientManager())

    payload = json.loads(await http_server.xianyu_add_user(t="token-123", ck="ck-123"))

    assert payload["success"] is False
    assert payload["phase"] == "expired"
    assert payload["status"] == "EXPIRED"
    assert recorded["deleted_session"] == {"t": "token-123", "ck": "ck-123"}


@pytest.mark.asyncio
async def test_xianyu_add_user_refreshes_existing_user_session_when_user_already_exists(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.http_server as http_server

    recorded = {}

    class FakePendingLoginManager:
        def get_session(self, t, ck):
            return {"t": t, "ck": ck}

        def delete_session(self, t, ck):
            recorded["deleted_session"] = {"t": t, "ck": ck}

    class FakeHttpClient:
        cookies = {"unb": "existing-user", "cookie2": "new-cookie"}
        device_id = "web_existing-user"

        def get_authenticated_user_identity(self):
            return {"user_id": "existing-user", "username": "existing-user"}

        async def fetch_user_nickname(self):
            return "老用户"

    class FakeClient:
        http_client = FakeHttpClient()

        async def login_poll(self, t, ck):
            return {"status": "CONFIRMED"}

        async def check_session(self):
            return {"valid": True}

    class FakeClientManager:
        def __init__(self):
            self.pending_client = FakeClient()

            class TargetClient:
                async def initialize(self_inner, cookies, device_id):
                    return await fake_initialize(self_inner, cookies, device_id)

                async def ensure_ws_started(self_inner, reason):
                    recorded["ws_reason"] = reason
                    return {"success": True, "status": "starting", "reason": reason}

                def get_ws_status(self_inner):
                    return {
                        "connected": False,
                        "status": "starting",
                        "last_error": None,
                        "started_at": None,
                    }

            self.target_client = TargetClient()

        def get_client(self, user_id):
            if user_id == http_server.PENDING_LOGIN_CLIENT_ID:
                return self.pending_client
            if user_id == "existing-user":
                return self.target_client
            raise AssertionError(f"unexpected user_id: {user_id}")

        async def stop_user(self, user_id):
            recorded["stopped_user"] = user_id

        async def start_keepalive(self, user_id, interval_minutes):
            recorded["runtime_activation"] = {
                "user_id": user_id,
                "reason": "login_confirmed",
                "interval_minutes": interval_minutes,
            }

    class FakeUserManager:
        def get_user(self, user_id):
            assert user_id == "existing-user"
            return {"user_id": user_id, "username": "已存在用户", "status": "expired"}

        def add_user(self, user_id, username):
            raise AssertionError("should not add an existing active user")

        def update_user(self, user_id, **fields):
            recorded["updated_user"] = {"user_id": user_id, **fields}
            return {"user_id": user_id, "username": "老用户", **fields}

    async def fake_initialize(self, cookies, device_id):
        recorded["initialized"] = {"cookies": cookies, "device_id": device_id}
        class FakeTargetHttpClient:
            def _save_auth(self_inner, cookies):
                recorded["saved_cookies"] = cookies
        self.http_client = FakeTargetHttpClient()

    fake_client_manager = FakeClientManager()

    monkeypatch.setattr(http_server, "get_pending_login_manager", lambda: FakePendingLoginManager())
    monkeypatch.setattr(http_server, "get_client_manager", lambda: fake_client_manager)
    monkeypatch.setattr(http_server, "get_user_manager", lambda: FakeUserManager())
    monkeypatch.setattr(http_server.XianyuApiClient, "initialize", fake_initialize)

    payload = json.loads(await http_server.xianyu_add_user(t="token-123", ck="ck-123"))

    assert payload["success"] is True
    assert payload["phase"] == "already_exists"
    assert payload["message"] == "用户已存在，已刷新登录态"
    assert payload["user"]["user_id"] == "existing-user"
    assert payload["user"]["status"] == "active"
    assert recorded["saved_cookies"] == {"unb": "existing-user", "cookie2": "new-cookie"}
    assert recorded["stopped_user"] == "existing-user"
    assert recorded["initialized"] == {
        "cookies": {"unb": "existing-user", "cookie2": "new-cookie"},
        "device_id": "web_existing-user",
    }
    assert recorded["updated_user"]["user_id"] == "existing-user"
    assert recorded["updated_user"]["status"] == "active"
    assert isinstance(recorded["updated_user"]["last_login_at"], str)
    assert recorded["deleted_session"] == {"t": "token-123", "ck": "ck-123"}
    assert recorded["runtime_activation"] == {
        "user_id": "existing-user",
        "reason": "login_confirmed",
        "interval_minutes": 240,
    }
    assert payload["ws_auto_start"] is True
    assert payload["ws_status"]["status"] == "starting"


@pytest.mark.asyncio
async def test_xianyu_add_user_uses_identity_username_when_nickname_empty(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.http_server as http_server

    class FakePendingLoginManager:
        def get_session(self, t, ck):
            return {"t": t, "ck": ck}

        def delete_session(self, t, ck):
            pass

    class FakeHttpClient:
        cookies = {"unb": "foo-user", "cookie2": "bar"}
        device_id = "web_foo-user"

        def get_authenticated_user_identity(self):
            return {"user_id": "foo-user", "username": "implicit-name"}

        async def fetch_user_nickname(self):
            return ""

    class FakeClient:
        http_client = FakeHttpClient()

        async def login_poll(self, t, ck):
            return {"status": "CONFIRMED"}

        async def check_session(self):
            return {"valid": True}

    class FakeClientManager:
        class _UserClient:
            async def initialize(self, cookies, device_id):
                class _FakeHttp:
                    def _save_auth(self_inner, cookies):
                        pass
                self.http_client = _FakeHttp()

            async def ensure_ws_started(self, reason):
                return {"success": True, "status": "starting", "reason": reason}

            def get_ws_status(self):
                return {
                    "connected": False,
                    "status": "starting",
                    "last_error": None,
                    "started_at": None,
                }

        def get_client(self, user_id):
            if user_id == http_server.PENDING_LOGIN_CLIENT_ID:
                return FakeClient()
            return self._UserClient()

        async def start_keepalive(self, user_id, interval_minutes):
            return None

    recorded_add = {}

    class FakeUserManager:
        def __init__(self):
            self.users = {}

        def get_user(self, user_id):
            try:
                return self.users[user_id]
            except KeyError as exc:
                raise ValueError(f"User '{user_id}' not found") from exc

        def add_user(self, user_id, username):
            recorded_add["username"] = username
            self.users[user_id] = {"user_id": user_id, "username": username, "status": "active"}
            return self.users[user_id]

        def update_user(self, user_id, **fields):
            current = self.users.get(user_id, {"user_id": user_id})
            current.update(fields)
            self.users[user_id] = current
            return current

    fake_user_manager = FakeUserManager()

    monkeypatch.setattr(http_server, "get_pending_login_manager", lambda: FakePendingLoginManager())
    monkeypatch.setattr(http_server, "get_client_manager", lambda: FakeClientManager())
    monkeypatch.setattr(http_server, "get_user_manager", lambda: fake_user_manager)

    payload = json.loads(await http_server.xianyu_add_user(t="token-123", ck="ck-123"))

    assert payload["success"] is True
    assert recorded_add["username"] == "implicit-name"


@pytest.mark.asyncio
async def test_xianyu_add_user_uses_user_id_when_nickname_and_identity_username_both_empty(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.http_server as http_server

    class FakePendingLoginManager:
        def get_session(self, t, ck):
            return {"t": t, "ck": ck}

        def delete_session(self, t, ck):
            pass

    class FakeHttpClient:
        cookies = {"unb": "uid-only", "cookie2": "bar"}
        device_id = "web_uid-only"

        def get_authenticated_user_identity(self):
            return {"user_id": "uid-only", "username": ""}

        async def fetch_user_nickname(self):
            return ""

    class FakeClient:
        http_client = FakeHttpClient()

        async def login_poll(self, t, ck):
            return {"status": "CONFIRMED"}

        async def check_session(self):
            return {"valid": True}

    class FakeClientManager:
        class _UserClient:
            async def initialize(self, cookies, device_id):
                class _FakeHttp:
                    def _save_auth(self_inner, cookies):
                        pass
                self.http_client = _FakeHttp()

            async def ensure_ws_started(self, reason):
                return {"success": True, "status": "starting", "reason": reason}

            def get_ws_status(self):
                return {
                    "connected": False,
                    "status": "starting",
                    "last_error": None,
                    "started_at": None,
                }

        def get_client(self, user_id):
            if user_id == http_server.PENDING_LOGIN_CLIENT_ID:
                return FakeClient()
            return self._UserClient()

        async def start_keepalive(self, user_id, interval_minutes):
            return None

    recorded_add = {}

    class FakeUserManager:
        def __init__(self):
            self.users = {}

        def get_user(self, user_id):
            try:
                return self.users[user_id]
            except KeyError as exc:
                raise ValueError(f"User '{user_id}' not found") from exc

        def add_user(self, user_id, username):
            recorded_add["username"] = username
            self.users[user_id] = {"user_id": user_id, "username": username, "status": "active"}
            return self.users[user_id]

        def update_user(self, user_id, **fields):
            current = self.users.get(user_id, {"user_id": user_id})
            current.update(fields)
            self.users[user_id] = current
            return current

    fake_user_manager = FakeUserManager()

    monkeypatch.setattr(http_server, "get_pending_login_manager", lambda: FakePendingLoginManager())
    monkeypatch.setattr(http_server, "get_client_manager", lambda: FakeClientManager())
    monkeypatch.setattr(http_server, "get_user_manager", lambda: fake_user_manager)

    payload = json.loads(await http_server.xianyu_add_user(t="token-123", ck="ck-123"))

    assert payload["success"] is True
    assert recorded_add["username"] == "uid-only"



@pytest.mark.asyncio
async def test_xianyu_add_user_returns_error_when_pending_session_missing(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.http_server as http_server

    class FakePendingLoginManager:
        def get_session(self, t, ck):
            raise ValueError("pending session not found")

    monkeypatch.setattr(http_server, "get_pending_login_manager", lambda: FakePendingLoginManager())

    payload = json.loads(await http_server.xianyu_add_user(t="token-123", ck="ck-123"))

    assert payload == {
        "success": False,
        "phase": "error",
        "message": "pending session not found",
    }


@pytest.mark.asyncio
async def test_xianyu_add_user_returns_expired_when_pending_session_expired(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.http_server as http_server

    class FakePendingLoginManager:
        def get_session(self, t, ck):
            raise ValueError("pending session expired")

    monkeypatch.setattr(http_server, "get_pending_login_manager", lambda: FakePendingLoginManager())

    payload = json.loads(await http_server.xianyu_add_user(t="token-123", ck="ck-123"))

    assert payload == {
        "success": False,
        "phase": "expired",
        "message": "pending session expired",
    }


@pytest.mark.asyncio
async def test_xianyu_add_user_returns_error_when_confirmed_but_session_invalid(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.http_server as http_server

    class FakePendingLoginManager:
        def get_session(self, t, ck):
            return {"t": t, "ck": ck}

        def delete_session(self, t, ck):
            raise AssertionError("should not delete session when check_session is invalid")

    class FakeClient:
        async def login_poll(self, t, ck):
            return {"status": "CONFIRMED"}

        async def check_session(self):
            return {"valid": False, "message": "cookie invalid"}

    class FakeClientManager:
        def get_client(self, user_id):
            assert user_id == http_server.PENDING_LOGIN_CLIENT_ID
            return FakeClient()

    monkeypatch.setattr(http_server, "get_pending_login_manager", lambda: FakePendingLoginManager())
    monkeypatch.setattr(http_server, "get_client_manager", lambda: FakeClientManager())

    payload = json.loads(await http_server.xianyu_add_user(t="token-123", ck="ck-123"))

    assert payload["success"] is False
    assert payload["phase"] == "error"
    assert payload["message"] == "cookie invalid"
    assert payload["session"] == {"valid": False, "message": "cookie invalid"}


@pytest.mark.asyncio
async def test_xianyu_list_users_returns_runtime_info(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.http_server as http_server

    class FakeUserManager:
        def list_users(self):
            return [{"user_id": "user-1", "username": "用户1", "status": "active"}]

    class FakeClientManager:
        def has_keepalive_task(self, user_id):
            return True
        def has_client(self, user_id):
            return True
        def get_client(self, user_id):
            class FakeClient:
                def ws_is_connected(self):
                    return True
            return FakeClient()

    monkeypatch.setattr(http_server, "get_user_manager", lambda: FakeUserManager())
    monkeypatch.setattr(http_server, "get_client_manager", lambda: FakeClientManager())

    payload = json.loads(await http_server.xianyu_list_users())

    assert payload["success"] is True
    assert payload["users"][0]["user_id"] == "user-1"
    assert payload["users"][0]["ws_connected"] is True
    assert payload["users"][0]["keepalive_running"] is True


@pytest.mark.asyncio
async def test_xianyu_delete_user_disables_and_stops(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.http_server as http_server

    class FakeUserManager:
        def disable_user(self, user_id):
            return {"user_id": user_id, "status": "disabled"}

    class FakeClientManager:
        async def stop_user(self, user_id):
            pass

    monkeypatch.setattr(http_server, "get_user_manager", lambda: FakeUserManager())
    monkeypatch.setattr(http_server, "get_client_manager", lambda: FakeClientManager())

    payload = json.loads(await http_server.xianyu_delete_user(user_id="user-1"))

    assert payload["user_id"] == "user-1"
    assert payload["status"] == "disabled"


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

    _patch_client(monkeypatch, http_server, FakeClient())

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

    _patch_client(monkeypatch, http_server, FakeClient())

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

    _patch_client(monkeypatch, http_server, FakeClient())

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

    _patch_client(monkeypatch, http_server, FakeClient())

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

    monkeypatch.setattr(http_server, "_resolve_user_id", lambda uid: "default")

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

    _patch_client(monkeypatch, http_server, FakeClient())

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

    _patch_client(monkeypatch, http_server, FakeClient())

    payload = json.loads(await http_server.xianyu_get_messages(conversation_id="conv-1", limit=5))

    assert payload == {
        "success": False,
        "source": "websocket",
        "message": "history timeout",
        "messages": [],
        "count": 0,
    }
