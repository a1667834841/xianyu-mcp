import asyncio
import sys
from types import SimpleNamespace

import pytest

import browser as browser_module
import core
import session


class FakeSessionManager:
    def __init__(self, browser, settings=None):
        self.browser = browser
        self.settings = settings


class FakeKeepaliveService:
    def __init__(self, browser, session, interval_minutes):
        self.browser = browser
        self.session = session
        self.interval_minutes = interval_minutes


class FakePageApiRunner:
    def __init__(self, callback):
        self.callback = callback

    async def search(self, params):
        return await self.callback(params)


class BoundPageApiRunner:
    def __init__(self, browser, page, callback):
        self.browser = browser
        self.page = page
        self.callback = callback

    async def search(self, params):
        return await self.callback(params, self.page, self.browser.page)


class TrackingLock:
    def __init__(self):
        self.active = False
        self.enter_count = 0

    async def __aenter__(self):
        self.active = True
        self.enter_count += 1
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self.active = False


class SearchBrowserManager:
    def __init__(self):
        self.page = None
        self.search_page = SimpleNamespace(url="https://search.local")
        self.work_page = SimpleNamespace(url="https://work.local")
        self.get_search_page_calls = 0
        self.get_work_page_calls = 0

    async def get_search_page(self):
        self.get_search_page_calls += 1
        return self.search_page

    async def get_work_page(self):
        self.get_work_page_calls += 1
        return self.work_page


class PublishBrowserManager:
    def __init__(self):
        self.page = SimpleNamespace(url="https://shared.local")
        self.publish_page = SimpleNamespace(url="https://publish.local")
        self.search_page = SimpleNamespace(url="https://search.local")
        self.get_publish_page_calls = 0
        self.get_search_page_calls = 0

    async def get_publish_page(self):
        self.get_publish_page_calls += 1
        return self.publish_page

    async def get_search_page(self):
        self.get_search_page_calls += 1
        return self.search_page


class IsolatedRoleBrowserManager:
    def __init__(self):
        self.page = None
        self.search_page = SimpleNamespace(url="https://search.local")
        self.session_page = SimpleNamespace(url="https://session.local")
        self.publish_page = SimpleNamespace(url="https://publish.local")
        self.get_search_page_calls = 0
        self.get_session_page_calls = 0
        self.get_publish_page_calls = 0

    async def get_search_page(self):
        self.get_search_page_calls += 1
        return self.search_page

    async def get_session_page(self):
        self.get_session_page_calls += 1
        return self.session_page

    async def get_publish_page(self):
        self.get_publish_page_calls += 1
        return self.publish_page


class PublishPage:
    def __init__(self):
        self.handlers = []

    def on(self, event, handler):
        self.handlers.append((event, handler))


class FalseyGotoPage(PublishPage):
    def __init__(self, name):
        super().__init__()
        self.name = name
        self.goto_calls = []

    def __bool__(self):
        return False

    async def goto(self, url, wait_until="networkidle", timeout=30000):
        self.goto_calls.append((url, wait_until, timeout))
        return None


class TruthyGotoPage(FalseyGotoPage):
    def __bool__(self):
        return True


class PublishBoundCopier:
    active_lock = None
    inactive_lock = None

    def __init__(self, browser, publish_page):
        self.browser = browser
        self.publish_page = publish_page
        assert self.browser.page.url == "https://shared.local"

    async def publish_from_item(self, item_url, **options):
        assert self.active_lock and self.active_lock.active
        assert self.inactive_lock and not self.inactive_lock.active
        assert self.publish_page is self.browser.publish_page
        return {"success": True, "item_url": item_url, "options": options}

    async def capture_item_detail(self, item_url):
        assert self.active_lock and self.active_lock.active
        assert self.inactive_lock and not self.inactive_lock.active
        assert self.publish_page is self.browser.publish_page
        return core.CopiedItem(
            item_id="detail-1",
            title="title",
            description="desc",
            category="category",
            category_id=1,
            brand=None,
            model=None,
            min_price=1.0,
            max_price=1.0,
            image_urls=[],
            seller_city="Hangzhou",
            is_free_ship=False,
            raw_data={"item_url": item_url},
        )


