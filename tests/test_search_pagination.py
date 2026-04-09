import asyncio

import pytest

from src.core import SearchItem, SearchParams, SearchOutcome, _BrowserSearchImpl


def make_item(item_id: str) -> SearchItem:
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


class DummyBrowser:
    def __init__(self):
        self.page = None
        self.search_page = EventPage()

    async def ensure_running(self):
        return True

    async def get_work_page(self):
        return self.page

    async def get_search_page(self):
        self.page = self.search_page
        return self.search_page

    async def navigate(self, url, wait_until=None):
        return True


class FakeSearchImpl(_BrowserSearchImpl):
    def __init__(self, pages, response_flags, max_stale_pages=3):
        browser = DummyBrowser()
        super().__init__(browser, browser.search_page, max_stale_pages=max_stale_pages)
        self.pages = pages
        self.response_flags = response_flags
        self.page_index = 0

    async def _setup_response_listener(self):
        self._captured_responses = []
        return None

    async def _navigate_to_home(self):
        return None

    async def _input_search_keyword(self, keyword: str):
        return None

    async def _apply_filters(self, params: SearchParams):
        return None

    async def _wait_for_api_response(self, timeout: int = 30, clear: bool = False):
        return self.response_flags[self.page_index]

    async def _wait_for_new_api_response(self, timeout: int = 30, prev_count: int = 0):
        return self.response_flags[self.page_index]

    async def _next_page(self, page: int):
        self.page_index = min(self.page_index + 1, len(self.pages) - 1)

    def _parse_results(self):
        return self.pages[self.page_index]


class FailingNavigateSearchImpl(FakeSearchImpl):
    async def _navigate_to_search(self, keyword: str):
        raise RuntimeError("navigate failed")


@pytest.mark.asyncio
async def test_search_collects_until_requested_rows():
    pages = [
        [make_item(f"a-{i}") for i in range(30)],
        [make_item(f"b-{i}") for i in range(30)],
        [make_item(f"c-{i}") for i in range(50)],
    ]
    searcher = FakeSearchImpl(
        pages=pages, response_flags=[True, True, True], max_stale_pages=3
    )

    outcome = await searcher.search(SearchParams(keyword="键盘", rows=100))

    assert len(outcome.items) == 100
    assert outcome.stop_reason == "target_reached"
    assert outcome.stale_pages == 0


@pytest.mark.asyncio
async def test_search_stops_after_configured_stale_pages():
    repeated_page = [make_item(f"same-{i}") for i in range(30)]
    searcher = FakeSearchImpl(
        pages=[repeated_page, repeated_page, repeated_page, repeated_page],
        response_flags=[True, True, True, True],
        max_stale_pages=2,
    )

    outcome = await searcher.search(SearchParams(keyword="键盘", rows=100))

    assert len(outcome.items) == 30
    assert outcome.stop_reason == "stale_limit"
    assert outcome.stale_pages == 2


@pytest.mark.asyncio
async def test_search_does_not_reparse_old_response_when_no_new_response():
    searcher = FakeSearchImpl(
        pages=[
            [make_item(f"a-{i}") for i in range(30)],
            [make_item(f"b-{i}") for i in range(30)],
        ],
        response_flags=[True, False],
        max_stale_pages=1,
    )

    outcome = await searcher.search(SearchParams(keyword="键盘", rows=60))

    assert len(outcome.items) == 30
    assert outcome.stop_reason == "stale_limit"
    assert outcome.stale_pages == 1


@pytest.mark.asyncio
async def test_search_outcome_exposes_engine_metadata():
    searcher = FakeSearchImpl(
        pages=[[make_item("a-1")]],
        response_flags=[True],
        max_stale_pages=1,
    )

    outcome = await searcher.search(SearchParams(keyword="泡泡玛特", rows=1))

    assert outcome.engine_used == "browser_fallback"
    assert outcome.fallback_reason is None
    assert outcome.pages_fetched == 1


@pytest.mark.asyncio
async def test_search_returns_error_outcome_when_navigation_fails_before_first_page():
    searcher = FailingNavigateSearchImpl(
        pages=[[make_item("a-1")]],
        response_flags=[True],
        max_stale_pages=1,
    )

    outcome = await searcher.search(SearchParams(keyword="机械键盘", rows=3))

    assert outcome.stop_reason == "error"
    assert outcome.engine_used == "browser_fallback"
    assert outcome.pages_fetched == 0


