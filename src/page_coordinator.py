from __future__ import annotations

import asyncio
from typing import Any, Optional


class PageLease:
    def __init__(
        self,
        coordinator: "PageCoordinator",
        page: Any,
        *,
        kind: str,
        temporary: bool,
    ):
        self._coordinator = coordinator
        self.page = page
        self.kind = kind
        self.temporary = temporary
        self._released = False

    async def __aenter__(self) -> "PageLease":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.release()

    async def release(self) -> None:
        if self._released:
            return
        self._released = True
        await self._coordinator._release(self)


class PageCoordinator:
    def __init__(self, browser: Any):
        self.browser = browser
        self._keepalive_page: Optional[Any] = None
        self._session_page: Optional[Any] = None
        self._session_page_lock = asyncio.Lock()
        self._task_page_lock = asyncio.Lock()

    def _page_alive(self, page: Any) -> bool:
        context = getattr(self.browser, "context", None)
        if page is None or context is None:
            return False
        if page not in context.pages:
            return False
        is_closed = getattr(page, "is_closed", None)
        if callable(is_closed) and is_closed():
            return False
        return True

    async def _new_page(self) -> Any:
        if not await self.browser.ensure_running():
            raise RuntimeError("[PageCoordinator] 浏览器未就绪")
        context = getattr(self.browser, "context", None)
        if context is None:
            raise RuntimeError("[PageCoordinator] 浏览器上下文未初始化")
        return await context.new_page()

    async def get_keepalive_page(self) -> Any:
        if self._page_alive(self._keepalive_page):
            return self._keepalive_page
        self._keepalive_page = await self._new_page()
        return self._keepalive_page

    async def lease_session_page(self) -> PageLease:
        async with self._session_page_lock:
            if not self._page_alive(self._session_page):
                self._session_page = await self._new_page()
            return PageLease(self, self._session_page, kind="session", temporary=False)

    async def close_session_page(self) -> None:
        async with self._session_page_lock:
            page = self._session_page
            self._session_page = None
        if self._page_alive(page):
            await page.close()

    async def lease_task_page(self) -> PageLease:
        await self._task_page_lock.acquire()
        try:
            page = await self._new_page()
        except Exception:
            self._task_page_lock.release()
            raise
        return PageLease(self, page, kind="task", temporary=True)

    async def _release(self, lease: PageLease) -> None:
        if lease.kind != "task":
            return
        try:
            if self._page_alive(lease.page):
                await lease.page.close()
        finally:
            self._task_page_lock.release()
