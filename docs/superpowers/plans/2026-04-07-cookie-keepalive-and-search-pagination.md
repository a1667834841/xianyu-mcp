# Cookie Keepalive And Search Pagination Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add host-persistent cookie/profile storage, a background page-refresh keepalive loop, and reliable search pagination that keeps collecting unique items until the requested total is reached or the stale-page limit is hit.

**Architecture:** Centralize runtime settings in one module, split browser usage into a shared-context `work_page` and `keepalive_page`, and move keepalive into a dedicated service that only refreshes the keepalive page. Refactor search to run under a work-page lock with per-request response collection and stale-page accounting, then expose the new search metadata through both MCP servers and the Docker/runtime configuration.

**Tech Stack:** Python 3.11, asyncio, Playwright CDP, pytest, Docker Compose, FastMCP

---

> Note: This workspace snapshot is not a git repository. The commit steps below assume execution in the source repository. If you are implementing in this exact snapshot, skip only the `git commit` command.

## File Map

- Create: `src/settings.py`
  Runtime settings loader, environment-variable precedence, multi-user storage path derivation.
- Create: `src/keepalive.py`
  Background cookie keepalive service that owns the periodic page refresh loop.
- Create: `tests/test_settings.py`
  Focused tests for config precedence and derived storage paths.
- Create: `tests/test_keepalive.py`
  Focused tests for dual-page behavior and the keepalive loop.
- Create: `tests/test_search_pagination.py`
  Focused tests for search pagination, stale-page stopping, and stale-response rejection.
- Create: `tests/test_http_server_unit.py`
  Focused tests for MCP search response metadata and app keepalive startup behavior.
- Modify: `src/browser.py`
  Use resolved settings, manage `work_page` and `keepalive_page`, keep `page` as a compatibility alias for `work_page`.
- Modify: `src/session.py`
  Use resolved `token_file`, save richer cookie snapshots, expose a helper for writing fresh cookies after keepalive runs.
- Modify: `src/core.py`
  Add `SearchOutcome`, work-page locking, keepalive lifecycle integration, and corrected pagination logic.
- Modify: `src/__init__.py`
  Export settings and search metadata types.
- Modify: `mcp_server/http_server.py`
  Start keepalive on app creation, return search metadata, update tool descriptions.
- Modify: `mcp_server/server.py`
  Start keepalive on app creation, stop it on shutdown, update tool descriptions.
- Modify: `config.json`
  Add `storage`, `keepalive`, and `search` sections.
- Modify: `docker-compose.yml`
  Move Chrome profile mount to the browser container, add per-user host path wiring, inject new env vars.
- Modify: `README.md`
  Document the new storage layout, keepalive behavior, and `rows` semantics.
- Modify: `docker/README.md`
  Document the new Docker env vars, host directory layout, and browser profile mount.

### Task 1: Centralize Runtime Settings And Storage Paths

**Files:**
- Create: `src/settings.py`
- Create: `tests/test_settings.py`
- Modify: `src/__init__.py`
- Modify: `config.json`

- [ ] **Step 1: Write the failing settings tests**

```python
import json
from pathlib import Path

from src.settings import load_settings


def write_config(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_load_settings_prefers_env_over_config(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    write_config(
        config_path,
        {
            "storage": {"data_root": "/config-users", "user_id": "config-user"},
            "keepalive": {"enabled": False, "interval_minutes": 30},
            "search": {"max_stale_pages": 5},
        },
    )

    monkeypatch.setenv("XIANYU_DATA_ROOT", "/env-users")
    monkeypatch.setenv("XIANYU_USER_ID", "env-user")
    monkeypatch.setenv("XIANYU_KEEPALIVE_ENABLED", "true")
    monkeypatch.setenv("XIANYU_KEEPALIVE_INTERVAL_MINUTES", "10")
    monkeypatch.setenv("XIANYU_SEARCH_MAX_STALE_PAGES", "3")

    settings = load_settings(config_path=config_path)

    assert str(settings.storage.data_root) == "/env-users"
    assert settings.storage.user_id == "env-user"
    assert str(settings.storage.token_file) == "/env-users/env-user/tokens/token.json"
    assert (
        str(settings.storage.chrome_user_data_dir)
        == "/env-users/env-user/chrome-profile"
    )
    assert settings.keepalive.enabled is True
    assert settings.keepalive.interval_minutes == 10
    assert settings.search.max_stale_pages == 3


def test_load_settings_derives_paths_from_config(tmp_path):
    users_root = tmp_path / "users"
    config_path = tmp_path / "config.json"
    write_config(
        config_path,
        {
            "storage": {"data_root": str(users_root), "user_id": "default"},
            "keepalive": {"enabled": True, "interval_minutes": 15},
            "search": {"max_stale_pages": 4},
        },
    )

    settings = load_settings(config_path=config_path)

    assert settings.storage.data_root == users_root
    assert settings.storage.user_id == "default"
    assert settings.storage.token_file == users_root / "default" / "tokens" / "token.json"
    assert settings.storage.chrome_user_data_dir == users_root / "default" / "chrome-profile"
    assert settings.keepalive.enabled is True
    assert settings.keepalive.interval_minutes == 15
    assert settings.search.max_stale_pages == 4
```

