# Multi-User Keepalive And Debug Unification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the implicit single-user `default` runtime from keepalive and debug flows, move keepalive orchestration into `MultiUserManager`, delete `xianyu_show_qr` and `/rest/show_qr`, and keep debug capability through multi-user `login`/`check_session`/`search`/`browser_overview` entrypoints.

**Architecture:** Keep `XianyuApp` and `CookieKeepaliveService` as the per-user execution engine, but let `MultiUserManager` own user selection, keepalive lifecycle, runtime status, and startup initialization. Refactor HTTP REST debug handlers and stdio MCP handlers to delegate to `MultiUserManager`, so all user-visible status and token updates come from the same runtime model.

**Tech Stack:** Python 3.11, FastMCP/stdio MCP, Starlette, pytest, Docker Compose

---

## File Map

- Modify: `src/keepalive.py`
  Add optional success/error callbacks so multi-user runtime state can be updated from real keepalive activity.
- Modify: `src/core.py`
  Add a small runtime-status helper so `MultiUserManager` can ask whether background tasks are actually running.
- Modify: `src/multi_user_manager.py`
  Add startup initialization, debug-user selection helpers, runtime-state write helpers, real keepalive state computation, debug-oriented wrappers, and `show_qr` removal.
- Modify: `mcp_server/http_server.py`
  Remove single-user `get_app()`, switch HTTP tools and REST debug handlers to `MultiUserManager`, add `/rest/login`, remove `/rest/show_qr`, and stop auto-starting `default` keepalive.
- Modify: `mcp_server/server.py`
  Replace single-user stdio `XianyuApp` wiring with a thin multi-user wrapper, remove `xianyu_show_qr`, and stop boot-time `default` keepalive.
- Modify: `tests/test_multi_user_keepalive.py`
  Add keepalive callback coverage and initialization/stop behavior checks.
- Modify: `tests/test_multi_user_manager.py`
  Add tests for debug user resolution, login selection, and keepalive state sync.
- Modify: `tests/test_http_server_multi_user_auth.py`
  Replace `show_qr` tests with `login`/`check_session`/`refresh_token` multi-user auth tests.
- Modify: `tests/test_http_server_unit.py`
  Replace tests that assert single-user `get_app()` startup with tests that assert manager initialization and multi-user handler behavior for HTTP and stdio MCP.
- Modify: `tests/test_mcp_dev_cli.py`
  Remove `show_qr` references from CLI parsing tests.
- Modify: `README.md`
  Replace `show_qr` references, explain that login returns QR when needed, and update the debug flow summary.
- Modify: `docs/mcp-e2e-regression.md`
  Replace `/rest/show_qr` and `xianyu_show_qr` with `/rest/login` and `xianyu_login`.
- Modify: `docs/mcp-dev-cheatsheet.md`
  Replace the QR examples and recommended flow.
- Modify: `docs/opencode-setup.md`
  Replace `xianyu_show_qr` examples with `xianyu_login`.
- Modify: `docs/claude-code-setup.md`
  Keep the setup instructions unchanged, but update any login wording to state that `xianyu_login` returns a QR code when the target user is not logged in.
- Modify: `docs/api-protocol.md`
  Replace any “`login` or `show_qr`” wording with `login` only.
- Modify: `.claude/skills/xianyu-skill/SKILL.md`
  Remove `xianyu_show_qr` from the tool table and workflow guidance.

### Task 1: Add real keepalive-state hooks and manager startup sync

**Files:**
- Modify: `tests/test_multi_user_keepalive.py`
- Modify: `src/keepalive.py`
- Modify: `src/core.py`
- Modify: `src/multi_user_manager.py`

- [ ] **Step 1: Write the failing keepalive callback and startup-sync tests**

Append these tests to `tests/test_multi_user_keepalive.py`:

