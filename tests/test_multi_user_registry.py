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


def test_get_user_raises_for_nonexistent_user(tmp_path):
    registry = MultiUserRegistry(make_pool(tmp_path))

    try:
        registry.get_user("nonexistent")
    except RuntimeError as exc:
        assert str(exc) == "user_not_found"
    else:
        raise AssertionError("expected user_not_found")
