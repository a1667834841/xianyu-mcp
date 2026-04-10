from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable, List, Optional

from .core import SearchItem, SearchOutcome, SearchParams


class StableSearchRunner:
    """稳定搜索运行器 - 支持分页、去重、stale page 控制"""

    def __init__(self, client, max_stale_pages: int = 3):
        """
        Args:
            client: 搜索客户端（HttpApiSearchClient）
            max_stale_pages: 最大连续无新增页数
        """
        self.client = client
        self.max_stale_pages = max_stale_pages

    async def search(self, params: SearchParams) -> SearchOutcome:
        """执行搜索"""
        all_items = []
        seen_item_ids = set()
        stale_pages = 0
        page_number = 1

        engine_name = getattr(self.client, "engine_name", "http_api")

        while len(all_items) < params.rows:
            result = await self.client.fetch_page(params, page_number=page_number)
            items = result.items

            new_count = 0
            for item in items:
                if item.item_id not in seen_item_ids:
                    seen_item_ids.add(item.item_id)
                    all_items.append(item)
                    new_count += 1

            print(
                f"[{engine_name}] 第 {page_number} 页解析完成 "
                f"raw_items={len(items)} new_items={new_count} total_items={len(all_items)}",
                flush=True,
            )

            if len(all_items) >= params.rows:
                return SearchOutcome(
                    items=all_items[: params.rows],
                    requested_rows=params.rows,
                    returned_rows=min(len(all_items), params.rows),
                    stop_reason="target_reached",
                    stale_pages=stale_pages,
                    engine_used=engine_name,
                    fallback_reason=None,
                    pages_fetched=page_number,
                )

            stale_pages = stale_pages + 1 if new_count == 0 else 0
            if stale_pages >= self.max_stale_pages:
                return SearchOutcome(
                    items=all_items[: params.rows],
                    requested_rows=params.rows,
                    returned_rows=min(len(all_items), params.rows),
                    stop_reason="stale_limit",
                    stale_pages=stale_pages,
                    engine_used=engine_name,
                    fallback_reason=None,
                    pages_fetched=page_number,
                )

            page_number += 1

        return SearchOutcome(
            items=all_items[: params.rows],
            requested_rows=params.rows,
            returned_rows=len(all_items[: params.rows]),
            stop_reason="target_reached",
            stale_pages=stale_pages,
            engine_used=engine_name,
            fallback_reason=None,
            pages_fetched=page_number,
        )