- [ ] **Step 2: Run the settings tests to verify they fail**

Run: `pytest tests/test_settings.py -v`

Expected: `ModuleNotFoundError: No module named 'src.settings'`

- [ ] **Step 3: Implement `src/settings.py`**

```python
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class StorageSettings:
    data_root: Path
    user_id: str
    token_file: Path
    chrome_user_data_dir: Path


@dataclass(frozen=True)
class KeepaliveSettings:
    enabled: bool
    interval_minutes: int


@dataclass(frozen=True)
class SearchSettings:
    max_stale_pages: int


@dataclass(frozen=True)
class AppSettings:
    storage: StorageSettings
    keepalive: KeepaliveSettings
    search: SearchSettings


def _expand_path(value: str) -> Path:
    return Path(value).expanduser()


def _read_config(config_path: Path | None = None) -> dict[str, Any]:
    candidate = config_path or (Path(__file__).parent.parent / "config.json")
    if not candidate.exists():
        return {}
    return json.loads(candidate.read_text(encoding="utf-8"))


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    return int(value) if value is not None else default


def load_settings(config_path: Path | None = None) -> AppSettings:
    raw = _read_config(config_path)

    storage_raw = raw.get("storage", {})
    keepalive_raw = raw.get("keepalive", {})
    search_raw = raw.get("search", {})

    data_root_value = os.environ.get("XIANYU_DATA_ROOT") or storage_raw.get(
        "data_root",
        str(Path.home() / ".claude" / "xianyu-data" / "users"),
    )
    user_id = os.environ.get("XIANYU_USER_ID") or storage_raw.get("user_id", "default")

    data_root = _expand_path(data_root_value)
    user_root = data_root / user_id

    token_file_value = os.environ.get("XIANYU_TOKEN_FILE") or storage_raw.get("token_file")
    chrome_dir_value = os.environ.get("XIANYU_CHROME_USER_DATA_DIR") or storage_raw.get(
        "chrome_user_data_dir"
    )

    token_file = (
        _expand_path(token_file_value)
        if token_file_value
        else user_root / "tokens" / "token.json"
    )
    chrome_user_data_dir = (
        _expand_path(chrome_dir_value)
        if chrome_dir_value
        else user_root / "chrome-profile"
    )

    return AppSettings(
        storage=StorageSettings(
            data_root=data_root,
            user_id=user_id,
            token_file=token_file,
            chrome_user_data_dir=chrome_user_data_dir,
        ),
        keepalive=KeepaliveSettings(
            enabled=_env_bool(
                "XIANYU_KEEPALIVE_ENABLED",
                keepalive_raw.get("enabled", True),
            ),
            interval_minutes=_env_int(
                "XIANYU_KEEPALIVE_INTERVAL_MINUTES",
                int(keepalive_raw.get("interval_minutes", 10)),
            ),
        ),
        search=SearchSettings(
            max_stale_pages=_env_int(
                "XIANYU_SEARCH_MAX_STALE_PAGES",
                int(search_raw.get("max_stale_pages", 3)),
            )
        ),
    )
```

- [ ] **Step 4: Export settings and add the new config sections**

```python
# src/__init__.py
from .settings import AppSettings, KeepaliveSettings, SearchSettings, StorageSettings, load_settings

__all__ = [
    "AsyncChromeManager",
    "ChromeManager",
    "SessionManager",
    "XianyuApp",
    "AppSettings",
    "StorageSettings",
    "KeepaliveSettings",
    "SearchSettings",
    "load_settings",
    "SearchItem",
    "SearchParams",
    "CopiedItem",
    "login",
    "refresh_token",
    "check_cookie_valid",
    "search",
    "publish",
    "get_detail",
]
```

```json
// config.json
{
  "chrome": {
    "path": {
      "macos": "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
      "linux": "/usr/bin/google-chrome",
      "windows": "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
    },
    "port": 9222,
    "user_data_dir": "~/.claude/xianyu-chrome-profile"
  },
  "storage": {
    "data_root": "~/.claude/xianyu-data/users",
    "user_id": "default",
    "token_file": "",
    "chrome_user_data_dir": ""
  },
  "keepalive": {
    "enabled": true,
    "interval_minutes": 10
  },
  "search": {
    "max_stale_pages": 3
  }
}
```

- [ ] **Step 5: Run the settings tests to verify they pass**

Run: `pytest tests/test_settings.py -v`

Expected: `2 passed`

- [ ] **Step 6: Commit the settings work**

```bash
git add src/settings.py src/__init__.py config.json tests/test_settings.py
git commit -m "feat: add centralized runtime settings"
```

