import json
from pathlib import Path

import settings as settings_module

from settings import (
    DEFAULT_DATA_ROOT,
    DEFAULT_KEEPALIVE_INTERVAL_MINUTES,
    DEFAULT_SEARCH_MAX_STALE_PAGES,
    DEFAULT_USER_ID,
    load_settings,
)


def test_keepalive_and_search_env_override_config(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "keepalive": {
            "enabled": False,
            "interval_minutes": 15
        },
        "search": {
            "max_stale_pages": 4
        }
    }))

    monkeypatch.setenv("XIANYU_KEEPALIVE_ENABLED", "true")
    monkeypatch.setenv("XIANYU_KEEPALIVE_INTERVAL_MINUTES", "25")
    monkeypatch.setenv("XIANYU_SEARCH_MAX_STALE_PAGES", "7")

    settings = load_settings(config_path=config_path)

    assert settings.keepalive.enabled is True
    assert settings.keepalive.interval_minutes == 25
    assert settings.search.max_stale_pages == 7


def test_keepalive_invalid_enabled_env_falls_back_to_config(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "keepalive": {
            "enabled": True,
            "interval_minutes": 12
        }
    }))

    monkeypatch.setenv("XIANYU_KEEPALIVE_ENABLED", "not-a-bool")

    settings = load_settings(config_path=config_path)

    assert settings.keepalive.enabled is True


def test_keepalive_invalid_interval_env_falls_back(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "keepalive": {
            "enabled": False,
            "interval_minutes": 18
        }
    }))

    monkeypatch.setenv("XIANYU_KEEPALIVE_INTERVAL_MINUTES", "0")

    settings = load_settings(config_path=config_path)

    assert settings.keepalive.interval_minutes == 18


def test_search_invalid_max_stale_env_falls_back(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "search": {
            "max_stale_pages": 5
        }
    }))

    monkeypatch.setenv("XIANYU_SEARCH_MAX_STALE_PAGES", "-3")

    settings = load_settings(config_path=config_path)

    assert settings.search.max_stale_pages == 5


def test_keepalive_bool_interval_config_falls_back_to_default(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "keepalive": {
            "interval_minutes": True
        }
    }))

    settings = load_settings(config_path=config_path)

    assert settings.keepalive.interval_minutes == DEFAULT_KEEPALIVE_INTERVAL_MINUTES


def test_search_bool_max_stale_config_falls_back_to_default(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "search": {
            "max_stale_pages": False
        }
    }))

    settings = load_settings(config_path=config_path)

    assert settings.search.max_stale_pages == DEFAULT_SEARCH_MAX_STALE_PAGES


def test_env_vars_derive_paths_over_config(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "storage": {
            "data_root": "/tmp/irrelevant",
            "user_id": "irrelevant-user",
            "token_file": str(tmp_path / "config/token.json"),
            "chrome_user_data_dir": str(tmp_path / "config/profile")
        }
    }))

    monkeypatch.setenv("XIANYU_DATA_ROOT", str(tmp_path / "env-root"))
    monkeypatch.setenv("XIANYU_USER_ID", "env-user")

    settings = load_settings(config_path=config_path)

    expected_root = Path(tmp_path / "env-root" / "env-user")
    assert settings.storage.data_root == Path(tmp_path / "env-root")
    assert settings.storage.user_id == "env-user"
    assert settings.storage.token_file == expected_root / "tokens" / "token.json"
    assert settings.storage.chrome_user_data_dir == expected_root / "chrome-profile"


def test_config_derives_paths_without_explicit_files(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "storage": {
            "data_root": str(tmp_path / "config-root"),
            "user_id": "config-user"
        }
    }))

    settings = load_settings(config_path=config_path)

    expected_root = Path(tmp_path / "config-root" / "config-user")
    assert settings.storage.token_file == expected_root / "tokens" / "token.json"
    assert settings.storage.chrome_user_data_dir == expected_root / "chrome-profile"


def test_config_root_not_mapping_falls_back(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text("[]")

    settings = load_settings(config_path=config_path)

    assert settings.storage.user_id == "default"
    assert settings.keepalive.interval_minutes == DEFAULT_KEEPALIVE_INTERVAL_MINUTES


def test_storage_not_mapping_falls_back(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "storage": []
    }))

    settings = load_settings(config_path=config_path)

    assert settings.storage.user_id == "default"
    assert settings.storage.token_file == DEFAULT_DATA_ROOT / DEFAULT_USER_ID / "tokens" / "token.json"


def test_storage_fields_invalid_types_fall_back(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "storage": {
            "data_root": 123,
            "user_id": 123,
            "token_file": 123,
            "chrome_user_data_dir": 123
        }
    }))

    settings = load_settings(config_path=config_path)

    assert settings.storage.data_root == DEFAULT_DATA_ROOT
    assert settings.storage.user_id == DEFAULT_USER_ID
    assert settings.storage.token_file == DEFAULT_DATA_ROOT / DEFAULT_USER_ID / "tokens" / "token.json"
    assert settings.storage.chrome_user_data_dir == DEFAULT_DATA_ROOT / DEFAULT_USER_ID / "chrome-profile"


def test_empty_string_storage_paths_use_derived_defaults(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "storage": {
            "data_root": str(tmp_path / "env-root"),
            "user_id": "custom",
            "token_file": "",
            "chrome_user_data_dir": ""
        }
    }))

    settings = load_settings(config_path=config_path)

    assert settings.storage.token_file == Path(tmp_path / "env-root" / "custom" / "tokens" / "token.json")
    assert settings.storage.chrome_user_data_dir == Path(tmp_path / "env-root" / "custom" / "chrome-profile")

def test_load_settings_prefers_xianfu_config_path(tmp_path, monkeypatch):
    custom_config = tmp_path / "custom-config.json"
    custom_config.write_text(json.dumps({
        "storage": {
            "data_root": str(tmp_path / "custom-root"),
            "user_id": "custom-user"
        }
    }))

    monkeypatch.setenv("XIANFU_CONFIG_PATH", str(custom_config))

    settings = load_settings()

    assert settings.storage.user_id == "custom-user"
    assert settings.storage.data_root == Path(tmp_path / "custom-root")


def test_load_settings_prefers_legacy_when_repo_root_missing(tmp_path, monkeypatch):
    legacy_root = tmp_path / ".claude" / "xianyu-chrome"
    legacy_root.mkdir(parents=True)
    legacy_config = legacy_root / "config.json"
    legacy_config.write_text(json.dumps({
        "storage": {
            "data_root": str(tmp_path / "legacy-root"),
            "user_id": "legacy-user"
        }
    }))

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("XIANFU_CONFIG_PATH", raising=False)
    monkeypatch.setattr(settings_module, "_repo_root_config_path", lambda: tmp_path / "nonexistent-repo-config.json")

    settings = load_settings()

    assert settings.storage.user_id == "legacy-user"
    assert settings.storage.data_root == Path(tmp_path / "legacy-root")
