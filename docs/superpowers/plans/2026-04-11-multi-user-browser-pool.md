# Multi-User Browser Pool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add multi-user support backed by a single browser container running a fixed-size pool of Chrome instances so multiple users can stay logged in and keep cookies alive concurrently while business operations remain globally serialized.

**Architecture:** Keep `XianyuApp`, `SessionManager`, and `AsyncChromeManager` as single-user units. Add a persisted user registry plus a `MultiUserManager` that binds users to browser slots, creates one single-user runtime per user, starts per-user keepalive tasks, and routes HTTP/SSE calls to the correct runtime. Extend the browser container to boot a fixed number of Chrome processes, each on its own CDP port and profile directory.

**Tech Stack:** Python 3.11, pytest, Playwright CDP, FastMCP/Starlette HTTP server, Docker Compose, shell startup scripts

---

### Task 1: Add browser pool configuration and registry models

**Files:**
- Modify: `src/settings.py`
- Create: `src/browser_pool.py`
- Test: `tests/test_multi_user_settings.py`

- [ ] **Step 1: Write the failing tests for browser pool and multi-user config parsing**

```python
from pathlib import Path

from src.settings import load_settings
from src.browser_pool import BrowserPoolSettings, BrowserSlot


def test_load_settings_keeps_single_user_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("XIANYU_DATA_ROOT", str(tmp_path / "users"))
    monkeypatch.setenv("XIANYU_USER_ID", "default")

    settings = load_settings()

    assert settings.storage.user_id == "default"
    assert settings.storage.token_file == tmp_path / "users" / "default" / "tokens" / "token.json"


def test_browser_pool_settings_from_config():
    config = {
        "multi_user": {
            "registry_file": "/data/registry/users.json",
            "default_display_name_prefix": "user",
        },
        "browser_pool": {
            "size": 3,
            "cdp_host": "browser",
            "start_port": 9222,
            "profile_root": "/data/browser-pool",
        },
    }

    settings = BrowserPoolSettings.from_config(config)

    assert settings.size == 3
    assert settings.cdp_host == "browser"
    assert settings.start_port == 9222
    assert settings.profile_root == Path("/data/browser-pool")


def test_browser_slot_profile_dir_uses_slot_id(tmp_path):
    slot = BrowserSlot(slot_id="slot-2", cdp_host="browser", cdp_port=9223, profile_dir=tmp_path / "slot-2" / "profile")

    assert slot.slot_id == "slot-2"
    assert slot.cdp_port == 9223
    assert slot.profile_dir == tmp_path / "slot-2" / "profile"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_multi_user_settings.py -v`
Expected: FAIL with import or attribute errors for `BrowserPoolSettings` / `BrowserSlot`

- [ ] **Step 3: Add browser pool models and config parsing**

```python
# src/browser_pool.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, MutableMapping


@dataclass(frozen=True)
class BrowserSlot:
    slot_id: str
    cdp_host: str
    cdp_port: int
    profile_dir: Path


@dataclass(frozen=True)
class BrowserPoolSettings:
    size: int
    cdp_host: str
    start_port: int
    profile_root: Path
    registry_file: Path
    default_display_name_prefix: str

    @classmethod
    def from_config(cls, config: MutableMapping[str, Any]) -> "BrowserPoolSettings":
        browser_pool = config.get("browser_pool") or {}
        multi_user = config.get("multi_user") or {}
        return cls(
            size=int(browser_pool.get("size", 1)),
            cdp_host=str(browser_pool.get("cdp_host", "browser")),
            start_port=int(browser_pool.get("start_port", 9222)),
            profile_root=Path(str(browser_pool.get("profile_root", "/data/browser-pool"))),
            registry_file=Path(str(multi_user.get("registry_file", "/data/registry/users.json"))),
            default_display_name_prefix=str(multi_user.get("default_display_name_prefix", "user")),
        )
```

```python
# src/settings.py
def _discover_raw_config(config_path: Path | None = None) -> MutableMapping[str, Any]:
    raw = _load_config(config_path)
    return raw if isinstance(raw, MutableMapping) else {}
```

- [ ] **Step 4: Export a helper for global config consumers without breaking single-user settings**

```python
# src/settings.py
def load_raw_config(config_path: Path | None = None) -> MutableMapping[str, Any]:
    """Load the raw project config for multi-user/global settings."""

    return dict(_discover_raw_config(config_path))
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_multi_user_settings.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/settings.py src/browser_pool.py tests/test_multi_user_settings.py
git commit -m "feat: add browser pool settings models"
```

### Task 2: Add persistent user registry and slot allocation

**Files:**
- Create: `src/multi_user_registry.py`
- Test: `tests/test_multi_user_registry.py`

- [ ] **Step 1: Write the failing tests for registry persistence and slot assignment**

