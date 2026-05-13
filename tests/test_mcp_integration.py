import json
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from mcp_server import http_server


class TestMCPHttpToolsIntegration:
    @pytest.mark.asyncio
    async def test_xianyu_show_qrcode_always_creates_pending_session(self):
        mock_client = AsyncMock()
        mock_client.show_qrcode.return_value = {
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

        mock_cm = MagicMock()
        mock_cm.get_client.return_value = mock_client

        mock_pending_manager = MagicMock()

        with (
            patch.object(http_server, "get_client_manager", return_value=mock_cm),
            patch.object(http_server, "get_pending_login_manager", return_value=mock_pending_manager),
        ):
            payload = json.loads(await http_server.xianyu_show_qrcode())

        assert payload["success"] is True
        assert payload["phase"] == "login_required"
        assert payload["t"] == "token-123"
        assert payload["ck"] == "ck-123"
        assert payload["qr_code"]["public_url"] == "https://example.com/qr.png"
        assert "url" not in payload["qr_code"]
        mock_cm.get_client.assert_called_once_with(http_server.PENDING_LOGIN_CLIENT_ID)
        mock_client.show_qrcode.assert_awaited_once_with()
        mock_pending_manager.create_session.assert_called_once()

    @pytest.mark.asyncio
    async def test_xianyu_login_success(self):
        """HTTP/SSE 登录工具返回客户端登录结果。"""
        mock_client = AsyncMock()
        mock_client.login.return_value = {
            "success": True,
            "logged_in": False,
            "qr_code_url": "https://example.com/qr",
        }

        mock_cm = MagicMock()
        mock_cm.get_client.return_value = mock_client
        with (
            patch.object(http_server, "get_client_manager", return_value=mock_cm),
            patch.object(http_server, "_resolve_user_id", return_value="default"),
        ):
            payload = json.loads(await http_server.xianyu_login())

        assert payload["success"] is True
        assert payload["qr_code_url"] == "https://example.com/qr"
        mock_client.login.assert_awaited_once_with()

    @pytest.mark.asyncio
    async def test_xianyu_search_success(self):
        """HTTP/SSE 搜索工具透传搜索结果。"""
        mock_client = AsyncMock()
        mock_client.search.return_value = {
            "success": True,
            "items": [{"item_id": "123", "title": "测试商品", "price": "¥100"}],
            "total": 1,
            "engine_used": "http_api",
        }

        mock_cm = MagicMock()
        mock_cm.get_client.return_value = mock_client
        with (
            patch.object(http_server, "get_client_manager", return_value=mock_cm),
            patch.object(http_server, "_resolve_user_id", return_value="default"),
        ):
            payload = json.loads(await http_server.xianyu_search(keyword="iPhone", rows=30))

        assert payload["total"] == 1
        assert payload["items"][0]["item_id"] == "123"
        mock_client.search.assert_awaited_once_with(
            keyword="iPhone",
            rows=30,
            min_price=None,
            max_price=None,
            free_ship=False,
            sort_field="",
            sort_order="",
        )

    def test_stdio_business_tool_registry_removed(self):
        """旧 stdio 模块不再暴露第二套 list_tools/call_tool 业务逻辑。"""
        import mcp_server.server as server_module

        assert not hasattr(server_module, "list_tools")
        assert not hasattr(server_module, "call_tool")

    @pytest.mark.asyncio
    async def test_xianyu_ws_send_success(self):
        """HTTP/SSE WebSocket 发消息工具。"""
        mock_client = AsyncMock()
        mock_client.ws_send_message.return_value = {"success": True, "message": "消息已发送"}

        mock_cm = MagicMock()
        mock_cm.get_client.return_value = mock_client
        with (
            patch.object(http_server, "get_client_manager", return_value=mock_cm),
            patch.object(http_server, "_resolve_user_id", return_value="default"),
        ):
            payload = json.loads(
                await http_server.xianyu_ws_send(target_id="user_123", content="hello")
            )

        assert payload["success"] is True
        mock_client.ws_send_message.assert_awaited_once_with("user_123", "hello", "", "")

    @pytest.mark.asyncio
    async def test_xianyu_publish_success(self):
        """HTTP/SSE 发布工具使用当前公开参数。"""
        mock_client = AsyncMock()
        mock_client.publish.return_value = {"success": True, "item_id": "item_123"}

        mock_cm = MagicMock()
        mock_cm.get_client.return_value = mock_client
        with (
            patch.object(http_server, "get_client_manager", return_value=mock_cm),
            patch.object(http_server, "_resolve_user_id", return_value="default"),
        ):
            payload = json.loads(
                await http_server.xianyu_publish(
                    images_paths="/tmp/a.jpg,/tmp/b.jpg",
                    title="测试商品",
                    current_price=88.0,
                    original_price=128.0,
                    shipping="包邮",
                )
            )

        assert payload == {"success": True, "item_id": "item_123"}
        mock_client.publish.assert_awaited_once_with(
            images_paths=["/tmp/a.jpg", "/tmp/b.jpg"],
            title="测试商品",
            price={"current_price": 88.0, "original_price": 128.0},
            shipping="包邮",
            self_pickup=False,
            post_price=0,
        )

    @pytest.mark.asyncio
    async def test_xianyu_publish_from_item_url_success(self):
        """HTTP/SSE 铺货工具转发商品链接到客户端。"""
        mock_client = AsyncMock()
        mock_client.publish_from_item_url.return_value = {
            "success": True,
            "source_platform": "xianyu",
            "source_item_url": "https://www.goofish.com/item?id=1047155930582",
            "published_item_id": "item_123",
            "published_item_url": "https://www.goofish.com/item?id=item_123",
            "selected_price": 88.0,
            "logs": [],
        }

        mock_cm = MagicMock()
        mock_cm.get_client.return_value = mock_client
        with (
            patch.object(http_server, "get_client_manager", return_value=mock_cm),
            patch.object(http_server, "_resolve_user_id", return_value="default"),
        ):
            payload = json.loads(
                await http_server.xianyu_publish_from_item_url(
                    item_url="https://www.goofish.com/item?id=1047155930582"
                )
            )

        assert payload == {
            "success": True,
            "source_platform": "xianyu",
            "source_item_url": "https://www.goofish.com/item?id=1047155930582",
            "published_item_id": "item_123",
            "published_item_url": "https://www.goofish.com/item?id=item_123",
            "selected_price": 88.0,
            "logs": [],
        }
        mock_client.publish_from_item_url.assert_awaited_once_with(
            item_url="https://www.goofish.com/item?id=1047155930582"
        )

    @pytest.mark.asyncio
    async def test_xianyu_ws_status_success(self):
        """HTTP/SSE WebSocket 状态工具。"""
        mock_client = MagicMock()
        mock_client.get_ws_status.return_value = {
            "connected": True,
            "status": "connected",
            "last_error": None,
            "started_at": "2026-05-03T13:00:00",
        }

        mock_cm = MagicMock()
        mock_cm.get_client.return_value = mock_client
        with (
            patch.object(http_server, "get_client_manager", return_value=mock_cm),
            patch.object(http_server, "_resolve_user_id", return_value="default"),
        ):
            payload = json.loads(await http_server.xianyu_ws_status())

        assert payload["connected"] is True
        assert payload["status"] == "connected"

    @pytest.mark.asyncio
    async def test_xianyu_list_conversations_success(self):
        """HTTP/SSE 对话列表工具使用 WebSocket RPC 返回格式。"""
        class FakeWsClient:
            async def get_conversation_list(self, max_sort_index=None, page_size=20):
                return {
                    "success": True,
                    "conversations": [
                        {
                            "cid": "conv_123",
                            "peer_user_name": "买家",
                            "last_message": "你好",
                            "last_message_time": 123.0,
                            "unread_count": 1,
                            "item_id": "item_123",
                        }
                    ],
                    "hasMore": False,
                }

        mock_client = MagicMock()
        mock_client.get_ws_status.return_value = {"connected": True, "status": "connected"}
        mock_client.ws_client = FakeWsClient()

        mock_cm = MagicMock()
        mock_cm.get_client.return_value = mock_client
        with (
            patch.object(http_server, "get_client_manager", return_value=mock_cm),
            patch.object(http_server, "_resolve_user_id", return_value="default"),
        ):
            payload = json.loads(await http_server.xianyu_list_conversations(limit=10))

        assert payload["source"] == "websocket"
        assert payload["count"] == 1
        assert payload["conversations"][0]["conversation_id"] == "conv_123"

    @pytest.mark.asyncio
    async def test_xianyu_get_messages_success(self):
        """HTTP/SSE 消息历史工具使用 WebSocket RPC 返回格式。"""
        class FakeWsClient:
            async def get_message_history(self, chat_id, anchor=None, count=50):
                return {
                    "success": True,
                    "messages": [
                        {
                            "message_id": "msg_123",
                            "sender_id": "user_123",
                            "receiver_id": "me",
                            "content": "你好",
                            "timestamp": 123.0,
                        }
                    ],
                    "hasMore": False,
                    "nextCursor": 0,
                }

        mock_client = MagicMock()
        mock_client.ws_is_connected.return_value = True
        mock_client.ws_client = FakeWsClient()

        mock_cm = MagicMock()
        mock_cm.get_client.return_value = mock_client
        with (
            patch.object(http_server, "get_client_manager", return_value=mock_cm),
            patch.object(http_server, "_resolve_user_id", return_value="default"),
        ):
            payload = json.loads(
                await http_server.xianyu_get_messages(conversation_id="conv_123", limit=3)
            )

        assert payload["source"] == "websocket"
        assert payload["count"] == 1
        assert payload["messages"][0]["message_id"] == "msg_123"

    @pytest.mark.asyncio
    async def test_xianyu_add_user_success(self):
        """HTTP/SSE 用户管理工具在扫码确认后创建用户。"""
        mock_um = MagicMock()
        mock_um.get_user.side_effect = [
            ValueError("User 'new-user' not found"),
            {
                "user_id": "new-user",
                "username": "新用户",
                "status": "active",
                "keepalive_enabled": True,
            },
        ]
        mock_um.add_user.return_value = {
            "user_id": "new-user",
            "username": "新用户",
            "status": "active",
        }
        mock_pending_manager = MagicMock()
        mock_pending_manager.get_session.return_value = {"t": "token-123", "ck": "ck-123"}

        mock_client = AsyncMock()
        mock_client.login_poll.return_value = {"status": "CONFIRMED"}
        mock_client.check_session.return_value = {"valid": True}
        mock_client.http_client = MagicMock()
        mock_client.http_client.get_authenticated_user_identity.return_value = {
            "user_id": "new-user",
            "username": "new-user",
        }
        mock_client.http_client.fetch_user_nickname = AsyncMock(return_value="真实昵称")

        mock_user_client = AsyncMock()
        mock_user_client.http_client = MagicMock()
        mock_user_client.ensure_ws_started = AsyncMock(
            return_value={"success": True, "status": "starting", "reason": "login_confirmed"}
        )
        mock_user_client.get_ws_status = MagicMock(return_value={
            "connected": False,
            "status": "starting",
            "last_error": None,
            "started_at": None,
        })

        mock_cm = MagicMock()
        mock_cm.start_keepalive = AsyncMock()
        def _get_client(user_id):
            if user_id == http_server.PENDING_LOGIN_CLIENT_ID:
                return mock_client
            return mock_user_client
        mock_cm.get_client.side_effect = _get_client

        with (
            patch.object(http_server, "get_user_manager", return_value=mock_um),
            patch.object(http_server, "get_pending_login_manager", return_value=mock_pending_manager),
            patch.object(http_server, "get_client_manager", return_value=mock_cm),
        ):
            payload = json.loads(
                await http_server.xianyu_add_user(t="token-123", ck="ck-123")
            )

        assert payload["success"] is True
        assert payload["phase"] == "completed"
        assert payload["user"]["user_id"] == "new-user"
        mock_pending_manager.get_session.assert_called_once_with(t="token-123", ck="ck-123")
        assert mock_cm.get_client.call_count == 3
        mock_cm.get_client.assert_any_call(http_server.PENDING_LOGIN_CLIENT_ID)
        mock_cm.get_client.assert_any_call("new-user")
        mock_client.login_poll.assert_awaited_once_with(t="token-123", ck="ck-123")
        mock_client.check_session.assert_awaited_once_with()
        mock_um.add_user.assert_called_once_with(user_id="new-user", username="真实昵称")
        mock_um.update_user.assert_called_once()
        mock_pending_manager.delete_session.assert_called_once_with(t="token-123", ck="ck-123")
        mock_user_client.initialize.assert_awaited_once_with(
            cookies=mock_client.http_client.cookies,
            device_id=mock_client.http_client.device_id,
        )
        mock_user_client.http_client._save_auth.assert_called_once_with(mock_client.http_client.cookies)
        assert payload["ws_auto_start"] is True
        assert payload["ws_status"]["status"] == "starting"
        mock_cm.start_keepalive.assert_awaited_once()
        mock_user_client.ensure_ws_started.assert_awaited_once_with(reason="login_confirmed")

    @pytest.mark.asyncio
    async def test_xianyu_add_user_returns_already_exists_when_user_exists(self):
        mock_um = MagicMock()
        mock_um.get_user.return_value = {
            "user_id": "existing-user",
            "username": "已存在用户",
            "status": "active",
            "keepalive_enabled": True,
        }
        mock_um.update_user.return_value = {
            "user_id": "existing-user",
            "username": "已存在用户",
            "status": "active",
        }
        mock_pending_manager = MagicMock()
        mock_pending_manager.get_session.return_value = {"t": "token-123", "ck": "ck-123"}

        mock_client = AsyncMock()
        mock_client.login_poll.return_value = {"status": "CONFIRMED"}
        mock_client.check_session.return_value = {"valid": True}
        mock_client.http_client = MagicMock()
        mock_client.http_client.get_authenticated_user_identity.return_value = {
            "user_id": "existing-user",
            "username": "existing-user",
        }
        mock_client.http_client.fetch_user_nickname = AsyncMock(return_value="老用户")

        mock_existing_client = AsyncMock()
        mock_existing_client.http_client = MagicMock()
        mock_existing_client.ensure_ws_started = AsyncMock(
            return_value={"success": True, "status": "starting", "reason": "login_confirmed"}
        )
        mock_existing_client.get_ws_status = MagicMock(return_value={
            "connected": False,
            "status": "starting",
            "last_error": None,
            "started_at": None,
        })

        mock_cm = MagicMock()
        mock_cm.stop_user = AsyncMock()
        mock_cm.start_keepalive = AsyncMock()
        def _get_client(user_id):
            if user_id == http_server.PENDING_LOGIN_CLIENT_ID:
                return mock_client
            return mock_existing_client
        mock_cm.get_client.side_effect = _get_client

        with (
            patch.object(http_server, "get_user_manager", return_value=mock_um),
            patch.object(http_server, "get_pending_login_manager", return_value=mock_pending_manager),
            patch.object(http_server, "get_client_manager", return_value=mock_cm),
        ):
            payload = json.loads(
                await http_server.xianyu_add_user(t="token-123", ck="ck-123")
            )

        assert payload == {
            "success": True,
            "phase": "already_exists",
            "message": "用户已存在，已刷新登录态",
            "user": {
                "user_id": "existing-user",
                "username": "已存在用户",
                "status": "active",
            },
            "ws_auto_start": True,
            "ws_status": {
                "connected": False,
                "status": "starting",
                "last_error": None,
                "started_at": None,
            },
        }
        mock_pending_manager.delete_session.assert_called_once_with(t="token-123", ck="ck-123")
        mock_um.add_user.assert_not_called()
        mock_um.update_user.assert_called_once()
        mock_cm.get_client.assert_any_call(http_server.PENDING_LOGIN_CLIENT_ID)
        mock_cm.get_client.assert_any_call("existing-user")
        mock_cm.stop_user.assert_awaited_once_with("existing-user")
        mock_existing_client.initialize.assert_awaited_once_with(
            cookies=mock_client.http_client.cookies,
            device_id=mock_client.http_client.device_id,
        )
        mock_existing_client.http_client._save_auth.assert_called_once_with(mock_client.http_client.cookies)
        mock_cm.start_keepalive.assert_awaited_once()
        mock_existing_client.ensure_ws_started.assert_awaited_once_with(reason="login_confirmed")

    @pytest.mark.asyncio
    async def test_xianyu_add_user_falls_back_to_identity_username_when_nickname_empty(self):
        mock_um = MagicMock()
        mock_um.get_user.side_effect = [
            ValueError("User 'bar-user' not found"),
            {
                "user_id": "bar-user",
                "username": "identity-name",
                "status": "active",
                "keepalive_enabled": True,
            },
        ]
        mock_um.add_user.return_value = {
            "user_id": "bar-user",
            "username": "identity-name",
            "status": "active",
        }
        mock_pending_manager = MagicMock()
        mock_pending_manager.get_session.return_value = {"t": "token-123", "ck": "ck-123"}

        mock_client = AsyncMock()
        mock_client.login_poll.return_value = {"status": "CONFIRMED"}
        mock_client.check_session.return_value = {"valid": True}
        mock_client.http_client = MagicMock()
        mock_client.http_client.get_authenticated_user_identity.return_value = {
            "user_id": "bar-user",
            "username": "identity-name",
        }
        mock_client.http_client.fetch_user_nickname = AsyncMock(return_value="")

        mock_user_client = AsyncMock()
        mock_user_client.http_client = MagicMock()
        mock_user_client.ensure_ws_started = AsyncMock(
            return_value={"success": True, "status": "starting", "reason": "login_confirmed"}
        )
        mock_user_client.get_ws_status = MagicMock(return_value={
            "connected": False,
            "status": "starting",
            "last_error": None,
            "started_at": None,
        })

        mock_cm = MagicMock()
        mock_cm.start_keepalive = AsyncMock()
        def _get_client(user_id):
            if user_id == http_server.PENDING_LOGIN_CLIENT_ID:
                return mock_client
            return mock_user_client
        mock_cm.get_client.side_effect = _get_client

        with (
            patch.object(http_server, "get_user_manager", return_value=mock_um),
            patch.object(http_server, "get_pending_login_manager", return_value=mock_pending_manager),
            patch.object(http_server, "get_client_manager", return_value=mock_cm),
        ):
            payload = json.loads(
                await http_server.xianyu_add_user(t="token-123", ck="ck-123")
            )

        assert payload["success"] is True
        assert payload["phase"] == "completed"
        assert payload["user"]["user_id"] == "bar-user"
        assert payload["user"]["username"] == "identity-name"
        mock_um.add_user.assert_called_once_with(user_id="bar-user", username="identity-name")
        mock_pending_manager.delete_session.assert_called_once_with(t="token-123", ck="ck-123")

    @pytest.mark.asyncio
    async def test_xianyu_add_user_falls_back_to_user_id_when_both_empty(self):
        mock_um = MagicMock()
        mock_um.get_user.side_effect = [
            ValueError("User 'uid-user' not found"),
            {
                "user_id": "uid-user",
                "username": "uid-user",
                "status": "active",
                "keepalive_enabled": True,
            },
        ]
        mock_um.add_user.return_value = {
            "user_id": "uid-user",
            "username": "uid-user",
            "status": "active",
        }
        mock_pending_manager = MagicMock()
        mock_pending_manager.get_session.return_value = {"t": "token-123", "ck": "ck-123"}

        mock_client = AsyncMock()
        mock_client.login_poll.return_value = {"status": "CONFIRMED"}
        mock_client.check_session.return_value = {"valid": True}
        mock_client.http_client = MagicMock()
        mock_client.http_client.get_authenticated_user_identity.return_value = {
            "user_id": "uid-user",
            "username": "",
        }
        mock_client.http_client.fetch_user_nickname = AsyncMock(return_value="")

        mock_user_client = AsyncMock()
        mock_user_client.http_client = MagicMock()
        mock_user_client.ensure_ws_started = AsyncMock(
            return_value={"success": True, "status": "starting", "reason": "login_confirmed"}
        )
        mock_user_client.get_ws_status = MagicMock(return_value={
            "connected": False,
            "status": "starting",
            "last_error": None,
            "started_at": None,
        })

        mock_cm = MagicMock()
        mock_cm.start_keepalive = AsyncMock()
        def _get_client(user_id):
            if user_id == http_server.PENDING_LOGIN_CLIENT_ID:
                return mock_client
            return mock_user_client
        mock_cm.get_client.side_effect = _get_client

        with (
            patch.object(http_server, "get_user_manager", return_value=mock_um),
            patch.object(http_server, "get_pending_login_manager", return_value=mock_pending_manager),
            patch.object(http_server, "get_client_manager", return_value=mock_cm),
        ):
            payload = json.loads(
                await http_server.xianyu_add_user(t="token-123", ck="ck-123")
            )

        assert payload["success"] is True
        assert payload["phase"] == "completed"
        assert payload["user"]["user_id"] == "uid-user"
        assert payload["user"]["username"] == "uid-user"
        mock_um.add_user.assert_called_once_with(user_id="uid-user", username="uid-user")
        mock_pending_manager.delete_session.assert_called_once_with(t="token-123", ck="ck-123")

    @pytest.mark.asyncio
    async def test_xianyu_add_user_returns_error_when_pending_session_missing(self):
        mock_pending_manager = MagicMock()
        mock_pending_manager.get_session.side_effect = ValueError("pending session not found")

        with patch.object(http_server, "get_pending_login_manager", return_value=mock_pending_manager):
            payload = json.loads(
                await http_server.xianyu_add_user(t="token-123", ck="ck-123")
            )

        assert payload == {
            "success": False,
            "phase": "error",
            "message": "pending session not found",
        }

    @pytest.mark.asyncio
    async def test_xianyu_add_user_returns_expired_when_pending_session_expired(self):
        mock_pending_manager = MagicMock()
        mock_pending_manager.get_session.side_effect = ValueError("pending session expired")

        with patch.object(http_server, "get_pending_login_manager", return_value=mock_pending_manager):
            payload = json.loads(
                await http_server.xianyu_add_user(t="token-123", ck="ck-123")
            )

        assert payload == {
            "success": False,
            "phase": "expired",
            "message": "pending session expired",
        }

    @pytest.mark.asyncio
    async def test_xianyu_add_user_returns_error_when_confirmed_but_session_invalid(self):
        mock_pending_manager = MagicMock()
        mock_pending_manager.get_session.return_value = {"t": "token-123", "ck": "ck-123"}

        mock_client = AsyncMock()
        mock_client.login_poll.return_value = {"status": "CONFIRMED"}
        mock_client.check_session.return_value = {"valid": False, "message": "cookie invalid"}

        mock_cm = MagicMock()
        mock_cm.get_client.return_value = mock_client

        with (
            patch.object(http_server, "get_pending_login_manager", return_value=mock_pending_manager),
            patch.object(http_server, "get_client_manager", return_value=mock_cm),
        ):
            payload = json.loads(
                await http_server.xianyu_add_user(t="token-123", ck="ck-123")
            )

        assert payload == {
            "success": False,
            "phase": "error",
            "message": "cookie invalid",
            "session": {"valid": False, "message": "cookie invalid"},
        }
        mock_pending_manager.delete_session.assert_not_called()

    @pytest.mark.asyncio
    async def test_xianyu_list_users_success(self):
        """HTTP/SSE 用户管理工具列出用户。"""
        mock_um = MagicMock()
        mock_um.list_users.return_value = [
            {"user_id": "user-1", "username": "用户1", "status": "active"},
        ]

        mock_cm = MagicMock()
        mock_cm.has_keepalive_task.return_value = True
        mock_cm.has_client.return_value = True
        fake_client = MagicMock()
        fake_client.ws_is_connected.return_value = True
        mock_cm.get_client.return_value = fake_client

        with (
            patch.object(http_server, "get_user_manager", return_value=mock_um),
            patch.object(http_server, "get_client_manager", return_value=mock_cm),
        ):
            payload = json.loads(await http_server.xianyu_list_users())

        assert payload["success"] is True
        assert payload["users"][0]["user_id"] == "user-1"
        assert payload["users"][0]["ws_connected"] is True
        assert payload["users"][0]["keepalive_running"] is True

    @pytest.mark.asyncio
    async def test_xianyu_delete_user_success(self):
        """HTTP/SSE 用户管理工具删除用户。"""
        mock_um = MagicMock()
        mock_um.disable_user.return_value = {
            "user_id": "user-1",
            "status": "disabled",
        }

        mock_cm = MagicMock()
        mock_cm.stop_user = AsyncMock()

        with (
            patch.object(http_server, "get_user_manager", return_value=mock_um),
            patch.object(http_server, "get_client_manager", return_value=mock_cm),
        ):
            payload = json.loads(await http_server.xianyu_delete_user(user_id="user-1"))

        assert payload["user_id"] == "user-1"
        assert payload["status"] == "disabled"
        mock_cm.stop_user.assert_awaited_once_with("user-1")
        mock_um.disable_user.assert_called_once_with("user-1")

    @pytest.mark.asyncio
    async def test_xianyu_search_routes_explicit_user_id(self):
        """传入 user_id='user-009' 时路由到对应客户端。"""
        mock_client = AsyncMock()
        mock_client.search.return_value = {
            "success": True,
            "items": [{"item_id": "123", "title": "测试商品", "price": "¥100"}],
            "total": 1,
            "engine_used": "http_api",
        }

        mock_cm = MagicMock()
        mock_cm.get_client.return_value = mock_client
        with patch.object(http_server, "get_client_manager", return_value=mock_cm):
            payload = json.loads(
                await http_server.xianyu_search(keyword="iPhone", user_id="user-009")
            )

        assert payload["total"] == 1
        mock_cm.get_client.assert_called_once_with("user-009")

    @pytest.mark.asyncio
    async def test_xianyu_delete_user_stops_runtime_before_disabling(self):
        """stop_user 在 disable_user 之前被调用。"""
        call_order = []

        async def track_stop(uid):
            call_order.append("stop_user")

        def track_disable(uid):
            call_order.append("disable_user")
            return {"user_id": uid, "status": "disabled"}

        mock_um = MagicMock()
        mock_um.disable_user.side_effect = track_disable

        mock_cm = MagicMock()
        mock_cm.stop_user = AsyncMock(side_effect=track_stop)

        with (
            patch.object(http_server, "get_user_manager", return_value=mock_um),
            patch.object(http_server, "get_client_manager", return_value=mock_cm),
        ):
            await http_server.xianyu_delete_user(user_id="user-001")

        assert call_order == ["stop_user", "disable_user"]
