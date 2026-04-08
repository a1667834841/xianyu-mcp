"""
test_browser.py - 浏览器管理测试
测试 AsyncChromeManager 类的功能
"""

import pytest
import asyncio
from pathlib import Path
import sys

src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from browser import AsyncChromeManager


class TestBrowser:
    """浏览器管理测试"""

    @pytest.mark.asyncio
    async def test_chrome_start(self):
        """B01 - 启动 Chrome 浏览器 (9222 端口)"""
        manager = AsyncChromeManager()
        success = manager.start_chrome()
        assert success, "Chrome 启动失败"
        await manager.close()

    @pytest.mark.asyncio
    async def test_chrome_connect(self):
        """B02 - 通过 CDP 连接浏览器"""
        manager = AsyncChromeManager()
        await manager.ensure_running()

        # 验证可以连接
        assert manager.browser is not None, "浏览器连接失败"
        assert manager.page is not None, "无法获取 page 对象"

        await manager.close()

    @pytest.mark.asyncio
    async def test_navigate(self):
        """B03 - 导航到指定 URL"""
        manager = AsyncChromeManager()
        await manager.ensure_running()

        # 导航到闲鱼
        await manager.navigate("https://www.goofish.com")
        await asyncio.sleep(2)  # 等待页面加载

        # 验证页面标题
        title = await manager.page.title()
        assert "闲鱼" in title or "Goofish" in title or "闲置" in title, f"页面标题不正确：{title}"

        # 验证 URL
        current_url = manager.page.url
        assert "goofish.com" in current_url, f"URL 不正确：{current_url}"

        await manager.close()

    @pytest.mark.asyncio
    async def test_get_cookie(self):
        """B04 - 获取 Cookie"""
        manager = AsyncChromeManager()
        await manager.ensure_running()

        await manager.navigate("https://www.goofish.com")
        await asyncio.sleep(2)

        # 获取 Cookie
        cookies = await manager.context.cookies()
        assert isinstance(cookies, list), "Cookie 应该返回列表"
        assert len(cookies) > 0, "应该至少有一个 Cookie"

        # 打印 Cookie 名称便于调试
        cookie_names = [c.get("name") for c in cookies]
        print(f"Cookie 列表：{cookie_names}")

        await manager.close()

    @pytest.mark.asyncio
    async def test_verify_xianyu_page(self):
        """B06 - 验证闲鱼页面元素"""
        manager = AsyncChromeManager()
        await manager.ensure_running()

        await manager.navigate("https://www.goofish.com")
        await asyncio.sleep(2)

        # 验证搜索框存在
        try:
            # 尝试多种选择器
            search_box = manager.page.locator('input[placeholder*="搜索"], input[data-placeholder*="搜索"], input[name*="q"], .search-input')
            await search_box.wait_for(state="visible", timeout=5000)
            assert await search_box.is_visible(), "搜索框未找到"
        except Exception as e:
            # 如果找不到搜索框，尝试验证页面内容
            content = await manager.page.content()
            assert "闲鱼" in content or "Goofish" in content, "页面不包含闲鱼关键词"

        await manager.close()

    @pytest.mark.asyncio
    async def test_close(self):
        """B05 - 关闭浏览器连接"""
        manager = AsyncChromeManager()
        await manager.ensure_running()

        # 关闭
        await manager.close()

        # 验证已关闭
        assert manager.browser is None, "浏览器应该已关闭"
