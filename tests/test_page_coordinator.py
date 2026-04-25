import asyncio

import pytest

from src.page_coordinator import PageCoordinator


class FakePage:
    def __init__(self, name: str, url: str = "https://www.goofish.com"):
        self.name = name
        self.url = url
        self.closed = False
        self.close_calls = 0
        self.fail_close = False
        self.fail_is_closed = False

    async def close(self):
        self.close_calls += 1
        if self.fail_close:
            raise RuntimeError(f"close failed: {self.name}")
        self.closed = True

    def is_closed(self):
        if self.fail_is_closed:
            raise RuntimeError(f"is_closed failed: {self.name}")
        return self.closed


class FakeContext:
    def __init__(self):
        self.pages = []
        self.new_page_calls = 0

    async def new_page(self):
        self.new_page_calls += 1
        page = FakePage(f"page-{self.new_page_calls}")
        self.pages.append(page)
        return page


class FakeBrowser:
    def __init__(self):
        self.context = FakeContext()
        self.ensure_running_calls = 0

    async def ensure_running(self):
        self.ensure_running_calls += 1
        return True


class LazyContextBrowser:
    def __init__(self):
        self.context = None
        self.ensure_running_calls = 0
        self.startup_blank_page = FakePage("startup-blank", url="about:blank")

    async def ensure_running(self):
        self.ensure_running_calls += 1
        if self.context is None:
            self.context = FakeContext()
            self.context.pages.append(self.startup_blank_page)
        return True


@pytest.mark.asyncio
async def test_task_page_lease_closes_page_on_success():
    coordinator = PageCoordinator(FakeBrowser())

    lease = await coordinator.lease_task_page()
    page = lease.page

    async with lease:
        assert page in coordinator.browser.context.pages

    assert page.closed is True
    assert coordinator.browser.context.new_page_calls == 1


@pytest.mark.asyncio
async def test_task_page_lease_closes_page_on_exception():
    coordinator = PageCoordinator(FakeBrowser())
    lease = await coordinator.lease_task_page()
    page = lease.page

    with pytest.raises(RuntimeError, match="boom"):
        async with lease:
            raise RuntimeError("boom")

    assert page.closed is True


@pytest.mark.asyncio
async def test_session_page_reused_until_explicitly_closed():
    coordinator = PageCoordinator(FakeBrowser())

    first = await coordinator.lease_session_page()
    second = await coordinator.lease_session_page()

    assert first.page is second.page

    await first.release()
    await second.release()
    await coordinator.close_session_page()

    third = await coordinator.lease_session_page()

    assert third.page is not first.page


@pytest.mark.asyncio
async def test_keepalive_page_reused():
    coordinator = PageCoordinator(FakeBrowser())

    first = await coordinator.get_keepalive_page()
    second = await coordinator.get_keepalive_page()

    assert first is second


@pytest.mark.asyncio
async def test_second_task_page_waits_for_first_to_release():
    coordinator = PageCoordinator(FakeBrowser())
    events = []

    async def first_task():
        lease = await coordinator.lease_task_page()
        async with lease:
            events.append("first-start")
            await asyncio.sleep(0.05)
            events.append("first-end")

    async def second_task():
        await asyncio.sleep(0.01)
        lease = await coordinator.lease_task_page()
        async with lease:
            events.append("second-start")

    await asyncio.gather(first_task(), second_task())

    assert events == ["first-start", "first-end", "second-start"]


@pytest.mark.asyncio
async def test_task_release_cleans_about_blank_pages():
    browser = FakeBrowser()
    coordinator = PageCoordinator(browser)
    blank_page = FakePage("blank", url="about:blank")
    real_page = FakePage("real", url="https://www.goofish.com/item?id=123")
    browser.context.pages.extend([blank_page, real_page])

    lease = await coordinator.lease_task_page()
    async with lease:
        pass

    assert lease.page.closed is True
    assert blank_page.closed is True
    assert real_page.closed is False


@pytest.mark.asyncio
async def test_task_release_cleans_empty_url_pages():
    browser = FakeBrowser()
    coordinator = PageCoordinator(browser)
    empty_url_page = FakePage("empty", url="")
    browser.context.pages.append(empty_url_page)

    lease = await coordinator.lease_task_page()
    async with lease:
        pass

    assert lease.page.closed is True
    assert empty_url_page.closed is True


@pytest.mark.asyncio
async def test_cleanup_failure_does_not_block_next_task_page():
    browser = FakeBrowser()
    coordinator = PageCoordinator(browser)
    broken_blank_page = FakePage("broken", url="about:blank")
    broken_blank_page.fail_close = True
    browser.context.pages.append(broken_blank_page)

    first = await coordinator.lease_task_page()
    async with first:
        pass

    second = await asyncio.wait_for(coordinator.lease_task_page(), timeout=0.1)
    async with second:
        pass

    assert first.page.closed is True
    assert second.page.closed is True
    assert broken_blank_page.close_calls >= 1


@pytest.mark.asyncio
async def test_task_release_cleans_blank_pages_loaded_when_browser_starts():
    browser = LazyContextBrowser()
    coordinator = PageCoordinator(browser)

    lease = await coordinator.lease_task_page()
    async with lease:
        pass

    assert lease.page.closed is True
    assert browser.startup_blank_page.closed is True


@pytest.mark.asyncio
async def test_cleanup_check_failure_does_not_block_next_task_page():
    browser = FakeBrowser()
    coordinator = PageCoordinator(browser)
    broken_page = FakePage("broken", url="about:blank")
    broken_page.fail_is_closed = True
    browser.context.pages.append(broken_page)

    first = await coordinator.lease_task_page()
    async with first:
        pass

    second = await asyncio.wait_for(coordinator.lease_task_page(), timeout=0.1)
    async with second:
        pass

    assert first.page.closed is True
    assert second.page.closed is True


@pytest.mark.asyncio
async def test_task_page_check_failure_still_cleans_candidates_and_releases_lock():
    browser = FakeBrowser()
    coordinator = PageCoordinator(browser)
    blank_page = FakePage("blank", url="about:blank")
    browser.context.pages.append(blank_page)

    first = await coordinator.lease_task_page()
    first.page.fail_is_closed = True
    async with first:
        pass

    second = await asyncio.wait_for(coordinator.lease_task_page(), timeout=0.1)
    async with second:
        pass

    assert first.page.closed is False
    assert blank_page.closed is True
    assert second.page.closed is True


@pytest.mark.asyncio
async def test_cleanup_closes_registered_blank_browser_page_and_clears_reference():
    browser = FakeBrowser()
    coordinator = PageCoordinator(browser)
    protected_page = FakePage("browser-page", url="about:blank")
    browser.page = protected_page
    browser._work_page = protected_page
    browser.context.pages.append(protected_page)

    lease = await coordinator.lease_task_page()
    async with lease:
        pass

    assert lease.page.closed is True
    assert protected_page.closed is True
    assert browser.page is None
    assert browser._work_page is None


@pytest.mark.asyncio
async def test_task_cleanup_keeps_active_session_blank_page():
    browser = FakeBrowser()
    coordinator = PageCoordinator(browser)

    session_lease = await coordinator.lease_session_page()
    session_lease.page.url = "about:blank"

    task_lease = await coordinator.lease_task_page()
    async with task_lease:
        pass

    assert task_lease.page.closed is True
    assert session_lease.page.closed is False
    assert coordinator._session_page is session_lease.page

    await session_lease.release()
