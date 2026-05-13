from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Callable

from src.api.client import XianyuApiClient

logger = logging.getLogger(__name__)

SHANGHAI_TZ = timezone(timedelta(hours=8))


class ClientManager:
    def __init__(
        self,
        user_manager: Any,
        data_root: Path,
        client_factory: Callable | None = None,
    ):
        self._user_manager = user_manager
        self._data_root = Path(data_root)
        self._client_factory = client_factory or XianyuApiClient
        self._clients: dict[str, XianyuApiClient] = {}
        self._keepalive_tasks: dict[str, asyncio.Task] = {}

    def get_client(self, user_id: str) -> XianyuApiClient:
        if user_id not in self._clients:
            self._clients[user_id] = self._client_factory(
                user_id=user_id,
                data_root=self._data_root,
            )
        return self._clients[user_id]

    def has_client(self, user_id: str) -> bool:
        return user_id in self._clients

    def has_keepalive_task(self, user_id: str) -> bool:
        task = self._keepalive_tasks.get(user_id)
        if task is None:
            return False
        return not task.done()

    async def run_keepalive_once(self, user_id: str) -> None:
        client = self.get_client(user_id)
        now = datetime.now(SHANGHAI_TZ).strftime("%Y-%m-%d %H:%M:%S")
        try:
            session = await client.check_session()
            if session.get("valid"):
                await client.refresh_token()
                self._user_manager.update_user(
                    user_id,
                    status="active",
                    last_keepalive_at=now,
                )
            else:
                self._user_manager.update_user(
                    user_id,
                    status="expired",
                    last_keepalive_at=now,
                )
        except Exception:
            logger.exception("Keepalive failed for user '%s'", user_id)
            self._user_manager.update_user(
                user_id,
                status="error",
                last_keepalive_at=now,
            )

    async def start_keepalive(self, user_id: str, interval_minutes: int) -> None:
        old_task = self._keepalive_tasks.get(user_id)
        if old_task is not None and not old_task.done():
            old_task.cancel()
            try:
                await old_task
            except asyncio.CancelledError:
                pass

        async def _loop():
            while True:
                await self.run_keepalive_once(user_id)
                await asyncio.sleep(interval_minutes * 60)

        task = asyncio.create_task(_loop())
        self._keepalive_tasks[user_id] = task

    async def stop_user(self, user_id: str) -> None:
        task = self._keepalive_tasks.pop(user_id, None)
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        client = self._clients.get(user_id)
        if client is not None:
            await client.stop_ws_listener()

    async def shutdown(self) -> None:
        for user_id in list(self._keepalive_tasks.keys()):
            await self.stop_user(user_id)
