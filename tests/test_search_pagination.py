import pytest

from src.core import SearchItem, SearchParams, SearchOutcome


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


# Note: Tests for _BrowserSearchImpl, _build_page_api_runner, and PageApiSearchError
# have been removed as those classes/functions were deleted in the cleanup.
# The search functionality is now handled by HttpApiSearchClient with StableSearchRunner.
# See tests/test_search_api.py for StableSearchRunner tests.