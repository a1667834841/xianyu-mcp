from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any

import aiohttp

from src.settings import HookSettings

logger = logging.getLogger(__name__)
SHANGHAI_TZ = timezone(timedelta(hours=8))


class HookNotifier:
    def __init__(self, settings: HookSettings):
        self.settings = settings

    def is_enabled(self) -> bool:
        return bool(self.settings.url_template.strip())

    def is_event_enabled(self, event_name: str) -> bool:
        return self.is_enabled() and event_name in self.settings.enabled_events

    def build_url(self, user_id: str) -> str:
        return self.settings.url_template.replace("{user_id}", user_id)

    def build_payload(self, event_name: str, user_id: str, event: dict[str, Any]) -> dict[str, Any]:
        return {
            "event": event_name,
            "user_id": user_id,
            "occurred_at": datetime.now(SHANGHAI_TZ).isoformat(),
            "data": {
                "conversation_id": event.get("cid", ""),
                "sender_id": event.get("sender_id", ""),
                "sender_name": event.get("sender_name", ""),
                "timestamp": event.get("timestamp", 0),
                "segments": event.get("segments", []),
            },
        }

    async def notify(self, *, event_name: str, user_id: str, event: dict[str, Any]) -> None:
        if not self.is_event_enabled(event_name):
            return

        payload = self.build_payload(event_name, user_id, event)
        url = self.build_url(user_id)

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=self.settings.timeout_seconds) as response:
                if response.status < 200 or response.status >= 300:
                    body = await response.text()
                    logger.warning(
                        "Hook notify failed: event=%s user_id=%s conversation_id=%s url=%s status=%s body=%s",
                        event_name,
                        user_id,
                        payload["data"]["conversation_id"],
                        url,
                        response.status,
                        body[:200],
                    )
                    return

                logger.info(
                    "Hook notify succeeded: event=%s user_id=%s conversation_id=%s url=%s status=%s",
                    event_name,
                    user_id,
                    payload["data"]["conversation_id"],
                    url,
                    response.status,
                )