### Task 2: Wire Settings Into Browser And Session, Then Add Page Roles

**Files:**
- Modify: `src/browser.py`
- Modify: `src/session.py`
- Create: `tests/test_keepalive.py`

- [ ] **Step 1: Write the failing browser/session tests**

```python
import json
from types import SimpleNamespace

import pytest

from src.browser import AsyncChromeManager
from src.session import SessionManager
from src.settings import AppSettings, KeepaliveSettings, SearchSettings, StorageSettings


class FakePage:
    pass


class FakeContext:
    def __init__(self):
        self.pages = [FakePage()]

    async def new_page(self):
        page = FakePage()
        self.pages.append(page)
        return page


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
async def test_browser_page_roles_are_distinct(tmp_path):
    manager = AsyncChromeManager(auto_start=False, settings=make_settings(tmp_path))
    manager.context = FakeContext()
    manager.page = manager.context.pages[0]

    work_page = await manager.get_work_page()
    keepalive_page = await manager.get_keepalive_page()

    assert work_page is manager.context.pages[0]
    assert keepalive_page is manager.context.pages[1]
    assert await manager.get_keepalive_page() is keepalive_page
    assert manager.page is work_page


def test_session_manager_uses_resolved_token_file(tmp_path):
    settings = make_settings(tmp_path)
    session = SessionManager(chrome_manager=SimpleNamespace(), settings=settings)

    session.save_cookie("a=1; b=2")

    data = json.loads(settings.storage.token_file.read_text(encoding="utf-8"))
    assert data["full_cookie"] == "a=1; b=2"
    assert "updated_at" in data
    assert "last_refresh_at" in data
```

- [ ] **Step 2: Run the browser/session tests to verify they fail**

Run: `pytest tests/test_keepalive.py -v`

Expected: `TypeError` because `AsyncChromeManager` and `SessionManager` do not accept a `settings` keyword argument yet.

- [ ] **Step 3: Update `src/browser.py` to use `AppSettings` and page roles**

```python
# src/browser.py
from .settings import AppSettings, load_settings


class AsyncChromeManager:
    def __init__(
        self,
        port: int = DEFAULT_PORT,
        host: str = DEFAULT_HOST,
        user_data_dir: Optional[Path] = None,
        headless: bool = False,
        auto_start: bool = True,
        config: Optional[Dict] = None,
        settings: Optional[AppSettings] = None,
    ):
        self.settings = settings or load_settings()
        self.config = config or load_config()

        chrome_config = self.config.get("chrome", {})
        self.port = port or chrome_config.get("port", self.DEFAULT_PORT)
        self.host = host
        self.user_data_dir = (
            user_data_dir
            or self.settings.storage.chrome_user_data_dir
        )
        self.headless = headless
        self.auto_start = auto_start

        self._work_page: Optional[Page] = None
        self._keepalive_page: Optional[Page] = None
        self.page: Optional[Page] = None

        self.user_data_dir.mkdir(parents=True, exist_ok=True)

    async def get_work_page(self) -> Page:
        if self._work_page:
            self.page = self._work_page
            return self._work_page

        if self.context and self.context.pages:
            self._work_page = self.context.pages[0]
        else:
            self._work_page = await self.context.new_page()

        self.page = self._work_page
        return self._work_page

    async def get_keepalive_page(self) -> Page:
        if self._keepalive_page:
            return self._keepalive_page

        work_page = await self.get_work_page()
        if self.context and len(self.context.pages) > 1:
            for candidate in self.context.pages:
                if candidate is not work_page:
                    self._keepalive_page = candidate
                    return candidate

        self._keepalive_page = await self.context.new_page()
        return self._keepalive_page

    async def connect(self) -> bool:
        try:
            self.playwright = await async_playwright().start()

            ws_url = await self._get_websocket_url()
            if not ws_url:
                ws_url = f"ws://{self.host}:{self.port}"

            self.browser = await self.playwright.chromium.connect_over_cdp(ws_url)
            self.context = (
                self.browser.contexts[0]
                if self.browser.contexts
                else await self.browser.new_context()
            )

            if self.context.pages:
                self._work_page = self.context.pages[0]
            else:
                self._work_page = await self.context.new_page()

            self.page = self._work_page
            return True
        except Exception as e:
            print(f"[Browser] 连接失败：{e}")
            return False
```

- [ ] **Step 4: Update `src/session.py` to use resolved storage and richer cookie snapshots**

