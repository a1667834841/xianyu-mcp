from pathlib import Path

from src.browser_pool import BrowserPoolSettings
from src.multi_user_registry import MultiUserRegistry


def make_pool(tmp_path):
    return BrowserPoolSettings(
        size=1,
        cdp_host="browser",
        start_port=9222,
        profile_root=tmp_path / "browser-pool",
        registry_file=tmp_path / "registry" / "users.json",
        default_display_name_prefix="user",
    )


def test_pool_settings_preserves_configured_size(monkeypatch, tmp_path):
    monkeypatch.setenv("BROWSER_POOL_SIZE", "3")
    monkeypatch.setenv("BROWSER_CDP_START_PORT", "9222")
    monkeypatch.setenv("BROWSER_PROFILE_ROOT", str(tmp_path / "browser-pool"))

    settings = BrowserPoolSettings.from_config(
        {
            "browser_pool": {"size": 5, "cdp_host": "browser"},
            "multi_user": {"registry_file": str(tmp_path / "registry" / "users.json")},
        }
    )

    assert settings.size == 3
    assert settings.start_port == 9222


def test_create_user_raises_when_browser_pool_is_full(tmp_path):
    pool = BrowserPoolSettings(
        size=3,
        cdp_host="browser",
        start_port=9222,
        profile_root=tmp_path / "browser-pool",
        registry_file=tmp_path / "registry" / "users.json",
        default_display_name_prefix="user",
    )
    registry = MultiUserRegistry(pool)
    registry.create_user(display_name="A")
    registry.create_user(display_name="B")
    registry.create_user(display_name="C")

    try:
        registry.create_user(display_name="D")
    except RuntimeError as exc:
        assert str(exc) == "no_available_browser_slot"
    else:
        raise AssertionError("expected no_available_browser_slot")


def test_create_user_still_uses_single_slot_when_pool_size_is_zero(tmp_path):
    pool = BrowserPoolSettings(
        size=0,
        cdp_host="browser",
        start_port=9222,
        profile_root=tmp_path / "browser-pool",
        registry_file=tmp_path / "registry" / "users.json",
        default_display_name_prefix="user",
    )
    registry = MultiUserRegistry(pool)

    entry = registry.create_user(display_name="A")

    assert entry.slot_id == "slot-1"
    assert entry.cdp_port == 9222


def test_create_user_assigns_first_free_slot(tmp_path):
    registry = MultiUserRegistry(make_pool(tmp_path))

    entry = registry.create_user(display_name=None)

    assert entry.user_id == "user-001"
    assert entry.slot_id == "slot-1"
    assert entry.cdp_port == 9222
    assert (
        entry.chrome_user_data_dir == tmp_path / "browser-pool" / "slot-1" / "profile"
    )


def test_registry_persists_and_restores_slot_binding(tmp_path):
    pool = make_pool(tmp_path)
    created = MultiUserRegistry(pool).create_user(display_name="Alice")

    restored = MultiUserRegistry(pool).list_users()

    assert len(restored) == 1
    assert restored[0].user_id == created.user_id
    assert restored[0].slot_id == created.slot_id


def test_registry_reloads_users_with_current_browser_runtime_binding(tmp_path):
    original_pool = BrowserPoolSettings(
        size=1,
        cdp_host="browser",
        start_port=9222,
        profile_root=tmp_path / "browser-pool",
        registry_file=tmp_path / "registry" / "users.json",
        default_display_name_prefix="user",
    )
    created = MultiUserRegistry(original_pool).create_user(display_name="Alice")

    updated_pool = BrowserPoolSettings(
        size=1,
        cdp_host="127.0.0.1",
        start_port=9330,
        profile_root=tmp_path / "runtime-browser-pool",
        registry_file=tmp_path / "registry" / "users.json",
        default_display_name_prefix="user",
    )

    restored = MultiUserRegistry(updated_pool).list_users()

    assert restored[0].user_id == created.user_id
    assert restored[0].slot_id == "slot-1"
    assert restored[0].cdp_host == "127.0.0.1"
    assert restored[0].cdp_port == 9330
    assert (
        restored[0].chrome_user_data_dir
        == tmp_path / "runtime-browser-pool" / "slot-1" / "profile"
    )


def test_get_user_raises_for_nonexistent_user(tmp_path):
    registry = MultiUserRegistry(make_pool(tmp_path))

    try:
        registry.get_user("nonexistent")
    except RuntimeError as exc:
        assert str(exc) == "user_not_found"
    else:
        raise AssertionError("expected user_not_found")
