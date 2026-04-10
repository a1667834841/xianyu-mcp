from datetime import datetime
from unittest.mock import patch

import pytest

from src.core import SearchItem, SearchParams
from src.search_api import StableSearchRunner, calculate_exposure_score


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


# ==================== 曝光度计算测试 ====================


def test_calculate_exposure_score_normal():
    """正常计算曝光度"""
    # 使用固定时间避免时间差问题
    with patch("src.search_api.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 4, 10, 12, 0, 0)
        mock_dt.strptime = datetime.strptime

        # 1天前发布，100人想要
        result = calculate_exposure_score(100, "2026-04-09 12:00:00")
        # 曝光度 = (100 * 100) / (1 + 1) = 5000
        assert result == 5000.0


def test_calculate_exposure_score_zero_want():
    """想要人数为 0"""
    result = calculate_exposure_score(0, "2026-04-09 00:00:00")
    assert result == 0.0


def test_calculate_exposure_score_no_publish_time():
    """无发布时间"""
    result = calculate_exposure_score(100, None)
    assert result == 0.0


def test_calculate_exposure_score_future_time():
    """发布时间在未来"""
    with patch("src.search_api.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 4, 10, 12, 0, 0)
        mock_dt.strptime = datetime.strptime

        result = calculate_exposure_score(100, "2026-04-11 12:00:00")
        assert result == 0.0


def test_calculate_exposure_score_just_published():
    """刚发布（0天）"""
    with patch("src.search_api.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 4, 10, 12, 0, 0)
        mock_dt.strptime = datetime.strptime

        result = calculate_exposure_score(100, "2026-04-10 12:00:00")
        # 曝光度 = (100 * 100) / (0 + 1) = 10000
        assert result == 10000.0