```python
from pathlib import Path

from src.browser_pool import BrowserPoolSettings
from src.multi_user_registry import MultiUserRegistry


def make_pool(tmp_path):
    return BrowserPoolSettings(
        size=2,
        cdp_host="browser",
        start_port=9222,
        profile_root=tmp_path / "browser-pool",
        registry_file=tmp_path / "registry" / "users.json",
        default_display_name_prefix="user",
    )


def test_create_user_assigns_first_free_slot(tmp_path):
    registry = MultiUserRegistry(make_pool(tmp_path))

    entry = registry.create_user(display_name=None)

    assert entry.user_id == "user-001"
    assert entry.slot_id == "slot-1"
    assert entry.cdp_port == 9222
    assert entry.chrome_user_data_dir == tmp_path / "browser-pool" / "slot-1" / "profile"


def test_registry_persists_and_restores_slot_binding(tmp_path):
    pool = make_pool(tmp_path)
    created = MultiUserRegistry(pool).create_user(display_name="Alice")

    restored = MultiUserRegistry(pool).list_users()

    assert len(restored) == 1
    assert restored[0].user_id == created.user_id
    assert restored[0].slot_id == created.slot_id


def test_create_user_raises_when_no_slot_available(tmp_path):
    registry = MultiUserRegistry(make_pool(tmp_path))
    registry.create_user(display_name="A")
    registry.create_user(display_name="B")

    try:
        registry.create_user(display_name="C")
    except RuntimeError as exc:
        assert str(exc) == "no_available_browser_slot"
    else:
        raise AssertionError("expected no_available_browser_slot")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_multi_user_registry.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.multi_user_registry'`

- [ ] **Step 3: Implement registry entry model and JSON persistence**

```python
# src/multi_user_registry.py
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from .browser_pool import BrowserPoolSettings


@dataclass(frozen=True)
class UserRegistryEntry:
    user_id: str
    display_name: str
    enabled: bool
    status: str
    created_at: str
    slot_id: str
    cdp_host: str
    cdp_port: int
    chrome_user_data_dir: Path
    token_file: Path


class MultiUserRegistry:
    def __init__(self, pool_settings: BrowserPoolSettings, data_root: Path | None = None):
        self.pool_settings = pool_settings
        self.data_root = data_root or Path("/data/users")
        self.registry_file = pool_settings.registry_file
        self.registry_file.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> list[UserRegistryEntry]:
        if not self.registry_file.exists():
            return []
        raw = json.loads(self.registry_file.read_text(encoding="utf-8"))
        return [
            UserRegistryEntry(
                **{**item, "chrome_user_data_dir": Path(item["chrome_user_data_dir"]), "token_file": Path(item["token_file"])}
            )
            for item in raw
        ]

    def _save(self, entries: list[UserRegistryEntry]) -> None:
        payload = []
        for entry in entries:
            item = asdict(entry)
            item["chrome_user_data_dir"] = str(entry.chrome_user_data_dir)
            item["token_file"] = str(entry.token_file)
            payload.append(item)
        self.registry_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
```

- [ ] **Step 4: Implement user id generation and slot allocation**

```python
# src/multi_user_registry.py
    def list_users(self) -> list[UserRegistryEntry]:
        return self._load()

    def create_user(self, display_name: str | None) -> UserRegistryEntry:
        entries = self._load()
        used_slots = {entry.slot_id for entry in entries}
        slot_index = next(
            (idx for idx in range(1, self.pool_settings.size + 1) if f"slot-{idx}" not in used_slots),
            None,
        )
        if slot_index is None:
            raise RuntimeError("no_available_browser_slot")

        next_id = f"user-{len(entries) + 1:03d}"
        slot_id = f"slot-{slot_index}"
        profile_dir = self.pool_settings.profile_root / slot_id / "profile"
        token_file = self.data_root / next_id / "tokens" / "token.json"
        entry = UserRegistryEntry(
            user_id=next_id,
            display_name=display_name or next_id,
            enabled=True,
            status="pending_login",
            created_at=datetime.now(timezone.utc).isoformat(),
            slot_id=slot_id,
            cdp_host=self.pool_settings.cdp_host,
            cdp_port=self.pool_settings.start_port + slot_index - 1,
            chrome_user_data_dir=profile_dir,
            token_file=token_file,
        )
        self._save([*entries, entry])
        return entry
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_multi_user_registry.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/multi_user_registry.py tests/test_multi_user_registry.py
git commit -m "feat: add multi-user registry persistence"
```

### Task 3: Add multi-user runtime manager and global operation lock

**Files:**
- Create: `src/multi_user_manager.py`
- Modify: `src/__init__.py`
- Test: `tests/test_multi_user_manager.py`

- [ ] **Step 1: Write the failing tests for runtime creation and serialization rules**

```python
import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.browser_pool import BrowserPoolSettings
from src.multi_user_manager import MultiUserManager
from src.multi_user_registry import MultiUserRegistry


def make_manager(tmp_path):
    pool = BrowserPoolSettings(
        size=2,
        cdp_host="browser",
        start_port=9222,
        profile_root=tmp_path / "browser-pool",
        registry_file=tmp_path / "registry" / "users.json",
        default_display_name_prefix="user",
    )
    registry = MultiUserRegistry(pool, data_root=tmp_path / "users")
    return MultiUserManager(pool_settings=pool, registry=registry)


def test_create_user_returns_registry_entry(tmp_path):
    manager = make_manager(tmp_path)

    entry = manager.create_user()

    assert entry.user_id == "user-001"
    assert entry.slot_id == "slot-1"


@pytest.mark.asyncio
async def test_global_operation_lock_serializes_search_and_publish(tmp_path):
    manager = make_manager(tmp_path)
    manager.create_user()
    manager.create_user()
    order = []

    async def fake_run(label):
        async with manager.operation_lock:
            order.append(f"start-{label}")
            await asyncio.sleep(0)
            order.append(f"end-{label}")

    await asyncio.gather(fake_run("search"), fake_run("publish"))

    assert order in (
        ["start-search", "end-search", "start-publish", "end-publish"],
        ["start-publish", "end-publish", "start-search", "end-search"],
    )


def test_pick_random_search_user_only_returns_ready_users(tmp_path):
    manager = make_manager(tmp_path)
    first = manager.create_user()
    second = manager.create_user()
    manager._runtime_state[first.user_id] = {"status": "ready", "enabled": True}
    manager._runtime_state[second.user_id] = {"status": "pending_login", "enabled": True}

    picked = manager.pick_search_user_id()

    assert picked == first.user_id
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_multi_user_manager.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.multi_user_manager'`