```python
# src/session.py
from .settings import AppSettings, load_settings


class SessionManager:
    def __init__(
        self,
        chrome_manager: Optional[AsyncChromeManager] = None,
        settings: Optional[AppSettings] = None,
    ):
        self.settings = settings or load_settings()
        self.chrome_manager = chrome_manager or AsyncChromeManager(settings=self.settings)
        self.token: Optional[str] = None
        self.full_cookie: Optional[str] = None
        self.token_file = self.settings.storage.token_file
        self.token_file.parent.mkdir(parents=True, exist_ok=True)

    def save_cookie(self, full_cookie: str):
        try:
            now = datetime.now()
            expires_at = now + timedelta(hours=self.TOKEN_EXPIRY_HOURS)
            existing = {}
            if self.token_file.exists():
                existing = json.loads(self.token_file.read_text(encoding="utf-8"))

            data = {
                "full_cookie": full_cookie,
                "created_at": existing.get("created_at", now.isoformat()),
                "updated_at": now.isoformat() if existing.get("full_cookie") != full_cookie else existing.get("updated_at", now.isoformat()),
                "last_refresh_at": now.isoformat(),
                "expires_at": expires_at.isoformat(),
            }

            with open(self.token_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[Session] 保存 Cookie 失败：{e}")
```

- [ ] **Step 5: Run the browser/session tests to verify they pass**

Run: `pytest tests/test_keepalive.py -v`

Expected: `2 passed`

- [ ] **Step 6: Commit the browser/session wiring**

```bash
git add src/browser.py src/session.py tests/test_keepalive.py
git commit -m "feat: add page roles and resolved cookie storage"
```

### Task 3: Add The Background Keepalive Service And App Lifecycle Hooks

**Files:**
- Create: `src/keepalive.py`
- Modify: `src/core.py`
- Modify: `src/__init__.py`
- Modify: `mcp_server/http_server.py`
- Modify: `mcp_server/server.py`
- Modify: `tests/test_keepalive.py`
- Create: `tests/test_http_server_unit.py`

- [ ] **Step 1: Write the failing keepalive tests**

```python
import json
from types import SimpleNamespace

import pytest

from src.keepalive import CookieKeepaliveService


class FakeKeepalivePage:
    def __init__(self):
        self.calls = []

    async def goto(self, url, wait_until="networkidle", timeout=30000):
        self.calls.append(("goto", url, wait_until))

    async def reload(self, wait_until="networkidle", timeout=30000):
        self.calls.append(("reload", wait_until))


class FakeBrowser:
    def __init__(self):
        self.keepalive_page = FakeKeepalivePage()
        self.cookies = ["a=1", "a=2"]

    async def ensure_running(self):
        return True

    async def get_keepalive_page(self):
        return self.keepalive_page

    async def get_full_cookie_string(self):
        return self.cookies.pop(0)


class RecordingSession:
    def __init__(self):
        self.saved = []

    def save_cookie(self, cookie):
        self.saved.append(cookie)


@pytest.mark.asyncio
async def test_keepalive_service_initializes_then_reloads():
    browser = FakeBrowser()
    session = RecordingSession()
    service = CookieKeepaliveService(browser=browser, session=session, interval_minutes=10)

    await service.run_once()
    await service.run_once()

    assert browser.keepalive_page.calls == [
        ("goto", "https://www.goofish.com", "networkidle"),
        ("reload", "networkidle"),
    ]
    assert session.saved == ["a=1", "a=2"]
```

```python
import json

import pytest

import mcp_server.http_server as http_server


class FakeApp:
    def __init__(self):
        self.started = 0

    def start_background_tasks(self):
        self.started += 1


def test_http_server_get_app_starts_background_tasks(monkeypatch):
    fake_app = FakeApp()
    monkeypatch.setattr(http_server, "_app", None)
    monkeypatch.setattr(http_server, "XianyuApp", lambda browser: fake_app)

    app = http_server.get_app()

    assert app is fake_app
    assert fake_app.started == 1
```

- [ ] **Step 2: Run the keepalive tests to verify they fail**

Run: `pytest tests/test_keepalive.py tests/test_http_server_unit.py -v`

Expected: `ModuleNotFoundError: No module named 'src.keepalive'`

- [ ] **Step 3: Create `src/keepalive.py`**

```python
from __future__ import annotations

import asyncio
from typing import Optional


class CookieKeepaliveService:
    def __init__(self, browser, session, interval_minutes: int):
        self.browser = browser
        self.session = session
        self.interval_seconds = interval_minutes * 60
        self._task: Optional[asyncio.Task] = None
        self._initialized = False

    def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        if not self._task:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def run_once(self) -> None:
        if not await self.browser.ensure_running():
            print("[Keepalive] 浏览器未就绪")
            return

        page = await self.browser.get_keepalive_page()
        try:
            if not self._initialized:
                await page.goto("https://www.goofish.com", wait_until="networkidle", timeout=30000)
                self._initialized = True
            else:
                await page.reload(wait_until="networkidle", timeout=30000)

            full_cookie = await self.browser.get_full_cookie_string()
            if full_cookie:
                self.session.save_cookie(full_cookie)
            else:
                print("[Keepalive] 未获取到有效 Cookie")
        except Exception as exc:
            print(f"[Keepalive] 刷新失败：{exc}")

    async def _run_loop(self) -> None:
        while True:
            await self.run_once()
            await asyncio.sleep(self.interval_seconds)
```

