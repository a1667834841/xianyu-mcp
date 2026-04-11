from __future__ import annotations

import os
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

        env_cdp_host = os.environ.get("BROWSER_CDP_HOST") or os.environ.get("CDP_HOST")
        env_size = os.environ.get("BROWSER_POOL_SIZE")
        env_start_port = os.environ.get("BROWSER_CDP_START_PORT")
        env_profile_root = os.environ.get("BROWSER_PROFILE_ROOT")

        return cls(
            size=int(env_size or browser_pool.get("size", 1)),
            cdp_host=str(env_cdp_host or browser_pool.get("cdp_host", "browser")),
            start_port=int(env_start_port or browser_pool.get("start_port", 9222)),
            profile_root=Path(
                str(
                    env_profile_root
                    or browser_pool.get("profile_root", "/data/browser-pool")
                )
            ),
            registry_file=Path(
                str(multi_user.get("registry_file", "/data/registry/users.json"))
            ),
            default_display_name_prefix=str(
                multi_user.get("default_display_name_prefix", "user")
            ),
        )
