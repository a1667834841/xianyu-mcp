import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class BrowserBridge:
    """浏览器降级桥接，用于 API 失败时的备用方案"""
    
    async def publish_via_browser(self, item_url: str, **kwargs) -> Dict[str, Any]:
        """通过浏览器发布商品"""
        logger.info(f"通过浏览器发布商品: {item_url}")
        return {"success": False, "method": "browser"}
    
    async def refresh_via_browser(self) -> Dict[str, Any]:
        """通过浏览器刷新 Token"""
        logger.info("通过浏览器刷新 Token")
        return {"success": False, "method": "browser"}