class LockAwareSession:
    def __init__(self, lock):
        self.lock = lock
        self.calls = []

    async def login(self, timeout=15):
        assert self.lock.active
        self.calls.append(("login", timeout))
        return {"success": True}

    async def show_qr_code(self):
        assert self.lock.active
        self.calls.append(("show_qr_code", None))
        return {"success": True}

    async def refresh_token(self):
        assert self.lock.active
        self.calls.append(("refresh_token", None))
        return {"token": "ok"}

    async def check_cookie_valid(self):
        assert self.lock.active
        self.calls.append(("check_cookie_valid", None))
        return True

    def get_cookie_status(self, is_valid):
        self.calls.append(("get_cookie_status", is_valid))
        return {"valid": is_valid}


class FakeResponse:
    url = "https://example.com/api"

    async def json(self):
        return {}


class FakeButton:
    @property
    def first(self):
        return self

    async def is_visible(self):
        return False

    async def click(self):
        return None


class FakeSessionPage:
    def __init__(self, evaluate_result=None):
        self.handlers = []
        self.locator_calls = []
        self.evaluate_result = evaluate_result
        self.screenshot_paths = []

    def on(self, event, handler):
        self.handlers.append((event, handler))

    def locator(self, selector, has_text=None):
        self.locator_calls.append((selector, has_text))
        return FakeButton()

    async def evaluate(self, script):
        return self.evaluate_result

    async def screenshot(self, path):
        self.screenshot_paths.append(path)
        return None


class FakeBrowserManager:
    def __init__(self, session_page=None):
        self.page = None
        self.session_page = session_page or FakeSessionPage()
        self.get_session_page_calls = 0
        self.navigate_calls = []

    async def ensure_running(self):
        return True

    async def get_session_page(self):
        self.get_session_page_calls += 1
        self.page = self.session_page
        return self.session_page

    async def navigate(self, url, wait_until="networkidle", page=None):
        self.navigate_calls.append((url, wait_until, self.page, page))
        return True

    async def get_xianyu_token(self):
        return "token-value"

    async def get_cookie(self, name):
        return "token-value_123"

    async def get_full_cookie_string(self):
        return "_m_h5_tk=token-value_123"


class SwitchingBrowserManager(FakeBrowserManager):
    def __init__(self, session_page=None, active_page=None):
        super().__init__(session_page=session_page)
        self.active_page = active_page or FakeSessionPage()

    async def navigate(self, url, wait_until="networkidle", page=None):
        self.navigate_calls.append((url, wait_until, self.page, page))
        self.page = self.active_page
        return True


class FakeRequestSession:
    def post(self, *args, **kwargs):
        return SimpleNamespace(
            json=lambda: {
                "ret": ["SUCCESS::调用成功"],
                "data": {"module": {"base": {"displayName": "tester"}}},
            }
        )


def build_search_outcome(item_id="search-1"):
    return core.SearchOutcome(
        items=[
            core.SearchItem(
                item_id=item_id,
                title="title",
                price="100",
                original_price="120",
                want_cnt=1,
                seller_nick="seller",
                seller_city="Hangzhou",
                image_urls=[],
                detail_url=f"https://www.goofish.com/item?id={item_id}",
                is_free_ship=False,
            )
        ],
        requested_rows=1,
        returned_rows=1,
        stop_reason="target_reached",
        stale_pages=0,
        engine_used="page_api",
        fallback_reason=None,
        pages_fetched=1,
    )


