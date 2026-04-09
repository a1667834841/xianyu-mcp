"""
test_browser.py - 浏览器管理测试
测试 AsyncChromeManager 类的功能
"""

import pytest
import asyncio
import json
from pathlib import Path
import sys

project_root = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(project_root))

from src.browser import AsyncChromeManager


ROLE_PAGE_CASES = [
    ("search", "get_search_page", "_search_page"),
    ("session", "get_session_page", "_session_page"),
    ("publish", "get_publish_page", "_publish_page"),
]


class FakePage:
    """轻量级 fake page，用于角色页测试。"""


class FakeContext:
    def __init__(self):
        self.pages = []
        self.new_page_calls = 0

    async def new_page(self):
        self.new_page_calls += 1
        page = FakePage()
        self.pages.append(page)
        return page


class SlowFakeContext(FakeContext):
    async def new_page(self):
        self.new_page_calls += 1
        await asyncio.sleep(0)
        page = FakePage()
        self.pages.append(page)
        return page


class FakeBrowser:
    def __init__(self):
        self.closed = False

    async def close(self):
        self.closed = True


class FailingBrowser:
    def __init__(self):
        self.closed = False

    async def close(self):
        self.closed = True
        raise RuntimeError("close failed")


class FakePlaywright:
    def __init__(self):
        self.stopped = False

    async def stop(self):
        self.stopped = True


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
        assert "闲鱼" in title or "Goofish" in title or "闲置" in title, (
            f"页面标题不正确：{title}"
        )

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
            search_box = manager.page.locator(
                'input[placeholder*="搜索"], input[data-placeholder*="搜索"], input[name*="q"], .search-input'
            )
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

    @pytest.mark.asyncio
    async def test_role_pages_are_distinct_and_reused(self, tmp_path):
        """B07 - 角色页彼此不同且同角色复用"""
        manager = AsyncChromeManager(user_data_dir=tmp_path, auto_start=False)
        manager.context = FakeContext()

        search_page = await manager.get_search_page()
        session_page = await manager.get_session_page()
        publish_page = await manager.get_publish_page()

        assert search_page is await manager.get_search_page()
        assert session_page is await manager.get_session_page()
        assert publish_page is await manager.get_publish_page()

        assert search_page is not session_page
        assert search_page is not publish_page
        assert session_page is not publish_page

    @pytest.mark.asyncio
    async def test_close_clears_role_page_references(self, tmp_path):
        """B08 - close 时清空角色页引用"""
        manager = AsyncChromeManager(user_data_dir=tmp_path, auto_start=False)
        manager.context = FakeContext()
        manager.browser = FakeBrowser()
        manager.playwright = FakePlaywright()

        await manager.get_search_page()
        await manager.get_session_page()
        await manager.get_publish_page()

        await manager.close()

        assert manager._search_page is None
        assert manager._session_page is None
        assert manager._publish_page is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("role_name", "getter_name", "cache_attr"),
        ROLE_PAGE_CASES,
    )
    async def test_concurrent_role_page_requests_reuse_same_page(
        self, tmp_path, role_name, getter_name, cache_attr
    ):
        f"""B09 - 并发请求同一角色页时只创建一次 {role_name} page"""
        manager = AsyncChromeManager(user_data_dir=tmp_path, auto_start=False)
        manager.context = SlowFakeContext()
        getter = getattr(manager, getter_name)

        first, second = await asyncio.gather(
            getter(),
            getter(),
        )

        assert first is second
        assert manager.context.new_page_calls == 1
        assert getattr(manager, cache_attr) is first

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("role_name", "getter_name", "cache_attr"),
        ROLE_PAGE_CASES,
    )
    async def test_role_page_rebuilds_when_reference_leaves_context(
        self, tmp_path, role_name, getter_name, cache_attr
    ):
        f"""B10 - 角色页引用失效后应重建 {role_name} page"""
        manager = AsyncChromeManager(user_data_dir=tmp_path, auto_start=False)
        manager.context = FakeContext()
        getter = getattr(manager, getter_name)

        first_page = await getter()
        manager.context.pages.remove(first_page)

        second_page = await getter()

        assert second_page is not first_page
        assert manager.context.new_page_calls == 2
        assert getattr(manager, cache_attr) is second_page

    @pytest.mark.asyncio
    async def test_close_cleans_local_state_when_browser_close_fails(self, tmp_path):
        """B11 - close 异常路径仍清理本地状态并继续 stop playwright"""
        manager = AsyncChromeManager(user_data_dir=tmp_path, auto_start=False)
        manager.context = FakeContext()
        manager.browser = FailingBrowser()
        playwright = FakePlaywright()
        manager.playwright = playwright
        manager.page = FakePage()
        manager._work_page = FakePage()

        await manager.get_search_page()
        await manager.get_session_page()
        await manager.get_publish_page()

        with pytest.raises(RuntimeError, match="close failed"):
            await manager.close()

        assert manager.context is None
        assert manager.page is None
        assert manager._work_page is None
        assert manager._search_page is None
        assert manager._session_page is None
        assert manager._publish_page is None
        assert manager.playwright is None
        assert playwright.stopped is True

    @pytest.mark.asyncio
    async def test_get_websocket_url_adds_missing_port_for_localhost(
        self, tmp_path, monkeypatch
    ):
        """B12 - localhost 返回无端口 ws URL 时补齐调试端口"""
        manager = AsyncChromeManager(user_data_dir=tmp_path, auto_start=False)

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return json.dumps(
                    {"webSocketDebuggerUrl": "ws://localhost/devtools/browser/test-id"}
                ).encode()

        def fake_urlopen(req, timeout):
            assert req.full_url == "http://localhost:9222/json/version"
            assert req.get_header("Host") == "localhost"
            assert timeout == 5
            return FakeResponse()

        monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

        ws_url = await manager._get_websocket_url()

        assert ws_url == "ws://localhost:9222/devtools/browser/test-id"
