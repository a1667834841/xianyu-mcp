"""
test_keepalive.py - Verify browser page roles and session cookie wiring.
"""

import importlib
import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.browser import AsyncChromeManager
from src.session import SessionManager
from src.settings import AppSettings, KeepaliveSettings, SearchSettings, StorageSettings


class FakePage:
    pass


class FakeContext:
    def __init__(self, initial_pages: int = 1):
        self.pages = [FakePage() for _ in range(initial_pages)]

    async def new_page(self):
        page = FakePage()
        self.pages.append(page)
        return page


@pytest.mark.asyncio
async def test_ensure_running_does_not_reconnect_when_connected(tmp_path):
    manager = AsyncChromeManager(auto_start=False, settings=make_settings(tmp_path))
    manager.browser = object()
    manager.context = FakeContext()
    work_page = FakePage()
    manager.context.pages[0] = work_page
    manager._work_page = work_page
    manager.page = work_page

    connect_called = False

    async def connect_stub():
        nonlocal connect_called
        connect_called = True
        return True

    manager.connect = connect_stub

    assert await manager.ensure_running()
    assert not connect_called


@pytest.mark.asyncio
async def test_ensure_running_serializes_concurrent_connects(tmp_path):
    manager = AsyncChromeManager(auto_start=False, settings=make_settings(tmp_path))

    connect_calls = 0

    async def connect_stub():
        nonlocal connect_calls
        connect_calls += 1
        await asyncio.sleep(0)
        manager.browser = object()
        manager.context = FakeContext()
        work_page = manager.context.pages[0]
        manager._work_page = work_page
        manager.page = work_page
        return True

    manager.connect = connect_stub

    first, second = await asyncio.gather(
        manager.ensure_running(),
        manager.ensure_running(),
    )

    assert first is True
    assert second is True
    assert connect_calls == 1


@pytest.mark.asyncio
async def test_keepalive_page_uses_dedicated_tab(tmp_path):
    manager = AsyncChromeManager(auto_start=False, settings=make_settings(tmp_path))
    manager.context = FakeContext(initial_pages=2)
    work_page = manager.context.pages[0]
    ambient_page = manager.context.pages[1]
    manager._work_page = work_page
    manager.page = work_page

    keepalive_page = await manager.get_keepalive_page()

    assert keepalive_page is manager._keepalive_page
    assert keepalive_page is not work_page
    assert keepalive_page is not ambient_page
    assert manager.context.pages[-1] is keepalive_page
    assert await manager.get_keepalive_page() is keepalive_page


def make_settings(tmp_path):
    user_root = tmp_path / "users" / "default"
    return AppSettings(
        storage=StorageSettings(
            data_root=tmp_path / "users",
            user_id="default",
            token_file=user_root / "tokens" / "token.json",
            chrome_user_data_dir=user_root / "chrome-profile",
        ),
        keepalive=KeepaliveSettings(enabled=True, interval_minutes=10),
        search=SearchSettings(max_stale_pages=3),
    )


@pytest.mark.asyncio
async def test_browser_page_roles_are_distinct(tmp_path):
    manager = AsyncChromeManager(auto_start=False, settings=make_settings(tmp_path))
    manager.context = FakeContext()
    manager.page = manager.context.pages[0]

    work_page = await manager.get_work_page()
    keepalive_page = await manager.get_keepalive_page()

    assert work_page is manager.context.pages[0]
    assert keepalive_page is manager.context.pages[1]
    assert await manager.get_keepalive_page() is keepalive_page
    assert manager.page is work_page


def test_session_manager_uses_resolved_token_file(tmp_path):
    settings = make_settings(tmp_path)
    session = SessionManager(chrome_manager=SimpleNamespace(), settings=settings)

    session.save_cookie("a=1; b=2")

    data = json.loads(settings.storage.token_file.read_text(encoding="utf-8"))
    assert data["full_cookie"] == "a=1; b=2"
    assert "updated_at" in data
    assert "last_refresh_at" in data


def test_session_manager_inherits_chrome_manager_settings(tmp_path):
    settings = make_settings(tmp_path)
    chrome_manager = SimpleNamespace(settings=settings)

    session = SessionManager(chrome_manager=chrome_manager, settings=None)

    assert session.settings is settings
    assert session.token_file == settings.storage.token_file


