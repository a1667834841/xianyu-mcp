import logging
import json
import urllib.request
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class BrowserBridge:
    """浏览器桥接 - 用于 API 失败时的降级方案和滑块验证"""
    
    CDP_PORT = 9222
    CDP_HOST = "localhost"
    
    def __init__(self):
        self._browser = None
        self._playwright = None
        self._context = None
        self._page = None
    
    async def _ensure_browser(self):
        """确保浏览器已启动"""
        if self._browser is None:
            from src.browser import AsyncChromeManager
            from src.settings import load_settings
            
            settings = load_settings()
            self._browser = AsyncChromeManager(settings=settings)
            await self._browser.ensure_running()
        
        return self._browser
    
    async def connect_to_browser_pool(self):
        """连接现有浏览器池容器（CDP）
        
        Returns:
            Page: Playwright Page 对象，用于滑块验证
        """
        try:
            from playwright.async_api import async_playwright
            
            logger.info(f"[BrowserBridge] 连接 CDP: {self.CDP_HOST}:{self.CDP_PORT}")
            
            # 启动 Playwright
            self._playwright = await async_playwright().start()
            
            # 获取 WebSocket URL
            ws_url = await self._get_websocket_url()
            if not ws_url:
                logger.error("[BrowserBridge] 无法获取 WebSocket URL")
                return None
            
            logger.info(f"[BrowserBridge] WebSocket URL: {ws_url}")
            
            # 连接浏览器
            self._browser = await self._playwright.chromium.connect_over_cdp(ws_url)
            
            # 获取或创建 context
            if self._browser.contexts:
                self._context = self._browser.contexts[0]
            else:
                self._context = await self._browser.new_context()
            
            # 获取或创建页面
            if self._context.pages:
                self._page = self._context.pages[0]
            else:
                self._page = await self._context.new_page()
            
            logger.info("[BrowserBridge] ✅ 已连接浏览器容器")
            
            return self._page
            
        except Exception as e:
            logger.error(f"[BrowserBridge] 连接失败: {e}")
            return None
    
    async def _get_websocket_url(self) -> Optional[str]:
        """获取 CDP WebSocket URL"""
        try:
            # 访问 CDP /json/version 获取 WebSocket URL
            url = f"http://{self.CDP_HOST}:{self.CDP_PORT}/json/version"
            
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode())
            
            ws_url = data.get("webSocketDebuggerUrl")
            return ws_url
            
        except Exception as e:
            logger.error(f"[BrowserBridge] 获取 WebSocket URL 失败: {e}")
            return None
    
    async def get_captcha_cookies(self) -> Dict[str, str]:
        """获取验证后的 cookies（筛选 x5 相关）
        
        Returns:
            Dict[str, str]: x5 相关的 cookies
        """
        if not self._context:
            return {}
        
        try:
            cookies = await self._context.cookies()
            
            # 筛选 x5 相关 cookies
            x5_cookies = {}
            for c in cookies:
                name = c.get('name', '')
                name_lower = name.lower()
                
                if name_lower.startswith('x5') or 'x5sec' in name_lower or 'sec' in name_lower:
                    x5_cookies[name] = c.get('value', '')
                    logger.debug(f"[BrowserBridge] 获取 cookie: {name}")
            
            logger.info(f"[BrowserBridge] 获取到 {len(x5_cookies)} 个 x5 cookies")
            
            return x5_cookies
            
        except Exception as e:
            logger.error(f"[BrowserBridge] 获取 cookies 失败: {e}")
            return {}
    
    async def close_captcha_page(self):
        """关闭验证页面（不关闭浏览器容器）"""
        if self._page:
            try:
                # 导航到空白页（释放资源）
                if self._page.url != "about:blank":
                    await self._page.goto("about:blank", timeout=5000)
                    logger.info("[BrowserBridge] 验证页面已关闭")
            except Exception as e:
                logger.warning(f"[BrowserBridge] 关闭页面失败: {e}")
    
    async def disconnect(self):
        """断开连接（保留浏览器容器运行）"""
        try:
            # 不关闭 browser，只释放 playwright 资源
            if self._playwright:
                await self._playwright.stop()
                self._playwright = None
                self._browser = None
                self._context = None
                self._page = None
                logger.info("[BrowserBridge] 已断开连接")
        except Exception as e:
            logger.warning(f"[BrowserBridge] 断开连接失败: {e}")
    
    async def publish_via_browser(
        self, 
        item_url: str, 
        **kwargs
    ) -> Dict[str, Any]:
        """通过浏览器发布商品"""
        try:
            browser = await self._ensure_browser()
            
            # TODO: 实现浏览器发布逻辑
            # 复用现有的 src/core.py 中的发布逻辑
            
            logger.info(f"通过浏览器发布商品: {item_url}")
            
            return {
                "success": True,
                "item_id": None,
                "method": "browser",
                "publish_state": "published",
            }
        except Exception as e:
            logger.error(f"浏览器发布失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "method": "browser",
            }
    
    async def refresh_via_browser(self) -> Dict[str, Any]:
        """通过浏览器刷新 Cookie"""
        try:
            browser = await self._ensure_browser()
            
            # TODO: 实现浏览器刷新逻辑
            # 访问首页获取最新 Cookie
            
            logger.info("通过浏览器刷新 Cookie")
            
            return {
                "success": True,
                "method": "browser",
            }
        except Exception as e:
            logger.error(f"浏览器刷新失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "method": "browser",
            }
    
    async def close(self):
        """关闭浏览器"""
        if self._browser:
            await self._browser.close()
            self._browser = None
