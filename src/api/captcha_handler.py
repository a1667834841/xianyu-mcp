"""滑块验证协调器"""
import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict

from .slider_solver import SliderSolver
from src.browser_bridge import BrowserBridge

logger = logging.getLogger(__name__)


class CaptchaHandler:
    """滑块验证协调器
    
    协调浏览器连接、滑块自动化、cookie 更新流程
    """
    
    def __init__(self, http_client):
        self.http_client = http_client
        self._browser_bridge = None
        self._slider_solver = SliderSolver()

    def _manual_debug_enabled(self) -> bool:
        raw = os.environ.get("XIANYU_CAPTCHA_DEBUG_MANUAL", "")
        return raw.strip().lower() in {"1", "true", "yes", "on"}

    def _write_debug_artifact(self, verification_url: str, page_state: Dict[str, str]) -> None:
        data_dir_getter = getattr(self.http_client, "_get_data_dir", None)
        if not callable(data_dir_getter):
            return

        debug_dir = Path(data_dir_getter()) / "captcha-debug"
        debug_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "verification_url": verification_url,
            "page": page_state,
            "cookie_names": sorted(self.http_client.cookies.keys()),
        }
        (debug_dir / "latest.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _is_challenge_page(self, page_state: Dict[str, str]) -> bool:
        url = (page_state.get("url") or "").lower()
        title = (page_state.get("title") or "").lower()
        body = (page_state.get("body_text") or "").lower()
        if "punish" in url:
            return True
        if "验证码拦截" in (page_state.get("title") or ""):
            return True
        if "captcha" in url or "captcha" in title:
            return True
        if "页面访问出现了问题" in (page_state.get("body_text") or ""):
            return True
        if "点击我反馈" in (page_state.get("body_text") or ""):
            return True
        return "verify" in url or "challenge" in body

    async def _capture_page_state(self, bridge: BrowserBridge, page) -> Dict[str, str]:
        if hasattr(bridge, "capture_page_state"):
            return await bridge.capture_page_state(page)

        state = {"url": "", "title": "", "body_text": ""}
        try:
            state["url"] = getattr(page, "url", "") or ""
        except Exception:
            pass
        try:
            state["title"] = await page.title()
        except Exception:
            pass
        try:
            state["body_text"] = await page.locator("body").inner_text(timeout=5000)
        except Exception:
            pass
        return state

    async def _wait_for_browser_resolution(
        self,
        bridge: BrowserBridge,
        page,
        timeout_seconds: float = 90.0,
        poll_interval: float = 1.0,
    ) -> Dict[str, str] | None:
        attempts = max(1, int(timeout_seconds / poll_interval))
        for _ in range(attempts):
            state = await self._capture_page_state(bridge, page)
            if not self._is_challenge_page(state):
                return state
            await asyncio.sleep(poll_interval)
        return None
    
    async def handle(self, verification_url: str, max_retries: int = 3) -> bool:
        """处理滑块验证
        
        Args:
            verification_url: 验证码 URL
            max_retries: 最大重试次数
            
        Returns:
            bool: 验证是否成功
        """
        bridge = BrowserBridge()
        page = None
        
        try:
            # 1. 连接浏览器容器
            page = await bridge.connect()
            if not page:
                logger.error("[Captcha] 无法连接浏览器容器")
                return False

            await bridge.add_cookies(self.http_client.cookies)
            
            logger.info("[Captcha] 已连接浏览器容器")

            if hasattr(bridge, "new_page"):
                page = await bridge.new_page() or page

            if self._manual_debug_enabled():
                await page.goto(verification_url, wait_until="domcontentloaded", timeout=30000)
                page_state = await self._capture_page_state(bridge, page)
                self._write_debug_artifact(verification_url, page_state)
                logger.warning("[Captcha] 人工调试模式已启用，已保留验证码现场")
                return False
            
            # 2. 执行滑块验证
            success = await self._slider_solver.solve(page, verification_url, max_retries)
            
            resolved_state = None
            if success:
                # 3. 刷新并确认滑块已消失，再收集最新 cookies
                await page.reload(wait_until="domcontentloaded", timeout=15000)
                if hasattr(page, "wait_for_timeout"):
                    await page.wait_for_timeout(1000)
                else:
                    await asyncio.sleep(1.0)

                slider_frame = await self._slider_solver._find_slider_frame(page)
                slider_btn, slider_track = await self._slider_solver._find_slider_elements(slider_frame)
                if slider_btn or slider_track:
                    logger.warning("[Captcha] 刷新后仍检测到滑块，视为验证未完成")
                else:
                    state = await self._capture_page_state(bridge, page)
                    if not self._is_challenge_page(state):
                        resolved_state = state

            if resolved_state is None:
                resolved_state = await self._wait_for_browser_resolution(bridge, page)

            if resolved_state is not None:
                # 4. 获取新 cookies
                new_cookies = await bridge.get_captcha_cookies()
                
                if new_cookies:
                    # 5. 更新 http_client cookies
                    self._update_cookies(new_cookies)
                    
                    # 6. 保存到 auth.json
                    self.http_client._save_cookies_to_file()
                    
                    logger.info(f"[Captcha] ✅ 验证成功，已更新 {len(new_cookies)} 个 cookies")
                    return True
                else:
                    logger.warning("[Captcha] 验证成功但未获取到新 cookies")

            page_state = await self._capture_page_state(bridge, page)
            self._write_debug_artifact(verification_url, page_state)
            logger.error("[Captcha] ❌ 验证失败")
            return False
                
        except Exception as e:
            logger.error(f"[Captcha] 处理异常: {e}")
            return False
            
        finally:
            # 6. 关闭验证页面
            if not self._manual_debug_enabled():
                await bridge.close_page(page)
                
            # 7. 断开连接（保留浏览器容器运行）
            await bridge.disconnect()
    
    def _update_cookies(self, new_cookies: Dict[str, str]):
        """更新 cookies
        
        Args:
            new_cookies: 新获取的 cookies
        """
        updated_count = 0
        for name, value in new_cookies.items():
            if self.http_client.cookies.get(name) != value:
                self.http_client.cookies[name] = value
                self.http_client.session.cookies.set(name, value)
                updated_count += 1
                logger.info(f"[Captcha] 更新 cookie: {name}")
        
        logger.info(f"[Captcha] 共更新 {updated_count} 个 cookies")
