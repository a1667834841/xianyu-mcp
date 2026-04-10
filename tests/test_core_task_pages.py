import pytest

from src.core import SearchOutcome, XianyuApp
from src.settings import AppSettings, KeepaliveSettings, SearchSettings, StorageSettings


class FakePage:
    def __init__(self):
        self.closed = False

    async def close(self):
        self.closed = True

    def is_closed(self):
        return self.closed


class FakeLease:
    def __init__(self, page):
        self.page = page

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.page.close()


class FakeCoordinator:
    def __init__(self):
        self.pages = []

    async def lease_task_page(self):
        page = FakePage()
        self.pages.append(page)
        return FakeLease(page)


class FakeBrowser:
    def __init__(self, settings):
        self.settings = settings

    async def ensure_running(self):
        return True

    async def get_full_cookie_string(self):
        return "a=1; b=2"

    async def navigate(self, *_args, **_kwargs):
        return True


class FakeSession:
    def __init__(self):
        self.saved = []

    def load_cached_cookie(self):
        return "a=1; b=2"

    def save_cookie(self, value):
        self.saved.append(value)


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
async def test_publish_closes_task_page(tmp_path, monkeypatch):
    settings = make_settings(tmp_path)
    app = XianyuApp(browser=FakeBrowser(settings), settings=settings)
    coordinator = FakeCoordinator()
    app.page_coordinator = coordinator
    app.session = FakeSession()

    async def fake_publish(self, *_args, **_kwargs):
        return {"success": True}

    monkeypatch.setattr("src.core._ItemCopierImpl.publish_from_item", fake_publish)

    result = await app.publish("https://www.goofish.com/item?id=1")

    assert result == {"success": True}
    assert coordinator.pages[0].closed is True


@pytest.mark.asyncio
async def test_get_detail_closes_task_page(tmp_path, monkeypatch):
    settings = make_settings(tmp_path)
    app = XianyuApp(browser=FakeBrowser(settings), settings=settings)
    coordinator = FakeCoordinator()
    app.page_coordinator = coordinator
    app.session = FakeSession()

    async def fake_capture(self, *_args, **_kwargs):
        return {"item_id": "1"}

    monkeypatch.setattr("src.core._ItemCopierImpl.capture_item_detail", fake_capture)

    result = await app.get_detail("https://www.goofish.com/item?id=1")

    assert result == {"item_id": "1"}
    assert coordinator.pages[0].closed is True


@pytest.mark.asyncio
async def test_search_with_meta_closes_task_page(tmp_path, monkeypatch):
    settings = make_settings(tmp_path)
    app = XianyuApp(browser=FakeBrowser(settings), settings=settings)
    coordinator = FakeCoordinator()
    app.page_coordinator = coordinator
    app.session = FakeSession()

    class FakeClient:
        def __init__(self, get_cookie):
            self.get_cookie = get_cookie
            self.closed = False

        async def aclose(self):
            self.closed = True

    class FakeRunner:
        def __init__(self, client, max_stale_pages):
            self.client = client
            self.max_stale_pages = max_stale_pages

        async def search(self, params):
            return SearchOutcome(
                items=[],
                requested_rows=params.rows,
                returned_rows=0,
                stop_reason="target_reached",
                stale_pages=0,
                engine_used="http_api",
                fallback_reason=None,
                pages_fetched=1,
            )

    monkeypatch.setattr("src.core.HttpApiSearchClient", FakeClient)
    monkeypatch.setattr("src.search_api.StableSearchRunner", FakeRunner)

    outcome = await app.search_with_meta("键盘", rows=5)

    assert outcome.requested_rows == 5
    assert coordinator.pages[0].closed is True