@pytest.mark.asyncio
async def test_xianyu_app_uses_distinct_role_locks(monkeypatch):
    monkeypatch.setattr(core, "SessionManager", FakeSessionManager)
    monkeypatch.setattr(core, "CookieKeepaliveService", FakeKeepaliveService)

    app = core.XianyuApp(browser=SimpleNamespace())

    assert isinstance(app._search_lock, asyncio.Lock)
    assert isinstance(app._session_lock, asyncio.Lock)
    assert isinstance(app._publish_lock, asyncio.Lock)
    assert app._search_lock is not app._session_lock
    assert app._search_lock is not app._publish_lock
    assert app._session_lock is not app._publish_lock


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method_name", "args", "expected_calls"),
    [
        ("login", {"timeout": 9}, [("login", 9)]),
        ("show_qr_code", {}, [("show_qr_code", None)]),
        ("refresh_token", {}, [("refresh_token", None)]),
        (
            "check_session",
            {},
            [("check_cookie_valid", None), ("get_cookie_status", True)],
        ),
    ],
)
async def test_xianyu_app_session_entries_use_session_lock(
    monkeypatch, method_name, args, expected_calls
):
    monkeypatch.setattr(core, "SessionManager", FakeSessionManager)
    monkeypatch.setattr(core, "CookieKeepaliveService", FakeKeepaliveService)

    app = core.XianyuApp(browser=SimpleNamespace())
    tracking_lock = TrackingLock()
    lock_aware_session = LockAwareSession(tracking_lock)
    app._session_lock = tracking_lock
    app.session = lock_aware_session

    result = await getattr(app, method_name)(**args)

    assert tracking_lock.enter_count == 1
    assert lock_aware_session.calls == expected_calls
    assert result is not None


@pytest.mark.asyncio
async def test_search_with_meta_uses_search_page_and_search_lock(monkeypatch):
    monkeypatch.setattr(core, "SessionManager", FakeSessionManager)
    monkeypatch.setattr(core, "CookieKeepaliveService", FakeKeepaliveService)
    monkeypatch.setitem(
        sys.modules,
        "search_api",
        SimpleNamespace(PageApiSearchError=RuntimeError),
    )

    settings = SimpleNamespace(
        search=SimpleNamespace(max_stale_pages=2),
        keepalive=SimpleNamespace(enabled=False, interval_minutes=5),
    )
    browser = SearchBrowserManager()
    app = core.XianyuApp(browser=browser, settings=settings)
    search_lock = TrackingLock()
    work_lock = TrackingLock()
    app._search_lock = search_lock
    app._work_lock = work_lock

    async def fake_page_api_search(_params):
        assert search_lock.active
        assert not work_lock.active
        assert browser.page is browser.search_page
        return core.SearchOutcome(
            items=[
                core.SearchItem(
                    item_id="search-1",
                    title="title",
                    price="100",
                    original_price="120",
                    want_cnt=1,
                    seller_nick="seller",
                    seller_city="Hangzhou",
                    image_urls=[],
                    detail_url="https://www.goofish.com/item?id=search-1",
                    is_free_ship=False,
                )
            ],
            requested_rows=1,
            returned_rows=1,
            stop_reason="target_reached",
            stale_pages=0,
            engine_used="page_api",
            fallback_reason=None,
            pages_fetched=1,
        )

    monkeypatch.setattr(
        core,
        "_build_page_api_runner",
        lambda browser, page, params, max_stale_pages: FakePageApiRunner(
            fake_page_api_search
        ),
    )
    monkeypatch.setattr(
        core,
        "_BrowserSearchImpl",
        lambda browser, page, max_stale_pages=3: pytest.fail("fallback should not run"),
    )

    await app.search_with_meta("泡泡玛特", rows=1)

    assert browser.get_search_page_calls == 1
    assert browser.get_work_page_calls == 0
    assert search_lock.enter_count == 1
    assert work_lock.enter_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method_name", "expected_result_type"),
    [("publish", dict), ("get_detail", core.CopiedItem)],
)
async def test_publish_entries_use_publish_page_and_publish_lock(
    monkeypatch, method_name, expected_result_type
):
    monkeypatch.setattr(core, "SessionManager", FakeSessionManager)
    monkeypatch.setattr(core, "CookieKeepaliveService", FakeKeepaliveService)
    monkeypatch.setattr(core, "_ItemCopierImpl", PublishBoundCopier)

    settings = SimpleNamespace(
        search=SimpleNamespace(max_stale_pages=2),
        keepalive=SimpleNamespace(enabled=False, interval_minutes=5),
    )
    browser = PublishBrowserManager()
    app = core.XianyuApp(browser=browser, settings=settings)
    publish_lock = TrackingLock()
    search_lock = TrackingLock()
    app._publish_lock = publish_lock
    app._search_lock = search_lock
    PublishBoundCopier.active_lock = publish_lock
    PublishBoundCopier.inactive_lock = search_lock

    if method_name == "publish":
        result = await app.publish("https://www.goofish.com/item?id=1", new_price=88)
    else:
        result = await app.get_detail("https://www.goofish.com/item?id=1")

    assert browser.get_publish_page_calls == 1
    assert browser.get_search_page_calls == 0
    assert publish_lock.enter_count == 1
    assert search_lock.enter_count == 0
    assert isinstance(result, expected_result_type)


