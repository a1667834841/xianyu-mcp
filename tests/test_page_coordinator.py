import asyncio

import pytest

from src.page_coordinator import PageCoordinator


class FakePage:
    def __init__(self, name: str):
        self.name = name
        self.closed = False
        self.close_calls = 0

    async def close(self):
        self.closed = True
        self.close_calls += 1

    def is_closed(self):
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
