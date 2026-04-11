# Task Page Lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace long-lived business role pages with one-shot task pages while keeping only the QR login page and keepalive page alive across calls.

**Architecture:** Introduce a thin `PageCoordinator / PageLease` layer that owns three page lifecycles: reusable `keepalive_page`, reusable-in-login `session_page`, and disposable `task_page`. `XianyuApp`, `SessionManager`, and `CookieKeepaliveService` stop calling scattered page getters directly and instead request the right lease from the coordinator, which also enforces a single in-flight task page.

**Tech Stack:** Python 3.10+, Playwright over CDP, asyncio, pytest

---

## File Map

- Create: `src/page_coordinator.py`
  - Own `PageCoordinator` and `PageLease`
  - Keep disposable task pages and long-lived login/keepalive pages in one place
- Modify: `src/core.py`
  - Construct one coordinator per `XianyuApp`
  - Route `search` / `publish` / `get_detail` through `lease_task_page()`
- Modify: `src/session.py`
  - Route `login` / `show_qr_code` through `lease_session_page()`
  - Route `check_cookie_valid` / `refresh_token` through `lease_task_page()`
  - Close lingering `session_page` after a successful login check or terminal login failure
- Modify: `src/keepalive.py`
  - Use the coordinator’s keepalive page getter instead of grabbing browser tabs directly
- Modify: `src/__init__.py`
  - Export `PageCoordinator` and `PageLease`
- Create: `tests/test_page_coordinator.py`
  - Unit-test lease semantics, auto-close behavior, keepalive reuse, session-page reuse, and single task-page concurrency
- Modify: `tests/test_keepalive.py`
  - Verify keepalive uses the coordinator and `XianyuApp` wires one coordinator into keepalive/session
- Create: `tests/test_session_page_lifecycle.py`
  - Verify short session tasks use disposable task pages and that successful session validation closes a lingering QR page
- Create: `tests/test_core_task_pages.py`
  - Verify `search`, `publish`, and `get_detail` all acquire disposable task pages and close them after success or failure

### Task 1: Add `PageCoordinator` and `PageLease`

**Files:**
- Create: `src/page_coordinator.py`
- Create: `tests/test_page_coordinator.py`
- Modify: `src/__init__.py`

- [ ] **Step 1: Write the failing coordinator tests**

Add `tests/test_page_coordinator.py` with these tests:

```python
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
```

- [ ] **Step 2: Run the new tests and verify they fail**

Run:

```bash
pytest tests/test_page_coordinator.py -v
```

Expected:
- `ERROR` because `src.page_coordinator` does not exist yet

- [ ] **Step 3: Implement the minimal coordinator and export it**

Create `src/page_coordinator.py` with:

```python
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
```

Update `src/__init__.py` imports and exports:

```python
from .page_coordinator import PageCoordinator, PageLease

__all__ = [
    "AsyncChromeManager",
    "ChromeManager",
    "SessionManager",
    "CookieKeepaliveService",
    "PageCoordinator",
    "PageLease",
    "XianyuApp",
    "SearchItem",
    "SearchParams",
    "SearchOutcome",
    "CopiedItem",
    "login",
    "refresh_token",
    "check_cookie_valid",
    "search",
    "publish",
    "get_detail",
    "StorageSettings",
    "KeepaliveSettings",
    "SearchSettings",
    "AppSettings",
    "load_settings",
]
```

- [ ] **Step 4: Run the coordinator tests again**

Run:

```bash
pytest tests/test_page_coordinator.py -v
```

Expected:
- All tests in `tests/test_page_coordinator.py` pass

- [ ] **Step 5: Commit**

```bash
git add src/page_coordinator.py src/__init__.py tests/test_page_coordinator.py
git commit -m "feat: add page coordinator leases"
```

### Task 2: Wire the coordinator into app startup and keepalive

**Files:**
- Modify: `src/core.py`
- Modify: `src/keepalive.py`
- Modify: `tests/test_keepalive.py`

- [ ] **Step 1: Write failing keepalive wiring tests**

Add these tests to `tests/test_keepalive.py`:

```python
class FakeCoordinator:
    def __init__(self, page):
        self.page = page
        self.calls = 0

    async def get_keepalive_page(self):
        self.calls += 1
        return self.page


@pytest.mark.asyncio
async def test_cookie_keepalive_uses_page_coordinator_when_present():
    from src.keepalive import CookieKeepaliveService

    browser = FakeKeepaliveBrowser(cookie_value="a=1; b=2")
    session = FakeKeepaliveSession()
    coordinator = FakeCoordinator(browser.keepalive_page)
    service = CookieKeepaliveService(
        browser=browser,
        session=session,
        interval_minutes=10,
        page_coordinator=coordinator,
    )

    await service.run_once()

    assert coordinator.calls == 1
    assert browser.keepalive_page.goto_calls == ["https://www.goofish.com"]


def test_app_builds_one_shared_page_coordinator(tmp_path):
    import src.core as core_mod

    settings = make_settings(tmp_path)

    class FakeBrowser:
        def __init__(self):
            self.settings = settings

    class FakeSession:
        def __init__(self, chrome_manager, settings=None, page_coordinator=None):
            self.chrome_manager = chrome_manager
            self.settings = settings
            self.page_coordinator = page_coordinator

    class FakeKeepalive:
        def __init__(self, browser, session, interval_minutes, page_coordinator=None):
            self.browser = browser
            self.session = session
            self.interval_minutes = interval_minutes
            self.page_coordinator = page_coordinator

    class FakeCoordinator:
        def __init__(self, browser):
            self.browser = browser

    browser = FakeBrowser()

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(core_mod, "SessionManager", FakeSession)
    monkeypatch.setattr(core_mod, "CookieKeepaliveService", FakeKeepalive)
    monkeypatch.setattr(core_mod, "PageCoordinator", FakeCoordinator)
    try:
        app = core_mod.XianyuApp(browser=browser, settings=settings)
    finally:
        monkeypatch.undo()

    assert isinstance(app.page_coordinator, FakeCoordinator)
    assert app.session.page_coordinator is app.page_coordinator
    assert app.keepalive.page_coordinator is app.page_coordinator
```

- [ ] **Step 2: Run the keepalive tests and verify they fail**

Run:

```bash
pytest tests/test_keepalive.py -k "coordinator or shared_page_coordinator" -v
```

Expected:
- `TypeError` because `CookieKeepaliveService` and `SessionManager` do not accept `page_coordinator`
- Or assertion failures because `XianyuApp` does not create a shared coordinator yet

- [ ] **Step 3: Implement app/keepalive coordinator wiring**

Update `src/keepalive.py` constructor and page lookup:

```python
class CookieKeepaliveService:
    def __init__(
        self,
        browser: Any,
        session: Any,
        interval_minutes: int,
        page_coordinator: Any | None = None,
    ):
        self.browser = browser
        self.session = session
        self.interval_minutes = interval_minutes
        self.page_coordinator = page_coordinator
        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
        self._initialized = False

    async def run_once(self) -> None:
        try:
            if not await self.browser.ensure_running():
                return

            if self.page_coordinator is not None:
                page = await self.page_coordinator.get_keepalive_page()
            else:
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
            logger.exception("CookieKeepaliveService.run_once failed.")
```

Update `src/core.py` initialization:

```python
from .page_coordinator import PageCoordinator


class XianyuApp:
    def __init__(
        self,
        browser: Optional[AsyncChromeManager] = None,
        settings: Optional[AppSettings] = None,
    ):
        resolved_settings = (
            settings or getattr(browser, "settings", None) or load_settings()
        )
        self.settings = resolved_settings
        self.browser = browser or AsyncChromeManager(settings=resolved_settings)
        try:
            self.browser.settings = resolved_settings
        except Exception:
            pass

        self.page_coordinator = PageCoordinator(self.browser)
        self.session = SessionManager(
            self.browser,
            settings=resolved_settings,
            page_coordinator=self.page_coordinator,
        )
        self._session_lock = asyncio.Lock()
        keepalive = CookieKeepaliveService(
            browser=self.browser,
            session=self.session,
            interval_minutes=resolved_settings.keepalive.interval_minutes,
            page_coordinator=self.page_coordinator,
        )
        self.keepalive = keepalive
        self.keepalive_service = keepalive
        self._background_started = False
```

- [ ] **Step 4: Run the keepalive tests again**

Run:

```bash
pytest tests/test_keepalive.py -k "coordinator or shared_page_coordinator" -v
```

Expected:
- Both new tests pass

- [ ] **Step 5: Commit**

```bash
git add src/core.py src/keepalive.py tests/test_keepalive.py
git commit -m "refactor: wire page coordinator into app lifecycle"
```