```python
from src.keepalive import CookieKeepaliveService


class _FakeTask:
    def done(self):
        return False


class _KeepaliveBrowser:
    def __init__(self):
        class Page:
            async def goto(self, url):
                return None

            async def reload(self):
                return None

        self.page = Page()

    async def ensure_running(self):
        return True

    async def get_keepalive_page(self):
        return self.page

    async def get_full_cookie_string(self):
        return "cookie=value"


class _KeepaliveSession:
    def __init__(self):
        self.saved = []

    def save_cookie(self, full_cookie):
        self.saved.append(full_cookie)

    def get_cookie_status(self, is_valid):
        assert is_valid is True
        return {"valid": True, "last_updated_at": "2026-04-12 10:20:30"}


@pytest.mark.asyncio
async def test_keepalive_run_once_emits_cookie_saved_callback():
    events = []
    service = CookieKeepaliveService(
        browser=_KeepaliveBrowser(),
        session=_KeepaliveSession(),
        interval_minutes=10,
        on_cookie_saved=lambda last_updated_at: events.append(last_updated_at),
        on_error=lambda message: events.append(f"error:{message}"),
    )

    await service.run_once()

    assert events == ["2026-04-12 10:20:30"]


@pytest.mark.asyncio
async def test_keepalive_run_once_emits_error_callback():
    events = []

    class FailingBrowser(_KeepaliveBrowser):
        async def get_full_cookie_string(self):
            raise RuntimeError("cookie boom")

    service = CookieKeepaliveService(
        browser=FailingBrowser(),
        session=_KeepaliveSession(),
        interval_minutes=10,
        on_cookie_saved=lambda last_updated_at: events.append(last_updated_at),
        on_error=lambda message: events.append(message),
    )

    await service.run_once()

    assert events == ["cookie boom"]


@pytest.mark.asyncio
async def test_ensure_initialized_starts_keepalive_for_valid_users(tmp_path):
    manager = make_manager(tmp_path)
    first = manager.create_user()
    second = manager.create_user()

    class FakeApp:
        def __init__(self, valid):
            self.valid = valid
            self._background_started = False
            self.keepalive = type("Keepalive", (), {"_task": None})()

        def start_background_tasks(self):
            self._background_started = True
            self.keepalive._task = _FakeTask()

        async def stop_background_tasks(self):
            self._background_started = False
            self.keepalive._task = None

        def background_tasks_running(self):
            task = self.keepalive._task
            return bool(self._background_started and task is not None and not task.done())

        async def check_session(self):
            return {
                "valid": self.valid,
                "last_updated_at": "2026-04-12 10:30:00" if self.valid else None,
            }

    manager._runtimes[first.user_id] = type(
        "Runtime", (), {"entry": first, "app": FakeApp(True)}
    )()
    manager._runtimes[second.user_id] = type(
        "Runtime", (), {"entry": second, "app": FakeApp(False)}
    )()

    await manager.ensure_initialized()

    first_status = manager.get_user_status(first.user_id)
    second_status = manager.get_user_status(second.user_id)
    assert first_status["keepalive_running"] is True
    assert first_status["status"] == "ready"
    assert second_status["keepalive_running"] is False
    assert second_status["status"] == "pending_login"
```

- [ ] **Step 2: Run the keepalive tests to verify they fail**

Run: `pytest tests/test_multi_user_keepalive.py -v`

Expected: FAIL with messages like `TypeError: CookieKeepaliveService.__init__() got an unexpected keyword argument 'on_cookie_saved'` and `AttributeError: 'MultiUserManager' object has no attribute 'ensure_initialized'`

- [ ] **Step 3: Add keepalive callbacks, app runtime introspection, and manager startup sync**

Update `src/keepalive.py` to accept callback hooks and emit them from real keepalive execution:

```python
from typing import Any, Callable, Optional


class CookieKeepaliveService:
    def __init__(
        self,
        browser: Any,
        session: Any,
        interval_minutes: int,
        page_coordinator: Any | None = None,
        on_cookie_saved: Callable[[str | None], None] | None = None,
        on_error: Callable[[str], None] | None = None,
    ):
        self.browser = browser
        self.session = session
        self.interval_minutes = interval_minutes
        self.page_coordinator = page_coordinator
        self.on_cookie_saved = on_cookie_saved
        self.on_error = on_error
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
                if self.on_cookie_saved is not None:
                    status = self.session.get_cookie_status(True)
                    self.on_cookie_saved(status.get("last_updated_at"))
        except Exception as exc:
            if self.on_error is not None:
                self.on_error(str(exc))
            logger.exception("CookieKeepaliveService.run_once failed.")
```

Add a small real-state helper to `src/core.py` right below `stop_background_tasks()`:

```python
    def background_tasks_running(self) -> bool:
        task = getattr(self.keepalive, "_task", None)
        return bool(self._background_started and task is not None and not task.done())
```

Update `src/multi_user_manager.py` with a startup-sync lock, real keepalive-state helpers, and initialization logic:

