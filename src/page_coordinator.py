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
        cleanup_candidates: Optional[tuple[Any, ...]] = None,
    ):
        self._coordinator = coordinator
        self.page = page
        self.kind = kind
        self.temporary = temporary
        self.cleanup_candidates = cleanup_candidates
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

    async def _ensure_context(self) -> Any:
        if not await self.browser.ensure_running():
            raise RuntimeError("[PageCoordinator] 浏览器未就绪")
        context = getattr(self.browser, "context", None)
        if context is None:
            raise RuntimeError("[PageCoordinator] 浏览器上下文未初始化")
        return context

    async def _new_page(self) -> Any:
        context = await self._ensure_context()
        return await context.new_page()

    def _is_blank_page(self, page: Any) -> bool:
        url = (getattr(page, "url", "") or "").strip().lower()
        return url == "" or url == "about:blank"

    def _coordinator_managed_pages(self) -> tuple[Any, ...]:
        return tuple(
            page
            for page in (self._keepalive_page, self._session_page)
            if page is not None
        )

    def _clear_page_references(self, page: Any) -> None:
        for attr in (
            "_work_page",
            "_keepalive_page",
            "_search_page",
            "_session_page",
            "_publish_page",
            "page",
        ):
            if getattr(self.browser, attr, None) is page:
                setattr(self.browser, attr, None)

    async def cleanup_pages(self, candidates: Optional[tuple[Any, ...]] = None) -> None:
        context = getattr(self.browser, "context", None)
        if context is None:
            return

        coordinator_pages = self._coordinator_managed_pages()
        pages = candidates if candidates is not None else getattr(context, "pages", [])
        for page in list(pages):
            try:
                if any(
                    page is coordinator_page for coordinator_page in coordinator_pages
                ):
                    continue
                if not self._page_alive(page):
                    continue
                if not self._is_blank_page(page):
                    continue
                await page.close()
                self._clear_page_references(page)
            except Exception as exc:
                print(f"[PageCoordinator] 清理空白页面失败：{exc}")

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
            context = await self._ensure_context()
            cleanup_candidates = tuple(getattr(context, "pages", []))
            page = await context.new_page()
        except Exception:
            self._task_page_lock.release()
            raise
        return PageLease(
            self,
            page,
            kind="task",
            temporary=True,
            cleanup_candidates=cleanup_candidates,
        )

    async def _release(self, lease: PageLease) -> None:
        if lease.kind != "task":
            return
        try:
            try:
                page_alive = self._page_alive(lease.page)
            except Exception as exc:
                page_alive = False
                print(f"[PageCoordinator] 检查任务页面失败：{exc}")
            if page_alive:
                try:
                    await lease.page.close()
                except Exception as exc:
                    print(f"[PageCoordinator] 关闭任务页面失败：{exc}")
            await self.cleanup_pages(candidates=lease.cleanup_candidates)
        finally:
            self._task_page_lock.release()