- [ ] **Step 4: Wire keepalive into `XianyuApp` and both MCP servers**

```python
# src/core.py
from .keepalive import CookieKeepaliveService
from .settings import AppSettings, load_settings


class XianyuApp:
    def __init__(self, browser: Optional[AsyncChromeManager] = None, settings: Optional[AppSettings] = None):
        self.settings = settings or load_settings()
        self.browser = browser or AsyncChromeManager(settings=self.settings)
        self.session = SessionManager(self.browser, settings=self.settings)
        self._work_lock = asyncio.Lock()
        self._keepalive = CookieKeepaliveService(
            browser=self.browser,
            session=self.session,
            interval_minutes=self.settings.keepalive.interval_minutes,
        )

    def start_background_tasks(self) -> None:
        if self.settings.keepalive.enabled:
            self._keepalive.start()

    async def stop_background_tasks(self) -> None:
        await self._keepalive.stop()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop_background_tasks()
        await self.browser.close()
```

```python
# mcp_server/http_server.py
def get_app() -> XianyuApp:
    global _app
    if _app is None:
        browser = AsyncChromeManager(
            host=CDP_HOST,
            port=CDP_PORT,
            auto_start=False,
        )
        _app = XianyuApp(browser)
        _app.start_background_tasks()
    return _app
```

```python
# mcp_server/server.py
def get_app() -> XianyuApp:
    global _app
    if _app is None:
        browser = AsyncChromeManager(
            host=CDP_HOST,
            port=CDP_PORT,
            auto_start=(CDP_HOST == "localhost"),
        )
        _app = XianyuApp(browser)
        _app.start_background_tasks()
    return _app


async def run_server():
    try:
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
    finally:
        if _app is not None:
            await _app.stop_background_tasks()
```

- [ ] **Step 5: Run the keepalive tests to verify they pass**

Run: `pytest tests/test_keepalive.py tests/test_http_server_unit.py -v`

Expected: `3 passed`

- [ ] **Step 6: Commit the keepalive service**

```bash
git add src/keepalive.py src/core.py src/__init__.py mcp_server/http_server.py mcp_server/server.py tests/test_keepalive.py tests/test_http_server_unit.py
git commit -m "feat: add background cookie keepalive service"
```

### Task 4: Refactor Search Pagination To Collect Unique Results Reliably

**Files:**
- Modify: `src/core.py`
- Create: `tests/test_search_pagination.py`

- [ ] **Step 1: Write the failing pagination tests**

```python
import pytest

from src.core import SearchItem, SearchOutcome, SearchParams, _BrowserSearchImpl


def make_item(item_id: str) -> SearchItem:
    return SearchItem(
        item_id=item_id,
        title=f"title-{item_id}",
        price="100",
        original_price="120",
        want_cnt=1,
        seller_nick="seller",
        seller_city="Hangzhou",
        image_urls=[],
        detail_url=f"https://www.goofish.com/item?id={item_id}",
        is_free_ship=False,
        publish_time=None,
        exposure_score=1.0,
    )


class DummyBrowser:
    async def ensure_running(self):
        return True


class FakeSearchImpl(_BrowserSearchImpl):
    def __init__(self, pages, response_flags, max_stale_pages=3):
        super().__init__(DummyBrowser(), max_stale_pages=max_stale_pages)
        self.pages = pages
        self.response_flags = response_flags
        self.page_index = 0

    async def _setup_response_listener(self):
        return None

    async def _navigate_to_home(self):
        return None

    async def _input_search_keyword(self, keyword: str):
        return None

    async def _apply_filters(self, params: SearchParams):
        return None

    async def _wait_for_api_response(self, timeout: int = 30, clear: bool = False):
        return self.response_flags[self.page_index]

    async def _wait_for_new_api_response(self, timeout: int = 30, prev_count: int = 0):
        return self.response_flags[self.page_index]

    async def _next_page(self, page: int):
        self.page_index = min(self.page_index + 1, len(self.pages) - 1)

    def _parse_results(self):
        return self.pages[self.page_index]


@pytest.mark.asyncio
async def test_search_collects_until_requested_rows():
    pages = [
        [make_item(f"a-{i}") for i in range(30)],
        [make_item(f"b-{i}") for i in range(30)],
        [make_item(f"c-{i}") for i in range(50)],
    ]
    searcher = FakeSearchImpl(pages=pages, response_flags=[True, True, True], max_stale_pages=3)

    outcome = await searcher.search(SearchParams(keyword="键盘", rows=100))

    assert isinstance(outcome, SearchOutcome)
    assert len(outcome.items) == 100
    assert outcome.stop_reason == "target_reached"
    assert outcome.stale_pages == 0


@pytest.mark.asyncio
async def test_search_stops_after_configured_stale_pages():
    repeated_page = [make_item(f"same-{i}") for i in range(30)]
    searcher = FakeSearchImpl(
        pages=[repeated_page, repeated_page, repeated_page, repeated_page],
        response_flags=[True, True, True, True],
        max_stale_pages=2,
    )

    outcome = await searcher.search(SearchParams(keyword="键盘", rows=100))

    assert len(outcome.items) == 30
    assert outcome.stop_reason == "stale_limit"
    assert outcome.stale_pages == 2


@pytest.mark.asyncio
async def test_search_does_not_reparse_old_response_when_no_new_response():
    searcher = FakeSearchImpl(
        pages=[
            [make_item(f"a-{i}") for i in range(30)],
            [make_item(f"b-{i}") for i in range(30)],
        ],
        response_flags=[True, False],
        max_stale_pages=1,
    )

    outcome = await searcher.search(SearchParams(keyword="键盘", rows=60))

    assert len(outcome.items) == 30
    assert outcome.stop_reason == "stale_limit"
    assert outcome.stale_pages == 1
```