from src.search_api import PageApiSearchError
from src.core import XianyuApp


class FakePageApiRunner:
    def __init__(self, outcome=None, error=None):
        self.outcome = outcome
        self.error = error

    async def search(self, params):
        if self.error:
            raise self.error
        return self.outcome


class BoundSearchRunner:
    def __init__(self, browser, page, observed, outcome, foreign_page):
        self.browser = browser
        self.page = page
        self.observed = observed
        self.outcome = outcome
        self.foreign_page = foreign_page

    async def search(self, params):
        self.observed.append(("runner_enter", self.page, self.browser.page))
        self.browser.page = self.foreign_page
        self.observed.append(("runner_resume", self.page, self.browser.page))
        return self.outcome


class CapturingFallback:
    def __init__(self, expected_page, outcome):
        self.expected_page = expected_page
        self.outcome = outcome

    async def search(self, params):
        assert self.expected_page is not None
        return self.outcome


class EventPage:
    def __init__(self):
        self.handlers = []
        self.goto_calls = []

    def on(self, event, handler):
        self.handlers.append((event, handler))

    async def goto(self, url, wait_until=None):
        self.goto_calls.append((url, wait_until))
        return None


@pytest.mark.asyncio
async def test_first_page_wait_prefers_newer_response_over_existing_empty_one():
    browser = DummyBrowser()
    page = EventPage()
    searcher = _BrowserSearchImpl(browser, page, max_stale_pages=1)
    empty_response = {"data": {"resultList": []}}
    newer_response = {
        "data": {
            "resultList": [
                {
                    "data": {
                        "item": {
                            "main": {
                                "clickParam": {"args": {"item_id": "newer-1"}},
                                "exContent": {"title": "newer"},
                            }
                        }
                    }
                }
            ]
        }
    }

    searcher._captured_responses = [empty_response]

    async def append_new_response():
        await asyncio.sleep(0.05)
        searcher._captured_responses.append(newer_response)

    task = asyncio.create_task(append_new_response())
    try:
        has_response = await searcher._wait_for_api_response(timeout=1)
        returned_with_newer = (
            task.done() and searcher.search_results[-1] is newer_response
        )
    finally:
        await task

    assert has_response is True
    assert returned_with_newer is True


@pytest.mark.asyncio
async def test_app_prefers_page_api_runner(monkeypatch):
    app = XianyuApp(browser=DummyBrowser())
    expected = SearchOutcome(
        items=[make_item("api-1")],
        requested_rows=1,
        returned_rows=1,
        stop_reason="target_reached",
        stale_pages=0,
        engine_used="page_api",
        fallback_reason=None,
        pages_fetched=1,
    )

    monkeypatch.setattr(
        "src.core._build_page_api_runner",
        lambda browser, page, params, max_stale_pages: FakePageApiRunner(
            outcome=expected
        ),
    )
    monkeypatch.setattr(
        "src.core._BrowserSearchImpl",
        lambda browser, page, max_stale_pages=3: pytest.fail("fallback should not run"),
    )

    outcome = await app.search_with_meta("泡泡玛特", rows=1)

    assert outcome.engine_used == "page_api"
    assert outcome.items[0].item_id == "api-1"


@pytest.mark.asyncio
async def test_app_falls_back_when_page_api_runner_fails(monkeypatch):
    app = XianyuApp(browser=DummyBrowser())
    fallback = FakeSearchImpl(pages=[[make_item("fallback-1")]], response_flags=[True])

    monkeypatch.setattr(
        "src.core._build_page_api_runner",
        lambda browser, page, params, max_stale_pages: FakePageApiRunner(
            error=PageApiSearchError("bridge missing")
        ),
    )
    monkeypatch.setattr(
        "src.core._BrowserSearchImpl",
        lambda browser, page, max_stale_pages=3: fallback,
    )

    outcome = await app.search_with_meta("泡泡玛特", rows=1)

    assert outcome.engine_used == "browser_fallback"
    assert outcome.fallback_reason == "bridge missing"


