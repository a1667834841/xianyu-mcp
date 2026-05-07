"""
闲鱼助手
"""

from .api.client import XianyuApiClient

from .settings import (
    AppSettings,
    KeepaliveSettings,
    SearchSettings,
    StorageSettings,
    load_settings,
)

__version__ = "2.0.0"
__all__ = [
    "XianyuApiClient",
    "AppSettings",
    "KeepaliveSettings",
    "SearchSettings",
    "StorageSettings",
    "load_settings",
]
