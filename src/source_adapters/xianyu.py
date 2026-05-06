from urllib.parse import parse_qs, urlparse

from .types import NormalizedSourceItem


class XianyuSourceAdapter:
    platform_name = "xianyu"

    def __init__(self, detail_client):
        self.detail_client = detail_client

    def supports(self, item_url: str) -> bool:
        hostname = urlparse(item_url).netloc.lower()
        return "goofish.com" in hostname or "xianyu.com" in hostname

    async def parse_item(self, item_url: str) -> NormalizedSourceItem:
        detail = await self.detail_client.get_detail(item_url=item_url)
        item_id = self._extract_item_id(item_url, detail)
        title = str(detail.get("title") or "").strip()
        description = str(detail.get("description") or "")
        images = list(detail.get("images") or detail.get("image_urls") or [])
        sku_prices = [self._coerce_price(price) for price in (detail.get("sku_prices") or [])]
        sku_prices = [price for price in sku_prices if price is not None]
        main_price = self._coerce_price(detail.get("price"))

        if not title:
            raise ValueError("商品标题缺失")
        if not images:
            raise ValueError("商品图片缺失")

        selected_price = min(sku_prices) if sku_prices else main_price
        if selected_price is None:
            raise ValueError("商品价格缺失")

        return NormalizedSourceItem(
            source_platform="xianyu",
            source_item_url=item_url,
            source_item_id=item_id,
            title=title,
            description=description,
            images=images,
            price=selected_price,
            sku_prices=sku_prices,
            raw_detail=dict(detail),
        )

    def _extract_item_id(self, item_url: str, detail: dict) -> str:
        query = parse_qs(urlparse(item_url).query)
        item_id = query.get("id", [""])[0] or str(detail.get("item_id") or "")
        if not item_id:
            raise ValueError("无法从商品链接提取 item_id")
        return item_id

    @staticmethod
    def _coerce_price(value):
        if value in (None, ""):
            return None
        return float(value)
