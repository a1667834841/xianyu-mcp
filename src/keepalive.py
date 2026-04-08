"""
keepalive.py - Background cookie keepalive service.

This service keeps the Goofish session warm by periodically refreshing a
dedicated keepalive tab and persisting the latest cookie string.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional


logger = logging.getLogger(__name__)


class CookieKeepaliveService:
    def __init__(self, browser: Any, session: Any, interval_minutes: int):
        self.browser = browser
        self.session = session
        self.interval_minutes = interval_minutes

        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
        self._initialized = False

    def start(self) -> None:
        if self._task and not self._task.done():
            return

        self._stop_event = asyncio.Event()
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # Start must never crash callers; the next async entrypoint can start it again.
            logger.warning(
                "CookieKeepaliveService.start called without a running event loop; skipped."
            )
            return

        self._task = loop.create_task(self._run_loop())

    async def stop(self) -> None:
        self._stop_event.set()

        task = self._task
        self._task = None
        if not task:
            return

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("CookieKeepaliveService loop failed during shutdown.")

    async def run_once(self) -> None:
        try:
            if not await self.browser.ensure_running():
                return

            page = await self.browser.get_keepalive_page()

            if not self._initialized:
                await page.goto("https://www.goofish.com")
                self._initialized = True
            else:
                await page.reload()

            full_cookie = await self.browser.get_full_cookie_string()
            if full_cookie:
                self.session.save_cookie(full_cookie)
        except Exception:
            # Keepalive must never crash the app.
            logger.exception("CookieKeepaliveService.run_once failed.")

    async def _run_loop(self) -> None:
        interval_seconds = max(1, int(self.interval_minutes)) * 60

        while not self._stop_event.is_set():
            await self.run_once()

            try:
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=interval_seconds
                )
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("CookieKeepaliveService sleep loop failed.")
