"""
browser.py - Chrome 浏览器管理模块 (异步版本)
通过 CDP 协议 (9222 端口) 控制 Chrome 浏览器
"""

import os
import subprocess
import time
import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from typing import Optional, List, Dict

try:
    from .settings import AppSettings, load_settings
except ImportError:
    from settings import AppSettings, load_settings


def get_platform() -> str:
    """获取当前平台名称"""
    import sys
    if sys.platform == "darwin":
        return "macos"
    elif sys.platform == "win32":
        return "windows"
    elif sys.platform == "linux":
        return "linux"
    else:
        return "unknown"


def load_config(auto_create: bool = True) -> Dict:
    """
    加载配置文件

    优先级：
    1. 环境变量 XIANFU_CONFIG_PATH 指定的路径
    2. 项目目录 config.json
    3. 用户目录 ~/.claude/xianyu-chrome/config.json
    4. 默认配置（可选自动生成）

    Args:
        auto_create: 是否自动生成默认配置文件
    """
    # 默认配置
    default_config = {
        "chrome": {
            "path": {
                "macos": "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                "linux": "/usr/bin/google-chrome",
                "windows": "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
            },
            "port": 9222,
            "user_data_dir": str(Path.home() / ".claude" / "xianyu-chrome-profile")
        }
    }

    # 1. 检查环境变量指定的配置路径
    config_path_env = os.environ.get("XIANFU_CONFIG_PATH")
    if config_path_env and os.path.exists(config_path_env):
        try:
            with open(config_path_env, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[Config] 加载环境变量配置失败：{e}")

    # 2. 检查项目目录 config.json
    project_config = Path(__file__).parent.parent / "config.json"
    if project_config.exists():
        try:
            with open(project_config, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[Config] 加载项目配置失败：{e}")

    # 3. 检查用户目录配置
    user_config = Path.home() / ".claude" / "xianyu-chrome" / "config.json"
    if user_config.exists():
        try:
            with open(user_config, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[Config] 加载用户配置失败：{e}")

    # 4. 自动生成配置文件
    if auto_create:
        config_path = project_config
        try:
            config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(default_config, f, indent=2, ensure_ascii=False)
            print(f"[Config] 自动生成配置文件：{config_path}")
            return default_config
        except Exception as e:
            print(f"[Config] 生成默认配置失败：{e}")

    # 5. 返回默认配置
    print("[Config] 使用默认配置")
    return default_config


def get_chrome_path(config: Optional[Dict] = None, platform: Optional[str] = None) -> str:
    """
    获取 Chrome 浏览器路径

    Args:
        config: 配置字典 (可选)
        platform: 平台名称 (可选，默认自动检测)

    Returns:
        Chrome 可执行文件路径
    """
    if config is None:
        config = load_config()

    if platform is None:
        platform = get_platform()

    # 1. 优先使用环境变量
    env_path = os.environ.get("XIANFU_CHROME_PATH")
    if env_path and os.path.exists(env_path):
        return env_path

    # 2. 从配置获取
    chrome_paths = config.get("chrome", {}).get("path", {})
    if platform in chrome_paths:
        path = chrome_paths[platform]
        if path and os.path.exists(path):
            return path

    # 3. 回退到默认路径
    default_paths = {
        "macos": [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Google Chrome Beta.app/Contents/MacOS/Google Chrome Beta",
        ],
        "linux": [
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium-browser",
            "/usr/bin/chromium",
        ],
        "windows": [
            "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
            "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
        ]
    }

    for path in default_paths.get(platform, []):
        if os.path.exists(path):
            return path

    # 4. 最后回退
    return "google-chrome"


class AsyncChromeManager:
    """Chrome 浏览器管理器 (异步版本)"""

    DEFAULT_PORT = 9222
    DEFAULT_HOST = "localhost"
    DEFAULT_USER_DATA_DIR = Path.home() / ".claude" / "xianyu-chrome-profile"

    def __init__(
        self,
        port: int = DEFAULT_PORT,
        host: str = DEFAULT_HOST,
        user_data_dir: Optional[Path] = None,
        headless: bool = False,
        auto_start: bool = True,  # 是否自动启动本地 Chrome
        config: Optional[Dict] = None,  # 配置文件内容 (可选)
        settings: Optional[AppSettings] = None,
    ):
        self.settings = settings or load_settings()
        # 加载配置
        self.config = config or load_config()

        # 从配置获取设置 (可通过参数覆盖)
        chrome_config = self.config.get("chrome", {})
        self.port = port or chrome_config.get("port", self.DEFAULT_PORT)
        self.host = host
        fallback_profile = chrome_config.get("user_data_dir")
        fallback_dir = (
            Path(fallback_profile).expanduser()
            if fallback_profile
            else self.DEFAULT_USER_DATA_DIR
        )
        preferred_dir = (
            user_data_dir
            or self.settings.storage.chrome_user_data_dir
            or fallback_dir
        )
        self.user_data_dir = Path(preferred_dir).expanduser()
        self.headless = headless
        self.auto_start = auto_start

        # 获取 Chrome 路径
        self.chrome_path = get_chrome_path(self.config)

        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self._work_page: Optional[Page] = None
        self._keepalive_page: Optional[Page] = None
        self.page: Optional[Page] = None

        # 创建用户数据目录
        self.user_data_dir.mkdir(parents=True, exist_ok=True)

        print(f"[Browser] Chrome 路径：{self.chrome_path}")
        print(f"[Browser] 用户数据目录：{self.user_data_dir}")

    def start_chrome(self, timeout: int = 30) -> bool:
        """
        启动 Chrome 浏览器 (带调试端口)

        Args:
            timeout: 启动超时时间 (秒)

        Returns:
            bool: 是否启动成功
        """
        # 检查 Chrome 是否存在
        if not os.path.exists(self.chrome_path):
            # 尝试从 PATH 查找
            chrome_path = "google-chrome"
            print(f"[Browser] 配置的 Chrome 路径不存在，使用系统路径：{chrome_path}")
        else:
            chrome_path = self.chrome_path

        # 构建启动命令
        cmd = [
            chrome_path,
            f"--remote-debugging-port={self.port}",
            f"--user-data-dir={self.user_data_dir}",
            "--disable-gpu",
            "--no-first-run",
            "--disable-dev-shm-usage",
        ]

        if self.headless:
            cmd.append("--headless=new")

        try:
            # 后台启动 Chrome
            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )

            # 等待浏览器启动
            start_time = time.time()
            while time.time() - start_time < timeout:
                try:
                    import socket
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(1)
                    result = sock.connect_ex(('localhost', self.port))
                    sock.close()
                    if result == 0:
                        print(f"[Browser] Chrome 已启动在端口 {self.port}")
                        return True
                except:
                    pass
                time.sleep(0.5)

            print(f"[Browser] Chrome 启动超时")
            return False

        except Exception as e:
            print(f"[Browser] 启动 Chrome 失败：{e}")
            return False

    async def connect(self) -> bool:
        """
        连接到 Chrome 浏览器 (通过 CDP)

        Returns:
            bool: 是否连接成功
        """
        try:
            self.playwright = await async_playwright().start()

            # 先尝试获取正确的 WebSocket URL
            ws_url = await self._get_websocket_url()
            if not ws_url:
                # 回退到默认 URL
                ws_url = f"ws://{self.host}:{self.port}"

            # 使用 ws:// 协议连接 CDP
            self.browser = await self.playwright.chromium.connect_over_cdp(ws_url)
            self.context = (
                self.browser.contexts[0]
                if self.browser.contexts
                else await self.browser.new_context()
            )

            self._keepalive_page = None

            if self.context.pages:
                self._work_page = self.context.pages[0]
            else:
                self._work_page = await self.context.new_page()

            self.page = self._work_page

            print(f"[Browser] 已连接到 Chrome ({self.host}:{self.port})")
            return True

        except Exception as e:
            print(f"[Browser] 连接失败：{e}")
            return False

    def _has_active_connection(self) -> bool:
        return bool(
            self.browser
            and self.context
            and self._work_page
            and self.page
        )

    async def _get_websocket_url(self) -> Optional[str]:
        """
        从 Chrome 调试端点获取 WebSocket URL

        Returns:
            WebSocket URL 或 None
        """
        try:
            import urllib.request
            import json
            import socket

            # 获取目标主机 IP（用于实际连接）
            target_host = self.host
            if self.host not in ("localhost", "127.0.0.1", "::1"):
                try:
                    target_host = socket.gethostbyname(self.host)
                except socket.gaierror:
                    pass

            # 创建请求，设置 Host: localhost 以绕过 Chrome 的安全限制
            url = f"http://{target_host}:{self.port}/json/version"
            req = urllib.request.Request(url, headers={"Host": "localhost"})
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode())
                ws_url = data.get("webSocketDebuggerUrl")
                # 替换 WebSocket URL 中的主机名为实际主机（带端口）
                # Chrome返回的URL可能是 ws://localhost/devtools/browser/xxx（无端口）
                # 需要替换为 ws://target_host:port/devtools/browser/xxx
                if ws_url and self.host not in ("localhost", "127.0.0.1"):
                    ws_url = ws_url.replace("127.0.0.1", f"{target_host}:{self.port}").replace("localhost", f"{target_host}:{self.port}")
                return ws_url
        except Exception as e:
            print(f"[Browser] 获取 WebSocket URL 失败：{e}")
        return None

    async def ensure_running(self) -> bool:
        """
        确保 Chrome 运行并连接

        Returns:
            bool: 是否成功
        """
        # 避免重复连接已有会话
        if self._has_active_connection():
            return True

        # 先尝试连接
        if await self.connect():
            return True

        # 如果是本地且允许自动启动，则启动 Chrome
        if self.auto_start and self.host == "localhost":
            if self.start_chrome():
                await asyncio.sleep(2)  # 等待 Chrome 完全启动
                return await self.connect()

        print(f"[Browser] 无法连接到 {self.host}:{self.port}，请确保 Chrome 已启动")
        return False

    async def _ensure_page(self) -> bool:
        """
        确保有可用的 page 对象

        Returns:
            bool: 是否成功
        """
        if self._work_page:
            return True

        if not self.context:
            return False

        try:
            # 尝试获取或创建页面
            if self.context.pages:
                self._work_page = self.context.pages[0]
            else:
                self._work_page = await self.context.new_page()
            self.page = self._work_page
            return True
        except Exception as e:
            print(f"[Browser] 创建页面失败：{e}")
            return False

    async def get_work_page(self) -> Page:
        """
        获取工作页，确保 self.page 始终指向它
        """
        if self._work_page:
            self.page = self._work_page
            return self._work_page

        if not await self._ensure_page():
            raise RuntimeError("[Browser] 无法获取工作页面：上下文未初始化")

        return self._work_page

    async def get_keepalive_page(self) -> Page:
        """
        获取保活页，与工作页保持区分
        """
        if self._keepalive_page and self.context and self._keepalive_page in self.context.pages:
            return self._keepalive_page

        await self.get_work_page()
        if not self.context:
            raise RuntimeError("[Browser] 无法获取保活页面：上下文未初始化")

        self._keepalive_page = await self.context.new_page()
        return self._keepalive_page

    async def navigate(self, url: str, wait_until: str = "networkidle") -> bool:
        """
        导航到 URL

        Args:
            url: 目标 URL
            wait_until: 等待条件 (load/domcontentloaded/networkidle/commit)

        Returns:
            bool: 是否成功
        """
        if not self.page:
            return False

        try:
            await self.page.goto(url, wait_until=wait_until, timeout=30000)
            return True
        except Exception as e:
            print(f"[Browser] 导航失败：{e}")
            return False

    async def get_cookie(self, name: str, domain: str = ".goofish.com") -> Optional[str]:
        """
        获取 Cookie

        Args:
            name: Cookie 名称
            domain: Cookie 域名

        Returns:
            Cookie 值，不存在返回 None
        """
        if not self.context:
            return None

        try:
            cookies = await self.context.cookies()
            for cookie in cookies:
                if cookie.get("name") == name:
                    return cookie.get("value")
            return None
        except Exception as e:
            print(f"[Browser] 获取 Cookie 失败：{e}")
            return None

    async def get_all_cookies(self) -> List[Dict]:
        """
        获取所有 Cookie

        Returns:
            Cookie 列表，每个元素为字典
        """
        if not self.context:
            return []

        try:
            cookies = await self.context.cookies()
            return cookies
        except Exception as e:
            print(f"[Browser] 获取所有 Cookie 失败：{e}")
            return []

    async def get_full_cookie_string(self) -> str:
        """
        获取完整 Cookie 字符串（用于 API 请求）

        Returns:
            Cookie 字符串，格式："name1=value1; name2=value2"
        """
        cookies = await self.get_all_cookies()
        if not cookies:
            return ""

        cookie_parts = [f"{c.get('name')}={c.get('value')}" for c in cookies]
        return "; ".join(cookie_parts)

    async def get_xianyu_token(self) -> Optional[str]:
        """
        获取闲鱼 Token (_m_h5_tk)

        Returns:
            Token 值 (不含时间戳部分)
        """
        full_token = await self.get_cookie("_m_h5_tk")
        if full_token:
            # Token 格式："xxx_timestamp"，取下划线前的部分
            return full_token.split("_")[0]
        return None

    async def close(self):
        """关闭浏览器连接"""
        if self.browser:
            await self.browser.close()
            self.browser = None
        if self.context:
            self.context = None
        self._work_page = None
        self._keepalive_page = None
        self.page = None
        if self.playwright:
            await self.playwright.stop()
            self.playwright = None
        print("[Browser] 已关闭连接")

    async def __aenter__(self):
        """异步上下文管理器入口"""
        success = await self.ensure_running()
        if not success:
            raise RuntimeError("无法启动或连接 Chrome 浏览器")
        await self.get_work_page()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.close()

    # 同步方法 (向后兼容)
    def connect_sync(self) -> bool:
        return asyncio.run(self.connect())

    def navigate_sync(self, url: str) -> bool:
        return asyncio.run(self.navigate(url))

    def get_cookie_sync(self, name: str) -> Optional[str]:
        return asyncio.run(self.get_cookie(name))

    def get_xianyu_token_sync(self) -> Optional[str]:
        return asyncio.run(self.get_xianyu_token())

    def close_sync(self):
        """同步关闭浏览器"""
        if self.browser:
            try:
                self.browser.close()
            except:
                pass
        if self.playwright:
            try:
                # 尝试在新事件循环中停止 playwright
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(self.playwright.stop())
                finally:
                    loop.close()
            except Exception as e:
                print(f"[Browser] 关闭 playwright 失败：{e}")
        print("[Browser] 已关闭连接")

    def __enter__(self):
        """同步上下文管理器入口"""
        self.ensure_running()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """同步上下文管理器出口"""
        self.close_sync()


# 便捷函数
def get_browser() -> AsyncChromeManager:
    """获取浏览器实例"""
    return AsyncChromeManager()


# 向后兼容：ChromeManager 是 AsyncChromeManager 的别名
ChromeManager = AsyncChromeManager
