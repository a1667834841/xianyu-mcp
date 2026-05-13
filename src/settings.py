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
DEFAULT_KEEPALIVE_INTERVAL_MINUTES = 240
DEFAULT_KEEPALIVE_MAX_CAPTCHA_RETRIES = 3
DEFAULT_SEARCH_MAX_STALE_PAGES = 3
DEFAULT_CREATE_CONVERSATION_GREETING = "在吗？"
DEFAULT_HOOK_TIMEOUT_SECONDS = 5
DEFAULT_HOOK_ENABLED_EVENTS = ("message.received",)

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


def _coerce_greeting(value: Any, default: str) -> str:
    if not isinstance(value, str):
        return default
    trimmed = value.strip()
    return trimmed or default


def _coerce_event_names(value: Any, default: tuple[str, ...]) -> tuple[str, ...]:
    if isinstance(value, str):
        items = [item.strip() for item in value.split(",")]
    elif isinstance(value, list):
        items = [item.strip() for item in value if isinstance(item, str)]
    else:
        return default

    normalized = tuple(item for item in items if item)
    return normalized or default


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


def _discover_raw_config(config_path: Path | None = None) -> MutableMapping[str, Any]:
    raw = _load_config(config_path)
    return raw if isinstance(raw, MutableMapping) else {}


def load_raw_config(config_path: Path | None = None) -> MutableMapping[str, Any]:
    """Load the raw project config for multi-user/global settings."""
    return dict(_discover_raw_config(config_path))


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


def _validate_user_id(user_id: str) -> str:
    trimmed = user_id.strip()
    if not trimmed or trimmed in {".", ".."}:
        raise ValueError("user_id must be a valid path segment")
    if "/" in trimmed or "\\" in trimmed:
        raise ValueError("user_id must be a valid path segment")
    return trimmed


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
    max_captcha_retries: int


@dataclass(frozen=True)
class SearchSettings:
    max_stale_pages: int


@dataclass(frozen=True)
class MessagingSettings:
    create_conversation_greeting: str


@dataclass(frozen=True)
class HookSettings:
    url_template: str
    timeout_seconds: int
    enabled_events: tuple[str, ...]


@dataclass(frozen=True)
class AppSettings:
    storage: StorageSettings
    keepalive: KeepaliveSettings
    search: SearchSettings
    messaging: MessagingSettings
    hook: HookSettings