- [ ] **Step 3: Implement `MultiUserManager` skeleton and runtime state map**

```python
# src/multi_user_manager.py
from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from typing import Any

from .browser_pool import BrowserPoolSettings
from .multi_user_registry import MultiUserRegistry, UserRegistryEntry


@dataclass
class UserRuntime:
    entry: UserRegistryEntry
    app: Any | None = None


class MultiUserManager:
    def __init__(self, pool_settings: BrowserPoolSettings, registry: MultiUserRegistry):
        self.pool_settings = pool_settings
        self.registry = registry
        self.operation_lock = asyncio.Lock()
        self._runtimes: dict[str, UserRuntime] = {}
        self._runtime_state: dict[str, dict[str, Any]] = {}
```

- [ ] **Step 4: Implement user creation and ready-user selection**

```python
# src/multi_user_manager.py
    def create_user(self, display_name: str | None = None) -> UserRegistryEntry:
        entry = self.registry.create_user(display_name=display_name)
        self._runtime_state[entry.user_id] = {
            "status": entry.status,
            "enabled": entry.enabled,
            "keepalive_running": False,
            "browser_connected": False,
            "cookie_present": False,
            "cookie_valid": False,
            "last_error": None,
            "busy": False,
        }
        return entry

    def list_users(self) -> list[UserRegistryEntry]:
        return self.registry.list_users()

    def pick_search_user_id(self) -> str:
        ready_users = [
            user_id
            for user_id, state in self._runtime_state.items()
            if state.get("enabled") and state.get("status") == "ready"
        ]
        if not ready_users:
            raise RuntimeError("no_available_user")
        return random.choice(ready_users)
```

- [ ] **Step 5: Export manager type from package root**

```python
# src/__init__.py
from .multi_user_manager import MultiUserManager
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_multi_user_manager.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/multi_user_manager.py src/__init__.py tests/test_multi_user_manager.py
git commit -m "feat: add multi-user manager skeleton"
```

### Task 4: Build per-user runtime creation and state reporting

**Files:**
- Modify: `src/multi_user_manager.py`
- Test: `tests/test_multi_user_manager.py`

- [ ] **Step 1: Write failing tests for runtime creation and status payloads**

```python
from types import SimpleNamespace


def test_get_user_status_returns_cookie_summary(tmp_path):
    manager = make_manager(tmp_path)
    entry = manager.create_user()
    manager._runtime_state[entry.user_id] = {
        "status": "ready",
        "enabled": True,
        "browser_connected": True,
        "keepalive_running": True,
        "cookie_present": True,
        "cookie_valid": True,
        "last_cookie_updated_at": "2026-04-11T10:00:00+00:00",
        "last_keepalive_at": "2026-04-11T10:05:00+00:00",
        "last_keepalive_status": "ok",
        "last_error": None,
        "busy": False,
        "token_preview": "token123",
    }

    status = manager.get_user_status(entry.user_id)

    assert status["user_id"] == entry.user_id
    assert status["slot_id"] == entry.slot_id
    assert status["cookie_valid"] is True
    assert status["token_preview"] == "token123"


def test_list_user_statuses_merges_registry_and_runtime_state(tmp_path):
    manager = make_manager(tmp_path)
    first = manager.create_user()
    second = manager.create_user()
    manager._runtime_state[first.user_id]["status"] = "ready"

    statuses = manager.list_user_statuses()

    assert [item["user_id"] for item in statuses] == [first.user_id, second.user_id]
    assert statuses[0]["slot_id"] == "slot-1"
    assert statuses[1]["slot_id"] == "slot-2"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_multi_user_manager.py -v`
Expected: FAIL with `AttributeError` for `get_user_status` / `list_user_statuses`

- [ ] **Step 3: Implement status merge helpers in `MultiUserManager`**

```python
# src/multi_user_manager.py
    def _entry_by_user_id(self, user_id: str) -> UserRegistryEntry:
        for entry in self.registry.list_users():
            if entry.user_id == user_id:
                return entry
        raise RuntimeError("user_not_found")

    def get_user_status(self, user_id: str) -> dict[str, Any]:
        entry = self._entry_by_user_id(user_id)
        state = self._runtime_state.get(user_id, {})
        return {
            "user_id": entry.user_id,
            "display_name": entry.display_name,
            "enabled": entry.enabled,
            "status": state.get("status", entry.status),
            "slot_id": entry.slot_id,
            "cdp_host": entry.cdp_host,
            "cdp_port": entry.cdp_port,
            "browser_connected": state.get("browser_connected", False),
            "keepalive_running": state.get("keepalive_running", False),
            "cookie_present": state.get("cookie_present", False),
            "cookie_valid": state.get("cookie_valid", False),
            "last_cookie_updated_at": state.get("last_cookie_updated_at"),
            "last_keepalive_at": state.get("last_keepalive_at"),
            "last_keepalive_status": state.get("last_keepalive_status"),
            "last_error": state.get("last_error"),
            "busy": state.get("busy", False),
            "token_preview": state.get("token_preview"),
        }

    def list_user_statuses(self) -> list[dict[str, Any]]:
        return [self.get_user_status(entry.user_id) for entry in self.registry.list_users()]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_multi_user_manager.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/multi_user_manager.py tests/test_multi_user_manager.py
git commit -m "feat: add multi-user status reporting"
```

