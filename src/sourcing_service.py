import logging
from typing import Any

from src.source_adapters.xianyu import XianyuSourceAdapter

logger = logging.getLogger(__name__)


class SourcingService:
    def __init__(self, publish_client, adapters=None):
        self.publish_client = publish_client
        self.adapters = adapters or [XianyuSourceAdapter(detail_client=publish_client)]

    async def publish_from_item_url(self, item_url: str) -> dict[str, Any]:
        logs: list[dict[str, Any]] = []
        source_platform = "unknown"

        try:
            adapter = self._select_source_adapter(item_url)
            source_platform = adapter.platform_name
            logs.append(self._log_entry("select_source_adapter", "success", "已选择闲鱼适配器", {"platform": source_platform}))

            item = await adapter.parse_item(item_url)
            logs.append(
                self._log_entry(
                    "parse_item",
                    "success",
                    "商品解析成功",
                    {
                        "source_item_id": item.source_item_id,
                        "images_count": len(item.images),
                        "sku_count": len(item.sku_prices),
                        "selected_price": item.price,
                        "price_source": "sku_min_price" if item.sku_prices else "item_price",
                    },
                )
            )

            publish_result = await self.publish_client.publish(
                images_paths=item.images,
                title=item.title,
                price={"current_price": item.price},
            )
            if not publish_result.get("success"):
                raise RuntimeError(publish_result.get("message", "发布失败"))

            logs.append(
                self._log_entry(
                    "publish_item",
                    "success",
                    "发布成功",
                    {"item_id": publish_result.get("item_id", "")},
                )
            )
            return {
                "success": True,
                "source_platform": item.source_platform,
                "source_item_url": item.source_item_url,
                "published_item_id": publish_result.get("item_id", ""),
                "published_item_url": publish_result.get("item_url", ""),
                "selected_price": item.price,
                "parsed_item": {
                    "title": item.title,
                    "description": item.description,
                    "images_count": len(item.images),
                    "sku_prices": item.sku_prices,
                },
                "logs": logs,
            }
        except Exception as exc:
            failed_step = self._failed_step_from_logs(logs)
            logs.append(
                self._log_entry(
                    failed_step,
                    "failed",
                    str(exc),
                    {"reason": str(exc)},
                )
            )
            return {
                "success": False,
                "source_platform": source_platform,
                "source_item_url": item_url,
                "failed_step": failed_step,
                "message": str(exc),
                "logs": logs,
            }

    def _select_source_adapter(self, item_url: str):
        for adapter in self.adapters:
            if adapter.supports(item_url):
                return adapter
        raise ValueError("不支持的来源平台")

    def _failed_step_from_logs(self, logs: list[dict[str, Any]]) -> str:
        if not logs:
            return "select_source_adapter"
        last_step = logs[-1]["step"]
        if last_step == "select_source_adapter":
            return "parse_item"
        if last_step == "parse_item":
            return "publish_item"
        return last_step

    def _log_entry(self, step: str, status: str, message: str, details: dict[str, Any]) -> dict[str, Any]:
        entry = {
            "step": step,
            "status": status,
            "message": message,
            "details": details,
        }
        log_method = logger.error if status == "failed" else logger.info
        log_method("[sourcing] %s %s %s %s", step, status, message, details)
        return entry
