import pytest

from src.browser_debugger import BrowserDebugger


class FakeBrowser:
    async def pick_debug_page(self):
        return "session", self.page

    async def get_page_snapshot_metadata(self, page):
        return {"url": page.url, "title": "闲鱼"}

    async def capture_page_screenshot(self, page, full_page=True):
        return b"png-bytes"


class FakePage:
    url = "https://www.goofish.com/session"


@pytest.mark.asyncio
async def test_browser_debugger_returns_snapshot_payload(monkeypatch):
    browser = FakeBrowser()
    browser.page = FakePage()
    debugger = BrowserDebugger(browser)

    monkeypatch.setattr(
        "src.browser_debugger.upload_image_bytes",
        lambda **kwargs: "https://img.example.com/xianyu/debug/debug-user-001.png",
    )

    payload = await debugger.capture_snapshot(
        user_id="user-001",
        slot_id="slot-1",
        selected_by="explicit",
        full_page=True,
    )

    assert payload["success"] is True
    assert payload["page"]["kind"] == "session"
    assert payload["screenshot"]["uploaded"] is True
    assert payload["screenshot"]["public_url"].startswith("https://img.example.com/")


@pytest.mark.asyncio
async def test_browser_debugger_raises_when_r2_upload_returns_none(monkeypatch):
    browser = FakeBrowser()
    browser.page = FakePage()
    debugger = BrowserDebugger(browser)

    monkeypatch.setattr(
        "src.browser_debugger.upload_image_bytes", lambda **kwargs: None
    )

    with pytest.raises(RuntimeError, match="r2_upload_failed"):
        await debugger.capture_snapshot(
            user_id="user-001",
            slot_id="slot-1",
            selected_by="explicit",
            full_page=True,
        )
