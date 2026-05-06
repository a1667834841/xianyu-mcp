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
        item_do = self._extract_item_do(detail)

        title = str(detail.get("title") or item_do.get("title") or "").strip()
        description = str(detail.get("description") or item_do.get("desc") or "")
        images = self._extract_images(detail, item_do)
        sku_prices = [self._coerce_price(price) for price in (detail.get("sku_prices") or [])]
        if not sku_prices:
            sku_prices = self._extract_sku_prices(item_do)
        sku_prices = [price for price in sku_prices if price is not None]
        main_price = self._coerce_price(
            detail.get("price") or item_do.get("soldPrice") or item_do.get("minPrice")
        )

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

    @staticmethod
    def _extract_item_do(detail: dict) -> dict:
        item_do = detail.get("itemDO")
        if isinstance(item_do, dict) and item_do:
            return item_do
        return detail

    @staticmethod
    def _extract_images(detail: dict, item_do: dict) -> list[str]:
        direct_images = detail.get("images") or detail.get("image_urls") or []
        if direct_images:
            return list(direct_images)

        image_infos = item_do.get("imageInfos") or []
        return [img.get("url", "") for img in image_infos if isinstance(img, dict) and img.get("url")]

    @classmethod
    def _extract_sku_prices(cls, item_do: dict) -> list[float]:
        raw_skus = item_do.get("skuList") or []
        prices = []
        for sku in raw_skus:
            if not isinstance(sku, dict):
                continue
            raw_price = sku.get("price")
            if raw_price is None and sku.get("priceInCent") not in (None, ""):
                try:
                    raw_price = round(float(sku.get("priceInCent")) / 100, 2)
                except (TypeError, ValueError):
                    raw_price = None
            price = cls._coerce_price(raw_price)
            if price is not None:
                prices.append(price)
        return prices

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
