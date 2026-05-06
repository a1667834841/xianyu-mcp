from typing import Protocol

from .types import NormalizedSourceItem


class SourceAdapter(Protocol):
    platform_name: str

    def supports(self, item_url: str) -> bool:
        ...

    async def parse_item(self, item_url: str) -> NormalizedSourceItem:
        ...