### Task 3: Route `SessionManager` through session and task leases

**Files:**
- Modify: `src/session.py`
- Create: `tests/test_session_page_lifecycle.py`

- [ ] **Step 1: Write failing session lifecycle tests**

Create `tests/test_session_page_lifecycle.py` with:

```python
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
    session = SessionManager(browser, settings=make_settings(tmp_path), page_coordinator=coordinator)

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
async def test_successful_cookie_check_closes_lingering_session_page(tmp_path, monkeypatch):
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

    session = SessionManager(FakeBrowser(), settings=settings, page_coordinator=coordinator)

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
```

- [ ] **Step 2: Run the session tests and verify they fail**

Run:

```bash
pytest tests/test_session_page_lifecycle.py -v
```

Expected:
- `TypeError` because `SessionManager` does not accept `page_coordinator`
- Or failures because `refresh_token` / `check_cookie_valid` still use `get_session_page()` and do not close task pages

- [ ] **Step 3: Implement session-page and task-page routing**

Update `SessionManager.__init__` and helpers in `src/session.py`:

```python
from .page_coordinator import PageCoordinator


class SessionManager:
    def __init__(
        self,
        chrome_manager: Optional[AsyncChromeManager] = None,
        settings: Optional[AppSettings] = None,
        page_coordinator: Optional[PageCoordinator] = None,
    ):
        resolved_settings = (
            settings
            or (getattr(chrome_manager, "settings", None) if chrome_manager else None)
            or load_settings()
        )
        self.settings = resolved_settings
        self.chrome_manager = chrome_manager or AsyncChromeManager(settings=self.settings)
        self.page_coordinator = page_coordinator or PageCoordinator(self.chrome_manager)
        self.token = None
        self.full_cookie = None
        self.token_file = self.settings.storage.token_file
        self.token_file.parent.mkdir(parents=True, exist_ok=True)

    async def _lease_session_page(self):
        return await self.page_coordinator.lease_session_page()

    async def _lease_task_page(self):
        return await self.page_coordinator.lease_task_page()
```

Update `refresh_token()` and `check_cookie_valid()` to use disposable task pages:

```python
    async def refresh_token(self) -> Optional[Dict[str, str]]:
        try:
            if not await self.chrome_manager.ensure_running():
                print("[Session] 浏览器启动失败")
                return None

            lease = await self._lease_task_page()
            async with lease:
                page = lease.page
                print("[Session] 正在刷新 token...")
                await self.chrome_manager.navigate("https://www.goofish.com", page=page)
                await asyncio.sleep(2)

                token = await self.chrome_manager.get_xianyu_token()
                full_cookie = await self.chrome_manager.get_cookie("_m_h5_tk")
                if not token:
                    print("[Session] 无法获取 token，请检查是否已登录")
                    return None

                self.token = token
                self.full_cookie = full_cookie
                full_cookie_str = await self.chrome_manager.get_full_cookie_string()
                self.save_cookie(full_cookie_str)
                print("[Session] Token 刷新成功")
                return {"token": token, "full_cookie": full_cookie}
        except Exception as e:
            print(f"[Session] 刷新 token 失败：{e}")
            return None

    async def check_cookie_valid(self) -> bool:
        try:
            if not await self.chrome_manager.ensure_running():
                print("[Session] 浏览器未运行")
                return False

            lease = await self._lease_task_page()
            async with lease:
                page = lease.page
                print("[Session] 正在检查 cookie 有效性...")
                await self.chrome_manager.navigate("https://www.goofish.com", page=page)
                await asyncio.sleep(2)

                full_cookie_str = await self.chrome_manager.get_full_cookie_string()
                if not full_cookie_str:
                    print("[Session] 未找到 cookie")
                    return False

                m_h5_tk = await self.chrome_manager.get_cookie("_m_h5_tk")
                if not m_h5_tk:
                    print("[Session] 无法获取 _m_h5_tk")
                    return False

                data = {}
                sign_params = self._generate_sign(data, m_h5_tk)
                headers = {
                    "accept": "application/json",
                    "accept-language": "zh-CN,zh;q=0.9",
                    "content-type": "application/x-www-form-urlencoded",
                    "origin": "https://www.goofish.com",
                    "referer": "https://www.goofish.com/",
                    "cookie": full_cookie_str,
                    "user-agent": "Mozilla/5.0",
                }
                url_params = {
                    "jsv": "2.7.2",
                    "appKey": sign_params["appKey"],
                    "t": sign_params["t"],
                    "sign": sign_params["sign"],
                    "v": "1.0",
                    "type": "originaljson",
                    "accountSite": "xianyu",
                    "dataType": "json",
                    "timeout": "20000",
                    "api": self.API_NAME,
                    "sessionOption": "AutoLoginOnly",
                }
                response = requests.Session().post(
                    self.API_BASE_URL,
                    params=url_params,
                    headers=headers,
                    data={"data": sign_params["data"]},
                    timeout=10,
                )
                result = response.json()
                ret = result.get("ret", [])
                if ret and "SUCCESS" in ret[0]:
                    display_name = (
                        result.get("data", {})
                        .get("module", {})
                        .get("base", {})
                        .get("displayName")
                    )
                    if display_name:
                        await self.page_coordinator.close_session_page()
                        print(f"[Session] Cookie 有效，用户：{display_name}")
                        return True
                return False
        except Exception as e:
            print(f"[Session] 检查 cookie 失败：{e}")
            return False
```

