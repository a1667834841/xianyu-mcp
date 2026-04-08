"""Centralized runtime settings for storage, keepalive, and search."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, MutableMapping

DEFAULT_DATA_ROOT = Path.home() / ".claude" / "xianyu-data" / "users"
DEFAULT_USER_ID = "default"
DEFAULT_TOKEN_FILE_NAME = "token.json"
DEFAULT_TOKEN_PATH = Path("tokens") / DEFAULT_TOKEN_FILE_NAME
DEFAULT_CHROME_PROFILE = Path("chrome-profile")
DEFAULT_KEEPALIVE_ENABLED = True
DEFAULT_KEEPALIVE_INTERVAL_MINUTES = 10
DEFAULT_SEARCH_MAX_STALE_PAGES = 3

_TRUE_TOKENS = {"1", "true", "yes", "on"}
_FALSE_TOKENS = {"0", "false", "no", "off"}


def _expand_path(value: str | Path) -> Path:
    return Path(value).expanduser()


def _path_value(value: Any) -> Path | None:
    if isinstance(value, Path):
        return value.expanduser()
    if isinstance(value, str):
        trimmed = value.strip()
        if not trimmed:
            return None
        return _expand_path(trimmed)
    return None


def _str_value(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _repo_root_config_path() -> Path:
    return Path(__file__).resolve().parents[1] / "config.json"


def _legacy_user_config_path() -> Path:
    return Path.home() / ".claude" / "xianyu-chrome" / "config.json"


def _discover_config_path(config_path: Path | None = None) -> Path | None:
    if config_path:
        return _expand_path(config_path)

    env_path = _path_value(os.environ.get("XIANFU_CONFIG_PATH"))
    if env_path and env_path.exists():
        return env_path

    repo_path = _repo_root_config_path()
    if repo_path.exists():
        return repo_path

    legacy_path = _legacy_user_config_path()
    if legacy_path.exists():
        return legacy_path

    return None


def _load_config(path: Path | None = None) -> MutableMapping[str, Any]:
    candidate = _discover_config_path(path)
    if candidate is None or not candidate.exists():
        return {}

    try:
        return json.loads(candidate.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in _TRUE_TOKENS:
        return True
    if normalized in _FALSE_TOKENS:
        return False
    return default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return _positive_int(raw, default)


def _coerce_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in _TRUE_TOKENS:
            return True
        if normalized in _FALSE_TOKENS:
            return False
    return default


def _positive_int(value: Any, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value if value > 0 else default
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return default
        try:
            parsed = int(raw)
        except ValueError:
            return default
        return parsed if parsed > 0 else default
    return default


def _coerce_int(value: Any, default: int) -> int:
    return _positive_int(value, default)


@dataclass(frozen=True)
class StorageSettings:
    """Storage settings for multi-user data, tokens, and Chrome profiles."""

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


def load_settings(config_path: Path | None = None) -> AppSettings:
    """Load settings with env var precedence, config fallbacks, and sane defaults."""

    raw_config = _load_config(config_path)
    config: MutableMapping[str, Any]
    if isinstance(raw_config, MutableMapping):
        config = raw_config
    else:
        config = {}

    def _section(name: str) -> MutableMapping[str, Any]:
        value = config.get(name)
        return value if isinstance(value, MutableMapping) else {}

    storage_cfg = _section("storage")
    keepalive_cfg = _section("keepalive")
    search_cfg = _section("search")

    env_data_root = os.environ.get("XIANYU_DATA_ROOT")
    config_data_root = _path_value(storage_cfg.get("data_root"))
    if env_data_root:
        data_root = _expand_path(env_data_root)
    elif config_data_root:
        data_root = _expand_path(config_data_root)
    else:
        data_root = DEFAULT_DATA_ROOT

    env_user_id = os.environ.get("XIANYU_USER_ID")
    config_user_id = _str_value(storage_cfg.get("user_id"))
    user_id = env_user_id or config_user_id or DEFAULT_USER_ID
    user_root = data_root / user_id
    use_env_derived_paths = bool(env_data_root or env_user_id)

    token_override = os.environ.get("XIANYU_TOKEN_FILE")
    config_token = _path_value(storage_cfg.get("token_file"))
    if token_override:
        token_file_path = _expand_path(token_override)
    elif use_env_derived_paths:
        token_file_path = user_root / "tokens" / DEFAULT_TOKEN_FILE_NAME
    elif config_token:
        token_file_path = _expand_path(config_token)
    else:
        token_file_path = user_root / "tokens" / DEFAULT_TOKEN_FILE_NAME

    chrome_override = os.environ.get("XIANYU_CHROME_USER_DATA_DIR")
    config_chrome = _path_value(storage_cfg.get("chrome_user_data_dir"))
    if chrome_override:
        chrome_profile = _expand_path(chrome_override)
    elif use_env_derived_paths:
        chrome_profile = user_root / DEFAULT_CHROME_PROFILE
    elif config_chrome:
        chrome_profile = _expand_path(config_chrome)
    else:
        chrome_profile = user_root / DEFAULT_CHROME_PROFILE

    storage_settings = StorageSettings(
        data_root=data_root,
        user_id=user_id,
        token_file=token_file_path,
        chrome_user_data_dir=chrome_profile,
    )

    keepalive_settings = KeepaliveSettings(
        enabled=_env_bool("XIANYU_KEEPALIVE_ENABLED", _coerce_bool(keepalive_cfg.get("enabled"), DEFAULT_KEEPALIVE_ENABLED)),
        interval_minutes=_env_int("XIANYU_KEEPALIVE_INTERVAL_MINUTES", _coerce_int(keepalive_cfg.get("interval_minutes"), DEFAULT_KEEPALIVE_INTERVAL_MINUTES)),
    )

    search_settings = SearchSettings(
        max_stale_pages=_env_int(
            "XIANYU_SEARCH_MAX_STALE_PAGES",
            _coerce_int(search_cfg.get("max_stale_pages"), DEFAULT_SEARCH_MAX_STALE_PAGES),
        ),
    )

    return AppSettings(
        storage=storage_settings,
        keepalive=keepalive_settings,
        search=search_settings,
    )