### Task 5: Add browser pool container startup script and compose wiring

**Files:**
- Create: `docker/start-browser-pool.sh`
- Modify: `docker-compose.yml`
- Test: `tests/test_browser_pool_script.py`

- [ ] **Step 1: Write the failing test for startup script command generation**

```python
from pathlib import Path

from docker import start_browser_pool


def test_build_chrome_commands_uses_pool_size_and_incrementing_ports(tmp_path):
    commands = start_browser_pool.build_chrome_commands(
        pool_size=3,
        start_port=9222,
        profile_root=tmp_path / "browser-pool",
        chrome_bin="google-chrome",
    )

    assert commands[0][-2] == "--remote-debugging-port=9222"
    assert commands[1][-2] == "--remote-debugging-port=9223"
    assert commands[2][-2] == "--remote-debugging-port=9224"
    assert any("slot-1/profile" in arg for arg in commands[0])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_browser_pool_script.py -v`
Expected: FAIL with import error for `docker.start_browser_pool`

- [ ] **Step 3: Add a small Python helper used by the shell script**

```python
# docker/start_browser_pool.py
from __future__ import annotations

from pathlib import Path


def build_chrome_commands(pool_size: int, start_port: int, profile_root: Path, chrome_bin: str) -> list[list[str]]:
    commands = []
    for index in range(pool_size):
        slot_id = f"slot-{index + 1}"
        profile_dir = profile_root / slot_id / "profile"
        profile_dir.mkdir(parents=True, exist_ok=True)
        commands.append(
            [
                chrome_bin,
                f"--user-data-dir={profile_dir}",
                "--disable-dev-shm-usage",
                f"--remote-debugging-port={start_port + index}",
                "about:blank",
            ]
        )
    return commands
```

- [ ] **Step 4: Add the shell startup script and compose environment**

```bash
#!/usr/bin/env bash
set -eu

POOL_SIZE="${BROWSER_POOL_SIZE:-1}"
START_PORT="${BROWSER_CDP_START_PORT:-9222}"
PROFILE_ROOT="${BROWSER_PROFILE_ROOT:-/data/browser-pool}"
CHROME_BIN="${CHROME_BIN:-google-chrome}"

python - <<'PY'
from pathlib import Path
import os
import subprocess
from docker.start_browser_pool import build_chrome_commands

commands = build_chrome_commands(
    pool_size=int(os.environ["POOL_SIZE"]),
    start_port=int(os.environ["START_PORT"]),
    profile_root=Path(os.environ["PROFILE_ROOT"]),
    chrome_bin=os.environ["CHROME_BIN"],
)

procs = [subprocess.Popen(cmd) for cmd in commands]
for proc in procs:
    proc.wait()
PY
```

```yaml
# docker-compose.yml
browser:
  environment:
    - BROWSER_POOL_SIZE=${BROWSER_POOL_SIZE:-1}
    - BROWSER_CDP_START_PORT=${BROWSER_CDP_START_PORT:-9222}
    - BROWSER_PROFILE_ROOT=/data/browser-pool
  volumes:
    - ${XIANYU_HOST_DATA_DIR:-./data}/browser-pool:/data/browser-pool
  entrypoint: ["/bin/bash", "/app/docker/start-browser-pool.sh"]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_browser_pool_script.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add docker/start_browser_pool.py docker/start-browser-pool.sh docker-compose.yml tests/test_browser_pool_script.py
git commit -m "feat: add browser pool container startup"
```

### Task 6: Route HTTP server through `MultiUserManager`

**Files:**
- Modify: `mcp_server/http_server.py`
- Test: `tests/test_http_server_multi_user.py`

- [ ] **Step 1: Write the failing tests for create/list/status/search/publish routing**

```python
import json

from mcp_server import http_server


class FakeManager:
    def create_user(self, display_name=None):
        return type("Entry", (), {"user_id": "user-001", "slot_id": "slot-1", "cdp_port": 9222, "status": "pending_login"})()

    def list_user_statuses(self):
        return [{"user_id": "user-001", "status": "ready"}]

    def get_user_status(self, user_id):
        return {"user_id": user_id, "status": "ready"}

    async def search(self, keyword, user_id=None, **options):
        return {"success": True, "user_id": user_id or "user-001", "items": []}

    async def publish(self, user_id, item_url, **options):
        return {"success": True, "user_id": user_id, "item_id": "123"}


async def test_xianyu_create_user_returns_user_payload(monkeypatch):
    monkeypatch.setattr(http_server, "get_manager", lambda: FakeManager())

    payload = json.loads(await http_server.xianyu_create_user())

    assert payload["success"] is True
    assert payload["user_id"] == "user-001"


async def test_xianyu_publish_requires_user_id(monkeypatch):
    monkeypatch.setattr(http_server, "get_manager", lambda: FakeManager())

    payload = json.loads(await http_server.xianyu_publish(user_id="user-001", item_url="https://www.goofish.com/item?id=1"))

    assert payload["success"] is True
    assert payload["user_id"] == "user-001"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_http_server_multi_user.py -v`
