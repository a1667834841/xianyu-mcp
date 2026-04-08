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

    async def ensure_running(self):
        return True

    async def get_work_page(self):
        return self.page

    async def navigate(self, url, wait_until=None):
        return True


class FakeSearchImpl(_BrowserSearchImpl):
    def __init__(self, pages, response_flags, max_stale_pages=3):
        super().__init__(DummyBrowser(), max_stale_pages=max_stale_pages)
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
        lambda browser, params, max_stale_pages: FakePageApiRunner(outcome=expected),
    )
    monkeypatch.setattr(
        "src.core._BrowserSearchImpl",
        lambda browser, max_stale_pages=3: pytest.fail("fallback should not run"),
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
        lambda browser, params, max_stale_pages: FakePageApiRunner(
            error=PageApiSearchError("bridge missing")
        ),
    )
    monkeypatch.setattr(
        "src.core._BrowserSearchImpl", lambda browser, max_stale_pages=3: fallback
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
        lambda browser, params, max_stale_pages: FakePageApiRunner(
            outcome=empty_outcome
        ),
    )
    monkeypatch.setattr(
        "src.core._BrowserSearchImpl", lambda browser, max_stale_pages=3: fallback
    )

    outcome = await app.search_with_meta("泡泡玛特", rows=1)

    assert outcome.engine_used == "browser_fallback"
    assert outcome.fallback_reason == "page_api_zero_items"
