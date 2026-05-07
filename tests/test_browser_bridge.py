import pytest
from unittest.mock import AsyncMock
from src.browser_bridge import BrowserBridge
from src.api.captcha_handler import CaptchaHandler


class TestBrowserBridge:
    @pytest.mark.asyncio
    async def test_connect_uses_cdp_and_reuses_existing_context_and_page(self, monkeypatch):
        bridge = BrowserBridge()

        existing_page = object()

        class FakeContext:
            def __init__(self):
                self.pages = [existing_page]

        fake_context = FakeContext()

        class FakeBrowser:
            def __init__(self):
                self.contexts = [fake_context]

        fake_browser = FakeBrowser()

        fake_playwright = type("FakePlaywright", (), {})()
        fake_playwright.chromium = type("FakeChromium", (), {})()
        fake_playwright.chromium.connect_over_cdp = AsyncMock(return_value=fake_browser)

        fake_launcher = AsyncMock(return_value=fake_playwright)

        monkeypatch.setattr(bridge, "_get_websocket_url", AsyncMock(return_value="ws://cdp-endpoint"))
        monkeypatch.setattr("playwright.async_api.async_playwright", lambda: type("FakeManager", (), {"start": fake_launcher})())

        page = await bridge.connect()

        assert page is existing_page
        assert bridge._browser is fake_browser
        assert bridge.get_context() is fake_context
        fake_playwright.chromium.connect_over_cdp.assert_awaited_once_with("ws://cdp-endpoint")

    @pytest.mark.asyncio
    async def test_connect_cleans_up_state_when_cdp_connection_fails(self, monkeypatch):
        bridge = BrowserBridge()

        fake_playwright = type("FakePlaywright", (), {"stop": AsyncMock()})()
        fake_playwright.chromium = type("FakeChromium", (), {})()
        fake_playwright.chromium.connect_over_cdp = AsyncMock(side_effect=RuntimeError("cdp failed"))

        fake_launcher = AsyncMock(return_value=fake_playwright)

        monkeypatch.setattr(bridge, "_get_websocket_url", AsyncMock(return_value="ws://cdp-endpoint"))
        monkeypatch.setattr("playwright.async_api.async_playwright", lambda: type("FakeManager", (), {"start": fake_launcher})())

        bridge._browser = object()
        bridge._context = object()
        bridge._page = object()

        page = await bridge.connect()

        assert page is None
        fake_playwright.stop.assert_awaited_once_with()
        assert bridge._playwright is None
        assert bridge._browser is None
        assert bridge._context is None
        assert bridge._page is None

    @pytest.mark.asyncio
    async def test_connect_cleans_up_state_when_websocket_url_is_missing(self, monkeypatch):
        bridge = BrowserBridge()

        fake_playwright = type("FakePlaywright", (), {"stop": AsyncMock()})()
        fake_playwright.chromium = type("FakeChromium", (), {})()
        fake_playwright.chromium.connect_over_cdp = AsyncMock()

        fake_launcher = AsyncMock(return_value=fake_playwright)

        monkeypatch.setattr(bridge, "_get_websocket_url", AsyncMock(return_value=None))
        monkeypatch.setattr("playwright.async_api.async_playwright", lambda: type("FakeManager", (), {"start": fake_launcher})())

        page = await bridge.connect()

        assert page is None
        fake_playwright.stop.assert_awaited_once_with()
        fake_playwright.chromium.connect_over_cdp.assert_not_awaited()
        assert bridge._playwright is None
        assert bridge._browser is None
        assert bridge._context is None
        assert bridge._page is None

    @pytest.mark.asyncio
    async def test_get_or_create_page_creates_page_when_context_has_none(self):
        bridge = BrowserBridge()

        created_page = object()

        class FakeContext:
            def __init__(self):
                self.pages = []

            async def new_page(self):
                self.pages.append(created_page)
                return created_page

        bridge._context = FakeContext()

        page = await bridge.get_or_create_page()

        assert page is created_page

    @pytest.mark.asyncio
    async def test_get_or_create_page_reuses_context_page_when_cached_page_is_unavailable(self):
        bridge = BrowserBridge()

        available_page = object()

        class FakeCachedPage:
            @property
            def url(self):
                raise RuntimeError("page closed")

        class FakeContext:
            def __init__(self):
                self.pages = [available_page]

            async def new_page(self):
                raise AssertionError("should not create new page")

        bridge._page = FakeCachedPage()
        bridge._context = FakeContext()

        page = await bridge.get_or_create_page()

        assert page is available_page
        assert bridge._page is available_page

    @pytest.mark.asyncio
    async def test_get_or_create_page_creates_new_page_when_cached_page_is_unavailable_and_context_has_none(self):
        bridge = BrowserBridge()

        created_page = object()

        class FakeCachedPage:
            @property
            def url(self):
                raise RuntimeError("page closed")

        class FakeContext:
            def __init__(self):
                self.pages = []

            async def new_page(self):
                self.pages.append(created_page)
                return created_page

        bridge._page = FakeCachedPage()
        bridge._context = FakeContext()

        page = await bridge.get_or_create_page()

        assert page is created_page
        assert bridge._page is created_page

    @pytest.mark.asyncio
    async def test_new_page_creates_fresh_page(self):
        bridge = BrowserBridge()

        created_page = object()

        class FakeContext:
            async def new_page(self):
                return created_page

        bridge._context = FakeContext()

        page = await bridge.new_page()

        assert page is created_page

    @pytest.mark.asyncio
    async def test_get_cookies_returns_cookie_mapping(self):
        bridge = BrowserBridge()

        class FakeContext:
            async def cookies(self):
                return [
                    {"name": "cookie2", "value": "abc"},
                    {"name": "_m_h5_tk", "value": "token_value"},
                ]

        bridge._context = FakeContext()

        cookies = await bridge.get_cookies()

        assert cookies == {"cookie2": "abc", "_m_h5_tk": "token_value"}

    @pytest.mark.asyncio
    async def test_get_captcha_cookies_falls_back_to_all_cookies_when_no_x5_present(self):
        bridge = BrowserBridge()

        class FakeContext:
            async def cookies(self):
                return [
                    {"name": "cookie2", "value": "abc"},
                    {"name": "_m_h5_tk", "value": "token_value"},
                    {"name": "unb", "value": "4188939592"},
                ]

        bridge._context = FakeContext()

        cookies = await bridge.get_captcha_cookies()

        assert cookies == {
            "cookie2": "abc",
            "_m_h5_tk": "token_value",
            "unb": "4188939592",
        }

    @pytest.mark.asyncio
    async def test_add_cookies_injects_http_client_cookies(self):
        bridge = BrowserBridge()

        class FakeContext:
            def __init__(self):
                self.received = None

            async def add_cookies(self, cookies):
                self.received = cookies

        bridge._context = FakeContext()

        await bridge.add_cookies(
            {
                "cookie2": "abc",
                "_m_h5_tk": "token_value_123",
                "unb": "4188939592",
            }
        )

        assert bridge._context.received == [
            {"name": "cookie2", "value": "abc", "domain": ".goofish.com", "path": "/"},
            {"name": "_m_h5_tk", "value": "token_value_123", "domain": ".goofish.com", "path": "/"},
            {"name": "unb", "value": "4188939592", "domain": ".goofish.com", "path": "/"},
        ]

    @pytest.mark.asyncio
    async def test_close_page_navigates_to_blank_and_clears_cached_page(self):
        bridge = BrowserBridge()

        class FakePage:
            def __init__(self):
                self.url = "https://example.com/captcha"
                self.goto = AsyncMock()

        page = FakePage()
        bridge._page = page

        await bridge.close_page()

        page.goto.assert_awaited_once_with("about:blank", timeout=5000)
        assert bridge._page is None

    @pytest.mark.asyncio
    async def test_close_page_clears_cached_page_even_when_already_blank(self):
        bridge = BrowserBridge()

        class FakePage:
            def __init__(self):
                self.url = "about:blank"
                self.goto = AsyncMock()

        page = FakePage()
        bridge._page = page

        await bridge.close_page()

        page.goto.assert_not_awaited()
        assert bridge._page is None

    def test_legacy_method_names_are_removed(self):
        bridge = BrowserBridge()

        assert not hasattr(bridge, "connect_to_browser_pool")
        assert not hasattr(bridge, "apply_cookies_to_context")
        assert not hasattr(bridge, "close_captcha_page")

    @pytest.mark.asyncio
    async def test_disconnect_stops_playwright_and_clears_cached_objects(self):
        bridge = BrowserBridge()

        fake_playwright = type("FakePlaywright", (), {"stop": AsyncMock()})()
        bridge._playwright = fake_playwright
        bridge._browser = object()
        bridge._context = object()
        bridge._page = object()

        await bridge.disconnect()

        fake_playwright.stop.assert_awaited_once_with()
        assert bridge._playwright is None
        assert bridge._browser is None
        assert bridge._context is None
        assert bridge._page is None