@pytest.mark.asyncio
async def test_search_and_check_session_run_in_parallel_with_isolated_pages(
    monkeypatch,
):
    monkeypatch.setattr(core, "SessionManager", FakeSessionManager)
    monkeypatch.setattr(core, "CookieKeepaliveService", FakeKeepaliveService)
    monkeypatch.setitem(
        sys.modules,
        "search_api",
        SimpleNamespace(PageApiSearchError=RuntimeError),
    )

    browser = IsolatedRoleBrowserManager()
    settings = SimpleNamespace(
        search=SimpleNamespace(max_stale_pages=2),
        keepalive=SimpleNamespace(enabled=False, interval_minutes=5),
    )
    app = core.XianyuApp(browser=browser, settings=settings)

    search_entered = asyncio.Event()
    session_entered = asyncio.Event()
    observed = []

    async def fake_page_api_search(_params, bound_page, active_page):
        observed.append(("search_enter", bound_page, active_page, browser.search_page))
        search_entered.set()
        await session_entered.wait()
        observed.append(
            ("search_resume", bound_page, browser.page, browser.search_page)
        )
        return build_search_outcome("search-parallel")

    class ParallelSession:
        def __init__(self, browser_manager):
            self.browser = browser_manager

        async def check_cookie_valid(self):
            page = await self.browser.get_session_page()
            self.browser.page = page
            observed.append(("session_enter", self.browser.page, page))
            session_entered.set()
            await search_entered.wait()
            observed.append(("session_resume", self.browser.page, page))
            return True

        def get_cookie_status(self, is_valid):
            observed.append(
                ("session_status", self.browser.page, self.browser.session_page)
            )
            return {"valid": is_valid}

    monkeypatch.setattr(
        core,
        "_build_page_api_runner",
        lambda browser, page, params, max_stale_pages: BoundPageApiRunner(
            browser, page, fake_page_api_search
        ),
    )
    monkeypatch.setattr(
        core,
        "_BrowserSearchImpl",
        lambda browser, page, max_stale_pages=3: pytest.fail("fallback should not run"),
    )
    app.session = ParallelSession(browser)

    search_task = asyncio.create_task(app.search_with_meta("泡泡玛特", rows=1))
    await asyncio.wait_for(search_entered.wait(), timeout=1)
    session_task = asyncio.create_task(app.check_session())

    search_result, session_result = await asyncio.wait_for(
        asyncio.gather(search_task, session_task),
        timeout=1,
    )

    assert search_result.items[0].item_id == "search-parallel"
    assert session_result == {"valid": True}
    assert browser.get_search_page_calls == 1
    assert browser.get_session_page_calls == 1
    assert observed == [
        (
            "search_enter",
            browser.search_page,
            browser.search_page,
            browser.search_page,
        ),
        ("session_enter", browser.session_page, browser.session_page),
        ("session_resume", browser.session_page, browser.session_page),
        ("session_status", browser.session_page, browser.session_page),
        (
            "search_resume",
            browser.search_page,
            browser.session_page,
            browser.search_page,
        ),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method_name", "expected_result_type"),
    [("publish", dict), ("get_detail", core.CopiedItem)],
)
async def test_search_and_publish_role_entries_run_in_parallel_with_isolated_pages(
    monkeypatch, method_name, expected_result_type
):
    monkeypatch.setattr(core, "SessionManager", FakeSessionManager)
    monkeypatch.setattr(core, "CookieKeepaliveService", FakeKeepaliveService)
    monkeypatch.setitem(
        sys.modules,
        "search_api",
        SimpleNamespace(PageApiSearchError=RuntimeError),
    )

    browser = IsolatedRoleBrowserManager()
    settings = SimpleNamespace(
        search=SimpleNamespace(max_stale_pages=2),
        keepalive=SimpleNamespace(enabled=False, interval_minutes=5),
    )
    app = core.XianyuApp(browser=browser, settings=settings)

    search_entered = asyncio.Event()
    publish_entered = asyncio.Event()
    observed = []

    async def fake_page_api_search(_params, bound_page, active_page):
        observed.append(("search_enter", bound_page, active_page, browser.search_page))
        search_entered.set()
        await publish_entered.wait()
        observed.append(
            ("search_resume", bound_page, browser.page, browser.search_page)
        )
        return build_search_outcome(f"search-{method_name}")

    class ParallelCopier:
        def __init__(self, browser_manager, publish_page):
            self.browser = browser_manager
            self.publish_page = publish_page

        async def publish_from_item(self, item_url, **options):
            self.browser.page = self.publish_page
            observed.append(("publish_enter", self.browser.page, self.publish_page))
            publish_entered.set()
            await search_entered.wait()
            observed.append(("publish_resume", self.browser.page, self.publish_page))
            return {"success": True, "item_url": item_url}

        async def capture_item_detail(self, item_url):
            self.browser.page = self.publish_page
            observed.append(("detail_enter", self.browser.page, self.publish_page))
            publish_entered.set()
            await search_entered.wait()
            observed.append(("detail_resume", self.browser.page, self.publish_page))
            return core.CopiedItem(
                item_id="detail-parallel",
                title="title",
                description="desc",
                category="category",
                category_id=1,
                brand=None,
                model=None,
                min_price=1.0,
                max_price=1.0,
                image_urls=[],
                seller_city="Hangzhou",
                is_free_ship=False,
                raw_data={"item_url": item_url},
            )

    monkeypatch.setattr(
        core,
        "_build_page_api_runner",
        lambda browser, page, params, max_stale_pages: BoundPageApiRunner(
            browser, page, fake_page_api_search
        ),
    )
    monkeypatch.setattr(
        core,
        "_BrowserSearchImpl",
        lambda browser, page, max_stale_pages=3: pytest.fail("fallback should not run"),
    )
    monkeypatch.setattr(core, "_ItemCopierImpl", ParallelCopier)

    search_task = asyncio.create_task(app.search_with_meta("泡泡玛特", rows=1))
    await asyncio.wait_for(search_entered.wait(), timeout=1)

    if method_name == "publish":
        role_task = asyncio.create_task(
            app.publish("https://www.goofish.com/item?id=1", new_price=88)
        )
    else:
        role_task = asyncio.create_task(
            app.get_detail("https://www.goofish.com/item?id=1")
        )

    search_result, role_result = await asyncio.wait_for(
        asyncio.gather(search_task, role_task),
        timeout=1,
    )

    role_enter = "publish_enter" if method_name == "publish" else "detail_enter"
    role_resume = "publish_resume" if method_name == "publish" else "detail_resume"

    assert search_result.items[0].item_id == f"search-{method_name}"
    assert isinstance(role_result, expected_result_type)
    assert browser.get_search_page_calls == 1
    assert browser.get_publish_page_calls == 1
    assert observed[:2] == [
        (
            "search_enter",
            browser.search_page,
            browser.search_page,
            browser.search_page,
        ),
        (role_enter, browser.publish_page, browser.publish_page),
    ]
    resume_events = observed[2:]
    assert len(resume_events) == 2
    assert (
        "search_resume",
        browser.search_page,
        browser.publish_page,
        browser.search_page,
    ) in resume_events
    assert (role_resume, browser.publish_page, browser.publish_page) in resume_events


