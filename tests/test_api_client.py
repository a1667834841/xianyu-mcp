import pytest
from unittest.mock import AsyncMock, patch
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
    async def test_publish_api_first_then_fallback(self):
        """测试发布优先使用 API，失败后降级浏览器"""
        client = XianyuApiClient()
        
        with patch.object(client.http_client, "publish", new_callable=AsyncMock) as mock_api:
            mock_api.side_effect = Exception("API failed")
            
            with patch.object(client.browser_bridge, "publish_via_browser", new_callable=AsyncMock) as mock_browser:
                mock_browser.return_value = {"success": True, "method": "browser"}
                
                result = await client.publish(item_url="http://example.com/item/123")
                
                assert result["success"] == True
                assert result["method"] == "browser"

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
