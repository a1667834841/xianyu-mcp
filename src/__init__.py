"""
闲鱼助手 - 三鱼店铺自动化工作流
"""

from .browser import AsyncChromeManager, ChromeManager
from .session import SessionManager, login, refresh_token, check_cookie_valid
from .keepalive import CookieKeepaliveService
from .page_coordinator import PageCoordinator, PageLease
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
from .keepalive import CookieKeepaliveService

__version__ = "2.0.0"
__all__ = [
    # 核心类
    "AsyncChromeManager",
    "ChromeManager",  # 向后兼容
    "SessionManager",
    "CookieKeepaliveService",
    "PageCoordinator",
    "PageLease",
    "MultiUserManager",
    "XianyuApp",
    # 数据类
    "SearchItem",
    "SearchParams",
    "SearchOutcome",
    "CopiedItem",
    # 便捷函数
    "login",
    "refresh_token",
    "check_cookie_valid",
    "search",
    "publish",
    "get_detail",
    # Keepalive service
    "CookieKeepaliveService",
    # 设置导出
    "StorageSettings",
    "KeepaliveSettings",
    "SearchSettings",
    "AppSettings",
    "load_settings",
]

from .multi_user_manager import MultiUserManager

from .settings import (
    AppSettings,
    KeepaliveSettings,
    SearchSettings,
    StorageSettings,
    load_settings,
)
