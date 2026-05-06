import pytest
from unittest.mock import AsyncMock

from src.source_adapters.xianyu import XianyuSourceAdapter


class DummyDetailClient:
    def __init__(self, detail):
        self.get_detail = AsyncMock(return_value=detail)


class TestXianyuSourceAdapter:
    def test_supports_goofish_and_xianyu_urls(self):
        adapter = XianyuSourceAdapter(detail_client=DummyDetailClient({}))

        assert adapter.supports("https://www.goofish.com/item?id=1047155930582") is True
        assert adapter.supports("https://2.taobao.com/item.htm?id=1047155930582") is False

    @pytest.mark.asyncio
    async def test_parse_item_uses_lowest_sku_price_when_available(self):
        detail = {
            "item_id": "1047155930582",
            "title": "测试商品",
            "description": "测试描述",
            "images": ["https://img.example/1.jpg", "https://img.example/2.jpg"],
            "price": 199.0,
            "sku_prices": [129.0, 149.0, 139.0],
        }
        adapter = XianyuSourceAdapter(detail_client=DummyDetailClient(detail))

        item = await adapter.parse_item("https://www.goofish.com/item?id=1047155930582")

        assert item.source_platform == "xianyu"
        assert item.source_item_id == "1047155930582"
        assert item.title == "测试商品"
        assert item.description == "测试描述"
        assert item.images == ["https://img.example/1.jpg", "https://img.example/2.jpg"]
        assert item.price == 129.0
        assert item.sku_prices == [129.0, 149.0, 139.0]

    @pytest.mark.asyncio
    async def test_parse_item_falls_back_to_main_price_when_no_sku_prices(self):
        detail = {
            "item_id": "1047155930582",
            "title": "测试商品",
            "description": "测试描述",
            "images": ["https://img.example/1.jpg"],
            "price": 188.0,
            "sku_prices": [],
        }
        adapter = XianyuSourceAdapter(detail_client=DummyDetailClient(detail))

        item = await adapter.parse_item("https://www.goofish.com/item?id=1047155930582")

        assert item.price == 188.0
        assert item.sku_prices == []

    @pytest.mark.asyncio
    async def test_parse_item_raises_when_no_price_available(self):
        detail = {
            "item_id": "1047155930582",
            "title": "测试商品",
            "description": "测试描述",
            "images": ["https://img.example/1.jpg"],
            "price": None,
            "sku_prices": [],
        }
        adapter = XianyuSourceAdapter(detail_client=DummyDetailClient(detail))

        with pytest.raises(ValueError, match="商品价格缺失"):
            await adapter.parse_item("https://www.goofish.com/item?id=1047155930582")

    @pytest.mark.asyncio
    async def test_parse_item_raises_when_images_missing(self):
        detail = {
            "item_id": "1047155930582",
            "title": "测试商品",
            "description": "测试描述",
            "images": [],
            "price": 188.0,
            "sku_prices": [],
        }
        adapter = XianyuSourceAdapter(detail_client=DummyDetailClient(detail))

        with pytest.raises(ValueError, match="商品图片缺失"):
            await adapter.parse_item("https://www.goofish.com/item?id=1047155930582")

    @pytest.mark.asyncio
    async def test_parse_item_accepts_detail_url_images_field(self):
        detail = {
            "item_id": "1047155930582",
            "title": "测试商品",
            "description": "测试描述",
            "image_urls": ["https://img.example/1.jpg", "https://img.example/2.jpg"],
            "price": "188.5",
        }
        adapter = XianyuSourceAdapter(detail_client=DummyDetailClient(detail))

        item = await adapter.parse_item("https://www.goofish.com/item?id=1047155930582")

        assert item.images == ["https://img.example/1.jpg", "https://img.example/2.jpg"]
        assert item.price == 188.5

    @pytest.mark.asyncio
    async def test_parse_item_accepts_real_itemdo_detail_shape(self):
        detail = {
            "itemDO": {
                "itemId": 886153110498,
                "title": "真实商品标题",
                "desc": "真实商品描述",
                "soldPrice": "5.40",
                "imageInfos": [
                    {"url": "http://img.example/1.jpg"},
                    {"url": "http://img.example/2.jpg"},
                ],
            }
        }
        adapter = XianyuSourceAdapter(detail_client=DummyDetailClient(detail))

        item = await adapter.parse_item("https://www.goofish.com/item?id=886153110498")

        assert item.source_item_id == "886153110498"
        assert item.title == "真实商品标题"
        assert item.description == "真实商品描述"
        assert item.images == ["http://img.example/1.jpg", "http://img.example/2.jpg"]
        assert item.price == 5.4