- [ ] **Step 2: Run the pagination tests to verify they fail**

Run: `pytest tests/test_search_pagination.py -v`

Expected: `ImportError` for `SearchOutcome` or assertion failures because `search()` still returns a list and reparses stale data.

- [ ] **Step 3: Add `SearchOutcome` and correct pagination flow in `src/core.py`**

```python
@dataclass
class SearchOutcome:
    items: List[SearchItem]
    requested_rows: int
    returned_rows: int
    stop_reason: str
    stale_pages: int


class XianyuApp:
    async def search(self, keyword: str, **options) -> List[SearchItem]:
        outcome = await self.search_with_meta(keyword, **options)
        return outcome.items

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

        async with self._work_lock:
            page = await self.browser.get_work_page()
            self.browser.page = page
            searcher = _BrowserSearchImpl(
                self.browser,
                max_stale_pages=self.settings.search.max_stale_pages,
            )
            return await searcher.search(params)
```

```python
class _BrowserSearchImpl:
    def __init__(self, chrome_manager: AsyncChromeManager, max_stale_pages: int = 3):
        self.chrome_manager = chrome_manager
        self.max_stale_pages = max_stale_pages
        self.search_results: List[Dict[str, Any]] = []

    async def search(self, params: SearchParams, timeout: int = 30) -> SearchOutcome:
        self.search_results = []
        all_items: List[SearchItem] = []
        seen_item_ids: set[str] = set()
        stale_pages = 0

        if not await self.chrome_manager.ensure_running():
            raise RuntimeError("无法启动浏览器")

        await self._setup_response_listener()
        await self._navigate_to_home()
        await asyncio.sleep(1)
        await self._input_search_keyword(params.keyword)
        await asyncio.sleep(2)
        await self._apply_filters(params)

        page = 1
        while len(all_items) < params.rows:
            if page == 1:
                has_new_response = await self._wait_for_api_response(timeout, clear=True)
            else:
                prev_count = len(self._captured_responses)
                await self._next_page(page)
                has_new_response = await self._wait_for_new_api_response(timeout, prev_count)

            items = self._parse_results() if has_new_response else []

            new_count = 0
            for item in items:
                if item.item_id not in seen_item_ids:
                    seen_item_ids.add(item.item_id)
                    all_items.append(item)
                    new_count += 1

            if len(all_items) >= params.rows:
                result = all_items[: params.rows]
                return SearchOutcome(
                    items=result,
                    requested_rows=params.rows,
                    returned_rows=len(result),
                    stop_reason="target_reached",
                    stale_pages=stale_pages,
                )

            if new_count == 0:
                stale_pages += 1
            else:
                stale_pages = 0

            if stale_pages >= self.max_stale_pages:
                return SearchOutcome(
                    items=all_items,
                    requested_rows=params.rows,
                    returned_rows=len(all_items),
                    stop_reason="stale_limit",
                    stale_pages=stale_pages,
                )

            page += 1

        return SearchOutcome(
            items=all_items[: params.rows],
            requested_rows=params.rows,
            returned_rows=min(len(all_items), params.rows),
            stop_reason="target_reached",
            stale_pages=stale_pages,
        )

    async def _wait_for_api_response(self, timeout: int = 30, clear: bool = False) -> bool:
        if clear:
            self._response_event.clear()
            self._captured_responses = []

        try:
            await asyncio.wait_for(self._response_event.wait(), timeout=timeout)
            self.search_results = self._captured_responses
            return bool(self._captured_responses)
        except asyncio.TimeoutError:
            return False

    async def _wait_for_new_api_response(self, timeout: int = 30, prev_count: int = 0) -> bool:
        self._response_event.clear()
        start_time = time.time()
        while time.time() - start_time < timeout:
            if len(self._captured_responses) > prev_count:
                self.search_results = self._captured_responses
                return True
            await asyncio.sleep(0.5)
        return False
```

- [ ] **Step 4: Run the pagination tests to verify they pass**