```python
from datetime import datetime


class MultiUserManager:
    def __init__(self, pool_settings: BrowserPoolSettings, registry: MultiUserRegistry):
        self.pool_settings = pool_settings
        self.registry = registry
        self.operation_lock = asyncio.Lock()
        self._startup_lock = asyncio.Lock()
        self._startup_complete = False
        self._runtimes: dict[str, UserRuntime] = {}
        self._runtime_state: dict[str, dict[str, Any]] = {}

    def _now_text(self) -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _is_keepalive_running(self, user_id: str) -> bool:
        runtime = self._runtimes.get(user_id)
        app = getattr(runtime, "app", None)
        if app is None or not hasattr(app, "background_tasks_running"):
            return self._runtime_state.get(user_id, {}).get("keepalive_running", False)
        return bool(app.background_tasks_running())

    def _record_keepalive_success(self, user_id: str, last_updated_at: str | None) -> None:
        state = self._runtime_state[user_id]
        state["keepalive_running"] = self._is_keepalive_running(user_id)
        state["last_keepalive_at"] = self._now_text()
        state["last_keepalive_status"] = "ok"
        state["last_error"] = None
        if last_updated_at is not None:
            state["last_cookie_updated_at"] = last_updated_at

    def _record_keepalive_error(self, user_id: str, message: str) -> None:
        state = self._runtime_state[user_id]
        state["keepalive_running"] = self._is_keepalive_running(user_id)
        state["last_keepalive_at"] = self._now_text()
        state["last_keepalive_status"] = "error"
        state["last_error"] = message

    async def _get_or_create_runtime(self, user_id: str) -> UserRuntime:
        if user_id in self._runtimes:
            return self._runtimes[user_id]

        entry = self._entry_by_user_id(user_id)
        state = self._ensure_runtime_state(entry)
        settings = build_user_settings(
            user_id=entry.user_id,
            token_file=entry.token_file,
            chrome_user_data_dir=entry.chrome_user_data_dir,
            data_root=entry.token_file.parents[2],
        )
        browser = AsyncChromeManager(
            host=entry.cdp_host,
            port=entry.cdp_port,
            auto_start=False,
            settings=settings,
        )
        app = XianyuApp(browser=browser, settings=settings)
        app.keepalive.on_cookie_saved = (
            lambda last_updated_at, uid=entry.user_id: self._record_keepalive_success(uid, last_updated_at)
        )
        app.keepalive.on_error = (
            lambda message, uid=entry.user_id: self._record_keepalive_error(uid, message)
        )
        runtime = UserRuntime(entry=entry, app=app)
        self._runtimes[user_id] = runtime
        state["browser_connected"] = True
        return runtime

    async def ensure_keepalive(self, user_id: str) -> None:
        runtime = await self._get_or_create_runtime(user_id)
        runtime.app.start_background_tasks()
        self._runtime_state[user_id]["keepalive_running"] = self._is_keepalive_running(user_id)

    async def stop_keepalive(self, user_id: str) -> None:
        runtime = await self._get_or_create_runtime(user_id)
        await runtime.app.stop_background_tasks()
        self._runtime_state[user_id]["keepalive_running"] = self._is_keepalive_running(user_id)

    async def ensure_initialized(self) -> None:
        if self._startup_complete:
            return
        async with self._startup_lock:
            if self._startup_complete:
                return
            for entry in self.registry.list_users():
                result = await self.check_session(entry.user_id)
                if result["valid"]:
                    await self.ensure_keepalive(entry.user_id)
                else:
                    await self.stop_keepalive(entry.user_id)
            self._startup_complete = True
```

Also update `get_user_status()` in `src/multi_user_manager.py` to read the real keepalive state:

```python
            "keepalive_running": self._is_keepalive_running(user_id),
```

- [ ] **Step 4: Run the keepalive tests to verify they pass**

Run: `pytest tests/test_multi_user_keepalive.py -v`

Expected: PASS with the new callback and initialization tests green.

- [ ] **Step 5: Commit**

```bash
git add tests/test_multi_user_keepalive.py src/keepalive.py src/core.py src/multi_user_manager.py
git commit -m "feat: move keepalive state under multi-user manager"
```

### Task 2: Add debug-user selection and remove manager-level `show_qr`

**Files:**
- Modify: `tests/test_multi_user_manager.py`
- Modify: `src/multi_user_manager.py`

- [ ] **Step 1: Write the failing user-selection and debug-wrapper tests**

Append these tests to `tests/test_multi_user_manager.py`:

```python
@pytest.mark.asyncio
async def test_resolve_debug_user_auto_picks_first_ready_user(tmp_path):
    manager = make_manager(tmp_path)
    first = manager.create_user()
    second = manager.create_user()
    manager.registry.update_user(replace(first, status="ready"))
    manager.registry.update_user(replace(second, status="pending_login"))

    entry, selected_by = manager.resolve_debug_user(None)

    assert entry.user_id == first.user_id
    assert selected_by == "auto"


@pytest.mark.asyncio
async def test_resolve_login_user_auto_picks_first_not_ready_user(tmp_path):
    manager = make_manager(tmp_path)
    first = manager.create_user()
    second = manager.create_user()
    manager._runtime_state[first.user_id] = {
        "status": "ready",
        "cookie_valid": True,
        "enabled": True,
    }
    manager._runtime_state[second.user_id] = {
        "status": "pending_login",
        "cookie_valid": False,
        "enabled": True,
    }

    entry, selected_by = manager.resolve_login_user(None)

    assert entry.user_id == second.user_id
    assert selected_by == "auto"


@pytest.mark.asyncio
async def test_debug_login_returns_selected_user_metadata(tmp_path):
    manager = make_manager(tmp_path)
    entry = manager.create_user()
    runtime = await manager._get_or_create_runtime(entry.user_id)

    async def fake_login(timeout=30):
        return {
            "success": True,
            "logged_in": False,
            "qr_code": {"url": "https://passport.goofish.com/qrcodeCheck.htm?lgToken=test"},
            "message": "请扫码登录",
        }

    runtime.app.login = fake_login

    result = await manager.debug_login(user_id=entry.user_id)

    assert result["user_id"] == entry.user_id
    assert result["slot_id"] == entry.slot_id
    assert result["selected_by"] == "explicit"
    assert result["qr_code"]["url"].startswith("https://passport.goofish.com/")


def test_resolve_login_user_raises_when_all_users_are_ready(tmp_path):
    manager = make_manager(tmp_path)
    entry = manager.create_user()
    manager._runtime_state[entry.user_id] = {
        "status": "ready",
        "cookie_valid": True,
        "enabled": True,
    }

    with pytest.raises(RuntimeError, match="no_available_user"):
        manager.resolve_login_user(None)
```

- [ ] **Step 2: Run the manager tests to verify they fail**