@pytest.mark.asyncio
async def test_app_falls_back_when_page_api_returns_zero_items(monkeypatch):
    app = XianyuApp(browser=DummyBrowser())
    fallback = FakeSearchImpl(pages=[[make_item("fallback-1")]], response_flags=[True])

    empty_outcome = SearchOutcome(
        items=[],
        requested_rows=1,
        returned_rows=0,
        stop_reason="stale_limit",
        stale_pages=3,
        engine_used="page_api",
        fallback_reason=None,
        pages_fetched=3,
    )
    monkeypatch.setattr(
        "src.core._build_page_api_runner",
        lambda browser, page, params, max_stale_pages: FakePageApiRunner(
            outcome=empty_outcome
        ),
    )
    monkeypatch.setattr(
        "src.core._BrowserSearchImpl",
        lambda browser, page, max_stale_pages=3: fallback,
    )

    outcome = await app.search_with_meta("泡泡玛特", rows=1)

    assert outcome.engine_used == "browser_fallback"
    assert outcome.fallback_reason == "page_api_zero_items"


@pytest.mark.asyncio
async def test_app_search_passes_explicit_search_page_to_runner_and_fallback(
    monkeypatch,
):
    browser = DummyBrowser()
    browser.search_page = object()
    browser.page = object()
    app = XianyuApp(browser=browser)
    captured = {}
    fallback_outcome = SearchOutcome(
        items=[make_item("fallback-1")],
        requested_rows=1,
        returned_rows=1,
        stop_reason="target_reached",
        stale_pages=0,
        engine_used="browser_fallback",
        fallback_reason=None,
        pages_fetched=1,
    )

    def fake_build_page_api_runner(browser_arg, page_arg, params, max_stale_pages):
        captured["runner_page"] = page_arg
        return FakePageApiRunner(
            outcome=SearchOutcome(
                items=[],
                requested_rows=1,
                returned_rows=0,
                stop_reason="stale_limit",
                stale_pages=1,
                engine_used="page_api",
                fallback_reason=None,
                pages_fetched=1,
            )
        )

    def fake_browser_search_impl(browser_arg, page_arg, max_stale_pages=3):
        captured["fallback_page"] = page_arg
        return CapturingFallback(page_arg, fallback_outcome)

    monkeypatch.setattr("src.core._build_page_api_runner", fake_build_page_api_runner)
    monkeypatch.setattr("src.core._BrowserSearchImpl", fake_browser_search_impl)

    outcome = await app.search_with_meta("泡泡玛特", rows=1)

    assert outcome.engine_used == "browser_fallback"
    assert captured == {
        "runner_page": browser.search_page,
        "fallback_page": browser.search_page,
    }


@pytest.mark.asyncio
async def test_app_search_runner_does_not_lose_search_page_when_shared_page_changes(
    monkeypatch,
):
    browser = DummyBrowser()
    app = XianyuApp(browser=browser)
    observed = []
    foreign_page = object()
    expected = SearchOutcome(
        items=[make_item("api-bound-1")],
        requested_rows=1,
        returned_rows=1,
        stop_reason="target_reached",
        stale_pages=0,
        engine_used="page_api",
        fallback_reason=None,
        pages_fetched=1,
    )

    monkeypatch.setattr(
        "src.core._build_page_api_runner",
        lambda browser_arg, page_arg, params, max_stale_pages: BoundSearchRunner(
            browser_arg, page_arg, observed, expected, foreign_page
        ),
    )
    monkeypatch.setattr(
        "src.core._BrowserSearchImpl",
        lambda browser, page, max_stale_pages=3: pytest.fail("fallback should not run"),
    )

    outcome = await app.search_with_meta("泡泡玛特", rows=1)

    assert outcome.items[0].item_id == "api-bound-1"
    assert observed == [
        ("runner_enter", browser.search_page, browser.search_page),
        ("runner_resume", browser.search_page, foreign_page),
    ]


@pytest.mark.asyncio
async def test_browser_search_response_listener_uses_explicit_page():
    search_page = EventPage()
    wrong_page = EventPage()
    browser = DummyBrowser()
    browser.page = wrong_page

    searcher = _BrowserSearchImpl(browser, search_page, max_stale_pages=1)

    await searcher._setup_response_listener()

    assert search_page.handlers and search_page.handlers[0][0] == "response"
    assert wrong_page.handlers == []