def test_top_level_imports_work():
    project_root = Path(__file__).resolve().parents[1]
    src_dir = project_root / "src"
    saved_sys_path = list(sys.path)
    saved_browser = sys.modules.pop("browser", None)
    saved_session = sys.modules.pop("session", None)
    saved_settings = sys.modules.pop("settings", None)

    try:
        sys.path[:] = [str(src_dir)]
        importlib.invalidate_caches()
        browser_mod = importlib.import_module("browser")
        session_mod = importlib.import_module("session")

        assert hasattr(browser_mod, "AsyncChromeManager")
        assert hasattr(session_mod, "SessionManager")
    finally:
        sys.path[:] = saved_sys_path
        for name, module in (
            ("browser", saved_browser),
            ("session", saved_session),
            ("settings", saved_settings),
        ):
            if module is not None:
                sys.modules[name] = module
            else:
                sys.modules.pop(name, None)


class FakeKeepalivePage:
    def __init__(self):
        self.goto_calls: list[str] = []
        self.reload_calls = 0

    async def goto(self, url: str, **_kwargs):
        self.goto_calls.append(url)

    async def reload(self, **_kwargs):
        self.reload_calls += 1


class FakeKeepaliveBrowser:
    def __init__(self, cookie_value: str):
        self.keepalive_page = FakeKeepalivePage()
        self.cookie_value = cookie_value
        self.ensure_running_calls = 0

    async def ensure_running(self):
        self.ensure_running_calls += 1
        return True

    async def get_keepalive_page(self):
        return self.keepalive_page

    async def get_full_cookie_string(self) -> str:
        return self.cookie_value


class FakeKeepaliveSession:
    def __init__(self):
        self.saved: list[str] = []

    def save_cookie(self, full_cookie: str):
        self.saved.append(full_cookie)


@pytest.mark.asyncio
async def test_cookie_keepalive_run_once_goto_then_reload_and_saves_cookie():
    from src.keepalive import CookieKeepaliveService

    browser = FakeKeepaliveBrowser(cookie_value="a=1; b=2")
    session = FakeKeepaliveSession()
    service = CookieKeepaliveService(
        browser=browser, session=session, interval_minutes=10
    )

    await service.run_once()
    assert browser.keepalive_page.goto_calls == ["https://www.goofish.com"]
    assert browser.keepalive_page.reload_calls == 0
    assert session.saved == ["a=1; b=2"]
    assert browser.ensure_running_calls == 1

    await service.run_once()
    assert browser.keepalive_page.goto_calls == ["https://www.goofish.com"]
    assert browser.keepalive_page.reload_calls == 1
    assert session.saved == ["a=1; b=2", "a=1; b=2"]
    assert browser.ensure_running_calls == 2


@pytest.mark.asyncio
async def test_cookie_keepalive_skips_when_browser_not_ready():
    from src.keepalive import CookieKeepaliveService

    class NotReadyBrowser:
        def __init__(self):
            self.get_keepalive_page_calls = 0

        async def ensure_running(self):
            return False

        async def get_keepalive_page(self):
            self.get_keepalive_page_calls += 1
            raise AssertionError(
                "should not request keepalive page when browser is not ready"
            )

        async def get_full_cookie_string(self):
            raise AssertionError("should not request cookies when browser is not ready")

    browser = NotReadyBrowser()
    session = FakeKeepaliveSession()
    service = CookieKeepaliveService(
        browser=browser, session=session, interval_minutes=10
    )

    await service.run_once()

    assert browser.get_keepalive_page_calls == 0
    assert session.saved == []


@pytest.mark.asyncio
async def test_app_start_background_tasks_idempotent_and_respects_settings(
    tmp_path, monkeypatch
):
    import src.core as core_mod

    settings = make_settings(tmp_path)
    events: list[str] = []

    class FakeBrowser:
        def __init__(self):
            self.settings = settings

        async def ensure_running(self):
            return True

        async def close(self):
            events.append("close")

    class FakeSession:
        def __init__(self, chrome_manager, settings=None, page_coordinator=None):
            self.chrome_manager = chrome_manager
            self.settings = settings
            self.page_coordinator = page_coordinator

        def save_cookie(self, full_cookie: str):
            return None

    class FakeKeepalive:
        def __init__(
            self, browser, session, interval_minutes: int, page_coordinator=None, **kwargs
        ):
            self.browser = browser
            self.session = session
            self.interval_minutes = interval_minutes
            self.page_coordinator = page_coordinator
            self.start_calls = 0
            self.stop_calls = 0

        def start(self):
            self.start_calls += 1
            events.append("start")

        async def stop(self):
            self.stop_calls += 1
            events.append("stop")

    monkeypatch.setattr(core_mod, "SessionManager", FakeSession)
    monkeypatch.setattr(core_mod, "CookieKeepaliveService", FakeKeepalive)

    app = core_mod.XianyuApp(browser=FakeBrowser(), settings=settings)

    app.start_background_tasks()
    app.start_background_tasks()

    keepalive = app.keepalive
    assert isinstance(keepalive, FakeKeepalive)
    assert keepalive.interval_minutes == settings.keepalive.interval_minutes
    assert keepalive.start_calls == 1

    await app.stop_background_tasks()
    await app.stop_background_tasks()
    assert keepalive.stop_calls == 1

    disabled_settings = AppSettings(
        storage=settings.storage,
        keepalive=KeepaliveSettings(
            enabled=False, interval_minutes=settings.keepalive.interval_minutes
        ),
        search=settings.search,
    )
    disabled_app = core_mod.XianyuApp(browser=FakeBrowser(), settings=disabled_settings)
    disabled_app.start_background_tasks()
    assert disabled_app.keepalive.start_calls == 0


