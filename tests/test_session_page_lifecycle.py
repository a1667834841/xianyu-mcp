from types import SimpleNamespace

import pytest

from src.session import SessionManager
from src.settings import AppSettings, KeepaliveSettings, SearchSettings, StorageSettings


class FakePage:
    def __init__(self):
        self.closed = False

    async def close(self):
        self.closed = True

    def is_closed(self):
        return self.closed


class FakeLease:
    def __init__(self, page, temporary):
        self.page = page
        self.temporary = temporary
        self.released = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self.released = True
        if self.temporary:
            await self.page.close()

    async def release(self):
        self.released = True


class FakeCoordinator:
    def __init__(self):
        self.task_pages = []
        self.session_page = FakePage()
        self.close_session_page_calls = 0

    async def lease_task_page(self):
        page = FakePage()
        self.task_pages.append(page)
        return FakeLease(page, temporary=True)

    async def lease_session_page(self):
        return FakeLease(self.session_page, temporary=False)

    async def close_session_page(self):
        self.close_session_page_calls += 1
        await self.session_page.close()


def make_settings(tmp_path):
    user_root = tmp_path / "users" / "default"
    return AppSettings(
        storage=StorageSettings(
            data_root=tmp_path / "users",
            user_id="default",
            token_file=user_root / "tokens" / "token.json",
            chrome_user_data_dir=user_root / "chrome-profile",
        ),
        keepalive=KeepaliveSettings(enabled=True, interval_minutes=10),
        search=SearchSettings(max_stale_pages=3),
    )


@pytest.mark.asyncio
async def test_refresh_token_uses_disposable_task_page(tmp_path, monkeypatch):
    coordinator = FakeCoordinator()
    browser = SimpleNamespace(
        ensure_running=lambda: True,
        navigate=lambda *args, **kwargs: True,
        get_xianyu_token=lambda: "token123",
        get_cookie=lambda *args, **kwargs: "token123_999",
        get_full_cookie_string=lambda: "a=1; b=2",
    )
    session = SessionManager(
        browser, settings=make_settings(tmp_path), page_coordinator=coordinator
    )

    async def ensure_running():
        return True

    async def navigate(*_args, **_kwargs):
        return True

    async def get_xianyu_token():
        return "token123"

    async def get_cookie(*_args, **_kwargs):
        return "token123_999"

    async def get_full_cookie_string():
        return "a=1; b=2"

    browser.ensure_running = ensure_running
    browser.navigate = navigate
    browser.get_xianyu_token = get_xianyu_token
    browser.get_cookie = get_cookie
    browser.get_full_cookie_string = get_full_cookie_string

    result = await session.refresh_token()

    assert result == {"token": "token123", "full_cookie": "token123_999"}
    assert coordinator.task_pages[0].closed is True


@pytest.mark.asyncio
async def test_successful_cookie_check_closes_lingering_session_page(
    tmp_path, monkeypatch
):
    coordinator = FakeCoordinator()
    settings = make_settings(tmp_path)

    class FakeBrowser:
        async def ensure_running(self):
            return True

        async def navigate(self, *_args, **_kwargs):
            return True

        async def get_full_cookie_string(self):
            return "cookie2=1; _m_h5_tk=token_999"

        async def get_cookie(self, *_args, **_kwargs):
            return "token_999"

    session = SessionManager(
        FakeBrowser(), settings=settings, page_coordinator=coordinator
    )

    class FakeResponse:
        def json(self):
            return {
                "ret": ["SUCCESS::调用成功"],
                "data": {"module": {"base": {"displayName": "tester"}}},
            }

    class FakeRequestsSession:
        def post(self, *_args, **_kwargs):
            return FakeResponse()

    monkeypatch.setattr("src.session.requests.Session", lambda: FakeRequestsSession())

    assert await session.check_cookie_valid() is True
    assert coordinator.task_pages[0].closed is True
    assert coordinator.close_session_page_calls == 1
