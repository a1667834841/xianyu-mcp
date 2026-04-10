from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Awaitable, Callable, List, Optional

from .core import SearchItem, SearchOutcome, SearchParams


def calculate_exposure_score(want_cnt: int, publish_time_str: Optional[str]) -> float:
    """
    计算曝光度分数

    公式: 曝光度 = (想要人数 × 100) / (天数差 + 1)
    天数差 = (当前时间 - 发布时间) / 24小时

    Args:
        want_cnt: 想要人数
        publish_time_str: 发布时间字符串（格式：%Y-%m-%d %H:%M:%S）

    Returns:
        曝光度分数，保留两位小数
    """
    if want_cnt <= 0 or not publish_time_str:
        return 0.0

    try:
        publish_dt = datetime.strptime(publish_time_str, "%Y-%m-%d %H:%M:%S")
        now = datetime.now()
        if publish_dt > now:
            return 0.0
        hours_diff = (now - publish_dt).total_seconds() / 3600
        days_diff = max(0, hours_diff / 24)
        exposure_score = (want_cnt * 100) / (days_diff + 1)
        return round(exposure_score, 2)
    except (ValueError, TypeError):
        return 0.0


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
                    # 计算曝光度
                    item.exposure_score = calculate_exposure_score(item.want_cnt, item.publish_time)
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