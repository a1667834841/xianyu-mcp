"""
Unit tests for MCP server lifecycle wiring (HTTP + stdio).
"""

from __future__ import annotations

import json
import sys
import types

import pytest

from src.core import SearchItem, SearchOutcome


def _install_fake_mcp(monkeypatch):
    """
    The real `mcp` dependency isn't available in this execution environment.
    These unit tests only need to import our server entrypoints and observe
    lifecycle wiring, so we install a minimal stub module tree.
    """

    mcp_mod = types.ModuleType("mcp")
    mcp_server_mod = types.ModuleType("mcp.server")
    mcp_server_stdio_mod = types.ModuleType("mcp.server.stdio")
    mcp_server_fastmcp_mod = types.ModuleType("mcp.server.fastmcp")
    mcp_server_lowlevel_mod = types.ModuleType("mcp.server.lowlevel")
    mcp_server_models_mod = types.ModuleType("mcp.server.models")
    mcp_types_mod = types.ModuleType("mcp.types")

    class FastMCP:
        def __init__(self, *args, **kwargs):
            return None

        def tool(self):
            def deco(fn):
                return fn

            return deco

    class Server:
        def __init__(self, name: str):
            self._name = name

        def list_tools(self):
            def deco(fn):
                return fn

            return deco

        def call_tool(self):
            def deco(fn):
                return fn

            return deco

        def get_capabilities(self, **_kwargs):
            return {}

        async def run(self, *_args, **_kwargs):
            return None

    class NotificationOptions:
        def __init__(self, *args, **kwargs):
            return None

    class InitializationOptions:
        def __init__(self, *args, **kwargs):
            return None

    class Tool:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    class TextContent:
        def __init__(self, type: str, text: str):
            self.type = type
            self.text = text

    class CallToolResult:
        def __init__(self, content, isError: bool = False):
            self.content = content
            self.isError = isError

    async def _default_stdio_server():
        raise RuntimeError("stdio_server stub should be monkeypatched in tests")

    mcp_server_stdio_mod.stdio_server = _default_stdio_server
    mcp_server_fastmcp_mod.FastMCP = FastMCP
    mcp_server_mod.Server = Server
    mcp_server_lowlevel_mod.NotificationOptions = NotificationOptions
    mcp_server_models_mod.InitializationOptions = InitializationOptions
    mcp_types_mod.Tool = Tool
    mcp_types_mod.TextContent = TextContent
    mcp_types_mod.CallToolResult = CallToolResult

    # Wire module hierarchy (attributes + sys.modules)
    mcp_mod.server = mcp_server_mod
    mcp_server_mod.stdio = mcp_server_stdio_mod
    mcp_server_mod.fastmcp = mcp_server_fastmcp_mod
    mcp_server_mod.lowlevel = mcp_server_lowlevel_mod
    mcp_server_mod.models = mcp_server_models_mod
    mcp_mod.types = mcp_types_mod

    for name, module in (
        ("mcp", mcp_mod),
        ("mcp.server", mcp_server_mod),
        ("mcp.server.stdio", mcp_server_stdio_mod),
        ("mcp.server.fastmcp", mcp_server_fastmcp_mod),
        ("mcp.server.lowlevel", mcp_server_lowlevel_mod),
        ("mcp.server.models", mcp_server_models_mod),
        ("mcp.types", mcp_types_mod),
    ):
        monkeypatch.setitem(sys.modules, name, module)