@pytest.mark.asyncio
async def test_same_search_role_serializes_concurrent_calls(monkeypatch):
    monkeypatch.setattr(core, "SessionManager", FakeSessionManager)
    monkeypatch.setattr(core, "CookieKeepaliveService", FakeKeepaliveService)
    monkeypatch.setitem(
        sys.modules,
        "search_api",
        SimpleNamespace(PageApiSearchError=RuntimeError),
    )

    browser = IsolatedRoleBrowserManager()
    settings = SimpleNamespace(
        search=SimpleNamespace(max_stale_pages=2),
        keepalive=SimpleNamespace(enabled=False, interval_minutes=5),
    )
    app = core.XianyuApp(browser=browser, settings=settings)

    release_first = asyncio.Event()
    first_entered = asyncio.Event()
    active_calls = 0
    max_active_calls = 0
    started = []
    finished = []

    async def fake_page_api_search(params):
        nonlocal active_calls, max_active_calls
        active_calls += 1
        max_active_calls = max(max_active_calls, active_calls)
        started.append(params.keyword)
        if params.keyword == "kw-1":
            first_entered.set()
            await release_first.wait()
        finished.append(params.keyword)
        active_calls -= 1
        return build_search_outcome(params.keyword)

    monkeypatch.setattr(
        core,
        "_build_page_api_runner",
        lambda browser, page, params, max_stale_pages: FakePageApiRunner(
            fake_page_api_search
        ),
    )
    monkeypatch.setattr(
        core,
        "_BrowserSearchImpl",
        lambda browser, page, max_stale_pages=3: pytest.fail("fallback should not run"),
    )

    first_task = asyncio.create_task(app.search_with_meta("kw-1", rows=1))
    second_task = asyncio.create_task(app.search_with_meta("kw-2", rows=1))

    await asyncio.wait_for(first_entered.wait(), timeout=1)
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert started == ["kw-1"]
    assert finished == []
    assert max_active_calls == 1

    release_first.set()
    first_result, second_result = await asyncio.wait_for(
        asyncio.gather(first_task, second_task),
        timeout=1,
    )

    assert first_result.items[0].item_id == "kw-1"
    assert second_result.items[0].item_id == "kw-2"
    assert started == ["kw-1", "kw-2"]
    assert finished == ["kw-1", "kw-2"]
    assert max_active_calls == 1