Run: `pytest tests/test_multi_user_manager.py -k "resolve_debug_user or resolve_login_user or debug_login" -v`

Expected: FAIL with `AttributeError` for `resolve_debug_user`, `resolve_login_user`, or `debug_login`.

- [ ] **Step 3: Add debug-user resolution helpers and delete `show_qr`**

Update `src/multi_user_manager.py` with explicit helper methods and a debug login wrapper:

```python
    def resolve_debug_user(self, user_id: str | None) -> tuple[UserRegistryEntry, str]:
        if user_id is not None:
            return self._entry_by_user_id(user_id), "explicit"

        for entry in self.registry.list_users():
            state = self._runtime_state.get(entry.user_id, {})
            status = state.get("status", entry.status)
            if entry.enabled and status == "ready":
                return entry, "auto"
        raise RuntimeError("no_available_user")

    def resolve_login_user(self, user_id: str | None) -> tuple[UserRegistryEntry, str]:
        if user_id is not None:
            return self._entry_by_user_id(user_id), "explicit"

        for entry in self.registry.list_users():
            state = self._runtime_state.get(entry.user_id, {})
            status = state.get("status", entry.status)
            cookie_valid = state.get("cookie_valid", False)
            if entry.enabled and not (status == "ready" and cookie_valid):
                return entry, "auto"
        raise RuntimeError("no_available_user")

    async def debug_login(self, user_id: str | None = None) -> dict[str, Any]:
        entry, selected_by = self.resolve_login_user(user_id)
        result = await self.login(entry.user_id)
        return {"slot_id": entry.slot_id, "selected_by": selected_by, **result}

    async def debug_check_session(self, user_id: str | None = None) -> dict[str, Any]:
        entry, selected_by = self.resolve_debug_user(user_id)
        result = await self.check_session(entry.user_id)
        return {"slot_id": entry.slot_id, "selected_by": selected_by, **result}

    async def debug_search(self, keyword: str, user_id: str | None = None, **options) -> dict[str, Any]:
        entry, selected_by = self.resolve_debug_user(user_id)
        result = await self.search(keyword=keyword, user_id=entry.user_id, **options)
        result["selected_by"] = selected_by
        return result

    async def debug_browser_overview(self, user_id: str | None = None) -> dict[str, Any]:
        if user_id is not None:
            runtime = await self._get_or_create_runtime(user_id)
            overview = await runtime.app.browser_overview()
            return {
                "user_id": user_id,
                "slot_id": runtime.entry.slot_id,
                "selected_by": "explicit",
                **overview,
            }

        users = []
        for runtime in self._runtimes.values():
            overview = await runtime.app.browser_overview()
            users.append(
                {
                    "user_id": runtime.entry.user_id,
                    "slot_id": runtime.entry.slot_id,
                    **overview,
                }
            )
        return {"users": users}
```

Remove the obsolete `show_qr()` method entirely from `src/multi_user_manager.py`.

Also ensure these existing methods start/stop keepalive as part of state transitions:

```python
    async def login(self, user_id: str) -> dict[str, Any]:
        runtime = await self._get_or_create_runtime(user_id)
        result = await runtime.app.login(timeout=30)
        if result.get("success"):
            status = "ready" if result.get("logged_in") or result.get("token") else "pending_login"
            self._runtime_state[user_id]["status"] = status
            entry = self._entry_by_user_id(user_id)
            self.registry.update_user(replace(entry, status=status))
            if status == "ready":
                await self.ensure_keepalive(user_id)
        return {"user_id": user_id, **result}

    async def check_session(self, user_id: str) -> dict[str, Any]:
        runtime = await self._get_or_create_runtime(user_id)
        result = await runtime.app.check_session()
        self._runtime_state[user_id]["cookie_valid"] = result["valid"]
        self._runtime_state[user_id]["cookie_present"] = True
        self._runtime_state[user_id]["last_cookie_updated_at"] = result.get("last_updated_at")
        status = "ready" if result["valid"] else "pending_login"
        self._runtime_state[user_id]["status"] = status
        entry = self._entry_by_user_id(user_id)
        self.registry.update_user(replace(entry, status=status))
        if result["valid"]:
            await self.ensure_keepalive(user_id)
        else:
            await self.stop_keepalive(user_id)
        return {"user_id": user_id, **result}

    async def refresh_token(self, user_id: str) -> dict[str, Any]:
        runtime = await self._get_or_create_runtime(user_id)
        result = await runtime.app.refresh_token()
        if result:
            self._runtime_state[user_id]["cookie_present"] = True
            self._runtime_state[user_id]["cookie_valid"] = True
            self._runtime_state[user_id]["status"] = "ready"
            entry = self._entry_by_user_id(user_id)
            self.registry.update_user(replace(entry, status="ready"))
            await self.ensure_keepalive(user_id)
        return {"user_id": user_id, "success": bool(result), **(result or {})}
```

- [ ] **Step 4: Run the manager tests to verify they pass**

Run: `pytest tests/test_multi_user_manager.py -k "resolve_debug_user or resolve_login_user or debug_login" -v`

Expected: PASS with the new helper and wrapper tests green.

- [ ] **Step 5: Commit**

```bash
git add tests/test_multi_user_manager.py src/multi_user_manager.py
git commit -m "feat: add multi-user debug selection helpers"
```

