from dataclasses import dataclass, field
from typing import Any


@dataclass
class NormalizedSourceItem:
    source_platform: str
    source_item_url: str
    source_item_id: str
    title: str
    description: str
    images: list[str]
    price: float
    sku_prices: list[float] = field(default_factory=list)
    raw_detail: dict[str, Any] = field(default_factory=dict)