Run: `pytest tests/test_search_pagination.py -v`

Expected: `3 passed`

- [ ] **Step 5: Commit the pagination refactor**

```bash
git add src/core.py tests/test_search_pagination.py
git commit -m "fix: continue search pagination until target rows"
```

### Task 5: Expose Search Metadata And Update Docker And Documentation

**Files:**
- Modify: `mcp_server/http_server.py`
- Modify: `mcp_server/server.py`
- Modify: `docker-compose.yml`
- Modify: `README.md`
- Modify: `docker/README.md`
- Modify: `tests/test_http_server_unit.py`

- [ ] **Step 1: Write the failing MCP search response test**

```python
import json
from types import SimpleNamespace

import pytest

import mcp_server.http_server as http_server
from src.core import SearchItem, SearchOutcome


def make_item(item_id: str) -> SearchItem:
    return SearchItem(
        item_id=item_id,
        title=f"title-{item_id}",
        price="100",
        original_price="120",
        want_cnt=1,
        seller_nick="seller",
        seller_city="Hangzhou",
        image_urls=[],
        detail_url=f"https://www.goofish.com/item?id={item_id}",
        is_free_ship=False,
        publish_time=None,
        exposure_score=1.0,
    )


class FakeBrowser:
    async def ensure_running(self):
        return True


class FakeAppWithSearch:
    def __init__(self):
        self.browser = FakeBrowser()

    async def search_with_meta(self, keyword: str, **options):
        return SearchOutcome(
            items=[make_item("item-1")],
            requested_rows=100,
            returned_rows=1,
            stop_reason="stale_limit",
            stale_pages=3,
        )


@pytest.mark.asyncio
async def test_xianyu_search_returns_requested_and_stop_reason(monkeypatch):
    monkeypatch.setattr(http_server, "get_app", lambda: FakeAppWithSearch())

    payload = json.loads(await http_server.xianyu_search(keyword="键盘", rows=100))

    assert payload["requested"] == 100
    assert payload["total"] == 1
    assert payload["stop_reason"] == "stale_limit"
    assert payload["stale_pages"] == 3
```

- [ ] **Step 2: Run the MCP search response test to verify it fails**

Run: `pytest tests/test_http_server_unit.py::test_xianyu_search_returns_requested_and_stop_reason -v`

Expected: assertion failure because the current response only includes `success`, `total`, and `items`.

- [ ] **Step 3: Update both MCP servers to use `search_with_meta()` and correct the tool descriptions**

```python
# mcp_server/http_server.py
@mcp.tool()
async def xianyu_search(
    keyword: str,
    rows: int = 30,
    min_price: float | None = None,
    max_price: float | None = None,
    free_ship: bool = False,
    sort_field: str = "",
    sort_order: str = "",
) -> str:
    """
    通过关键词搜索闲鱼商品，返回目标数量内的唯一商品列表。

    Args:
        keyword: 搜索关键词
        rows: 目标唯一商品总数，默认 30
        min_price: 最低价格（可选）
        max_price: 最高价格（可选）
        free_ship: 是否只看包邮，默认 false
        sort_field: 排序字段：pub_time（发布时间）或 price（价格）
        sort_order: 排序方向：ASC（升序）或 DESC（降序）
    """
    app = get_app()
    await app.browser.ensure_running()

    outcome = await app.search_with_meta(
        keyword=keyword,
        rows=rows,
        min_price=min_price,
        max_price=max_price,
        free_ship=free_ship,
        sort_field=sort_field,
        sort_order=sort_order,
    )

    items = [asdict(item) for item in outcome.items]
    result = {
        "success": True,
        "requested": outcome.requested_rows,
        "total": outcome.returned_rows,
        "stop_reason": outcome.stop_reason,
        "stale_pages": outcome.stale_pages,
        "items": items,
    }
    return json.dumps(result, ensure_ascii=False, indent=2)
```

```python
# mcp_server/server.py
"rows": {
    "type": "integer",
    "description": "目标唯一商品总数，默认 30",
    "default": 30
}
```

- [ ] **Step 4: Update Docker Compose and docs for the new storage layout**