Update `login()` to keep the QR page alive by leasing `session_page` without closing it, but close it for terminal outcomes that do not require keeping the QR page open:

```python
    async def login(self, timeout: int = 30) -> Dict[str, Any]:
        if not await self.chrome_manager.ensure_running():
            return {"success": False, "message": "浏览器启动失败"}

        lease = await self._lease_session_page()
        page = lease.page
        await lease.release()

        capture_event = asyncio.Event()
        captured_data = {}

        async def process_response(response):
            try:
                url = response.url
                if "newlogin/qrcode/generate.do" in url:
                    data = await response.json()
                    content = data.get("content", {})
                    qr_data = content.get("data", {})
                    code_content = qr_data.get("codeContent")
                    if code_content:
                        if code_content.startswith("http://"):
                            code_content = code_content.replace("http://", "https://")
                        captured_data.update(
                            {
                                "url": code_content,
                                "ck": qr_data.get("ck"),
                                "t": qr_data.get("t"),
                            }
                        )
                        capture_event.set()
            except Exception as e:
                print(f"[Session] 解析二维码响应失败：{e}")

        page.on("response", lambda response: asyncio.create_task(process_response(response)))
        await self.chrome_manager.navigate("https://www.goofish.com", page=page)
        await asyncio.sleep(2)

        if await self.check_login_status():
            m_h5_tk = await self.chrome_manager.get_cookie("_m_h5_tk")
            self.save_cookie(await self.chrome_manager.get_full_cookie_string())
            await self.page_coordinator.close_session_page()
            return {
                "success": True,
                "logged_in": True,
                "token": m_h5_tk.split("_")[0] if m_h5_tk else None,
                "message": "已登录",
            }

        try:
            await asyncio.wait_for(capture_event.wait(), timeout=timeout)
            qr_result = await self._generate_qr_base64(captured_data["url"])
            return {
                "success": True,
                "logged_in": False,
                "qr_code": {
                    "url": captured_data["url"],
                    "public_url": qr_result.get("public_url", ""),
                    "text": captured_data["url"],
                    "ck": captured_data.get("ck"),
                    "t": captured_data.get("t"),
                },
                "message": "请扫码登录。扫码后浏览器会自动跳转，然后请调用 check_session 确认登录状态",
            }
        except asyncio.TimeoutError:
            await self.page_coordinator.close_session_page()
            return {"success": False, "message": "获取二维码超时"}
```

- [ ] **Step 4: Run the session lifecycle tests again**

Run:

```bash
pytest tests/test_session_page_lifecycle.py -v
```

Expected:
- The new lifecycle tests pass

- [ ] **Step 5: Commit**

```bash
git add src/session.py tests/test_session_page_lifecycle.py
git commit -m "refactor: move session tasks to page leases"
```

### Task 4: Route `search`, `publish`, and `get_detail` through disposable task pages

**Files:**
- Modify: `src/core.py`
- Create: `tests/test_core_task_pages.py`

- [ ] **Step 1: Write failing core task-page tests**

Create `tests/test_core_task_pages.py` with:

```python
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
```

- [ ] **Step 2: Run the core task-page tests and verify they fail**

Run:

```bash
pytest tests/test_core_task_pages.py -v
```

