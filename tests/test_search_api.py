import pytest

from src.core import SearchItem, SearchParams
from src.search_api import PageApiSearchClient, PageApiSearchError, StableSearchRunner


def make_item(item_id: str) -> dict:
    return {
        "item_id": item_id,
        "title": f"title-{item_id}",
        "price": "100",
        "original_price": "120",
        "want_cnt": 1,
        "seller_nick": "seller",
        "seller_city": "Hangzhou",
        "image_urls": [],
        "detail_url": f"https://www.goofish.com/item?id={item_id}",
        "is_free_ship": False,
        "publish_time": None,
        "exposure_score": 1.0,
    }


class FakePage:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []
        self.url = "https://www.goofish.com"

    async def evaluate(self, script, payload=None):
        self.calls.append(payload)
        idx = len(self.calls) % len(self.responses)
        response = self.responses[idx]
        if isinstance(response, Exception):
            raise response
        return response


@pytest.mark.asyncio
async def test_page_api_client_returns_structured_page():
    page = FakePage(
        [
            None,
            {
                "keyword": "泡泡玛特",
                "page": 1,
                "items": [make_item("a-1"), make_item("a-2")],
            },
            {
                "keyword": "泡泡玛特",
                "page": 1,
                "items": [make_item("a-1"), make_item("a-2")],
            },
        ]
    )
    client = PageApiSearchClient(page)

    result = await client.fetch_page(
        SearchParams(keyword="泡泡玛特", rows=10), page_number=1
    )

    assert result.keyword == "泡泡玛特"
    assert [item.item_id for item in result.items] == ["a-1", "a-2"]


@pytest.mark.asyncio
async def test_page_api_client_rejects_keyword_mismatch():
    page = FakePage(
        [
            None,
            {"keyword": "Mac mini", "page": 1, "items": [make_item("wrong-1")]},
            {"keyword": "Mac mini", "page": 1, "items": [make_item("wrong-1")]},
        ]
    )
    client = PageApiSearchClient(page)

    with pytest.raises(PageApiSearchError, match="keyword mismatch"):
        await client.fetch_page(
            SearchParams(keyword="泡泡玛特", rows=10), page_number=1
        )


class StubClient:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    async def fetch_page(self, params, page_number):
        self.calls.append(page_number)
        return self.pages[page_number - 1]


@pytest.mark.asyncio
async def test_stable_runner_collects_multiple_pages_until_target():
    params = SearchParams(keyword="泡泡玛特", rows=4)
    runner = StableSearchRunner(
        client=StubClient(
            [
                type(
                    "Result",
                    (),
                    {
                        "page": 1,
                        "items": [
                            SearchItem(**make_item("a-1")),
                            SearchItem(**make_item("a-2")),
                        ],
                    },
                )(),
                type(
                    "Result",
                    (),
                    {
                        "page": 2,
                        "items": [
                            SearchItem(**make_item("b-1")),
                            SearchItem(**make_item("b-2")),
                        ],
                    },
                )(),
            ]
        ),
        max_stale_pages=2,
    )

    outcome = await runner.search(params)

    assert [item.item_id for item in outcome.items] == ["a-1", "a-2", "b-1", "b-2"]
    assert outcome.engine_used == "page_api"
    assert outcome.stop_reason == "target_reached"
    assert outcome.pages_fetched == 2


@pytest.mark.asyncio
async def test_stable_runner_stops_after_stale_pages():
    repeated = [SearchItem(**make_item("a-1")), SearchItem(**make_item("a-2"))]
    runner = StableSearchRunner(
        client=StubClient(
            [
                type("Result", (), {"page": 1, "items": repeated})(),
                type("Result", (), {"page": 2, "items": repeated})(),
                type("Result", (), {"page": 3, "items": repeated})(),
            ]
        ),
        max_stale_pages=2,
    )

    outcome = await runner.search(SearchParams(keyword="泡泡玛特", rows=10))

    assert len(outcome.items) == 2
    assert outcome.stop_reason == "stale_limit"
    assert outcome.stale_pages == 2


@pytest.mark.asyncio
async def test_page_api_client_installs_bridge_once():
    class BridgePage(FakePage):
        def __init__(self):
            super().__init__(
                [
                    None,
                    {"keyword": "泡泡玛特", "page": 1, "items": []},
                    {"keyword": "泡泡玛特", "page": 1, "items": []},
                ]
            )
            self.init_calls = 0

        async def evaluate(self, script, payload=None):
            if payload is None:
                self.init_calls += 1
                return None
            return await super().evaluate(script, payload)

    page = BridgePage()
    client = PageApiSearchClient(page)

    await client.fetch_page(SearchParams(keyword="泡泡玛特", rows=1), page_number=1)
    await client.fetch_page(SearchParams(keyword="泡泡玛特", rows=1), page_number=1)

    assert page.init_calls == 1


@pytest.mark.asyncio
async def test_page_api_client_runs_ready_hook_before_bridge():
    class OffDomainPage(FakePage):
        def __init__(self):
            super().__init__(
                [{"keyword": "泡泡玛特", "page": 1, "items": [make_item("a-1")]}]
            )
            self.url = "about:blank"

        async def evaluate(self, script, payload=None):
            if self.url != "https://www.goofish.com":
                raise RuntimeError("missing _m_h5_tk")
            if payload is None:
                return None
            return self.responses[0]

    page = OffDomainPage()
    ready_calls = 0

    async def ensure_page_ready():
        nonlocal ready_calls
        ready_calls += 1
        page.url = "https://www.goofish.com"

    client = PageApiSearchClient(page, ensure_page_ready=ensure_page_ready)

    result = await client.fetch_page(
        SearchParams(keyword="泡泡玛特", rows=1), page_number=1
    )

    assert ready_calls == 1
    assert [item.item_id for item in result.items] == ["a-1"]


@pytest.mark.asyncio
async def test_page_api_client_wraps_page_errors_as_search_errors():
    class BrokenPage(FakePage):
        async def evaluate(self, script, payload=None):
            raise RuntimeError("missing _m_h5_tk")

    client = PageApiSearchClient(BrokenPage([]))

    with pytest.raises(PageApiSearchError, match="missing _m_h5_tk"):
        await client.fetch_page(SearchParams(keyword="泡泡玛特", rows=1), page_number=1)