Expected: FAIL with missing `get_manager` / `xianyu_create_user`

- [ ] **Step 3: Replace single `_app` entrypoint with manager singleton**

```python
# mcp_server/http_server.py
_manager = None


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
```

- [ ] **Step 4: Add the new HTTP/MCP tool handlers and route existing ones through manager**

```python
# mcp_server/http_server.py
@mcp.tool()
async def xianyu_create_user(display_name: str | None = None) -> str:
    entry = get_manager().create_user(display_name=display_name)
    return json.dumps(
        {
            "success": True,
            "user_id": entry.user_id,
            "slot_id": entry.slot_id,
            "cdp_port": entry.cdp_port,
            "status": entry.status,
        },
        ensure_ascii=False,
    )


@mcp.tool()
async def xianyu_list_users() -> str:
    return json.dumps({"success": True, "users": get_manager().list_user_statuses()}, ensure_ascii=False)


@mcp.tool()
async def xianyu_get_user_status(user_id: str) -> str:
    return json.dumps({"success": True, **get_manager().get_user_status(user_id)}, ensure_ascii=False)
```

```python
# mcp_server/http_server.py
@mcp.tool()
async def xianyu_search(keyword: str, user_id: str | None = None, rows: int = 30, min_price: float | None = None, max_price: float | None = None, free_ship: bool = False, sort_field: str = "", sort_order: str = "") -> str:
    result = await get_manager().search(keyword=keyword, user_id=user_id, rows=rows, min_price=min_price, max_price=max_price, free_ship=free_ship, sort_field=sort_field, sort_order=sort_order)
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
async def xianyu_publish(user_id: str, item_url: str, new_price: float | None = None, new_description: str | None = None, condition: str = "全新") -> str:
    result = await get_manager().publish(user_id=user_id, item_url=item_url, new_price=new_price, new_description=new_description, condition=condition)
    return json.dumps(result, ensure_ascii=False)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_http_server_multi_user.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add mcp_server/http_server.py tests/test_http_server_multi_user.py
git commit -m "feat: route http server through multi-user manager"
```

### Task 7: Connect `MultiUserManager` to real single-user runtimes

**Files:**
- Modify: `src/multi_user_manager.py`
- Modify: `src/settings.py`
- Test: `tests/test_multi_user_runtime_integration.py`

- [ ] **Step 1: Write the failing tests for runtime construction with per-user settings**

```python
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.multi_user_manager import MultiUserManager


@pytest.mark.asyncio
async def test_build_runtime_uses_registry_entry_paths(tmp_path, monkeypatch):
    manager = make_manager(tmp_path)
    entry = manager.create_user()

    created = {}

    class FakeApp:
        def __init__(self, browser, settings):
            created["browser"] = browser
            created["settings"] = settings

    monkeypatch.setattr("src.multi_user_manager.XianyuApp", FakeApp)

    runtime = await manager._get_or_create_runtime(entry.user_id)

    assert runtime.entry.user_id == entry.user_id
    assert created["settings"].storage.user_id == entry.user_id
    assert created["settings"].storage.chrome_user_data_dir == entry.chrome_user_data_dir
    assert created["settings"].storage.token_file == entry.token_file
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_multi_user_runtime_integration.py -v`
Expected: FAIL with missing `_get_or_create_runtime`

- [ ] **Step 3: Add a helper that converts registry entries into `AppSettings`**

```python
# src/settings.py
from .settings import AppSettings, KeepaliveSettings, SearchSettings, StorageSettings


def build_user_settings(user_id: str, token_file: Path, chrome_user_data_dir: Path, data_root: Path, keepalive_enabled: bool = True, keepalive_interval_minutes: int = DEFAULT_KEEPALIVE_INTERVAL_MINUTES, max_stale_pages: int = DEFAULT_SEARCH_MAX_STALE_PAGES) -> AppSettings:
    return AppSettings(
        storage=StorageSettings(
            data_root=data_root,
            user_id=user_id,
            token_file=token_file,
            chrome_user_data_dir=chrome_user_data_dir,
        ),
        keepalive=KeepaliveSettings(enabled=keepalive_enabled, interval_minutes=keepalive_interval_minutes),
        search=SearchSettings(max_stale_pages=max_stale_pages),
    )
```

- [ ] **Step 4: Implement runtime creation using per-user CDP endpoints**

```python
# src/multi_user_manager.py
from .core import XianyuApp
from .browser import AsyncChromeManager
from .settings import build_user_settings

    async def _get_or_create_runtime(self, user_id: str) -> UserRuntime:
        if user_id in self._runtimes:
            return self._runtimes[user_id]

        entry = self._entry_by_user_id(user_id)
        settings = build_user_settings(
            user_id=entry.user_id,
            token_file=entry.token_file,
            chrome_user_data_dir=entry.chrome_user_data_dir,
            data_root=entry.token_file.parents[2],
        )
        browser = AsyncChromeManager(host=entry.cdp_host, port=entry.cdp_port, auto_start=False, settings=settings)
        app = XianyuApp(browser=browser, settings=settings)
        runtime = UserRuntime(entry=entry, app=app)
        self._runtimes[user_id] = runtime
        self._runtime_state[user_id]["browser_connected"] = True
        return runtime
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_multi_user_runtime_integration.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/multi_user_manager.py src/settings.py tests/test_multi_user_runtime_integration.py
git commit -m "feat: build per-user runtimes from registry"
```

