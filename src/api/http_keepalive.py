from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Optional


logger = logging.getLogger(__name__)


class HttpKeepaliveService:
    def __init__(
        self,
        http_client,
        browser_bridge,
        interval_minutes: int,
        max_captcha_retries: int = 3,
    ):
        self.http_client = http_client
        self.browser_bridge = browser_bridge
        self.interval_minutes = interval_minutes
        self.max_captcha_retries = max_captcha_retries
        self.last_success_at: Optional[str] = None
        self.last_error: Optional[str] = None
        self.running = True
        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()

    def start(self) -> None:
        if self._task and not self._task.done():
            return
        self.running = True
        self._stop_event = asyncio.Event()
        loop = asyncio.get_running_loop()
        self._task = loop.create_task(self._run_loop())

    async def stop(self) -> None:
        self.running = False
        self._stop_event.set()
        task = self._task
        self._task = None
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def run_once(self) -> None:
        try:
            await self.http_client.check_session()
            self.last_success_at = datetime.now().isoformat()
            self.last_error = None
            self.running = True
            return
        except Exception as exc:
            self.last_error = str(exc)
            self.running = False

    async def _run_loop(self) -> None:
        interval_seconds = max(1, int(self.interval_minutes)) * 60
        while not self._stop_event.is_set() and self.running:
            await self.run_once()
            if not self.running:
                return
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=interval_seconds)
            except asyncio.TimeoutError:
                continue
