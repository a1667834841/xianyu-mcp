import pytest

from src.core import SearchItem, SearchParams
from src.search_api import StableSearchRunner


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
    assert outcome.engine_used == "http_api"
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