### Task 3: Refactor HTTP MCP and REST debug endpoints to use `MultiUserManager`

**Files:**
- Modify: `tests/test_http_server_multi_user_auth.py`
- Modify: `tests/test_http_server_unit.py`
- Modify: `mcp_server/http_server.py`

- [ ] **Step 1: Write the failing HTTP tests for `/rest/login`, browser overview, and `show_qr` removal**

Add these tests to `tests/test_http_server_multi_user_auth.py`:

```python
class FakeAuthManager:
    async def debug_login(self, user_id=None):
        return {
            "success": True,
            "user_id": user_id or "user-002",
            "slot_id": "slot-2",
            "selected_by": "auto" if user_id is None else "explicit",
            "logged_in": False,
            "qr_code": {"url": "https://passport.goofish.com/qrcodeCheck.htm?lgToken=test"},
            "message": "请扫码登录",
        }

    async def debug_check_session(self, user_id=None):
        return {
            "success": True,
            "user_id": user_id or "user-001",
            "slot_id": "slot-1",
            "selected_by": "auto" if user_id is None else "explicit",
            "valid": True,
            "last_updated_at": "2026-04-12 10:40:00",
        }

    async def refresh_token(self, user_id):
        return {"success": True, "user_id": user_id, "token": "abc"}


async def test_http_rest_login_uses_debug_login(monkeypatch):
    from starlette.requests import Request
    from mcp_server import http_server

    async def receive():
        return {"type": "http.request", "body": b'{"user_id":"user-001"}', "more_body": False}

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/rest/login",
            "headers": [(b"content-type", b"application/json")],
        },
        receive,
    )
    monkeypatch.setattr(http_server, "get_manager", lambda: FakeAuthManager())

    response = await http_server.rest_login(request)
    assert response.status_code == 200
    assert b'user-001' in response.body


async def test_http_module_no_longer_exports_xianyu_show_qr():
    from mcp_server import http_server

    assert not hasattr(http_server, "xianyu_show_qr")
```

Replace the browser overview test in `tests/test_http_server_unit.py` with manager-based assertions:

```python
@pytest.mark.asyncio
async def test_xianyu_browser_overview_returns_manager_payload(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.http_server as http_server

    class FakeManager:
        async def debug_browser_overview(self, user_id=None):
            return {
                "users": [
                    {
                        "user_id": "user-001",
                        "slot_id": "slot-1",
                        "browser_context_count": 1,
                        "contexts": [{"page_count": 1, "pages": [{"title": "闲鱼", "url": "https://www.goofish.com/"}]}],
                    }
                ]
            }

    monkeypatch.setattr(http_server, "get_manager", lambda: FakeManager())

    payload = json.loads(await http_server.xianyu_browser_overview())

    assert payload["success"] is True
    assert payload["users"][0]["user_id"] == "user-001"
```

- [ ] **Step 2: Run the HTTP tests to verify they fail**

Run: `pytest tests/test_http_server_multi_user_auth.py tests/test_http_server_unit.py -k "rest_login or browser_overview or show_qr" -v`

Expected: FAIL because `rest_login` does not exist, `xianyu_show_qr` still exists, and `xianyu_browser_overview()` still calls `get_app()`.

- [ ] **Step 3: Remove single-user `get_app()`, add `/rest/login`, and route everything through the manager**

Refactor `mcp_server/http_server.py` like this:

