from pathlib import Path

from src.settings import load_settings
from src.browser_pool import BrowserPoolSettings, BrowserSlot


def test_load_settings_keeps_single_user_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("XIANYU_DATA_ROOT", str(tmp_path / "users"))
    monkeypatch.setenv("XIANYU_USER_ID", "default")

    settings = load_settings()

    assert settings.storage.user_id == "default"
    assert (
        settings.storage.token_file
        == tmp_path / "users" / "default" / "tokens" / "token.json"
    )


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
    slot = BrowserSlot(
        slot_id="slot-2",
        cdp_host="browser",
        cdp_port=9223,
        profile_dir=tmp_path / "slot-2" / "profile",
    )

    assert slot.slot_id == "slot-2"
    assert slot.cdp_port == 9223
    assert slot.profile_dir == tmp_path / "slot-2" / "profile"


def test_browser_pool_settings_env_overrides_config(monkeypatch):
    monkeypatch.setenv("BROWSER_POOL_SIZE", "4")
    monkeypatch.setenv("BROWSER_CDP_START_PORT", "9330")
    monkeypatch.setenv("BROWSER_PROFILE_ROOT", "/runtime/browser-pool")

    config = {
        "multi_user": {
            "registry_file": "/data/registry/users.json",
            "default_display_name_prefix": "user",
        },
        "browser_pool": {
            "size": 1,
            "cdp_host": "browser",
            "start_port": 9222,
            "profile_root": "/data/browser-pool",
        },
    }

    settings = BrowserPoolSettings.from_config(config)

    assert settings.size == 4
    assert settings.start_port == 9330
    assert settings.profile_root == Path("/runtime/browser-pool")