@pytest.mark.asyncio
async def test_item_copier_capture_item_detail_uses_explicit_publish_page(monkeypatch):
    publish_page = PublishPage()
    browser = SimpleNamespace(page=None, navigate_calls=[])

    async def ensure_running():
        return True

    async def navigate(url, wait_until="networkidle", page=None):
        browser.navigate_calls.append((url, wait_until, page))
        return True

    browser.ensure_running = ensure_running
    browser.navigate = navigate

    copier = core._ItemCopierImpl(browser, publish_page)

    async def raise_timeout(awaitable, timeout):
        awaitable.close()
        raise asyncio.TimeoutError

    monkeypatch.setattr(core.asyncio, "wait_for", raise_timeout)

    assert (
        await copier.capture_item_detail(
            "https://www.goofish.com/item?id=1", timeout=0.01
        )
        is None
    )
    assert publish_page.handlers and publish_page.handlers[0][0] == "response"
    assert browser.navigate_calls == [
        ("https://www.goofish.com/item?id=1", "networkidle", publish_page)
    ]


@pytest.mark.asyncio
async def test_publish_from_item_navigates_with_explicit_publish_page(monkeypatch):
    publish_page = FalseyGotoPage("publish")
    shared_page = TruthyGotoPage("shared")
    browser = SimpleNamespace(page=shared_page)

    async def ensure_running():
        return True

    async def navigate(url, wait_until="networkidle", page=None):
        return await browser_module.AsyncChromeManager.navigate(
            browser, url, wait_until=wait_until, page=page
        )

    browser.ensure_running = ensure_running
    browser.navigate = navigate

    copier = core._ItemCopierImpl(browser, publish_page)

    async def fake_capture(_item_url):
        return core.CopiedItem(
            item_id="detail-1",
            title="title",
            description="desc",
            category="",
            category_id=1,
            brand=None,
            model=None,
            min_price=1.0,
            max_price=1.0,
            image_urls=[],
            seller_city="Hangzhou",
            is_free_ship=False,
            raw_data={},
        )

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(copier, "capture_item_detail", fake_capture)
    monkeypatch.setattr(core.asyncio, "sleep", no_sleep)

    result = await copier.publish_from_item("https://www.goofish.com/item?id=1")

    assert result["error"] == "商品没有图片"
    assert publish_page.goto_calls == [
        ("https://www.goofish.com/publish", "networkidle", 30000)
    ]
    assert shared_page.goto_calls == []