```yaml
# docker-compose.yml
services:
  browser:
    image: registry.cn-hangzhou.aliyuncs.com/ggball/chrome-headless-shell-zh:latest
    container_name: xianyu-browser
    restart: unless-stopped
    ports:
      - "9222:9222"
    environment:
      - HTTP_PROXY=${HTTP_PROXY:-}
      - HTTPS_PROXY=${HTTPS_PROXY:-}
      - NO_PROXY=${NO_PROXY:-localhost,127.0.0.1}
      - XIANYU_USER_ID=${XIANYU_USER_ID:-default}
    command:
      - --remote-debugging-address=0.0.0.0
      - --remote-debugging-port=9222
      - --user-data-dir=/data/users/${XIANYU_USER_ID:-default}/chrome-profile
      - --disable-dev-shm-usage
    volumes:
      - ${XIANYU_HOST_DATA_DIR:-./data}/users/${XIANYU_USER_ID:-default}/chrome-profile:/data/users/${XIANYU_USER_ID:-default}/chrome-profile
    shm_size: 2g
    networks:
      - xianyu-net

  mcp-server:
    build:
      context: .
      dockerfile: docker/Dockerfile
    container_name: xianyu-mcp
    restart: unless-stopped
    ports:
      - "8080:8080"
    environment:
      - CDP_HOST=${CDP_HOST:-browser}
      - CDP_PORT=${CDP_PORT:-9222}
      - MCP_HOST=${MCP_HOST:-0.0.0.0}
      - MCP_PORT=${MCP_PORT:-8080}
      - XIANYU_DATA_ROOT=/data/users
      - XIANYU_USER_ID=${XIANYU_USER_ID:-default}
      - XIANYU_KEEPALIVE_ENABLED=${XIANYU_KEEPALIVE_ENABLED:-true}
      - XIANYU_KEEPALIVE_INTERVAL_MINUTES=${XIANYU_KEEPALIVE_INTERVAL_MINUTES:-10}
      - XIANYU_SEARCH_MAX_STALE_PAGES=${XIANYU_SEARCH_MAX_STALE_PAGES:-3}
      - CF_ACCOUNT_ID=${CF_ACCOUNT_ID:-}
      - CF_ACCESS_KEY_ID=${CF_ACCESS_KEY_ID:-}
      - CF_SECRET_ACCESS_KEY=${CF_SECRET_ACCESS_KEY:-}
      - CF_BUCKET_NAME=${CF_BUCKET_NAME:-blog}
      - CF_PUBLIC_DOMAIN=${CF_PUBLIC_DOMAIN:-https://img.ggball.top}
    volumes:
      - ${XIANYU_HOST_DATA_DIR:-./data}/users/${XIANYU_USER_ID:-default}/tokens:/data/users/${XIANYU_USER_ID:-default}/tokens
    depends_on:
      - browser
    networks:
      - xianyu-net
```

```markdown
# README.md
- **登录能力** (`xianyu-login`) - 扫码登录获取 Token，Cookie 快照持久化到用户目录
- **后台保活** - MCP Server 启动后在独立 `keepalive_page` 上按间隔刷新首页，自动落盘最新 Cookie
- **搜索能力** (`xianyu-search`) - `rows` 表示目标唯一商品总数，不足时继续翻页，直到凑够或连续 stale page 达到阈值

## 持久化目录

- 浏览器 Profile: `/data/users/<user_id>/chrome-profile`
- Cookie 快照: `/data/users/<user_id>/tokens/token.json`

Docker 环境可通过以下变量控制：

- `XIANYU_HOST_DATA_DIR`
- `XIANYU_USER_ID`
- `XIANYU_KEEPALIVE_ENABLED`
- `XIANYU_KEEPALIVE_INTERVAL_MINUTES`
- `XIANYU_SEARCH_MAX_STALE_PAGES`
```

```markdown
# docker/README.md
### 新增环境变量

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `XIANYU_HOST_DATA_DIR` | 宿主机数据根目录 | `./data` |
| `XIANYU_USER_ID` | 当前用户目录名 | `default` |
| `XIANYU_KEEPALIVE_ENABLED` | 是否启用后台保活 | `true` |
| `XIANYU_KEEPALIVE_INTERVAL_MINUTES` | 页面刷新间隔（分钟） | `10` |
| `XIANYU_SEARCH_MAX_STALE_PAGES` | 连续无新增页上限 | `3` |
```

- [ ] **Step 5: Run the focused server test and one full regression slice**

Run: `pytest tests/test_http_server_unit.py::test_xianyu_search_returns_requested_and_stop_reason -v`

Expected: `1 passed`

Run: `pytest tests/test_settings.py tests/test_keepalive.py tests/test_search_pagination.py tests/test_http_server_unit.py -v`

Expected: all targeted tests pass.

- [ ] **Step 6: Commit the server, Docker, and docs updates**

```bash
git add mcp_server/http_server.py mcp_server/server.py docker-compose.yml README.md docker/README.md tests/test_http_server_unit.py
git commit -m "feat: expose search meta and persistent docker storage"
```

## Self-Review Checklist

- Spec coverage:
  - Storage and host persistence: Task 1, Task 2, Task 5
  - Background keepalive: Task 2, Task 3
  - `rows` as target total and stale-page stopping: Task 4, Task 5
  - MCP config/env support: Task 1, Task 5
  - Docker/browser profile mount fix: Task 5
- Placeholder scan:
  - No unresolved placeholders or shorthand references remain.
- Type consistency:
  - `AppSettings`, `CookieKeepaliveService`, `SearchOutcome`, `search_with_meta`, `get_work_page`, and `get_keepalive_page` are used with the same names in every task.
