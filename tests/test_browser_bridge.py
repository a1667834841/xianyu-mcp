import pytest
from unittest.mock import AsyncMock, patch
from src.browser_bridge import BrowserBridge
from src.api.captcha_handler import CaptchaHandler


class TestBrowserBridge:
    @pytest.mark.asyncio
    async def test_publish_via_browser(self):
        """测试通过浏览器发布商品"""
        bridge = BrowserBridge()
        
        with patch.object(bridge, "_ensure_browser") as mock_ensure:
            mock_ensure.return_value = True
            
            result = await bridge.publish_via_browser(
                item_url="http://example.com/item/123",
                title="测试商品",
                price=100.0
            )
            
            assert "success" in result
            assert "method" in result
            assert result["method"] == "browser"

    @pytest.mark.asyncio
    async def test_refresh_via_browser(self):
        """测试通过浏览器刷新 Cookie"""
        bridge = BrowserBridge()
        
        with patch.object(bridge, "_ensure_browser") as mock_ensure:
            mock_ensure.return_value = True
            
            result = await bridge.refresh_via_browser()
            
            assert "success" in result
            assert result["success"] == True

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
    async def test_apply_cookies_to_context_injects_http_client_cookies(self):
        bridge = BrowserBridge()

        class FakeContext:
            def __init__(self):
                self.received = None

            async def add_cookies(self, cookies):
                self.received = cookies

        bridge._context = FakeContext()

        await bridge.apply_cookies_to_context(
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
    async def test_get_access_token_via_browser_returns_token_from_page(self):
        bridge = BrowserBridge()

        async def fake_connect():
            return bridge._page

        class FakePage:
            async def goto(self, url, wait_until=None, timeout=None):
                return None

            async def evaluate(self, script, payload):
                return {"data": {"accessToken": "oauth_k1:browser_token_value"}}

        bridge._page = FakePage()
        bridge.connect_to_browser_pool = fake_connect

        async def fake_close_page():
            return None

        async def fake_disconnect():
            return None

        bridge.close_captcha_page = fake_close_page
        bridge.disconnect = fake_disconnect

        async def fake_get_captcha_cookies():
            return {"_m_h5_tk": "token_value_123"}

        bridge.get_captcha_cookies = fake_get_captcha_cookies

        token = await bridge.get_access_token_via_browser("web_4188939592")

        assert token == "oauth_k1:browser_token_value"


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
                self.applied = None
                self.cookies_collected = False

            async def connect_to_browser_pool(self):
                return fake_page

            async def apply_cookies_to_context(self, cookies):
                self.applied = dict(cookies)

            async def get_captcha_cookies(self):
                self.cookies_collected = True
                return {"_m_h5_tk": "token_value_123", "cookie2": "abc"}

            async def close_captcha_page(self):
                return None

            async def disconnect(self):
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
        assert fake_bridge.applied == {"cookie2": "abc"}
        assert fake_page.reload_calls == [("domcontentloaded", 15000)]
        assert fake_page.wait_calls == [1000]
        assert fake_bridge.cookies_collected is True
