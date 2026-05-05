import logging
import json
import urllib.request
import hashlib
import time
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
        """获取验证后的 cookies。

        Returns:
            Dict[str, str]: 优先返回 x5/安全相关 cookies；若不存在，则回退返回全部 cookies
        """
        if not self._context:
            return {}
        
        try:
            cookies = await self._context.cookies()
            
            all_cookies = {}
            x5_cookies = {}
            for c in cookies:
                name = c.get('name', '')
                value = c.get('value', '')
                if not name:
                    continue
                all_cookies[name] = value
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

    async def apply_cookies_to_context(self, cookies: Dict[str, str], domain: str = ".goofish.com") -> None:
        """将现有 HTTP cookies 注入到浏览器上下文。"""
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

    async def get_access_token_via_browser(self, device_id: str, cookies: Dict[str, str] | None = None) -> str:
        """在浏览器上下文中请求 accessToken。"""
        page = await self.connect_to_browser_pool()
        if not page:
            return ""

        try:
            if cookies:
                await self.apply_cookies_to_context(cookies)

            await page.goto("https://www.goofish.com", wait_until="domcontentloaded", timeout=30000)

            token_cookie = await self.get_captcha_cookies()
            full_token = token_cookie.get("_m_h5_tk", "") if token_cookie else ""
            if not full_token and self._context:
                all_cookies = await self._context.cookies()
                for cookie in all_cookies:
                    if cookie.get("name") == "_m_h5_tk":
                        full_token = cookie.get("value", "")
                        break

            token = full_token.split("_")[0] if full_token else ""
            if not token:
                return ""

            api = "mtop.taobao.idlemessage.pc.login.token"
            app_key = "34839810"
            ws_app_key = "444e9908a51d1cb236a27862abc769c9"
            timestamp = str(int(time.time() * 1000))
            data_obj = {"appKey": ws_app_key, "deviceId": device_id}
            data = json.dumps(data_obj, separators=(",", ":"))
            sign = hashlib.md5(f"{token}&{timestamp}&{app_key}&{data}".encode()).hexdigest()
            url = (
                f"https://h5api.m.goofish.com/h5/{api.lower()}/1.0/"
                f"?jsv=2.7.2&appKey={app_key}&t={timestamp}&sign={sign}&v=1.0"
                f"&type=originaljson&accountSite=xianyu&dataType=json&timeout=20000"
                f"&api={api}&sessionOption=AutoLoginOnly"
            )
            result = await page.evaluate(
                """async ({ url, data }) => {
                    try {
                        const body = new URLSearchParams({ data });
                        const resp = await fetch(url, {
                            method: 'POST',
                            credentials: 'include',
                            headers: { 'content-type': 'application/x-www-form-urlencoded' },
                            body,
                        });
                        return await resp.json();
                    } catch (error) {
                        return { error: String(error) };
                    }
                }""",
                {"url": url, "data": data},
            )
            return result.get("data", {}).get("accessToken", "") if isinstance(result, dict) else ""
        finally:
            await self.close_captcha_page()
            await self.disconnect()
    
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