@pytest.mark.asyncio
async def test_browser_navigate_prefers_explicit_page_even_if_falsey():
    explicit_page = FalseyGotoPage("explicit")
    shared_page = SimpleNamespace(goto_calls=[])

    async def shared_goto(url, wait_until="networkidle", timeout=30000):
        shared_page.goto_calls.append((url, wait_until, timeout))
        return None

    shared_page.goto = shared_goto
    manager = SimpleNamespace(page=shared_page)

    result = await browser_module.AsyncChromeManager.navigate(
        manager,
        "https://www.goofish.com/publish",
        page=explicit_page,
    )

    assert result is True
    assert explicit_page.goto_calls == [
        ("https://www.goofish.com/publish", "networkidle", 30000)
    ]
    assert shared_page.goto_calls == []


@pytest.mark.asyncio
async def test_check_cookie_valid_uses_session_page(monkeypatch, tmp_path):
    browser = FakeBrowserManager()
    manager = session.SessionManager(
        chrome_manager=browser,
        settings=SimpleNamespace(
            storage=SimpleNamespace(token_file=tmp_path / "token.json")
        ),
    )

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(session.asyncio, "sleep", no_sleep)
    monkeypatch.setattr(session.requests, "Session", lambda: FakeRequestSession())

    assert await manager.check_cookie_valid() is True
    assert browser.get_session_page_calls == 1
    assert browser.navigate_calls == [
        (
            "https://www.goofish.com",
            "networkidle",
            browser.session_page,
            browser.session_page,
        )
    ]


