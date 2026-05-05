import pytest

from src.api.http_keepalive import HttpKeepaliveService


class FakeHttpClient:
    def __init__(self, should_fail=False):
        self.should_fail = should_fail
        self.calls = 0

    async def check_session(self):
        self.calls += 1
        if self.should_fail:
            raise RuntimeError("FAIL_SYS_USER_VALIDATE")
        return {"valid": True, "message": "Cookie 有效"}


class FakeBrowserBridge:
    def __init__(self, success=True):
        self.success = success
        self.calls = 0

    async def get_access_token_via_browser(self, device_id, cookies=None):
        self.calls += 1
        return "oauth_k1:test" if self.success else ""


@pytest.mark.asyncio
async def test_keepalive_marks_success_after_http_ping():
    service = HttpKeepaliveService(
        http_client=FakeHttpClient(),
        browser_bridge=FakeBrowserBridge(success=True),
        interval_minutes=240,
        max_captcha_retries=3,
    )

    await service.run_once()

    assert service.last_error is None
    assert service.last_success_at is not None
    assert service.running is True


@pytest.mark.asyncio
async def test_keepalive_stops_after_http_failure_without_browser_recovery():
    bridge = FakeBrowserBridge(success=False)
    service = HttpKeepaliveService(
        http_client=FakeHttpClient(should_fail=True),
        browser_bridge=bridge,
        interval_minutes=240,
        max_captcha_retries=3,
    )

    await service.run_once()

    assert bridge.calls == 0
    assert service.running is False
    assert service.last_error == "FAIL_SYS_USER_VALIDATE"