### Task 8: Implement keepalive orchestration and session status refresh

**Files:**
- Modify: `src/multi_user_manager.py`
- Test: `tests/test_multi_user_keepalive.py`

- [ ] **Step 1: Write the failing tests for keepalive startup and bulk session checks**

```python
import pytest


@pytest.mark.asyncio
async def test_start_keepalive_marks_user_running(tmp_path, monkeypatch):
    manager = make_manager(tmp_path)
    entry = manager.create_user()
    runtime = type("Runtime", (), {"entry": entry, "app": type("App", (), {"start_background_tasks": lambda self: None})()})()
    manager._runtimes[entry.user_id] = runtime

    await manager.start_keepalive(entry.user_id)

    assert manager._runtime_state[entry.user_id]["keepalive_running"] is True


@pytest.mark.asyncio
async def test_check_all_sessions_returns_status_per_user(tmp_path, monkeypatch):
    manager = make_manager(tmp_path)
    first = manager.create_user()
    second = manager.create_user()

    class FakeApp:
        async def check_session(self):
            return {"valid": True, "last_updated_at": "2026-04-11T10:00:00+00:00"}

    manager._runtimes[first.user_id] = type("Runtime", (), {"entry": first, "app": FakeApp()})()
    manager._runtimes[second.user_id] = type("Runtime", (), {"entry": second, "app": FakeApp()})()

    result = await manager.check_all_sessions()

    assert result[0]["user_id"] == first.user_id
    assert result[0]["cookie_valid"] is True
    assert result[1]["user_id"] == second.user_id
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_multi_user_keepalive.py -v`
Expected: FAIL with missing `start_keepalive` / `check_all_sessions`

- [ ] **Step 3: Implement keepalive start/stop hooks in manager**

```python
# src/multi_user_manager.py
    async def start_keepalive(self, user_id: str) -> None:
        runtime = await self._get_or_create_runtime(user_id)
        runtime.app.start_background_tasks()
        self._runtime_state[user_id]["keepalive_running"] = True

    async def stop_keepalive(self, user_id: str) -> None:
        runtime = await self._get_or_create_runtime(user_id)
        await runtime.app.stop_background_tasks()
        self._runtime_state[user_id]["keepalive_running"] = False
```

- [ ] **Step 4: Implement bulk session checks and state refresh**

```python
# src/multi_user_manager.py
    async def check_all_sessions(self) -> list[dict[str, Any]]:
        results = []
        for entry in self.registry.list_users():
            runtime = await self._get_or_create_runtime(entry.user_id)
            session_status = await runtime.app.check_session()
            self._runtime_state[entry.user_id]["cookie_valid"] = session_status["valid"]
            self._runtime_state[entry.user_id]["last_cookie_updated_at"] = session_status.get("last_updated_at")
            self._runtime_state[entry.user_id]["cookie_present"] = True
            self._runtime_state[entry.user_id]["status"] = "ready" if session_status["valid"] else "pending_login"
            results.append(self.get_user_status(entry.user_id))
        return results
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_multi_user_keepalive.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/multi_user_manager.py tests/test_multi_user_keepalive.py
git commit -m "feat: orchestrate per-user keepalive and session checks"
```

### Task 9: Implement real multi-user search and publish routing

**Files:**
- Modify: `src/multi_user_manager.py`
- Test: `tests/test_multi_user_operations.py`

- [ ] **Step 1: Write the failing tests for `search` and `publish` semantics**

```python
import pytest


@pytest.mark.asyncio
async def test_search_without_user_id_uses_ready_user(tmp_path):
    manager = make_manager(tmp_path)
    entry = manager.create_user()
    manager._runtime_state[entry.user_id]["status"] = "ready"

    class FakeApp:
        async def search_with_meta(self, keyword, **options):
            return type("Outcome", (), {"items": [], "requested_rows": 10, "returned_rows": 0, "stop_reason": "target_reached", "stale_pages": 0, "engine_used": "http_api", "fallback_reason": None, "pages_fetched": 1})()

    manager._runtimes[entry.user_id] = type("Runtime", (), {"entry": entry, "app": FakeApp()})()

    result = await manager.search(keyword="键盘", rows=10)

    assert result["success"] is True
    assert result["user_id"] == entry.user_id


@pytest.mark.asyncio
async def test_publish_requires_explicit_user_id(tmp_path):
    manager = make_manager(tmp_path)

    with pytest.raises(TypeError):
        await manager.publish(item_url="https://www.goofish.com/item?id=1")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_multi_user_operations.py -v`
Expected: FAIL with missing manager methods

- [ ] **Step 3: Implement `search` with global operation lock and selected user**

