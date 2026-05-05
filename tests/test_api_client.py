import asyncio
import logging
from pathlib import Path
import pytest
from unittest.mock import AsyncMock, patch, MagicMock, PropertyMock
from src.api.client import XianyuApiClient
from src.api.websocket_client import WebSocketClient
from src.settings import build_user_settings


class TestXianyuApiClient:
    @pytest.mark.asyncio
    async def test_singleton_pattern(self):
        """测试单例模式"""
        client1 = XianyuApiClient()
        client2 = XianyuApiClient()
        
        assert client1 is client2

    @pytest.mark.asyncio
    async def test_search_delegates_http_client(self):
        """测试搜索委托给 HttpClient"""
        client = XianyuApiClient()
        
        with patch.object(client.http_client, "search", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = []
            
            result = await client.search(keyword="iPhone", rows=30)
            
            mock_search.assert_called_once_with(keyword="iPhone", rows=30)

    @pytest.mark.asyncio
    async def test_login_returns_logged_in_when_session_valid(self):
        client = XianyuApiClient()

        with patch.object(client.http_client, "check_session", new_callable=AsyncMock) as mock_check:
            mock_check.return_value = {"valid": True, "message": "Cookie 有效"}
            with patch.object(client.http_client, "login", new_callable=AsyncMock) as mock_login:
                result = await client.login()

        assert result == {"success": True, "logged_in": True, "message": "Cookie 有效"}
        mock_login.assert_not_called()

    @pytest.mark.asyncio
    async def test_publish_requires_images_and_title(self):
        """测试发布需要图片和标题"""
        client = XianyuApiClient()
        
        result = await client.publish()
        assert result["success"] is False
        assert "图片" in result["message"]
        
        result = await client.publish(images_paths=["/path/to/image.jpg"])
        assert result["success"] is False
        assert "标题" in result["message"]

    @pytest.mark.asyncio
    async def test_publish_returns_http_failure_when_no_browser_fallback(self):
        client = XianyuApiClient()

        with patch.object(client.http_client, "publish", new_callable=AsyncMock) as mock_api:
            mock_api.return_value = {"success": False, "message": "发布接口返回非 JSON"}

            result = await client.publish(
                images_paths=["/path/to/image.jpg"],
                title="测试商品",
            )

        assert result == {
            "success": False,
            "method": "http",
            "message": "发布接口返回非 JSON",
        }

    @pytest.mark.asyncio
    async def test_ws_send_message_starts_websocket_before_sending(self):
        client = XianyuApiClient()

        with patch.object(type(client.ws_client), 'is_connected', new_callable=PropertyMock) as mock_conn:
            mock_conn.return_value = True
            with patch.object(client, "ensure_ws_started", new_callable=AsyncMock) as mock_start:
                mock_start.return_value = {"success": True, "status": "connected", "reason": "send_message"}
                with patch.object(client.ws_client, "send_message", new_callable=AsyncMock) as mock_send:
                    mock_send.return_value = True

                    result = await client.ws_send_message("target-1", "hello", "", "conv-1")

        assert result == {"success": True, "message": "消息已发送"}
        mock_start.assert_awaited_once_with(reason="send_message")
        mock_send.assert_awaited_once_with("target-1", "hello", "", "conv-1")

    @pytest.mark.asyncio
    async def test_ws_send_message_returns_start_failure_when_websocket_unavailable(self):
        client = XianyuApiClient()

        with patch.object(type(client.ws_client), 'is_connected', new_callable=PropertyMock) as mock_conn:
            mock_conn.return_value = False
            with patch.object(client, "ensure_ws_started", new_callable=AsyncMock) as mock_start:
                mock_start.return_value = {"success": False, "status": "failed", "message": "token failed"}
                with patch.object(client.ws_client, "send_message", new_callable=AsyncMock) as mock_send:
                    result = await client.ws_send_message("target-1", "hello", "", "conv-1")

        assert result == {"success": False, "message": "WebSocket 未连接: token failed"}
        mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_conversation_resolves_seller_from_detail(self):
        client = XianyuApiClient()
        client.settings = build_user_settings(
            user_id="default",
            token_file=Path("/tmp/token.json"),
            chrome_user_data_dir=Path("/tmp/profile"),
            data_root=Path("/tmp/data"),
            create_conversation_greeting="在吗？",
        )

        with patch.object(client.http_client, "get_item_detail", new_callable=AsyncMock) as mock_detail:
            mock_detail.return_value = {
                "sellerDO": {"sellerId": "seller-123"}
            }
            with patch.object(client, "ensure_ws_started", new_callable=AsyncMock) as mock_start:
                mock_start.return_value = {"success": True, "status": "connected"}
                with patch.object(type(client.ws_client), 'is_connected', new_callable=PropertyMock) as mock_conn:
                    mock_conn.return_value = True
                    with patch.object(client.ws_client, "create_conversation", new_callable=AsyncMock) as mock_create:
                        mock_create.return_value = {"success": True, "conversation_id": "conv-123"}
                        with patch.object(client, "ws_send_message", new_callable=AsyncMock) as mock_send:
                            mock_send.return_value = {"success": True, "message": "消息已发送"}

                            result = await client.create_conversation(
                                item_url="https://www.goofish.com/item?id=1047155930582"
                            )

        assert result == {
            "success": True,
            "conversation_id": "conv-123",
            "item_id": "1047155930582",
            "message": "对话已创建并已发送问候语",
        }
        mock_detail.assert_awaited_once_with(item_id="1047155930582")
        mock_start.assert_awaited_once_with(reason="create_conversation")
        mock_create.assert_awaited_once_with(seller_id="seller-123", item_id="1047155930582")
        mock_send.assert_awaited_once_with(
            target_id="seller-123",
            content="在吗？",
            image_url="",
            conversation_id="conv-123",
        )

    @pytest.mark.asyncio
    async def test_create_conversation_uses_websocket_rpc_when_connected(self):
        client = XianyuApiClient()
        client.settings = build_user_settings(
            user_id="default",
            token_file=Path("/tmp/token.json"),
            chrome_user_data_dir=Path("/tmp/profile"),
            data_root=Path("/tmp/data"),
            create_conversation_greeting="你好，请问还在吗？",
        )

        with patch.object(client.http_client, "get_item_detail", new_callable=AsyncMock) as mock_detail:
            mock_detail.return_value = {"sellerDO": {"sellerId": "2201414115913"}}
            with patch.object(client, "ensure_ws_started", new_callable=AsyncMock) as mock_start:
                mock_start.return_value = {"success": True, "status": "connected"}
                with patch.object(type(client.ws_client), 'is_connected', new_callable=PropertyMock) as mock_conn:
                    mock_conn.return_value = True
                    with patch.object(client.ws_client, "create_conversation", new_callable=AsyncMock) as mock_ws_create:
                        mock_ws_create.return_value = {"success": True, "conversation_id": "60971615689"}
                        with patch.object(client, "ws_send_message", new_callable=AsyncMock) as mock_send:
                            mock_send.return_value = {"success": True, "message": "消息已发送"}

                            result = await client.create_conversation(
                                item_url="https://www.goofish.com/item?id=1027628395193"
                            )

        assert result == {
            "success": True,
            "conversation_id": "60971615689",
            "item_id": "1027628395193",
            "message": "对话已创建并已发送问候语",
        }
        mock_start.assert_awaited_once_with(reason="create_conversation")
        mock_ws_create.assert_awaited_once_with(seller_id="2201414115913", item_id="1027628395193")
        mock_send.assert_awaited_once_with(
            target_id="2201414115913",
            content="你好，请问还在吗？",
            image_url="",
            conversation_id="60971615689",
        )

    @pytest.mark.asyncio
    async def test_create_conversation_sends_default_greeting_after_creation(self):
        client = XianyuApiClient()
        client.settings = build_user_settings(
            user_id="default",
            token_file=Path("/tmp/token.json"),
            chrome_user_data_dir=Path("/tmp/profile"),
            data_root=Path("/tmp/data"),
            create_conversation_greeting="在吗？",
        )

        with patch.object(client.http_client, "get_item_detail", new_callable=AsyncMock) as mock_detail:
            mock_detail.return_value = {"sellerDO": {"sellerId": "2201414115913"}}
            with patch.object(client, "ensure_ws_started", new_callable=AsyncMock) as mock_start:
                mock_start.return_value = {"success": True, "status": "connected"}
                with patch.object(type(client.ws_client), "is_connected", new_callable=PropertyMock) as mock_conn:
                    mock_conn.return_value = True
                    with patch.object(client.ws_client, "create_conversation", new_callable=AsyncMock) as mock_create:
                        mock_create.return_value = {"success": True, "conversation_id": "conv-123"}
                        with patch.object(client, "ws_send_message", new_callable=AsyncMock) as mock_send:
                            mock_send.return_value = {"success": True, "message": "消息已发送"}

                            result = await client.create_conversation(
                                item_url="https://www.goofish.com/item?id=1047155930582"
                            )

        assert result == {
            "success": True,
            "conversation_id": "conv-123",
            "item_id": "1047155930582",
            "message": "对话已创建并已发送问候语",
        }
        mock_send.assert_awaited_once_with(
            target_id="2201414115913",
            content="在吗？",
            image_url="",
            conversation_id="conv-123",
        )

    @pytest.mark.asyncio
    async def test_create_conversation_returns_failure_when_greeting_send_fails(self):
        client = XianyuApiClient()
        client.settings = build_user_settings(
            user_id="default",
            token_file=Path("/tmp/token.json"),
            chrome_user_data_dir=Path("/tmp/profile"),
            data_root=Path("/tmp/data"),
            create_conversation_greeting="你好，请问还在吗？",
        )

        with patch.object(client.http_client, "get_item_detail", new_callable=AsyncMock) as mock_detail:
            mock_detail.return_value = {"sellerDO": {"sellerId": "2201414115913"}}
            with patch.object(client, "ensure_ws_started", new_callable=AsyncMock) as mock_start:
                mock_start.return_value = {"success": True, "status": "connected"}
                with patch.object(type(client.ws_client), "is_connected", new_callable=PropertyMock) as mock_conn:
                    mock_conn.return_value = True
                    with patch.object(client.ws_client, "create_conversation", new_callable=AsyncMock) as mock_create:
                        mock_create.return_value = {"success": True, "conversation_id": "conv-123"}
                        with patch.object(client, "ws_send_message", new_callable=AsyncMock) as mock_send:
                            mock_send.return_value = {"success": False, "message": "发送失败"}

                            result = await client.create_conversation(
                                item_url="https://www.goofish.com/item?id=1047155930582"
                            )

        assert result == {
            "success": False,
            "error_code": "GREETING_SEND_FAILED",
            "conversation_id": "conv-123",
            "item_id": "1047155930582",
            "message": "默认问候语发送失败: 发送失败",
        }

    @pytest.mark.asyncio
    async def test_create_conversation_uses_loaded_default_greeting_when_settings_not_replaced(self):
        client = XianyuApiClient()
        client.settings = build_user_settings(
            user_id="default",
            token_file=Path("/tmp/token.json"),
            chrome_user_data_dir=Path("/tmp/profile"),
            data_root=Path("/tmp/data"),
            create_conversation_greeting="你好，请问还在吗？",
        )

        with patch("src.api.client.load_settings") as mock_load_settings:
            mock_load_settings.return_value = build_user_settings(
                user_id="default",
                token_file=Path("/tmp/token.json"),
                chrome_user_data_dir=Path("/tmp/profile"),
                data_root=Path("/tmp/data"),
                create_conversation_greeting="在吗？",
            )

            await client.initialize(cookies={"test": "cookie"}, device_id="test-device")

            with patch.object(client.http_client, "get_item_detail", new_callable=AsyncMock) as mock_detail:
                mock_detail.return_value = {"sellerDO": {"sellerId": "2201414115913"}}
                with patch.object(client, "ensure_ws_started", new_callable=AsyncMock) as mock_start:
                    mock_start.return_value = {"success": True, "status": "connected"}
                    with patch.object(type(client.ws_client), "is_connected", new_callable=PropertyMock) as mock_conn:
                        mock_conn.return_value = True
                        with patch.object(client.ws_client, "create_conversation", new_callable=AsyncMock) as mock_create:
                            mock_create.return_value = {"success": True, "conversation_id": "conv-123"}
                            with patch.object(client, "ws_send_message", new_callable=AsyncMock) as mock_send:
                                mock_send.return_value = {"success": True, "message": "消息已发送"}

                                result = await client.create_conversation(
                                    item_url="https://www.goofish.com/item?id=1047155930582"
                                )

        assert result == {
            "success": True,
            "conversation_id": "conv-123",
            "item_id": "1047155930582",
            "message": "对话已创建并已发送问候语",
        }
        mock_send.assert_awaited_once_with(
            target_id="2201414115913",
            content="在吗？",
            image_url="",
            conversation_id="conv-123",
        )

    @pytest.mark.asyncio
    async def test_create_conversation_rejects_own_item(self):
        client = XianyuApiClient()
        client.http_client.cookies["unb"] = "4188939592"

        with patch.object(client.http_client, "get_item_detail", new_callable=AsyncMock) as mock_detail:
            mock_detail.return_value = {"sellerDO": {"sellerId": 4188939592}}
            result = await client.create_conversation(
                item_url="https://www.goofish.com/item?id=1047155930582"
            )

        assert result == {
            "success": False,
            "error_code": "CANNOT_CREATE_CONVERSATION_WITH_SELF",
            "item_id": "1047155930582",
            "message": "无法与自己创建对话，商品为当前账号发布",
        }

    @pytest.mark.asyncio
    async def test_get_ws_status_returns_correct_snapshot(self):
        """测试 get_ws_status() 返回正确快照"""
        client = XianyuApiClient()
        client.ws_status = "starting"
        client.ws_last_error = None
        client.ws_started_at = "2024-01-01T00:00:00"
        with patch.object(type(client.ws_client), 'is_connected', new_callable=PropertyMock) as mock_conn:
            mock_conn.return_value = False
            
            result = client.get_ws_status()
        
        assert result["connected"] is False
        assert result["status"] == "starting"
        assert result["last_error"] is None
        assert result["started_at"] == "2024-01-01T00:00:00"

    @pytest.mark.asyncio
    async def test_get_ws_status_returns_connected_when_connected(self):
        """测试 get_ws_status() 已连接时返回 connected"""
        client = XianyuApiClient()
        client.ws_status = "starting"
        with patch.object(type(client.ws_client), 'is_connected', new_callable=PropertyMock) as mock_conn:
            mock_conn.return_value = True
            
            result = client.get_ws_status()
        
        assert result["connected"] is True
        assert result["status"] == "connected"

    @pytest.mark.asyncio
    async def test_ensure_ws_started_fast_return_when_connected(self):
        """测试 ensure_ws_started() 已连接时的快速返回路径"""
        client = XianyuApiClient()
        client.ws_status = "connected"
        with patch.object(type(client.ws_client), 'is_connected', new_callable=PropertyMock) as mock_conn:
            mock_conn.return_value = True
            
            result = await client.ensure_ws_started(reason="test")
        
        assert result["success"] is True
        assert result["status"] == "connected"
        assert result["reason"] == "test"

    @pytest.mark.asyncio
    async def test_ensure_ws_started_idempotent_when_starting(self):
        """测试 ensure_ws_started() 启动中时的幂等返回"""
        client = XianyuApiClient()
        client.ws_status = "disconnected"
        client._ws_start_task = None
        client.ws_client.connect = AsyncMock(return_value=True)
        
        with patch.object(type(client.ws_client), 'is_connected', new_callable=PropertyMock) as mock_conn:
            mock_conn.return_value = False
            
            result1 = await client.ensure_ws_started(reason="first")
            result2 = await client.ensure_ws_started(reason="second")
        
        assert result1["success"] is True
        assert result1["status"] == "starting"
        assert result2["success"] is True
        assert result2["status"] == "starting"
        
        await client._ws_start_task

    @pytest.mark.asyncio
    async def test_run_ws_start_updates_status_on_connect_failure(self):
        """测试 _run_ws_start() 连接失败时的状态更新"""
        client = XianyuApiClient()
        client.ws_client.connect = AsyncMock(return_value=False)
        client.ws_status = "starting"
        
        with patch.object(type(client.ws_client), 'is_connected', new_callable=PropertyMock) as mock_conn:
            mock_conn.return_value = False
            await client._run_ws_start(reason="test")
        
        assert client.ws_status == "failed"
        assert client.ws_last_error == "WebSocket connect returned false"

    @pytest.mark.asyncio
    async def test_run_ws_start_updates_status_on_timeout(self):
        """测试 _run_ws_start() 超时场景"""
        client = XianyuApiClient()
        client.ws_client.connect = AsyncMock(return_value=True)
        client.ws_status = "starting"
        
        with patch.object(type(client.ws_client), 'is_connected', new_callable=PropertyMock) as mock_conn:
            mock_conn.return_value = False
            await client._run_ws_start(reason="test")
        
        assert client.ws_status == "failed"
        assert "timed out" in client.ws_last_error.lower()

    @pytest.mark.asyncio
    async def test_run_ws_start_updates_status_on_exception(self):
        """测试 _run_ws_start() 异常时的状态更新"""
        client = XianyuApiClient()
        client.ws_client.connect = AsyncMock(side_effect=Exception("Connection error"))
        client.ws_status = "starting"
        
        await client._run_ws_start(reason="test")
        
        assert client.ws_status == "failed"
        assert "Connection error" in client.ws_last_error

    @pytest.mark.asyncio
    async def test_run_ws_start_reports_websocket_internal_init_error(self):
        """测试 WebSocket 内部异步初始化失败时不长期停留 starting。"""
        client = XianyuApiClient()
        client.ws_status = "starting"
        client.ws_client.connect = AsyncMock(return_value=True)
        client.ws_client.last_error = "accessToken 获取失败"
        client.ws_client._running = False

        with patch.object(type(client.ws_client), 'is_connected', new_callable=PropertyMock) as mock_conn:
            mock_conn.return_value = False
            await client._run_ws_start(reason="test")

        assert client.ws_status == "failed"
        assert client.ws_last_error == "accessToken 获取失败"

    @pytest.mark.asyncio
    async def test_client_starts_http_keepalive_when_session_valid(self):
        client = XianyuApiClient()

        class FakeKeepalive:
            def __init__(self):
                self.started = False

            def start(self):
                self.started = True

        client.keepalive_service = FakeKeepalive()

        with patch.object(client.http_client, "check_session", new_callable=AsyncMock) as mock_check:
            mock_check.return_value = {"valid": True}
            result = await client.start_keepalive()

        assert result is True
        assert client.keepalive_service.started is True

    @pytest.mark.asyncio
    async def test_client_does_not_start_http_keepalive_when_session_invalid(self):
        client = XianyuApiClient()

        class FakeKeepalive:
            def __init__(self):
                self.started = False

            def start(self):
                self.started = True

        client.keepalive_service = FakeKeepalive()

        with patch.object(client.http_client, "check_session", new_callable=AsyncMock) as mock_check:
            mock_check.return_value = {"valid": False}
            result = await client.start_keepalive()

        assert result is False
        assert client.keepalive_service.started is False

    @pytest.mark.asyncio
    async def test_client_stops_http_keepalive(self):
        client = XianyuApiClient()

        class FakeKeepalive:
            def __init__(self):
                self.stopped = False

            async def stop(self):
                self.stopped = True

        client.keepalive_service = FakeKeepalive()

        await client.stop_keepalive()

        assert client.keepalive_service.stopped is True

    @pytest.mark.asyncio
    async def test_get_ws_status_reports_internal_failure(self):
        """测试状态快照能反映 WebSocketClient 内部失败原因。"""
        client = XianyuApiClient()
        client.ws_status = "starting"
        client.ws_last_error = None
        client.ws_client.last_error = "accessToken 获取失败"
        client.ws_client._running = False

        with patch.object(type(client.ws_client), 'is_connected', new_callable=PropertyMock) as mock_conn:
            mock_conn.return_value = False
            result = client.get_ws_status()

        assert result["connected"] is False
        assert result["status"] == "failed"
        assert result["last_error"] == "accessToken 获取失败"

    @pytest.mark.asyncio
    async def test_initialize_stops_existing_ws_connection(self):
        """测试 initialize() 停止现有 WebSocket 连接"""
        client = XianyuApiClient()
        stop_mock = AsyncMock()
        with patch.object(client.ws_client, 'stop', stop_mock):
            with patch.object(type(client.ws_client), 'is_connected', new_callable=PropertyMock) as mock_conn:
                mock_conn.return_value = True
                await client.initialize(cookies={"test": "cookie"}, device_id="test_device")
        
        stop_mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_initialize_creates_new_ws_client(self):
        """测试 initialize() 创建新的 ws_client"""
        client = XianyuApiClient()
        old_ws_client = client.ws_client
        
        await client.initialize(cookies={"test": "cookie"}, device_id="test_device")
        
        assert client.ws_client is not old_ws_client

    @pytest.mark.asyncio
    async def test_initialize_cancels_existing_ws_start_task(self):
        """测试 initialize() 会取消未完成的 WS 启动任务，避免旧任务污染新状态。"""
        client = XianyuApiClient()
        cancelled = asyncio.Event()

        async def pending_start():
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                cancelled.set()
                raise

        client._ws_start_task = asyncio.create_task(pending_start())
        await asyncio.sleep(0)

        await client.initialize(cookies={"test": "cookie"}, device_id="test_device")

        assert cancelled.is_set()
        assert client._ws_start_task is None
        assert client.ws_status == "disconnected"

    @pytest.mark.asyncio
    async def test_old_ws_start_task_does_not_update_replaced_ws_client_status(self):
        """测试旧 WS 启动任务绑定旧实例，不会把新实例状态写成 connected。"""
        client = XianyuApiClient()
        old_ws_client = client.ws_client
        old_ws_client.connect = AsyncMock(return_value=True)
        client.ws_status = "starting"

        await client.initialize(cookies={"new": "cookie"}, device_id="new_device")
        new_ws_client = client.ws_client

        with patch.object(type(old_ws_client), 'is_connected', new_callable=PropertyMock) as old_conn:
            old_conn.return_value = True
            await client._run_ws_start(reason="old", ws_client=old_ws_client)

        assert client.ws_client is new_ws_client
        assert client.ws_status == "disconnected"


@pytest.mark.asyncio
async def test_ensure_ws_started_creates_background_task(monkeypatch):
    client = XianyuApiClient()
    client.ws_status = "disconnected"
    client.ws_last_error = None
    client.ws_started_at = None
    client._ws_start_task = None
    client.ws_client.connect = AsyncMock(return_value=True)

    result = await client.ensure_ws_started(reason="service_start")

    assert result["success"] is True
    assert result["status"] == "starting"
    assert result["reason"] == "service_start"
    assert client._ws_start_task is not None

    await client._ws_start_task


@pytest.mark.asyncio
async def test_start_ws_listener_uses_ensure_ws_started(monkeypatch):
    client = XianyuApiClient()
    client.ensure_ws_started = AsyncMock(
        return_value={"success": True, "status": "starting", "reason": "manual"}
    )

    result = await client.start_ws_listener()

    assert result == {"success": True, "status": "starting", "reason": "manual"}
    client.ensure_ws_started.assert_awaited_once_with(reason="manual")


@pytest.mark.asyncio
async def test_stop_ws_listener_marks_status_disconnected(monkeypatch):
    client = XianyuApiClient()
    client.ws_status = "connected"
    client.ws_last_error = None
    client.ws_client.stop = AsyncMock()

    result = await client.stop_ws_listener()

    assert result["success"] is True
    assert client.ws_status == "disconnected"
    assert client.get_ws_status()["status"] == "disconnected"


@pytest.mark.asyncio
async def test_publish_returns_http_failure_when_api_raises():
    client = XianyuApiClient()

    with patch.object(client.http_client, "publish", new_callable=AsyncMock) as mock_api:
        mock_api.side_effect = Exception("API failed")

        result = await client.publish(
            images_paths=["/path/to/image.jpg"],
            title="测试商品",
            item_url="http://example.com/item/123",
        )

    mock_api.assert_called_once()
    assert result == {
        "success": False,
        "method": "http",
        "message": "API failed",
    }


@pytest.mark.asyncio
async def test_refresh_token_returns_http_failure_when_api_raises():
    client = XianyuApiClient()

    with patch.object(client.http_client, "refresh_token", new_callable=AsyncMock) as mock_api:
        mock_api.side_effect = Exception("API failed")

        result = await client.refresh_token()

    assert result == {"success": False, "method": "http", "message": "API failed"}


@pytest.mark.asyncio
async def test_websocket_init_success_log_does_not_include_access_token(caplog):
    class FakeHttpClient:
        cookies = {"unb": "user-1"}
        device_id = "device-1"

        async def get_access_token(self):
            return "oauth_k1:abcdefghijklmnopqrstuvwxyz"

    class FakeWs:
        def __init__(self):
            self.sent = []

        async def send(self, payload):
            self.sent.append(payload)

    ws_client = WebSocketClient(FakeHttpClient())
    ws_client.ws = FakeWs()

    with caplog.at_level(logging.INFO, logger="src.api.websocket_client"):
        result = await ws_client._init_connection()

    assert result is True
    assert "获取 accessToken 成功" in caplog.text
    assert "oauth_k1:abcdefghijklmnopqrstuvwxyz" not in caplog.text
    assert "oauth_k1:abcdefghijk" not in caplog.text
