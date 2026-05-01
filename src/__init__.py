"""
闲鱼助手 - 三鱼店铺自动化工作流
"""

from .browser import AsyncChromeManager, ChromeManager
from .session import SessionManager, login, refresh_token, check_cookie_valid
from .keepalive import CookieKeepaliveService
from .core import (
    XianyuApp,
    SearchItem,
    SearchParams,
    SearchOutcome,
    CopiedItem,
    search,
    publish,
    get_detail,
)

__version__ = "2.0.0"
__all__ = [
    "AsyncChromeManager",
    "ChromeManager",
    "SessionManager",
    "CookieKeepaliveService",
    "XianyuApp",
    "SearchItem",
    "SearchParams",
    "SearchOutcome",
    "CopiedItem",
    "login",
    "refresh_token",
    "check_cookie_valid",
    "search",
    "publish",
    "get_detail",
    "StorageSettings",
    "KeepaliveSettings",
    "SearchSettings",
    "AppSettings",
    "load_settings",
]

from .settings import (
    AppSettings,
    KeepaliveSettings,
    SearchSettings,
    StorageSettings,
    load_settings,
)