Expected:
- Failures because `publish`, `get_detail`, and `search_with_meta` still call cached role pages instead of `lease_task_page()`

- [ ] **Step 3: Implement disposable task-page routing in `src/core.py`**

Update the three business entry points:

```python
    async def search_with_meta(self, keyword: str, **options) -> SearchOutcome:
        params = SearchParams(
            keyword=keyword,
            rows=options.get("rows", 30),
            min_price=options.get("min_price"),
            max_price=options.get("max_price"),
            free_ship=options.get("free_ship", False),
            sort_field=options.get("sort_field", ""),
            sort_order=options.get("sort_order", ""),
        )

        lease = await self.page_coordinator.lease_task_page()
        async with lease:
            page = lease.page

            async def get_cookie():
                cached = self.session.load_cached_cookie()
                if cached:
                    return cached
                if await self.browser.ensure_running():
                    await self.browser.navigate("https://www.goofish.com", page=page)
                    full_cookie = await self.browser.get_full_cookie_string()
                    if full_cookie:
                        self.session.save_cookie(full_cookie)
                        return full_cookie
                return None

            client = HttpApiSearchClient(get_cookie)
            try:
                from .search_api import StableSearchRunner
            except ImportError:
                from search_api import StableSearchRunner

            try:
                runner = StableSearchRunner(
                    client=client,
                    max_stale_pages=self.settings.search.max_stale_pages,
                )
                return await runner.search(params)
            finally:
                await client.aclose()

    async def publish(self, item_url: str, **options) -> Dict[str, Any]:
        lease = await self.page_coordinator.lease_task_page()
        async with lease:
            copier = _ItemCopierImpl(self.browser, lease.page)
            return await copier.publish_from_item(
                item_url,
                new_title=options.get("new_title"),
                new_description=options.get("new_description"),
                new_price=options.get("new_price"),
                original_price=options.get("original_price"),
                condition=options.get("condition", "全新"),
            )

    async def get_detail(self, item_url: str) -> Optional[CopiedItem]:
        lease = await self.page_coordinator.lease_task_page()
        async with lease:
            copier = _ItemCopierImpl(self.browser, lease.page)
            return await copier.capture_item_detail(item_url)
```

- [ ] **Step 4: Run the core task-page tests again**

Run:

```bash
pytest tests/test_core_task_pages.py -v
```

Expected:
- All tests in `tests/test_core_task_pages.py` pass

- [ ] **Step 5: Commit**

```bash
git add src/core.py tests/test_core_task_pages.py
git commit -m "refactor: use disposable task pages for business flows"
```

### Task 5: Run the focused regression suite

**Files:**
- Test only: `tests/test_page_coordinator.py`
- Test only: `tests/test_keepalive.py`
- Test only: `tests/test_session_page_lifecycle.py`
- Test only: `tests/test_core_task_pages.py`

- [ ] **Step 1: Run the focused regression suite**

Run:

```bash
pytest \
  tests/test_page_coordinator.py \
  tests/test_keepalive.py \
  tests/test_session_page_lifecycle.py \
  tests/test_core_task_pages.py -v
```

Expected:
- All targeted lifecycle tests pass
- No test should rely on persistent `search_page`, `session_page`, or `publish_page` role caches for business flows

- [ ] **Step 2: Run one existing smoke suite that touches current app wiring**

Run:

```bash
pytest tests/test_http_server_unit.py -v
```

Expected:
- Existing HTTP server unit tests still pass without MCP API changes

- [ ] **Step 3: If any test still assumes old role pages, update only that assertion**

For example, if a test still expects `publish()` to reuse `_publish_page`, replace that assertion with a task-page closure assertion like:

```python
assert fake_task_page.closed is True
assert fake_coordinator.pages == [fake_task_page]
```

- [ ] **Step 4: Re-run the full focused suite after fixes**

Run:

```bash
pytest \
  tests/test_page_coordinator.py \
  tests/test_keepalive.py \
  tests/test_session_page_lifecycle.py \
  tests/test_core_task_pages.py \
  tests/test_http_server_unit.py -v
```

Expected:
- All listed suites pass

- [ ] **Step 5: Commit**

```bash
git add tests/test_page_coordinator.py tests/test_keepalive.py tests/test_session_page_lifecycle.py tests/test_core_task_pages.py src/page_coordinator.py src/core.py src/session.py src/keepalive.py src/__init__.py
git commit -m "test: cover task page lifecycle workflow"
```
