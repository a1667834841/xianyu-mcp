import pytest
from unittest.mock import AsyncMock, patch
from src.browser_bridge import BrowserBridge


class TestBrowserBridge:
    @pytest.mark.asyncio
    async def test_publish_via_browser(self):
        """测试通过浏览器发布商品"""
        bridge = BrowserBridge()
        
        with patch.object(bridge, "_ensure_browser") as mock_ensure:
            mock_ensure.return_value = True
            
            result = await bridge.publish_via_browser(
                item_url="http://example.com/item/123",
                title="测试商品",
                price=100.0
            )
            
            assert "success" in result
            assert "method" in result
            assert result["method"] == "browser"

    @pytest.mark.asyncio
    async def test_refresh_via_browser(self):
        """测试通过浏览器刷新 Cookie"""
        bridge = BrowserBridge()
        
        with patch.object(bridge, "_ensure_browser") as mock_ensure:
            mock_ensure.return_value = True
            
            result = await bridge.refresh_via_browser()
            
            assert "success" in result
            assert result["success"] == True
