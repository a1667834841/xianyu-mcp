import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_server import http_server


class TestMCPHttpToolsIntegration:
    @pytest.mark.asyncio
    async def test_xianyu_login_success(self):
        """HTTP/SSE 登录工具返回客户端登录结果。"""
        mock_client = AsyncMock()
        mock_client.login.return_value = {
            "success": True,
            "logged_in": False,
            "qr_code_url": "https://example.com/qr",
        }

        with patch.object(http_server, "get_client", return_value=mock_client):
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

        with patch.object(http_server, "get_client", return_value=mock_client):
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

        with patch.object(http_server, "get_client", return_value=mock_client):
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

        with patch.object(http_server, "get_client", return_value=mock_client):
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

        with patch.object(http_server, "get_client", return_value=mock_client):
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

        with patch.object(http_server, "get_client", return_value=mock_client):
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

        with patch.object(http_server, "get_client", return_value=mock_client):
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

        with patch.object(http_server, "get_client", return_value=mock_client):
            payload = json.loads(
                await http_server.xianyu_get_messages(conversation_id="conv_123", limit=3)
            )

        assert payload["source"] == "websocket"
        assert payload["count"] == 1
        assert payload["messages"][0]["message_id"] == "msg_123"