@pytest.mark.asyncio
async def test_http_server_get_app_starts_background_tasks_once(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.http_server as http_server

    http_server._app = None
    start_calls = 0

    class FakeBrowser:
        def __init__(self, host: str, port: int, auto_start: bool):
            self.host = host
            self.port = port
            self.auto_start = auto_start

    class FakeApp:
        def __init__(self, browser):
            self.browser = browser

        def start_background_tasks(self):
            nonlocal start_calls
            start_calls += 1

    monkeypatch.setattr(http_server, "AsyncChromeManager", FakeBrowser)
    monkeypatch.setattr(http_server, "XianyuApp", FakeApp)

    app1 = http_server.get_app()
    app2 = http_server.get_app()

    assert app1 is app2
    assert start_calls == 1


@pytest.mark.asyncio
async def test_stdio_server_get_app_starts_background_tasks_once(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.server as stdio_server
    import src.browser as browser_mod

    stdio_server._app = None
    start_calls = 0

    class FakeBrowser:
        def __init__(self, host: str, port: int, auto_start: bool):
            self.host = host
            self.port = port
            self.auto_start = auto_start

    class FakeApp:
        def __init__(self, browser):
            self.browser = browser

        def start_background_tasks(self):
            nonlocal start_calls
            start_calls += 1

        async def stop_background_tasks(self):
            return None

    monkeypatch.setattr(browser_mod, "AsyncChromeManager", FakeBrowser)
    monkeypatch.setattr(stdio_server, "XianyuApp", FakeApp)

    app1 = stdio_server.get_app()
    app2 = stdio_server.get_app()

    assert app1 is app2
    assert start_calls == 1


@pytest.mark.asyncio
async def test_stdio_run_server_stops_background_tasks_on_shutdown(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.server as stdio_server

    stop_calls = 0

    class FakeApp:
        def start_background_tasks(self):
            return None

        async def stop_background_tasks(self):
            nonlocal stop_calls
            stop_calls += 1

    fake_app = FakeApp()

    class DummyStdio:
        async def __aenter__(self):
            return (object(), object())

        async def __aexit__(self, exc_type, exc, tb):
            return False

    async def run_stub(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(stdio_server, "get_app", lambda: fake_app)
    monkeypatch.setattr(
        stdio_server.mcp.server.stdio, "stdio_server", lambda: DummyStdio()
    )
    monkeypatch.setattr(stdio_server.server, "run", run_stub)

    with pytest.raises(RuntimeError):
        await stdio_server.run_server()

    assert stop_calls == 1


def _make_search_item(item_id: str) -> SearchItem:
    return SearchItem(
        item_id=item_id,
        title=f"title-{item_id}",
        price="100",
        original_price="120",
        want_cnt=1,
        seller_nick="seller",
        seller_city="Hangzhou",
        image_urls=[],
        detail_url=f"https://www.goofish.com/item?id={item_id}",
        is_free_ship=False,
        publish_time=None,
        exposure_score=1.0,
    )


@pytest.mark.asyncio
async def test_xianyu_search_returns_requested_and_stop_reason(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.http_server as http_server

    class FakeBrowser:
        async def ensure_running(self):
            return True

    class FakeAppWithSearch:
        def __init__(self):
            self.browser = FakeBrowser()

        async def search_with_meta(self, keyword: str, **options):
            return SearchOutcome(
                items=[_make_search_item("item-1")],
                requested_rows=100,
                returned_rows=1,
                stop_reason="stale_limit",
                stale_pages=3,
            )

    monkeypatch.setattr(http_server, "get_app", lambda: FakeAppWithSearch())

    payload = json.loads(await http_server.xianyu_search(keyword="键盘", rows=100))

    assert payload["requested"] == 100
    assert payload["total"] == 1
    assert payload["stop_reason"] == "stale_limit"
    assert payload["stale_pages"] == 3


@pytest.mark.asyncio
async def test_xianyu_search_returns_engine_metadata(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.http_server as http_server

    class FakeBrowser:
        async def ensure_running(self):
            return True

    class FakeAppWithMetadata:
        def __init__(self):
            self.browser = FakeBrowser()

        async def search_with_meta(self, keyword: str, **options):
            return SearchOutcome(
                items=[_make_search_item("item-1")],
                requested_rows=10,
                returned_rows=1,
                stop_reason="target_reached",
                stale_pages=0,
                engine_used="page_api",
                fallback_reason=None,
                pages_fetched=1,
            )

    monkeypatch.setattr(http_server, "get_app", lambda: FakeAppWithMetadata())

    payload = json.loads(await http_server.xianyu_search(keyword="泡泡玛特", rows=10))

    assert payload["engine_used"] == "page_api"
    assert payload["fallback_reason"] is None
    assert payload["pages_fetched"] == 1


@pytest.mark.asyncio
async def test_xianyu_check_session_returns_formatted_last_updated_at(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.http_server as http_server

    class FakeAppWithSessionTime:
        async def check_session(self):
            return {
                "valid": True,
                "last_updated_at": "2026-04-09 15:16:17",
            }

    monkeypatch.setattr(http_server, "get_app", lambda: FakeAppWithSessionTime())

    payload = json.loads(await http_server.xianyu_check_session())

    assert payload["valid"] is True
    assert payload["last_updated_at"] == "2026-04-09 15:16:17"


@pytest.mark.asyncio
async def test_xianyu_check_session_returns_null_when_last_updated_missing(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.http_server as http_server

    class FakeAppWithoutSessionTime:
        async def check_session(self):
            return {"valid": False, "last_updated_at": None}

    monkeypatch.setattr(http_server, "get_app", lambda: FakeAppWithoutSessionTime())

    payload = json.loads(await http_server.xianyu_check_session())

    assert payload["valid"] is False
    assert payload["last_updated_at"] is None


@pytest.mark.asyncio
async def test_xianyu_browser_overview_returns_http_payload(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.http_server as http_server

    class FakeApp:
        async def browser_overview(self):
            return {
                "browser_context_count": 2,
                "contexts": [
                    {
                        "page_count": 1,
                        "pages": [
                            {
                                "title": "闲鱼",
                                "url": "https://www.goofish.com/",
                            }
                        ],
                    }
                ],
            }

    monkeypatch.setattr(http_server, "get_app", lambda: FakeApp())

    payload = json.loads(await http_server.xianyu_browser_overview())

    assert payload == {
        "success": True,
        "browser_context_count": 2,
        "contexts": [
            {
                "page_count": 1,
                "pages": [
                    {
                        "title": "闲鱼",
                        "url": "https://www.goofish.com/",
                    }
                ],
            }
        ],
    }


@pytest.mark.asyncio
async def test_xianyu_browser_overview_returns_http_failure_payload(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.http_server as http_server

    class FakeApp:
        async def browser_overview(self):
            raise RuntimeError("浏览器未连接，无法获取概览")

    monkeypatch.setattr(http_server, "get_app", lambda: FakeApp())

    payload = json.loads(await http_server.xianyu_browser_overview())

    assert payload == {
        "success": False,
        "message": "浏览器未连接，无法获取概览",
    }
