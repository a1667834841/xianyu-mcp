import logging
import json
import urllib.request
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class BrowserBridge:
    """最小通用 CDP 客户端。"""

    CDP_PORT = 9222
    CDP_HOST = "localhost"

    def __init__(self):
        self._browser = None
        self._playwright = None
        self._context = None
        self._page = None

    def _reset_state(self):
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None

    async def _cleanup_failed_connect(self):
        playwright = self._playwright
        self._reset_state()

        if playwright is None:
            return

        try:
            await playwright.stop()
        except Exception as e:
            logger.warning(f"[BrowserBridge] 清理失败连接资源时出错: {e}")

    async def connect(self):
        """通过 CDP 连接到远端浏览器，并返回可用页面。"""
        if self._playwright and self._browser and self._context:
            return await self.get_or_create_page()

        if self._playwright or self._browser or self._context or self._page:
            await self._cleanup_failed_connect()

        try:
            from playwright.async_api import async_playwright

            logger.info(f"[BrowserBridge] 连接 CDP: {self.CDP_HOST}:{self.CDP_PORT}")

            self._playwright = await async_playwright().start()
            ws_url = await self._get_websocket_url()
            if not ws_url:
                logger.error("[BrowserBridge] 无法获取 WebSocket URL")
                await self._cleanup_failed_connect()
                return None

            logger.info(f"[BrowserBridge] WebSocket URL: {ws_url}")
            self._browser = await self._playwright.chromium.connect_over_cdp(ws_url)

            if self._browser.contexts:
                self._context = self._browser.contexts[0]
            else:
                self._context = await self._browser.new_context()

            self._page = await self.get_or_create_page()

            logger.info("[BrowserBridge] ✅ 已连接浏览器容器")
            return self._page

        except Exception as e:
            logger.error(f"[BrowserBridge] 连接失败: {e}")
            await self._cleanup_failed_connect()
            return None

    def get_context(self):
        """返回当前浏览器上下文。"""
        return self._context

    async def get_or_create_page(self):
        """返回现有页面，必要时创建一个。"""
        if not self._context:
            return None

        if self._page is not None:
            try:
                _ = self._page.url
                return self._page
            except Exception:
                self._page = None

        if self._context.pages:
            self._page = self._context.pages[0]
        else:
            self._page = await self._context.new_page()

        return self._page

    async def new_page(self):
        """创建并缓存一个新页面。"""
        if not self._context:
            return None

        self._page = await self._context.new_page()
        return self._page

    async def _get_websocket_url(self) -> Optional[str]:
        """获取 CDP WebSocket URL"""
        try:
            url = f"http://{self.CDP_HOST}:{self.CDP_PORT}/json/version"

            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode())

            ws_url = data.get("webSocketDebuggerUrl")
            return ws_url

        except Exception as e:
            logger.error(f"[BrowserBridge] 获取 WebSocket URL 失败: {e}")
            return None

    async def get_cookies(self) -> Dict[str, str]:
        """返回当前 context 中的全部 cookies。"""
        if not self._context:
            return {}

        try:
            cookies = await self._context.cookies()
            return {
                cookie["name"]: cookie["value"]
                for cookie in cookies
                if cookie.get("name")
            }
        except Exception as e:
            logger.error(f"[BrowserBridge] 获取 cookies 失败: {e}")
            return {}

    async def get_captcha_cookies(self) -> Dict[str, str]:
        """获取验证后的 cookies。

        Returns:
            Dict[str, str]: 优先返回 x5/安全相关 cookies；若不存在，则回退返回全部 cookies
        """
        try:
            all_cookies = await self.get_cookies()
            x5_cookies = {}
            for name, value in all_cookies.items():
                name_lower = name.lower()
                if name_lower.startswith('x5') or 'x5sec' in name_lower or 'sec' in name_lower:
                    x5_cookies[name] = value
                    logger.debug(f"[BrowserBridge] 获取 cookie: {name}")

            if x5_cookies:
                logger.info(f"[BrowserBridge] 获取到 {len(x5_cookies)} 个 x5 cookies")
                return x5_cookies

            logger.info(f"[BrowserBridge] 未发现 x5 cookies，回退返回 {len(all_cookies)} 个浏览器 cookies")
            return all_cookies
        except Exception as e:
            logger.error(f"[BrowserBridge] 获取 cookies 失败: {e}")
            return {}

    async def add_cookies(self, cookies: Dict[str, str], domain: str = ".goofish.com") -> None:
        """将 HTTP cookies 注入到浏览器上下文。"""
        if not self._context or not cookies:
            return

        payload = []
        for name, value in cookies.items():
            if not name:
                continue
            payload.append({"name": name, "value": value, "domain": domain, "path": "/"})

        if not payload:
            return

        await self._context.add_cookies(payload)
        logger.info(f"[BrowserBridge] 已向浏览器上下文注入 {len(payload)} 个 cookies")

    async def close_page(self, page=None):
        """释放页面资源，但不关闭远端共享浏览器。
        
        Args:
            page: 要释放的页面。默认使用当前缓存页。
        """
        target = page or self._page
        self._page = None

        if not target:
            return

        try:
            if target.url != "about:blank":
                await target.goto("about:blank", timeout=5000)
        except Exception as e:
            logger.warning(f"[BrowserBridge] 关闭页面失败: {e}")

    async def disconnect(self):
        """断开连接（保留浏览器容器运行）"""
        playwright = self._playwright
        self._reset_state()

        try:
            if playwright:
                await playwright.stop()
            logger.info("[BrowserBridge] 已断开连接")
        except Exception as e:
            logger.warning(f"[BrowserBridge] 断开连接失败: {e}")