```python
# src/multi_user_manager.py
    async def search(self, keyword: str, user_id: str | None = None, **options) -> dict[str, Any]:
        selected_user_id = user_id or self.pick_search_user_id()
        runtime = await self._get_or_create_runtime(selected_user_id)
        async with self.operation_lock:
            self._runtime_state[selected_user_id]["busy"] = True
            try:
                outcome = await runtime.app.search_with_meta(keyword=keyword, **options)
            finally:
                self._runtime_state[selected_user_id]["busy"] = False

        return {
            "success": True,
            "user_id": selected_user_id,
            "slot_id": runtime.entry.slot_id,
            "requested": outcome.requested_rows,
            "total": outcome.returned_rows,
            "stop_reason": outcome.stop_reason,
            "stale_pages": outcome.stale_pages,
            "items": [item.__dict__ for item in outcome.items],
            "engine_used": outcome.engine_used,
            "fallback_reason": outcome.fallback_reason,
            "pages_fetched": outcome.pages_fetched,
        }
```

- [ ] **Step 4: Implement `publish` with explicit user validation**

```python
# src/multi_user_manager.py
    async def publish(self, user_id: str, item_url: str, **options) -> dict[str, Any]:
        entry = self._entry_by_user_id(user_id)
        state = self._runtime_state.get(user_id, {})
        if not entry.enabled:
            raise RuntimeError("user_disabled")
        if state.get("status") != "ready":
            raise RuntimeError("user_not_logged_in")

        runtime = await self._get_or_create_runtime(user_id)
        async with self.operation_lock:
            self._runtime_state[user_id]["busy"] = True
            try:
                result = await runtime.app.publish(item_url=item_url, **options)
            finally:
                self._runtime_state[user_id]["busy"] = False

        return {"user_id": user_id, "slot_id": runtime.entry.slot_id, **result}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_multi_user_operations.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/multi_user_manager.py tests/test_multi_user_operations.py
git commit -m "feat: add multi-user search and publish routing"
```

### Task 10: Add multi-user login, QR, refresh-token, and single-user status endpoints

**Files:**
- Modify: `src/multi_user_manager.py`
- Modify: `mcp_server/http_server.py`
- Test: `tests/test_http_server_multi_user_auth.py`

- [ ] **Step 1: Write the failing tests for login/show_qr/check_session/refresh_token routing**

```python
import json

from mcp_server import http_server


class FakeAuthManager:
    async def login(self, user_id):
        return {"success": True, "user_id": user_id, "need_qr": True}

    async def show_qr(self, user_id):
        return {"success": True, "user_id": user_id, "message": "请扫码登录"}

    async def check_session(self, user_id):
        return {"success": True, "user_id": user_id, "valid": True}

    async def refresh_token(self, user_id):
        return {"success": True, "user_id": user_id, "token": "abc"}


async def test_xianyu_login_routes_user_id(monkeypatch):
    monkeypatch.setattr(http_server, "get_manager", lambda: FakeAuthManager())

    payload = json.loads(await http_server.xianyu_login(user_id="user-001"))

    assert payload["user_id"] == "user-001"


async def test_xianyu_check_session_routes_user_id(monkeypatch):
    monkeypatch.setattr(http_server, "get_manager", lambda: FakeAuthManager())

    payload = json.loads(await http_server.xianyu_check_session(user_id="user-001"))

    assert payload["valid"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_http_server_multi_user_auth.py -v`
Expected: FAIL because current handlers do not accept `user_id`

- [ ] **Step 3: Implement auth/session helpers in `MultiUserManager`**

```python
# src/multi_user_manager.py
    async def login(self, user_id: str) -> dict[str, Any]:
        runtime = await self._get_or_create_runtime(user_id)
        result = await runtime.app.login(timeout=30)
        if result.get("success"):
            self._runtime_state[user_id]["status"] = "ready" if result.get("logged_in") or result.get("token") else "pending_login"
        return {"user_id": user_id, **result}

    async def show_qr(self, user_id: str) -> dict[str, Any]:
        runtime = await self._get_or_create_runtime(user_id)
        result = await runtime.app.show_qr_code()
        return {"user_id": user_id, **result}

    async def check_session(self, user_id: str) -> dict[str, Any]:
        runtime = await self._get_or_create_runtime(user_id)
        result = await runtime.app.check_session()
        self._runtime_state[user_id]["cookie_valid"] = result["valid"]
        return {"user_id": user_id, **result}

    async def refresh_token(self, user_id: str) -> dict[str, Any]:
        runtime = await self._get_or_create_runtime(user_id)
        result = await runtime.app.refresh_token()
        return {"user_id": user_id, "success": bool(result), **(result or {})}
```

- [ ] **Step 4: Route HTTP handlers to the new manager methods**

```python
# mcp_server/http_server.py
@mcp.tool()
async def xianyu_login(user_id: str) -> str:
    return json.dumps(await get_manager().login(user_id), ensure_ascii=False)


@mcp.tool()
async def xianyu_show_qr(user_id: str) -> str:
    return json.dumps(await get_manager().show_qr(user_id), ensure_ascii=False)


@mcp.tool()
async def xianyu_check_session(user_id: str) -> str:
    return json.dumps(await get_manager().check_session(user_id), ensure_ascii=False)


@mcp.tool()
async def xianyu_refresh_token(user_id: str) -> str:
    return json.dumps(await get_manager().refresh_token(user_id), ensure_ascii=False)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_http_server_multi_user_auth.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/multi_user_manager.py mcp_server/http_server.py tests/test_http_server_multi_user_auth.py
git commit -m "feat: add multi-user auth and session routing"
```

