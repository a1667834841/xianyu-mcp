import asyncio
from dataclasses import replace

import pytest

from src.browser_pool import BrowserPoolSettings
from src.multi_user_manager import MultiUserManager
from src.multi_user_registry import MultiUserRegistry


def make_manager(tmp_path):
    pool = BrowserPoolSettings(
        size=1,
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
    entry = manager.create_user()
    manager.registry.update_user(replace(entry, status="ready"))

    picked = manager.pick_search_user_id()

    assert picked == entry.user_id


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


def test_list_user_statuses_returns_single_user(tmp_path):
    manager = make_manager(tmp_path)
    first = manager.create_user()
    manager._runtime_state[first.user_id]["status"] = "ready"

    statuses = manager.list_user_statuses()

    assert [item["user_id"] for item in statuses] == [first.user_id]
    assert statuses[0]["slot_id"] == "slot-1"


def test_pick_search_user_id_respects_registry_enabled_flag(tmp_path):
    manager = make_manager(tmp_path)
    entry = manager.create_user()
    updated_entry = replace(entry, enabled=False)
    manager.registry.update_user(updated_entry)

    with pytest.raises(RuntimeError, match="no_available_user"):
        manager.pick_search_user_id()


@pytest.mark.asyncio
async def test_publish_with_disabled_user_raises_error(tmp_path):
    manager = make_manager(tmp_path)
    entry = manager.create_user()
    updated_entry = replace(entry, enabled=False)
    manager.registry.update_user(updated_entry)

    with pytest.raises(RuntimeError, match="user_disabled"):
        await manager.publish(entry.user_id, "https://www.goofish.com/item?id=123")


@pytest.mark.asyncio
async def test_publish_with_nonexistent_user_raises_error(tmp_path):
    manager = make_manager(tmp_path)

    with pytest.raises(RuntimeError, match="user_not_found"):
        await manager.publish("nonexistent-user", "https://www.goofish.com/item?id=123")


@pytest.mark.asyncio
async def test_publish_with_non_ready_user_raises_error(tmp_path):
    manager = make_manager(tmp_path)
    entry = manager.create_user()

    with pytest.raises(RuntimeError, match="user_not_logged_in"):
        await manager.publish(entry.user_id, "https://www.goofish.com/item?id=123")


@pytest.mark.asyncio
async def test_search_with_explicit_user_id(tmp_path):
    manager = make_manager(tmp_path)
    entry = manager.create_user()
    updated_entry = replace(entry, status="ready", enabled=True)
    manager.registry.update_user(updated_entry)

    runtime = await manager._get_or_create_runtime(entry.user_id)

    class FakeOutcome:
        requested_rows = 1
        returned_rows = 1
        stop_reason = "done"
        stale_pages = 0
        items = []
        engine_used = "test"
        fallback_reason = None
        pages_fetched = 1

    async def mock_search(**kwargs):
        return FakeOutcome()

    runtime.app.search_with_meta = mock_search

    result = await manager.search(keyword="test", user_id=entry.user_id)

    assert result["user_id"] == entry.user_id


@pytest.mark.asyncio
async def test_publish_happy_path(tmp_path):
    manager = make_manager(tmp_path)
    entry = manager.create_user()
    updated_entry = replace(entry, status="ready")
    manager.registry.update_user(updated_entry)

    runtime = await manager._get_or_create_runtime(entry.user_id)

    async def mock_publish(**kwargs):
        return {"success": True, "item_id": "12345"}

    runtime.app.publish = mock_publish

    result = await manager.publish(entry.user_id, "https://www.goofish.com/item?id=123")

    assert result["success"] is True
    assert result["user_id"] == entry.user_id


@pytest.mark.asyncio
async def test_resolve_debug_user_auto_picks_ready_user(tmp_path):
    manager = make_manager(tmp_path)
    entry = manager.create_user()
    manager.registry.update_user(replace(entry, status="ready"))

    resolved, selected_by = manager.resolve_debug_user(None)

    assert resolved.user_id == entry.user_id
    assert selected_by == "auto"


@pytest.mark.asyncio
async def test_resolve_login_user_auto_picks_not_ready_user(tmp_path):
    manager = make_manager(tmp_path)
    entry = manager.create_user()
    manager._runtime_state[entry.user_id] = {
        "status": "pending_login",
        "cookie_valid": False,
        "enabled": True,
    }

    resolved, selected_by = manager.resolve_login_user(None)

    assert resolved.user_id == entry.user_id
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
            "qr_code": {
                "public_url": "https://passport.goofish.com/qrcodeCheck.htm?lgToken=test"
            },
            "message": "请扫码登录",
        }

    runtime.app.login = fake_login

    result = await manager.debug_login(user_id=entry.user_id)

    assert result["user_id"] == entry.user_id
    assert result["slot_id"] == entry.slot_id
    assert result["selected_by"] == "explicit"
    assert result["qr_code"]["public_url"].startswith("https://passport.goofish.com/")


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


def test_create_user_rejects_second_browser_user(tmp_path):
    manager = make_manager(tmp_path)
    manager.create_user()

    with pytest.raises(RuntimeError, match="no_available_browser_slot"):
        manager.create_user()
