import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock, PropertyMock
from src.api.client import XianyuApiClient


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
    async def test_refresh_token_api_first_then_fallback(self):
        """测试刷新 Token 优先使用 API，失败后降级浏览器"""
        client = XianyuApiClient()
        
        with patch.object(client.http_client, "refresh_token", new_callable=AsyncMock) as mock_api:
            mock_api.side_effect = Exception("API failed")
            
            with patch.object(client.browser_bridge, "refresh_via_browser", new_callable=AsyncMock) as mock_browser:
                mock_browser.return_value = {"success": True, "method": "browser"}
                
                result = await client.refresh_token()
                
                assert result["success"] == True
                assert result["method"] == "browser"

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
