from pathlib import Path
from types import SimpleNamespace

import pytest

from src.multi_user_manager import MultiUserManager


def make_manager(tmp_path):
    from src.browser_pool import BrowserPoolSettings
    from src.multi_user_registry import MultiUserRegistry

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
    assert (
        created["settings"].storage.chrome_user_data_dir == entry.chrome_user_data_dir
    )
    assert created["settings"].storage.token_file == entry.token_file


@pytest.mark.asyncio
async def test_build_runtime_restores_state_for_existing_registry_user(
    tmp_path, monkeypatch
):
    first_manager = make_manager(tmp_path)
    entry = first_manager.create_user()

    class FakeApp:
        def __init__(self, browser, settings):
            self.browser = browser
            self.settings = settings

    monkeypatch.setattr("src.multi_user_manager.XianyuApp", FakeApp)

    restarted_manager = make_manager(tmp_path)

    runtime = await restarted_manager._get_or_create_runtime(entry.user_id)

    assert runtime.entry.user_id == entry.user_id
    assert restarted_manager._runtime_state[entry.user_id]["status"] == "pending_login"
    assert restarted_manager._runtime_state[entry.user_id]["browser_connected"] is True