def build_user_settings(
    user_id: str,
    token_file: Path,
    chrome_user_data_dir: Path,
    data_root: Path,
    keepalive_enabled: bool = True,
    keepalive_interval_minutes: int = DEFAULT_KEEPALIVE_INTERVAL_MINUTES,
    keepalive_max_captcha_retries: int = DEFAULT_KEEPALIVE_MAX_CAPTCHA_RETRIES,
    max_stale_pages: int = DEFAULT_SEARCH_MAX_STALE_PAGES,
    create_conversation_greeting: str = DEFAULT_CREATE_CONVERSATION_GREETING,
    hook_url_template: str = "",
    hook_timeout_seconds: int = DEFAULT_HOOK_TIMEOUT_SECONDS,
    hook_enabled_events: tuple[str, ...] = DEFAULT_HOOK_ENABLED_EVENTS,
) -> AppSettings:
    return AppSettings(
        storage=StorageSettings(
            data_root=data_root,
            user_id=user_id,
            token_file=token_file,
            chrome_user_data_dir=chrome_user_data_dir,
        ),
        keepalive=KeepaliveSettings(
            enabled=keepalive_enabled,
            interval_minutes=keepalive_interval_minutes,
            max_captcha_retries=keepalive_max_captcha_retries,
        ),
        search=SearchSettings(max_stale_pages=max_stale_pages),
        messaging=MessagingSettings(
            create_conversation_greeting=_coerce_greeting(
                create_conversation_greeting,
                DEFAULT_CREATE_CONVERSATION_GREETING,
            )
        ),
        hook=HookSettings(
            url_template=hook_url_template,
            timeout_seconds=hook_timeout_seconds,
            enabled_events=hook_enabled_events,
        ),
    )


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
    messaging_cfg = _section("messaging")
    hook_cfg = _section("hook")

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
        enabled=_env_bool(
            "XIANYU_KEEPALIVE_ENABLED",
            _coerce_bool(keepalive_cfg.get("enabled"), DEFAULT_KEEPALIVE_ENABLED),
        ),
        interval_minutes=_env_int(
            "XIANYU_KEEPALIVE_INTERVAL_MINUTES",
            _coerce_int(
                keepalive_cfg.get("interval_minutes"),
                DEFAULT_KEEPALIVE_INTERVAL_MINUTES,
            ),
        ),
        max_captcha_retries=_env_int(
            "XIANYU_KEEPALIVE_MAX_CAPTCHA_RETRIES",
            _coerce_int(
                keepalive_cfg.get("max_captcha_retries"),
                DEFAULT_KEEPALIVE_MAX_CAPTCHA_RETRIES,
            ),
        ),
    )

    search_settings = SearchSettings(
        max_stale_pages=_env_int(
            "XIANYU_SEARCH_MAX_STALE_PAGES",
            _coerce_int(
                search_cfg.get("max_stale_pages"), DEFAULT_SEARCH_MAX_STALE_PAGES
            ),
        ),
    )

    hook_settings = HookSettings(
        url_template=(
            os.environ.get("XIANYU_HOOK_URL_TEMPLATE")
            or _str_value(hook_cfg.get("url_template"))
            or ""
        ),
        timeout_seconds=_env_int(
            "XIANYU_HOOK_TIMEOUT_SECONDS",
            _coerce_int(hook_cfg.get("timeout_seconds"), DEFAULT_HOOK_TIMEOUT_SECONDS),
        ),
        enabled_events=_coerce_event_names(
            os.environ.get("XIANYU_HOOK_ENABLED_EVENTS", hook_cfg.get("enabled_events")),
            DEFAULT_HOOK_ENABLED_EVENTS,
        ),
    )

    env_greeting = os.environ.get("XIANYU_CREATE_CONVERSATION_GREETING")
    messaging_settings = MessagingSettings(
        create_conversation_greeting=_coerce_greeting(
            env_greeting
            if env_greeting is not None
            else messaging_cfg.get("create_conversation_greeting"),
            DEFAULT_CREATE_CONVERSATION_GREETING,
        )
    )

    return AppSettings(
        storage=storage_settings,
        keepalive=keepalive_settings,
        search=search_settings,
        messaging=messaging_settings,
        hook=hook_settings,
    )


def load_settings_for_user(
    user_id: str,
    data_root: Path | None = None,
    config_path: Path | None = None,
) -> AppSettings:
    """Load base settings, then derive explicit storage paths for one user."""

    base_settings = load_settings(config_path=config_path)
    validated_user_id = _validate_user_id(user_id)
    resolved_data_root = (
        _expand_path(data_root) if data_root else base_settings.storage.data_root
    )
    user_root = resolved_data_root / validated_user_id

    return build_user_settings(
        user_id=validated_user_id,
        data_root=resolved_data_root,
        token_file=user_root / "tokens" / DEFAULT_TOKEN_FILE_NAME,
        chrome_user_data_dir=user_root / DEFAULT_CHROME_PROFILE,
        keepalive_enabled=base_settings.keepalive.enabled,
        keepalive_interval_minutes=base_settings.keepalive.interval_minutes,
        keepalive_max_captcha_retries=base_settings.keepalive.max_captcha_retries,
        max_stale_pages=base_settings.search.max_stale_pages,
        create_conversation_greeting=base_settings.messaging.create_conversation_greeting,
        hook_url_template=base_settings.hook.url_template,
        hook_timeout_seconds=base_settings.hook.timeout_seconds,
        hook_enabled_events=base_settings.hook.enabled_events,
    )