```python
import json
import os
import sys

from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route


def get_manager():
    global _manager
    if _manager is None:
        from src.browser_pool import BrowserPoolSettings
        from src.multi_user_manager import MultiUserManager
        from src.multi_user_registry import MultiUserRegistry
        from src.settings import load_raw_config

        raw = load_raw_config()
        pool = BrowserPoolSettings.from_config(raw)
        registry = MultiUserRegistry(pool)
        _manager = MultiUserManager(pool_settings=pool, registry=registry)
    return _manager


async def initialize_manager() -> None:
    manager = get_manager()
    if hasattr(manager, "ensure_initialized"):
        await manager.ensure_initialized()


@mcp.tool()
async def xianyu_login(user_id: str | None = None) -> str:
    manager = get_manager()
    if user_id is None:
        payload = await manager.debug_login()
    else:
        payload = await manager.login(user_id)
        payload["selected_by"] = "explicit"
        payload["slot_id"] = manager.get_user_status(payload["user_id"])["slot_id"]
    return json.dumps(payload, ensure_ascii=False)


@mcp.tool()
async def xianyu_browser_overview(user_id: str | None = None) -> str:
    manager = get_manager()
    try:
        overview = await manager.debug_browser_overview(user_id=user_id)
        response = {"success": True, **overview}
    except RuntimeError as exc:
        response = {"success": False, "message": str(exc)}
    return json.dumps(response, ensure_ascii=False)


async def rest_login(request):
    try:
        data = await request.json() if request.method == "POST" else {}
    except json.JSONDecodeError:
        data = {}
    try:
        result = await get_manager().debug_login(data.get("user_id"))
        return JSONResponse(result)
    except RuntimeError as exc:
        message = str(exc)
        status_code = 409 if message == "no_available_user" else 500
        return JSONResponse({"success": False, "error": message, "message": message}, status_code=status_code)


async def rest_check_session(request):
    try:
        data = await request.json() if request.method == "POST" else {}
    except json.JSONDecodeError:
        data = {}
    try:
        result = await get_manager().debug_check_session(data.get("user_id"))
        return JSONResponse({
            "success": True,
            "user_id": result["user_id"],
            "slot_id": result["slot_id"],
            "selected_by": result["selected_by"],
            "valid": result["valid"],
            "message": "Cookie 有效" if result["valid"] else "Cookie 已过期",
            "last_updated_at": result.get("last_updated_at"),
        })
    except RuntimeError as exc:
        message = str(exc)
        status_code = 409 if message == "no_available_user" else 500
        return JSONResponse({"success": False, "error": message, "message": message}, status_code=status_code)


async def rest_search(request):
    data = await request.json()
    try:
        result = await get_manager().debug_search(
            keyword=data.get("keyword", ""),
            user_id=data.get("user_id"),
            rows=data.get("rows", 30),
            min_price=data.get("min_price"),
            max_price=data.get("max_price"),
            free_ship=data.get("free_ship", False),
            sort_field=data.get("sort_field", ""),
            sort_order=data.get("sort_order", ""),
        )
        return JSONResponse(result)
    except RuntimeError as exc:
        message = str(exc)
        status_code = 409 if message == "no_available_user" else 500
        return JSONResponse({"success": False, "error": message, "message": message}, status_code=status_code)


def build_app() -> Starlette:
    middleware = [
        Middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )
    ]
    rest_routes = [
        Route("/rest/login", rest_login, methods=["GET", "POST"]),
        Route("/rest/check_session", rest_check_session, methods=["GET", "POST"]),
        Route("/rest/search", rest_search, methods=["POST"]),
    ]
    return Starlette(
        routes=rest_routes + [Mount("/", app=mcp.sse_app())],
        middleware=middleware,
        on_startup=[initialize_manager],
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(build_app(), host=MCP_HOST, port=MCP_PORT)
```

Also delete the `get_app()` function and the `xianyu_show_qr()` MCP tool from `mcp_server/http_server.py`.

- [ ] **Step 4: Run the HTTP tests to verify they pass**

Run: `pytest tests/test_http_server_multi_user_auth.py tests/test_http_server_unit.py -v`

Expected: PASS with browser overview, login, and REST handler tests green, and no remaining references to `xianyu_show_qr` in these test files.

- [ ] **Step 5: Commit**

```bash
git add tests/test_http_server_multi_user_auth.py tests/test_http_server_unit.py mcp_server/http_server.py
git commit -m "feat: move http debug endpoints to multi-user runtime"
```

### Task 4: Convert stdio MCP to a thin multi-user wrapper and remove boot-time `default` keepalive

**Files:**
- Modify: `tests/test_http_server_unit.py`
- Modify: `mcp_server/server.py`

- [ ] **Step 1: Write the failing stdio multi-user tests**

Append these tests to `tests/test_http_server_unit.py`:

```python
@pytest.mark.asyncio
async def test_stdio_list_tools_drops_show_qr_and_adds_multi_user_tools(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.server as stdio_server

    tools = await stdio_server.list_tools()
    tool_names = [tool.name for tool in tools]

    assert "xianyu_show_qr" not in tool_names
    assert "xianyu_list_users" in tool_names
    assert "xianyu_create_user" in tool_names
    assert "xianyu_get_user_status" in tool_names


@pytest.mark.asyncio
async def test_stdio_call_tool_routes_login_through_manager(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.server as stdio_server

    class FakeManager:
        async def ensure_initialized(self):
            return None

        async def debug_login(self, user_id=None):
            return {
                "success": True,
                "user_id": user_id or "user-001",
                "slot_id": "slot-1",
                "selected_by": "auto" if user_id is None else "explicit",
                "logged_in": False,
                "message": "请扫码登录",
            }

    monkeypatch.setattr(stdio_server, "get_manager", lambda: FakeManager())

    result = await stdio_server.call_tool("xianyu_login", {})
    payload = json.loads(result.content[0].text)

    assert payload["success"] is True
    assert payload["selected_by"] == "auto"


@pytest.mark.asyncio
async def test_stdio_run_server_initializes_manager_without_get_app(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.server as stdio_server

    calls = {"init": 0}

    class FakeManager:
        async def ensure_initialized(self):
            calls["init"] += 1

    class DummyStdio:
        async def __aenter__(self):
            return (object(), object())

        async def __aexit__(self, exc_type, exc, tb):
            return False

    async def run_stub(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(stdio_server, "get_manager", lambda: FakeManager())
    monkeypatch.setattr(stdio_server.mcp.server.stdio, "stdio_server", lambda: DummyStdio())
    monkeypatch.setattr(stdio_server.server, "run", run_stub)

    with pytest.raises(RuntimeError):
        await stdio_server.run_server()

    assert calls["init"] == 1
```

- [ ] **Step 2: Run the stdio tests to verify they fail**

Run: `pytest tests/test_http_server_unit.py -k "stdio" -v`

Expected: FAIL because `xianyu_show_qr` is still present, `xianyu_list_users` is missing, and `run_server()` still calls `get_app()`.

