"""滑块验证协调器"""
import asyncio
import logging
from typing import Dict, Any, Optional

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
            page = await bridge.connect_to_browser_pool()
            if not page:
                logger.error("[Captcha] 无法连接浏览器容器")
                return False
            
            logger.info("[Captcha] 已连接浏览器容器")
            
            # 2. 执行滑块验证
            success = await self._slider_solver.solve(page, verification_url, max_retries)
            
            if success:
                # 3. 获取新 cookies
                new_cookies = await bridge.get_captcha_cookies()
                
                if new_cookies:
                    # 4. 更新 http_client cookies
                    self._update_cookies(new_cookies)
                    
                    # 5. 保存到 auth.json
                    self.http_client._save_cookies_to_file()
                    
                    logger.info(f"[Captcha] ✅ 验证成功，已更新 {len(new_cookies)} 个 cookies")
                else:
                    logger.warning("[Captcha] 验证成功但未获取到新 cookies")
                
                return True
            else:
                logger.error("[Captcha] ❌ 验证失败")
                return False
                
        except Exception as e:
            logger.error(f"[Captcha] 处理异常: {e}")
            return False
            
        finally:
            # 6. 关闭验证页面
            await bridge.close_captcha_page()
                
            # 7. 断开连接（保留浏览器容器运行）
            await bridge.disconnect()
    
    def _update_cookies(self, new_cookies: Dict[str, str]):
        """更新 cookies
        
        Args:
            new_cookies: 新获取的 cookies
        """
        # 只更新 x5 相关的 cookies
        updated_count = 0
        for name, value in new_cookies.items():
            name_lower = name.lower()
            if name_lower.startswith('x5') or 'x5sec' in name_lower or 'sec' in name_lower:
                if self.http_client.cookies.get(name) != value:
                    self.http_client.cookies[name] = value
                    self.http_client.session.cookies.set(name, value)
                    updated_count += 1
                    logger.info(f"[Captcha] 更新 cookie: {name}")
        
        logger.info(f"[Captcha] 共更新 {updated_count} 个 cookies")