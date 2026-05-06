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
        price={"current_price": 129.0},
    )
    assert result["success"] is True
    assert result["selected_price"] == 129.0
    assert result["logs"][0]["step"] == "select_source_adapter"
    assert result["logs"][-1]["step"] == "publish_item"