- [ ] **Step 3: Replace the stdio single-user app with manager-based handlers**

Refactor `mcp_server/server.py` so it imports and reuses the multi-user manager instead of building a single-user `XianyuApp`:

```python
import asyncio
import json
import os
import sys
from dataclasses import asdict

import mcp.server.stdio
import mcp.types as types
from mcp.server import Server
from mcp.server.lowlevel import NotificationOptions
from mcp.server.models import InitializationOptions

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp_server.http_server import get_manager


server = Server("xianyu-mcp")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(name="xianyu_create_user", description="创建新用户", inputSchema={"type": "object", "properties": {"display_name": {"type": "string"}}, "required": []}),
        types.Tool(name="xianyu_list_users", description="查看全部用户", inputSchema={"type": "object", "properties": {}, "required": []}),
        types.Tool(name="xianyu_get_user_status", description="查看单个用户状态", inputSchema={"type": "object", "properties": {"user_id": {"type": "string"}}, "required": ["user_id"]}),
        types.Tool(name="xianyu_login", description="登录或返回二维码", inputSchema={"type": "object", "properties": {"user_id": {"type": "string"}}, "required": []}),
        types.Tool(name="xianyu_search", description="搜索商品", inputSchema={"type": "object", "properties": {"keyword": {"type": "string"}, "user_id": {"type": "string"}, "rows": {"type": "integer", "default": 30}}, "required": ["keyword"]}),
        types.Tool(name="xianyu_publish", description="复制发布商品", inputSchema={"type": "object", "properties": {"user_id": {"type": "string"}, "item_url": {"type": "string"}}, "required": ["user_id", "item_url"]}),
        types.Tool(name="xianyu_refresh_token", description="刷新 token", inputSchema={"type": "object", "properties": {"user_id": {"type": "string"}}, "required": ["user_id"]}),
        types.Tool(name="xianyu_check_session", description="检查登录态", inputSchema={"type": "object", "properties": {"user_id": {"type": "string"}}, "required": ["user_id"]}),
        types.Tool(name="xianyu_browser_overview", description="获取浏览器概览", inputSchema={"type": "object", "properties": {"user_id": {"type": "string"}}, "required": []}),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> types.CallToolResult:
    manager = get_manager()
    try:
        if name == "xianyu_create_user":
            entry = manager.create_user(arguments.get("display_name"))
            payload = {
                "success": True,
                "user_id": entry.user_id,
                "slot_id": entry.slot_id,
                "cdp_port": entry.cdp_port,
                "status": entry.status,
            }
        elif name == "xianyu_list_users":
            payload = {"success": True, "users": manager.list_user_statuses()}
        elif name == "xianyu_get_user_status":
            payload = {"success": True, **manager.get_user_status(arguments["user_id"])}
        elif name == "xianyu_login":
            payload = await manager.debug_login(arguments.get("user_id"))
        elif name == "xianyu_search":
            payload = await manager.debug_search(
                keyword=arguments["keyword"],
                user_id=arguments.get("user_id"),
                rows=arguments.get("rows", 30),
                min_price=arguments.get("min_price"),
                max_price=arguments.get("max_price"),
                free_ship=arguments.get("free_ship", False),
                sort_field=arguments.get("sort_field", ""),
                sort_order=arguments.get("sort_order", ""),
            )
        elif name == "xianyu_publish":
            payload = await manager.publish(arguments["user_id"], arguments["item_url"], new_price=arguments.get("new_price"), new_description=arguments.get("new_description"), condition=arguments.get("condition", "全新"))
        elif name == "xianyu_refresh_token":
            payload = await manager.refresh_token(arguments["user_id"])
        elif name == "xianyu_check_session":
            payload = await manager.check_session(arguments["user_id"])
        elif name == "xianyu_browser_overview":
            payload = {"success": True, **(await manager.debug_browser_overview(arguments.get("user_id")))}
        else:
            return types.CallToolResult(content=[types.TextContent(type="text", text=f"未知工具：{name}")], isError=True)
        return types.CallToolResult(content=[types.TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))])
    except Exception as exc:
        return types.CallToolResult(content=[types.TextContent(type="text", text=str(exc))], isError=True)


async def run_server():
    manager = get_manager()
    if hasattr(manager, "ensure_initialized"):
        await manager.ensure_initialized()
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="xianyu-mcp",
                server_version="2.0.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )
```

Delete `get_app()`, `handle_show_qr()`, and all remaining single-user `XianyuApp` usage from `mcp_server/server.py`.

- [ ] **Step 4: Run the stdio tests to verify they pass**

Run: `pytest tests/test_http_server_unit.py -k "stdio" -v`

Expected: PASS with stdio MCP listing, routing, and startup-initialization tests green.

- [ ] **Step 5: Commit**

```bash
git add tests/test_http_server_unit.py mcp_server/server.py
git commit -m "feat: unify stdio mcp with multi-user runtime"
```

### Task 5: Update CLI tests and user-facing docs to `login`-only QR flow

