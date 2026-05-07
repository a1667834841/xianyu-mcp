"""
core.py - 闲鱼数据类与类型定义
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


@dataclass
class SearchItem:
    item_id: str
    title: str
    price: str
    original_price: str
    want_cnt: int
    seller_nick: str
    seller_city: str
    image_urls: List[str]
    detail_url: str
    is_free_ship: bool
    publish_time: Optional[str] = None
    exposure_score: float = 0.0


@dataclass
class SearchParams:
    keyword: str
    rows: int = 30
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    free_ship: bool = False
    sort_field: str = ""
    sort_order: str = ""


@dataclass
class CopiedSku:
    sku_id: str
    price: float
    quantity: Optional[int]
    props: List[Dict[str, str]]
    image_url: Optional[str] = None


@dataclass
class CopiedItem:
    item_id: str
    title: str
    description: str
    category: str
    category_id: int
    brand: Optional[str]
    model: Optional[str]
    min_price: float
    max_price: float
    image_urls: List[str]
    seller_city: str
    is_free_ship: bool
    raw_data: Dict[str, Any]
    sku_list: List[CopiedSku] = field(default_factory=list)


@dataclass
class SearchOutcome:
    items: List[SearchItem]
    requested_rows: int
    returned_rows: int
    stop_reason: str
    stale_pages: int
    engine_used: str = "browser_fallback"
    fallback_reason: Optional[str] = None
    pages_fetched: int = 0
