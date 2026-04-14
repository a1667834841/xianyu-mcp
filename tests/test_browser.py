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


class OpenPortFakeSocket:
    def settimeout(self, timeout):
        self.timeout = timeout

    def connect_ex(self, address):
        return 0

    def close(self):
        return None


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

    def test_start_chrome_fails_when_port_is_occupied_without_debug_endpoint(
        self, tmp_path, monkeypatch
    ):
        """B13 - 端口被占用但 CDP 端点不可用时不应误报启动成功"""
        manager = AsyncChromeManager(user_data_dir=tmp_path, auto_start=False)
        manager.chrome_path = "/fake/chrome"

        class FakeProcess:
            def poll(self):
                return None

        current_time = {"value": 0.0}

        def fake_time():
            return current_time["value"]

        def fake_sleep(seconds):
            current_time["value"] += seconds

        monkeypatch.setattr("os.path.exists", lambda path: True)
        monkeypatch.setattr("subprocess.Popen", lambda *args, **kwargs: FakeProcess())
        monkeypatch.setattr(
            "socket.socket", lambda *args, **kwargs: OpenPortFakeSocket()
        )
        monkeypatch.setattr("time.time", fake_time)
        monkeypatch.setattr("time.sleep", fake_sleep)

        assert manager.start_chrome(timeout=1) is False

    def test_start_chrome_adds_no_sandbox_when_running_as_root(
        self, tmp_path, monkeypatch
    ):
        """B14 - root 用户启动本地 Chrome 时追加 --no-sandbox"""
        manager = AsyncChromeManager(user_data_dir=tmp_path, auto_start=False)
        manager.chrome_path = "/fake/chrome"
        captured = {}

        class FakeProcess:
            def poll(self):
                return None

        monkeypatch.setattr("os.path.exists", lambda path: True)
        monkeypatch.setattr("os.geteuid", lambda: 0)

        def fake_popen(cmd, **kwargs):
            captured["cmd"] = cmd
            return FakeProcess()

        monkeypatch.setattr("subprocess.Popen", fake_popen)
        monkeypatch.setattr(
            "socket.socket", lambda *args, **kwargs: OpenPortFakeSocket()
        )
        monkeypatch.setattr(
            AsyncChromeManager,
            "_debug_endpoint_ready",
            lambda self, host: True,
        )

        assert manager.start_chrome(timeout=1) is True
        assert "--no-sandbox" in captured["cmd"]


class OverviewFakePage:
    def __init__(self, title_text: str, url: str, *, fail_title: bool = False):
        self._title_text = title_text
        self.url = url
        self._fail_title = fail_title

    async def title(self):
        if self._fail_title:
            raise RuntimeError("title failed")
        return self._title_text


class OverviewFakeContext:
    def __init__(self, pages):
        self.pages = pages


class OverviewFakeBrowserRoot:
    def __init__(self, contexts):
        self.contexts = contexts


@pytest.mark.asyncio
async def test_get_browser_overview_returns_all_contexts_and_pages(tmp_path):
    manager = AsyncChromeManager(user_data_dir=tmp_path, auto_start=False)

    async def fake_ensure_running():
        return True

    manager.ensure_running = fake_ensure_running
    manager.browser = OverviewFakeBrowserRoot(
        [
            OverviewFakeContext(
                [
                    OverviewFakePage("闲鱼", "https://www.goofish.com/"),
                    OverviewFakePage("发布", "https://www.goofish.com/publish"),
                ]
            ),
            OverviewFakeContext(
                [
                    OverviewFakePage("消息", "https://www.goofish.com/im"),
                ]
            ),
        ]
    )

    overview = await manager.get_browser_overview()

    assert overview == {
        "browser_context_count": 2,
        "contexts": [
            {
                "page_count": 2,
                "pages": [
                    {"title": "闲鱼", "url": "https://www.goofish.com/"},
                    {"title": "发布", "url": "https://www.goofish.com/publish"},
                ],
            },
            {
                "page_count": 1,
                "pages": [
                    {"title": "消息", "url": "https://www.goofish.com/im"},
                ],
            },
        ],
    }


@pytest.mark.asyncio
async def test_get_browser_overview_falls_back_when_page_title_fails(tmp_path):
    manager = AsyncChromeManager(user_data_dir=tmp_path, auto_start=False)

    async def fake_ensure_running():
        return True

    manager.ensure_running = fake_ensure_running
    manager.browser = OverviewFakeBrowserRoot(
        [
            OverviewFakeContext(
                [
                    OverviewFakePage(
                        "ignored",
                        "https://www.goofish.com/failing-title",
                        fail_title=True,
                    )
                ]
            )
        ]
    )

    overview = await manager.get_browser_overview()

    assert overview["contexts"][0]["pages"] == [
        {"title": "", "url": "https://www.goofish.com/failing-title"}
    ]


@pytest.mark.asyncio
async def test_get_browser_overview_raises_when_browser_not_ready(tmp_path):
    manager = AsyncChromeManager(user_data_dir=tmp_path, auto_start=False)

    async def fake_ensure_running():
        return False

    manager.ensure_running = fake_ensure_running

    with pytest.raises(RuntimeError, match="浏览器未连接，无法获取概览"):
        await manager.get_browser_overview()


class DebugFakePage:
    def __init__(self, title_text, url, screenshot_bytes=b"img"):
        self._title_text = title_text
        self.url = url
        self._screenshot_bytes = screenshot_bytes
        self.screenshot_calls = []

    async def title(self):
        return self._title_text

    async def screenshot(self, *, type, full_page):
        self.screenshot_calls.append({"type": type, "full_page": full_page})
        return self._screenshot_bytes


@pytest.mark.asyncio
async def test_pick_debug_page_prefers_session_then_publish_then_work(tmp_path):
    manager = AsyncChromeManager(user_data_dir=tmp_path, auto_start=False)
    session_page = DebugFakePage("登录", "https://www.goofish.com/session")
    publish_page = DebugFakePage("发布", "https://www.goofish.com/publish")
    work_page = DebugFakePage("首页", "https://www.goofish.com/")
    manager.context = type(
        "Context", (), {"pages": [work_page, publish_page, session_page]}
    )()
    manager._session_page = session_page
    manager._publish_page = publish_page
    manager._work_page = work_page

    kind, page = await manager.pick_debug_page()

    assert kind == "session"
    assert page is session_page


@pytest.mark.asyncio
async def test_capture_debug_screenshot_returns_binary_payload(tmp_path):
    manager = AsyncChromeManager(user_data_dir=tmp_path, auto_start=False)
    page = DebugFakePage(
        "发布", "https://www.goofish.com/publish", screenshot_bytes=b"png"
    )

    image_bytes = await manager.capture_page_screenshot(page, full_page=True)

    assert image_bytes == b"png"
    assert page.screenshot_calls == [{"type": "png", "full_page": True}]