**Files:**
- Modify: `tests/test_mcp_dev_cli.py`
- Modify: `README.md`
- Modify: `docs/mcp-e2e-regression.md`
- Modify: `docs/mcp-dev-cheatsheet.md`
- Modify: `docs/opencode-setup.md`
- Modify: `docs/claude-code-setup.md`
- Modify: `docs/api-protocol.md`
- Modify: `.claude/skills/xianyu-skill/SKILL.md`

- [ ] **Step 1: Update the failing CLI test away from `show_qr`**

Change `tests/test_mcp_dev_cli.py` from:

```python
def test_parse_call_rejects_missing_flag_value():
    module = load_module()

    try:
        module.parse_call_args(["xianyu_show_qr", "--user-id"])
    except ValueError as exc:
        assert "missing value" in str(exc)
    else:
        raise AssertionError("expected ValueError")
```

to:

```python
def test_parse_call_rejects_missing_flag_value():
    module = load_module()

    try:
        module.parse_call_args(["xianyu_login", "--user-id"])
    except ValueError as exc:
        assert "missing value" in str(exc)
    else:
        raise AssertionError("expected ValueError")
```

- [ ] **Step 2: Run the CLI test to verify it still passes after the rename**

Run: `pytest tests/test_mcp_dev_cli.py -v`

Expected: PASS with no remaining `xianyu_show_qr` reference in this test file.

- [ ] **Step 3: Update the docs and skill text to the new login flow**

Apply these representative content changes.

In `README.md`, keep the overview short and replace any QR references like this:

````md
在客户端中直接使用自然语言：

```text
登录闲鱼账号
搜索盲盒商品 rows=5
发布商品 https://www.goofish.com/item?id=xxx 价格150
```

详细工具说明见 `.claude/skills/xianyu-skill/SKILL.md`
````

In `docs/mcp-dev-cheatsheet.md`, replace the QR section and recommended flow with:

````md
登录并在需要时拿二维码：

```bash
./scripts/mcp-dev call xianyu_login --user-id user-001
```

3. 如果失效，直接重新调用登录

```bash
./scripts/mcp-dev call xianyu_login --user-id user-001
```
````

In `docs/mcp-e2e-regression.md`, replace the old QR checks with:

```md
- `curl --max-time 60 -X POST http://127.0.0.1:8080/rest/login -H "Content-Type: application/json" -d '{"user_id":"user-001"}'`
- `tools/call` 已覆盖：`xianyu_check_session`、`xianyu_search`、`xianyu_refresh_token`、`xianyu_login`
```

In `docs/opencode-setup.md`, replace the example block with:

````md
```bash
./scripts/mcp-dev call xianyu_list_users
./scripts/mcp-dev call xianyu_login --user-id user-001
./scripts/mcp-dev call xianyu_check_session --user-id user-001
./scripts/mcp-dev call xianyu_search --user-id user-001 --keyword 机械键盘 --rows 5
```
````

In `docs/api-protocol.md`, replace wording like this:

```md
- 调用 `xianyu_login` 重新登录；未登录时该接口直接返回二维码
```

In `.claude/skills/xianyu-skill/SKILL.md`, remove the `xianyu_show_qr` row and replace the login workflow with:

````md
### 新用户登录

1. `xianyu_create_user(display_name?)`
2. `xianyu_login(user_id)`
3. 把 `qr_code.public_url` 或 `qr_code.url` 发给用户
4. 用户扫码后执行 `xianyu_check_session(user_id)`
````

Also remove any remaining `show_qr` references from:

- `docs/claude-code-setup.md`
- `README.md`
- `docs/mcp-e2e-regression.md`
- `docs/mcp-dev-cheatsheet.md`
- `docs/opencode-setup.md`
- `docs/api-protocol.md`
- `.claude/skills/xianyu-skill/SKILL.md`

- [ ] **Step 4: Verify the documentation is aligned and `show_qr` is gone from current user-facing docs**

Run:

```bash
pytest tests/test_mcp_dev_cli.py -v && rg "xianyu_show_qr|/rest/show_qr|show_qr" README.md docs/mcp-e2e-regression.md docs/mcp-dev-cheatsheet.md docs/opencode-setup.md docs/claude-code-setup.md docs/api-protocol.md .claude/skills/xianyu-skill/SKILL.md
```

Expected:

- `tests/test_mcp_dev_cli.py` PASS
- `rg` shows no matches in the user-facing files listed above

- [ ] **Step 5: Commit**

```bash
git add tests/test_mcp_dev_cli.py README.md docs/mcp-e2e-regression.md docs/mcp-dev-cheatsheet.md docs/opencode-setup.md docs/claude-code-setup.md docs/api-protocol.md .claude/skills/xianyu-skill/SKILL.md
git commit -m "docs: switch qr guidance to login-only flow"
```

## Self-Review

- Spec coverage: Task 1 and Task 2 cover multi-user keepalive ownership and runtime state; Task 3 covers HTTP debug entrypoints and `/rest/login`; Task 4 covers stdio MCP migration away from `default`; Task 5 covers docs, skill text, and regression guidance.
- Placeholder scan: No `TODO`/`TBD` markers remain, and each code task includes concrete snippets and commands.
- Type consistency: The plan consistently uses `debug_login`, `debug_check_session`, `debug_search`, `debug_browser_overview`, `ensure_initialized`, and `ensure_keepalive` as the new manager-facing method names.