class TestCaptchaHandler:
    def test_update_cookies_accepts_non_x5_cookies_from_browser(self):
        class FakeSessionCookies:
            def __init__(self):
                self.values = {}

            def set(self, key, value):
                self.values[key] = value

        class FakeSession:
            def __init__(self):
                self.cookies = FakeSessionCookies()

        class FakeHttpClient:
            def __init__(self):
                self.cookies = {}
                self.session = FakeSession()

        http_client = FakeHttpClient()
        handler = CaptchaHandler(http_client)

        handler._update_cookies(
            {
                "cookie2": "abc",
                "_m_h5_tk": "token_value",
                "x5secdata": "sec_value",
            }
        )

        assert http_client.cookies == {
            "cookie2": "abc",
            "_m_h5_tk": "token_value",
            "x5secdata": "sec_value",
        }
        assert http_client.session.cookies.values == http_client.cookies

    @pytest.mark.asyncio
    async def test_handle_refreshes_and_confirms_no_slider_before_collecting_cookies(self, monkeypatch):
        class FakeSessionCookies:
            def __init__(self):
                self.values = {}

            def set(self, key, value):
                self.values[key] = value

        class FakeSession:
            def __init__(self):
                self.cookies = FakeSessionCookies()

        class FakeHttpClient:
            def __init__(self):
                self.cookies = {"cookie2": "abc"}
                self.session = FakeSession()
                self.saved = False

            def _save_cookies_to_file(self):
                self.saved = True

        class FakePage:
            def __init__(self):
                self.reload_calls = []
                self.wait_calls = []

            async def reload(self, wait_until=None, timeout=None):
                self.reload_calls.append((wait_until, timeout))

            async def wait_for_timeout(self, timeout):
                self.wait_calls.append(timeout)

        fake_page = FakePage()

        class FakeBridge:
            def __init__(self):
                self.connected = False
                self.applied = None
                self.cookies_collected = False
                self.closed = False
                self.disconnected = False

            async def connect(self):
                self.connected = True
                return fake_page

            async def add_cookies(self, cookies):
                self.applied = dict(cookies)

            async def get_captcha_cookies(self):
                self.cookies_collected = True
                return {"_m_h5_tk": "token_value_123", "cookie2": "abc"}

            async def close_page(self, page=None):
                self.closed = True
                return None

            async def disconnect(self):
                self.disconnected = True
                return None

        fake_bridge = FakeBridge()
        monkeypatch.setattr("src.api.captcha_handler.BrowserBridge", lambda: fake_bridge)

        handler = CaptchaHandler(FakeHttpClient())
        handler._slider_solver.solve = AsyncMock(return_value=True)
        handler._slider_solver._find_slider_frame = AsyncMock(return_value=fake_page)

        async def no_slider(*args, **kwargs):
            return (None, None)

        handler._slider_solver._find_slider_elements = AsyncMock(side_effect=no_slider)

        result = await handler.handle("https://example.com/captcha")

        assert result is True
        assert fake_bridge.connected is True
        assert fake_bridge.applied == {"cookie2": "abc"}
        assert fake_page.reload_calls == [("domcontentloaded", 15000)]
        assert fake_page.wait_calls == [1000]
        assert fake_bridge.cookies_collected is True
        assert fake_bridge.closed is True
        assert fake_bridge.disconnected is True