@pytest.mark.asyncio
async def test_refresh_token_uses_session_page(monkeypatch, tmp_path):
    browser = FakeBrowserManager()
    manager = session.SessionManager(
        chrome_manager=browser,
        settings=SimpleNamespace(
            storage=SimpleNamespace(token_file=tmp_path / "token.json")
        ),
    )

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(session.asyncio, "sleep", no_sleep)

    result = await manager.refresh_token()

    assert result == {"token": "token-value", "full_cookie": "token-value_123"}
    assert browser.get_session_page_calls == 1
    assert browser.navigate_calls == [
        (
            "https://www.goofish.com",
            "networkidle",
            browser.session_page,
            browser.session_page,
        )
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("method_name", ["login", "show_qr_code"])
async def test_session_login_paths_use_session_page(monkeypatch, tmp_path, method_name):
    browser = FakeBrowserManager()
    manager = session.SessionManager(
        chrome_manager=browser,
        settings=SimpleNamespace(
            storage=SimpleNamespace(token_file=tmp_path / "token.json")
        ),
    )

    async def no_sleep(_seconds):
        return None

    async def logged_in():
        return True

    monkeypatch.setattr(session.asyncio, "sleep", no_sleep)
    monkeypatch.setattr(manager, "check_login_status", logged_in)

    result = await getattr(manager, method_name)()

    assert result == {
        "success": True,
        "logged_in": True,
        "token": "token-value",
        "message": "已登录",
    }
    assert browser.get_session_page_calls == 1
    assert browser.navigate_calls == [
        (
            "https://www.goofish.com",
            "networkidle",
            browser.session_page,
            browser.session_page,
        )
    ]


@pytest.mark.asyncio
async def test_get_qr_code_uses_session_page(monkeypatch, tmp_path):
    session_page = FakeSessionPage()
    wrong_page = FakeSessionPage()
    browser = FakeBrowserManager(session_page=session_page)
    browser.page = wrong_page
    manager = session.SessionManager(
        chrome_manager=browser,
        settings=SimpleNamespace(
            storage=SimpleNamespace(token_file=tmp_path / "token.json")
        ),
    )

    async def raise_timeout(_awaitable, timeout):
        _awaitable.close()
        raise asyncio.TimeoutError

    monkeypatch.setattr(session.asyncio, "wait_for", raise_timeout)

    assert await manager._get_qr_code() is None
    assert browser.get_session_page_calls == 1
    assert session_page.handlers and session_page.handlers[0][0] == "response"
    assert wrong_page.handlers == []


@pytest.mark.asyncio
async def test_get_qr_code_from_dom_uses_session_page(monkeypatch, tmp_path):
    session_page = FakeSessionPage(evaluate_result="http://alicdn.com/qr.png")
    wrong_page = FakeSessionPage(evaluate_result=None)
    browser = FakeBrowserManager(session_page=session_page)
    browser.page = wrong_page
    manager = session.SessionManager(
        chrome_manager=browser,
        settings=SimpleNamespace(
            storage=SimpleNamespace(token_file=tmp_path / "token.json")
        ),
    )

    async def fake_generate_qr_base64(url):
        return {"base64": f"b64:{url}"}

    monkeypatch.setattr(manager, "_generate_qr_base64", fake_generate_qr_base64)
    monkeypatch.setattr(manager, "_generate_ascii_qr", lambda url: f"ascii:{url}")

    result = await manager._get_qr_code_from_dom()

    assert result == {
        "url": "https://alicdn.com/qr.png",
        "base64": "b64:https://alicdn.com/qr.png",
        "ascii": "ascii:https://alicdn.com/qr.png",
        "text": "https://alicdn.com/qr.png",
    }
    assert browser.get_session_page_calls == 1


@pytest.mark.asyncio
async def test_show_qr_code_screenshot_fallback_uses_session_page(
    monkeypatch, tmp_path
):
    session_page = FakeSessionPage()
    wrong_page = FakeSessionPage()
    browser = FakeBrowserManager(session_page=session_page)
    browser.page = wrong_page
    manager = session.SessionManager(
        chrome_manager=browser,
        settings=SimpleNamespace(
            storage=SimpleNamespace(token_file=tmp_path / "token.json")
        ),
    )

    async def no_qr_code():
        return None

    monkeypatch.setattr(manager, "_get_qr_code", no_qr_code)

    await manager._show_qr_code()

    assert browser.get_session_page_calls == 1
    assert session_page.screenshot_paths == ["/tmp/xianyu-login.png"]
    assert wrong_page.screenshot_paths == []


@pytest.mark.asyncio
async def test_login_uses_explicit_session_page_reference_after_navigation(
    monkeypatch, tmp_path
):
    session_page = FakeSessionPage()
    wrong_page = FakeSessionPage()
    browser = SwitchingBrowserManager(session_page=session_page, active_page=wrong_page)
    manager = session.SessionManager(
        chrome_manager=browser,
        settings=SimpleNamespace(
            storage=SimpleNamespace(token_file=tmp_path / "token.json")
        ),
    )

    async def no_sleep(_seconds):
        return None

    async def not_logged_in():
        return False

    monkeypatch.setattr(session.asyncio, "sleep", no_sleep)
    monkeypatch.setattr(manager, "check_login_status", not_logged_in)

    result = await manager.login(timeout=0)

    assert result == {"success": False, "message": "获取二维码超时"}
    assert session_page.locator_calls == [("button", "登录")]
    assert wrong_page.locator_calls == []
