import pytest
from unittest.mock import AsyncMock

from src.sourcing_service import SourcingService
from src.source_adapters.types import NormalizedSourceItem


class StubAdapter:
    platform_name = "xianyu"

    def supports(self, item_url: str) -> bool:
        return True

    async def parse_item(self, item_url: str) -> NormalizedSourceItem:
        return NormalizedSourceItem(
            source_platform="xianyu",
            source_item_url=item_url,
            source_item_id="1047155930582",
            title="测试商品",
            description="测试描述",
            images=["https://img.example/1.jpg"],
            price=129.0,
            sku_prices=[129.0, 149.0],
            raw_detail={"title": "测试商品"},
        )


@pytest.mark.asyncio
async def test_sourcing_service_publishes_with_selected_price():
    publish_client = AsyncMock()
    publish_client.publish.return_value = {
        "success": True,
        "item_id": "new-item-1",
        "item_url": "https://www.goofish.com/item?id=new-item-1",
        "message": "发布成功",
        "method": "http",
    }
    service = SourcingService(publish_client=publish_client, adapters=[StubAdapter()])

    result = await service.publish_from_item_url("https://www.goofish.com/item?id=1047155930582")

    publish_client.publish.assert_awaited_once_with(
        images_paths=["https://img.example/1.jpg"],
        title="测试商品",
        description="测试描述",
        price={"current_price": 129.0},
    )
    assert result["success"] is True
    assert result["selected_price"] == 129.0
    assert result["logs"][0]["step"] == "select_source_adapter"
    assert result["logs"][-1]["step"] == "publish_item"


@pytest.mark.asyncio
async def test_sourcing_service_publishes_with_real_itemdo_detail_shape():
    publish_client = AsyncMock()
    publish_client.get_detail.return_value = {
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
    publish_client.publish.return_value = {
        "success": True,
        "item_id": "new-item-2",
        "item_url": "https://www.goofish.com/item?id=new-item-2",
        "message": "发布成功",
        "method": "http",
    }

    service = SourcingService(publish_client=publish_client)

    result = await service.publish_from_item_url("https://www.goofish.com/item?id=886153110498")

    publish_client.get_detail.assert_awaited_once_with(
        item_url="https://www.goofish.com/item?id=886153110498"
    )
    publish_client.publish.assert_awaited_once_with(
        images_paths=["http://img.example/1.jpg", "http://img.example/2.jpg"],
        title="真实商品标题",
        description="真实商品描述",
        price={"current_price": 5.4},
    )
    assert result["success"] is True
    assert result["selected_price"] == 5.4
    assert result["parsed_item"]["title"] == "真实商品标题"
    assert result["parsed_item"]["description"] == "真实商品描述"
    assert result["parsed_item"]["images_count"] == 2
    assert result["logs"][1]["step"] == "parse_item"
    assert result["logs"][1]["details"]["price_source"] == "item_price"