@pytest.mark.asyncio
async def test_app_aexit_stops_background_tasks_before_closing_browser(
    tmp_path, monkeypatch
):
    import src.core as core_mod

    settings = make_settings(tmp_path)
    events: list[str] = []

    class FakeBrowser:
        def __init__(self):
            self.settings = settings

        async def ensure_running(self):
            return True

        async def close(self):
            events.append("close")

    class FakeSession:
        def __init__(self, chrome_manager, settings=None, page_coordinator=None):
            self.chrome_manager = chrome_manager
            self.settings = settings
            self.page_coordinator = page_coordinator

        def save_cookie(self, full_cookie: str):
            return None

    class FakeKeepalive:
        def __init__(
            self, browser, session, interval_minutes: int, page_coordinator=None, **kwargs
        ):
            self.browser = browser
            self.session = session
            self.interval_minutes = interval_minutes
            self.page_coordinator = page_coordinator
            self.start_calls = 0
            self.stop_calls = 0

        def start(self):
            self.start_calls += 1

        async def stop(self):
            self.stop_calls += 1
            events.append("stop")

    monkeypatch.setattr(core_mod, "SessionManager", FakeSession)
    monkeypatch.setattr(core_mod, "CookieKeepaliveService", FakeKeepalive)

    app = core_mod.XianyuApp(browser=FakeBrowser(), settings=settings)
    app.start_background_tasks()

    await app.__aexit__(None, None, None)

    assert events == ["stop", "close"]


class FakeCoordinator:
    def __init__(self, page):
        self.page = page
        self.calls = 0

    async def get_keepalive_page(self):
        self.calls += 1
        return self.page


@pytest.mark.asyncio
async def test_cookie_keepalive_uses_page_coordinator_when_present():
    from src.keepalive import CookieKeepaliveService

    browser = FakeKeepaliveBrowser(cookie_value="a=1; b=2")
    session = FakeKeepaliveSession()
    coordinator = FakeCoordinator(browser.keepalive_page)
    service = CookieKeepaliveService(
        browser=browser,
        session=session,
        interval_minutes=10,
        page_coordinator=coordinator,
    )

    await service.run_once()

    assert coordinator.calls == 1
    assert browser.keepalive_page.goto_calls == ["https://www.goofish.com"]


def test_app_builds_one_shared_page_coordinator(tmp_path):
    import src.core as core_mod

    settings = make_settings(tmp_path)

    class FakeBrowser:
        def __init__(self):
            self.settings = settings

    class FakeSession:
        def __init__(self, chrome_manager, settings=None, page_coordinator=None):
            self.chrome_manager = chrome_manager
            self.settings = settings
            self.page_coordinator = page_coordinator

    class FakeKeepalive:
        def __init__(self, browser, session, interval_minutes, page_coordinator=None, **kwargs):
            self.browser = browser
            self.session = session
            self.interval_minutes = interval_minutes
            self.page_coordinator = page_coordinator

    class FakeCoordinator:
        def __init__(self, browser):
            self.browser = browser

    browser = FakeBrowser()

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(core_mod, "SessionManager", FakeSession)
    monkeypatch.setattr(core_mod, "CookieKeepaliveService", FakeKeepalive)
    monkeypatch.setattr(core_mod, "PageCoordinator", FakeCoordinator)
    try:
        app = core_mod.XianyuApp(browser=browser, settings=settings)
    finally:
        monkeypatch.undo()

    assert isinstance(app.page_coordinator, FakeCoordinator)
    assert app.session.page_coordinator is app.page_coordinator
    assert app.keepalive.page_coordinator is app.page_coordinator