### Task 11: Document deployment changes and add verification tests

**Files:**
- Modify: `README.md`
- Modify: `docker/README.md`
- Test: `tests/test_http_server_multi_user.py`
- Test: `tests/test_multi_user_end_to_end_smoke.py`

- [ ] **Step 1: Write the failing smoke test for returned payload shape**

```python
import pytest


@pytest.mark.asyncio
async def test_search_payload_includes_user_and_slot(tmp_path):
    manager = make_manager(tmp_path)
    entry = manager.create_user()
    manager._runtime_state[entry.user_id]["status"] = "ready"

    class FakeApp:
        async def search_with_meta(self, keyword, **options):
            return type("Outcome", (), {"items": [], "requested_rows": 5, "returned_rows": 0, "stop_reason": "target_reached", "stale_pages": 0, "engine_used": "http_api", "fallback_reason": None, "pages_fetched": 1})()

    manager._runtimes[entry.user_id] = type("Runtime", (), {"entry": entry, "app": FakeApp()})()

    payload = await manager.search(keyword="球鞋", rows=5)

    assert payload["user_id"] == entry.user_id
    assert payload["slot_id"] == entry.slot_id
```

- [ ] **Step 2: Run tests to verify they fail or cover missing fields**

Run: `pytest tests/test_multi_user_end_to_end_smoke.py -v`
Expected: FAIL until final payload shape is complete

- [ ] **Step 3: Update README with multi-user workflow**

```markdown
## 多用户模式

- 浏览器容器支持通过 `BROWSER_POOL_SIZE` 启动多个 Chrome 槽位
- 新增用户使用 `xianyu_create_user`
- 用户登录使用 `xianyu_show_qr(user_id)` 或 `xianyu_login(user_id)`
- 查看全部状态使用 `xianyu_list_users`
- `publish` 必须传 `user_id`
- `search` 可选传 `user_id`，不传时随机挑选可用账号
```

- [ ] **Step 4: Update Docker deployment docs with browser-pool environment**

```markdown
新增环境变量：

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `BROWSER_POOL_SIZE` | Chrome 槽位数量 | `1` |
| `BROWSER_CDP_START_PORT` | 浏览器池起始 CDP 端口 | `9222` |
| `BROWSER_PROFILE_ROOT` | 浏览器池 profile 根目录 | `/data/browser-pool` |

浏览器容器会一次性拉起多个 Chrome 进程：

- `slot-1 -> browser:9222`
- `slot-2 -> browser:9223`
- `slot-3 -> browser:9224`
```

- [ ] **Step 5: Run the focused smoke tests and docs-adjacent unit tests**

Run: `pytest tests/test_multi_user_end_to_end_smoke.py tests/test_http_server_multi_user.py tests/test_http_server_multi_user_auth.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add README.md docker/README.md tests/test_multi_user_end_to_end_smoke.py tests/test_http_server_multi_user.py tests/test_http_server_multi_user_auth.py
git commit -m "docs: add multi-user browser pool usage"
```

### Task 12: Run final verification suite

**Files:**
- Modify: none
- Test: `tests/test_multi_user_settings.py`
- Test: `tests/test_multi_user_registry.py`
- Test: `tests/test_multi_user_manager.py`
- Test: `tests/test_multi_user_runtime_integration.py`
- Test: `tests/test_multi_user_keepalive.py`
- Test: `tests/test_multi_user_operations.py`
- Test: `tests/test_http_server_multi_user.py`
- Test: `tests/test_http_server_multi_user_auth.py`
- Test: `tests/test_multi_user_end_to_end_smoke.py`

- [ ] **Step 1: Run all new multi-user tests**

Run: `pytest tests/test_multi_user_settings.py tests/test_multi_user_registry.py tests/test_multi_user_manager.py tests/test_multi_user_runtime_integration.py tests/test_multi_user_keepalive.py tests/test_multi_user_operations.py tests/test_http_server_multi_user.py tests/test_http_server_multi_user_auth.py tests/test_multi_user_end_to_end_smoke.py -v`
Expected: PASS

- [ ] **Step 2: Run a targeted regression slice for existing single-user behavior**

Run: `pytest tests/test_settings.py tests/test_keepalive.py tests/test_session_page_lifecycle.py tests/test_http_server_unit.py -v`
Expected: PASS

- [ ] **Step 3: Run formatting/lint checks if the repository already uses them**

Run: `python -m compileall src mcp_server`
Expected: PASS with no syntax errors

- [ ] **Step 4: Commit the final integration checkpoint**

```bash
git add .
git commit -m "feat: add multi-user browser pool support"
```

## Self-Review

- Spec coverage: browser pool sizing, slot allocation, registry persistence, dynamic user creation, per-user keepalive, multi-user status, forced `publish user_id`, random ready-user `search`, HTTP/SSE exposure, and deployment docs each have dedicated tasks.
- Placeholder scan: no `TODO`, `TBD`, or “implement later” placeholders remain; every task has concrete files, code, and commands.
- Type consistency: the plan consistently uses `BrowserPoolSettings`, `BrowserSlot`, `UserRegistryEntry`, `MultiUserRegistry`, `MultiUserManager`, `UserRuntime`, `slot_id`, and `user_id` across all tasks.
