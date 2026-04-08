"""
session.py - 闲鱼会话管理器
管理登录、Token 刷新和 Cookie 有效性检查
"""

import json
import time
import hashlib
import asyncio
import base64
import io
import requests
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any, Union

try:
    from .settings import AppSettings, load_settings
except ImportError:
    from settings import AppSettings, load_settings

try:
    from .browser import AsyncChromeManager
except ImportError:
    from browser import AsyncChromeManager


# ==================== 二维码显示相关 ====================


def show_qr_in_terminal(qr_data: str):
    """在终端显示二维码图片"""
    # qr_data 已经是 Base64 或 URL
    if qr_data.startswith("data:image"):
        # 已经是 Base64 格式，直接解码显示
        try:
            header, img_data = qr_data.split(",", 1)
            img_data = base64.b64decode(img_data)
        except Exception as e:
            print(f"[QR] 解析 Base64 失败：{e}")
            _show_qr_url(qr_data)
            return
    elif qr_data.startswith("http"):
        # URL 格式，尝试下载或使用 qrcode 生成
        try:
            import urllib.request

            with urllib.request.urlopen(qr_data, timeout=5) as response:
                img_data = response.read()
        except Exception as e:
            print(f"[QR] 下载二维码失败：{e}")
            # 降级为使用 qrcode 生成
            try:
                import qrcode
                from qrcode.terminal import print as qr_print

                _print_qr_header()
                qr_print(qr_data)
                _print_qr_footer()
                return
            except ImportError:
                pass
            except Exception as e2:
                print(f"[QR] qrcode 生成失败：{e2}")
            _show_qr_url(qr_data)
            return
    else:
        # 其他格式，尝试直接解码
        header, img_data = qr_data.split(",", 1) if "," in qr_data else ("", qr_data)
        img_data = base64.b64decode(img_data)

    # 尝试使用 term_image 显示
    try:
        from term_image.client import TermImage
        from PIL import Image

        img = Image.open(io.BytesIO(img_data))
        max_size = (40, 40)
        img.thumbnail((max_size[0] * 8, max_size[1] * 16))
        term_img = TermImage(img)
        _print_qr_header()
        term_img.draw()
        _print_qr_footer()
        return
    except ImportError:
        pass
    except Exception as e:
        print(f"[QR] term_image 显示失败：{e}")

    # 尝试使用 qrcode 生成 ASCII 二维码
    try:
        import qrcode
        from qrcode.terminal import print as qr_print

        qr_content = _extract_qr_content(qr_data)
        if qr_content:
            _print_qr_header()
            qr_print(qr_content)
            _print_qr_footer()
            return
    except ImportError:
        pass
    except Exception as e:
        print(f"[QR] qrcode 生成失败：{e}")

    # 降级方案：显示 URL
    _show_qr_url(qr_data)


def _extract_qr_content(qr_url: str) -> Optional[str]:
    """从二维码 URL 提取原始内容"""
    try:
        import urllib.request
        from PIL import Image
        from pyzbar.pyzbar import decode

        with urllib.request.urlopen(qr_url, timeout=5) as response:
            img_data = response.read()
        img = Image.open(io.BytesIO(img_data))
        decoded = decode(img)
        if decoded:
            return decoded[0].data.decode("utf-8")
    except ImportError:
        return qr_url
    except Exception:
        pass
    return qr_url


def _print_qr_header():
    """打印二维码头部提示"""
    print("\n" + "=" * 60)
    print("请打开闲鱼 APP 扫码登录".center(60))
    print("=" * 60 + "\n")


def _print_qr_footer():
    """打印二维码底部提示"""
    print("\n" + "=" * 60)
    print("提示：如果无法扫码，请在手机闲鱼 APP 中扫描上方二维码")
    print("=" * 60 + "\n")


def _show_qr_url(qr_data: str):
    """降级方案：显示文字提示和 URL"""
    _print_qr_header()
    print(f"二维码 URL: {qr_data}")
    print("\n提示：")
    print("  1. 复制上方 URL 到浏览器打开")
    print("  2. 或直接在浏览器窗口中扫码")
    print("  3. 安装 pyzbar 可显示 ASCII 二维码：pip install pyzbar")
    _print_qr_footer()


class SessionManager:
    """闲鱼会话管理器 - 登录态全生命周期管理"""

    # API 配置
    API_BASE_URL = "https://h5api.m.goofish.com/h5/mtop.idle.web.user.page.nav/1.0/"
    API_NAME = "mtop.idle.web.user.page.nav"
    APP_KEY = "34839810"

    # Token 配置
    TOKEN_FILE = Path.home() / ".claude" / "xianyu-tokens" / "token.json"
    TOKEN_EXPIRY_HOURS = 24

    def __init__(
        self,
        chrome_manager: Optional[AsyncChromeManager] = None,
        settings: Optional[AppSettings] = None,
    ):
        """
        初始化会话管理器

        Args:
            chrome_manager: 浏览器管理器实例
        """
        resolved_settings = (
            settings
            or (getattr(chrome_manager, "settings", None) if chrome_manager else None)
            or load_settings()
        )
        self.settings = resolved_settings
        self.chrome_manager = chrome_manager or AsyncChromeManager(
            settings=self.settings
        )
        self.token: Optional[str] = None
        self.full_cookie: Optional[str] = None
        self.token_file = self.settings.storage.token_file
        self.token_file.parent.mkdir(parents=True, exist_ok=True)

    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self.chrome_manager.ensure_running()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.chrome_manager.close()

    async def refresh_token(self) -> Optional[Dict[str, str]]:
        """
        刷新 token - 通过访问闲鱼首页获取最新 token

        Returns:
            字典：{"token": "...", "full_cookie": "..."}
            失败返回 None
        """
        try:
            # 确保浏览器运行
            if not await self.chrome_manager.ensure_running():
                print("[Session] 浏览器启动失败")
                return None

            # 导航到闲鱼首页
            print("[Session] 正在刷新 token...")
            await self.chrome_manager.navigate("https://www.goofish.com")

            # 等待页面加载
            import asyncio

            await asyncio.sleep(2)

            # 从浏览器获取最新 cookie
            token = await self.chrome_manager.get_xianyu_token()
            full_cookie = await self.chrome_manager.get_cookie("_m_h5_tk")

            if not token:
                print("[Session] 无法获取 token，请检查是否已登录")
                return None

            # 更新内存中的 token
            self.token = token
            self.full_cookie = full_cookie

            # 获取完整 cookie 字符串并保存
            full_cookie_str = await self.chrome_manager.get_full_cookie_string()
            self.save_cookie(full_cookie_str)

            print(f"[Session] Token 刷新成功")
            return {"token": token, "full_cookie": full_cookie}

        except Exception as e:
            print(f"[Session] 刷新 token 失败：{e}")
            return None

    async def check_cookie_valid(self) -> bool:
        """
        检查 cookie 是否有效 - 调用用户信息接口

        接口：mtop.idle.web.user.page.nav
        成功响应：ret[0] 包含 "SUCCESS"

        Returns:
            bool: cookie 是否有效
        """
        try:
            # 确保浏览器运行
            if not await self.chrome_manager.ensure_running():
                print("[Session] 浏览器未运行")
                return False

            # 导航到闲鱼首页确保 cookie 是最新的
            print("[Session] 正在检查 cookie 有效性...")
            await self.chrome_manager.navigate("https://www.goofish.com")

            import asyncio

            await asyncio.sleep(2)

            # 获取完整 cookie 字符串（包含 cookie2, _m_h5_tk, sgcookie 等）
            full_cookie_str = await self.chrome_manager.get_full_cookie_string()

            if not full_cookie_str:
                print("[Session] 未找到 cookie")
                return False

            # 从浏览器获取 _m_h5_tk cookie 用于签名（格式：token_timestamp）
            m_h5_tk = await self.chrome_manager.get_cookie("_m_h5_tk")
            if not m_h5_tk:
                print("[Session] 无法获取 _m_h5_tk")
                return False

            # 构建请求
            data = {}
            sign_params = self._generate_sign(data, m_h5_tk)

            # 设置请求头
            headers = {
                "accept": "application/json",
                "accept-language": "zh-CN,zh;q=0.9",
                "content-type": "application/x-www-form-urlencoded",
                "origin": "https://www.goofish.com",
                "referer": "https://www.goofish.com/",
                "sec-ch-ua": '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"macOS"',
                "sec-fetch-dest": "empty",
                "sec-fetch-mode": "cors",
                "sec-fetch-site": "same-site",
                "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
                "cookie": full_cookie_str,
            }

            # 构建 URL 参数
            url_params = {
                "jsv": "2.7.2",
                "appKey": sign_params["appKey"],
                "t": sign_params["t"],
                "sign": sign_params["sign"],
                "v": "1.0",
                "type": "originaljson",
                "accountSite": "xianyu",
                "dataType": "json",
                "timeout": "20000",
                "api": self.API_NAME,
                "sessionOption": "AutoLoginOnly",
            }

            # 发送 POST 请求（带重试）
            session = requests.Session()
            max_retries = 2
            for attempt in range(max_retries + 1):
                try:
                    response = session.post(
                        self.API_BASE_URL,
                        params=url_params,
                        headers=headers,
                        data={"data": sign_params["data"]},
                        timeout=10,
                    )

                    result = response.json()

                    # 判断是否成功
                    ret = result.get("ret", [])
                    if not ret or "SUCCESS" not in ret[0]:
                        # 真正过期才返回 False
                        if ret and "SESSION_EXPIRED" in ret[0]:
                            print(f"[Session] Cookie 已过期：{ret[0]}")
                            return False
                        # 其他错误可能是临时问题，重试
                        print(
                            f"[Session] 检查 cookie 收到响应：{ret} (尝试 {attempt + 1}/{max_retries + 1})"
                        )
                        if attempt < max_retries:
                            await asyncio.sleep(1)
                            continue
                        return False

                    # 深度检查：验证是否返回真实用户信息
                    module = result.get("data", {}).get("module", {})
                    base = module.get("base", {})
                    display_name = base.get("displayName")

                    if display_name:
                        print(f"[Session] Cookie 有效，用户：{display_name}")
                        return True
                    else:
                        # 返回 SUCCESS 但没有用户信息，可能是异常状态
                        print(f"[Session] 接口返回成功但未获取到用户信息")
                        if attempt < max_retries:
                            await asyncio.sleep(1)
                            continue
                        return False

                except requests.exceptions.RequestException as e:
                    print(
                        f"[Session] 网络请求失败 (尝试 {attempt + 1}/{max_retries + 1}): {e}"
                    )
                    if attempt < max_retries:
                        await asyncio.sleep(1)
                        continue
                    return False

            return False

        except Exception as e:
            print(f"[Session] 检查 cookie 失败：{e}")
            return False

    async def get_token(self) -> Optional[str]:
        """
        获取当前 token

        Returns:
            token 值，不存在返回 None
        """
        # 优先返回内存中的 token
        if self.token:
            return self.token

        # 从浏览器获取
        try:
            token = await self.chrome_manager.get_xianyu_token()
            self.token = token
            return token
        except:
            return None

    async def get_full_cookie(self) -> Optional[str]:
        """
        获取完整 cookie

        Returns:
            完整 cookie 值，不存在返回 None
        """
        # 优先返回内存中的 cookie
        if self.full_cookie:
            return self.full_cookie

        # 从浏览器获取
        try:
            full_cookie = await self.chrome_manager.get_cookie("_m_h5_tk")
            self.full_cookie = full_cookie
            return full_cookie
        except:
            return None

    # ==================== Cookie 缓存管理 ====================

    def load_cached_cookie(self) -> Optional[str]:
        """
        从缓存加载完整 Cookie，过期或不存在返回 None

        Returns:
            完整 cookie 字符串，格式："name1=value1; name2=value2; ..."
        """
        if not self.token_file.exists():
            return None

        try:
            with open(self.token_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            expires_at = datetime.fromisoformat(data["expires_at"])
            if datetime.now() > expires_at:
                print("[Session] 缓存 Cookie 已过期")
                return None

            print(f"[Session] 从缓存加载 Cookie (过期时间：{expires_at})")
            return data.get("full_cookie") or data.get("token")

        except Exception as e:
            print(f"[Session] 加载缓存 Cookie 失败：{e}")
            return None

    def save_cookie(self, full_cookie: str):
        """
        保存完整 Cookie 到缓存

        Args:
            full_cookie: 完整 cookie 字符串
        """
        try:
            now = datetime.now()
            expires_at = now + timedelta(hours=self.TOKEN_EXPIRY_HOURS)
            existing: Dict[str, Any] = {}
            if self.token_file.exists():
                try:
                    existing = json.loads(
                        self.token_file.read_text(encoding="utf-8")
                    )
                except Exception:
                    existing = {}
                if not isinstance(existing, dict):
                    existing = {}

            data = {
                "full_cookie": full_cookie,
                "created_at": existing.get("created_at", now.isoformat()),
                "updated_at": (
                    now.isoformat()
                    if existing.get("full_cookie") != full_cookie
                    else existing.get("updated_at", now.isoformat())
                ),
                "last_refresh_at": now.isoformat(),
                "expires_at": expires_at.isoformat(),
            }

            with open(self.token_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            print(f"[Session] Cookie 已保存 (过期时间：{expires_at})")

        except Exception as e:
            print(f"[Session] 保存 Cookie 失败：{e}")

    # ==================== 登录功能 ====================

    async def check_login_status(self) -> bool:
        """
        检查当前登录状态 - 深度检查

        通过调用用户信息接口 (mtop.idle.web.user.page.nav) 验证登录有效性
        成功返回用户详细信息，失败返回 False

        Returns:
            bool: 登录是否有效
        """
        # 复用 check_cookie_valid 的逻辑
        return await self.check_cookie_valid()

    async def login(self, timeout: int = 30) -> Dict[str, Any]:
        """
        登录流程：
        1. 访问闲鱼首页
        2. 检查是否已登录 → 已登录则直接返回
        3. 未登录则获取并显示二维码
        4. 返回二维码数据（不等待扫码）

        Args:
            timeout: 等待二维码 API 超时时间（秒），默认 15 秒

        Returns:
            字典，包含：
            - success: bool
            - logged_in: bool (是否已登录)
            - token: str (可选，已登录时返回)
            - qr_code: Dict (可选，未登录时返回)
            - message: str
        """
        # 确保浏览器运行
        if not await self.chrome_manager.ensure_running():
            return {"success": False, "message": "浏览器启动失败"}

        # 设置二维码 API 监听器（在导航之前）
        page = self.chrome_manager.page
        if not page:
            return {"success": False, "message": "无法获取页面"}

        capture_event = asyncio.Event()
        captured_data = {}

        async def process_response(response):
            try:
                url = response.url
                if "newlogin/qrcode/generate.do" in url:
                    data = await response.json()
                    content = data.get("content", {})
                    qr_data = content.get("data", {})

                    code_content = qr_data.get("codeContent")
                    ck = qr_data.get("ck")
                    t = qr_data.get("t")

                    if code_content:
                        if code_content.startswith("http://"):
                            code_content = code_content.replace("http://", "https://")

                        captured_data.update({"url": code_content, "ck": ck, "t": t})
                        capture_event.set()
                        print(f"[Session] 已捕获二维码 API 响应")
            except Exception as e:
                print(f"[Session] 解析二维码响应失败：{e}")

        def on_response(response):
            asyncio.create_task(process_response(response))

        # 先设置监听器
        page.on("response", on_response)

        # 访问闲鱼首页
        print("[Session] 正在访问闲鱼首页...")
        await self.chrome_manager.navigate("https://www.goofish.com")
        await asyncio.sleep(2)

        if await self.check_login_status():
            print("[Session] 已登录")
            m_h5_tk = await self.chrome_manager.get_cookie("_m_h5_tk")
            self.save_cookie(await self.chrome_manager.get_full_cookie_string())
            return {
                "success": True,
                "logged_in": True,
                "token": m_h5_tk.split("_")[0] if m_h5_tk else None,
                "message": "已登录",
            }

        # 未登录，尝试点击登录按钮触发二维码
        print("[Session] 未登录，正在获取二维码...")
        try:
            login_btn = self.chrome_manager.page.locator(
                "button", has_text="登录"
            ).first
            if await login_btn.is_visible():
                await login_btn.click()
                print("[Session] 已点击登录按钮")
                await asyncio.sleep(2)
        except Exception as e:
            print(f"[Session] 点击登录按钮失败：{e}")

        # 等待二维码 API 响应
        try:
            await asyncio.wait_for(capture_event.wait(), timeout=timeout)
            print(f"[Session] 已获取二维码 URL: {captured_data['url'][:80]}...")

            # 生成二维码图片（Base64 + ASCII）
            qr_result = await self._generate_qr_base64(captured_data["url"])
            ascii_qr = self._generate_ascii_qr(captured_data["url"])

            qr_data = {
                "url": captured_data["url"],
                "public_url": qr_result.get("public_url", ""),
                "text": captured_data["url"],
                "ck": captured_data.get("ck"),
                "t": captured_data.get("t"),
            }

            # 显示二维码
            if qr_data.get("public_url"):
                print(f"[Session] 二维码图片: {qr_data['public_url']}")
            else:
                print(f"[Session] 二维码 URL: {qr_data['text']}")

            # 返回二维码数据（不等待扫码）
            return {
                "success": True,
                "logged_in": False,
                "qr_code": qr_data,
                "message": "请扫码登录。扫码后浏览器会自动跳转，然后请调用 check_session 确认登录状态",
            }

        except asyncio.TimeoutError:
            print(f"[Session] 等待二维码响应超时")
            return {"success": False, "message": "获取二维码超时"}

    async def _restore_cookie(self, cookie_str: str):
        """
        恢复 cookie 字符串到浏览器

        Args:
            cookie_str: 完整 cookie 字符串，格式："name1=value1; name2=value2; ..."
        """
        try:
            # 解析 cookie 字符串
            cookies_to_set = []
            for part in cookie_str.split("; "):
                if "=" in part:
                    name, value = part.split("=", 1)
                    cookies_to_set.append(
                        {
                            "name": name,
                            "value": value,
                            "domain": ".goofish.com",
                            "path": "/",
                        }
                    )

            # 批量设置 cookie
            if self.chrome_manager.context and cookies_to_set:
                # 先清除旧 cookie
                await self.chrome_manager.context.clear_cookies()
                # 添加新 cookie
                await self.chrome_manager.context.add_cookies(cookies_to_set)
                print("[Session] Cookie 已恢复到浏览器")
        except Exception as e:
            print(f"[Session] 恢复 Cookie 失败：{e}")

    async def show_qr_code(self) -> Optional[Dict[str, Any]]:
        """
        显示登录二维码（不等待扫码）

        访问闲鱼首页，如果未登录则显示二维码。用户扫码后浏览器会自动跳转完成登录。

        注意：此方法内部复用 login() 的逻辑，推荐使用 login() 方法。

        Returns:
            字典，包含：
            - success: bool
            - logged_in: bool (是否已登录)
            - qr_code: Dict (仅未登录时返回，包含 url/base64/ascii/text)
            - message: str

            如果已登录，返回 {"success": True, "logged_in": True, "message": "已登录"}
            如果未登录，返回 {"success": True, "logged_in": False, "qr_code": {...}, "message": "请扫码登录"}
        """
        # 复用 login() 方法
        result = await self.login(timeout=15)
        return result

    async def _get_qr_code(self, timeout: int = 15) -> Optional[Dict[str, Any]]:
        """
        获取二维码数据（监听页面触发的 API）

        通过监听页面访问 newlogin/qrcode/generate.do 接口获取二维码，
        而不是自己主动调用接口，确保二维码与页面一致。

        Args:
            timeout: 等待 API 响应超时时间（秒）

        Returns:
            二维码数据包：
            - url: str (二维码图片 URL)
            - base64: str (Base64 图片数据，格式 data:image/png;base64,xxx)
            - ascii: str (ASCII 二维码，可选)
            - text: str (纯文本 URL，降级用)
            - ck: str (验证 token，用于后续轮询)
            - t: int (时间戳)

            失败返回 None
        """
        page = self.chrome_manager.page
        if not page:
            return None

        capture_event = asyncio.Event()
        captured_data = {}

        async def process_response(response):
            try:
                url = response.url
                if "newlogin/qrcode/generate.do" in url:
                    data = await response.json()
                    content = data.get("content", {})
                    qr_data = content.get("data", {})

                    code_content = qr_data.get("codeContent")
                    ck = qr_data.get("ck")
                    t = qr_data.get("t")

                    if code_content:
                        if code_content.startswith("http://"):
                            code_content = code_content.replace("http://", "https://")

                        captured_data.update({"url": code_content, "ck": ck, "t": t})
                        capture_event.set()
                        print(f"[Session] 已捕获二维码 API 响应")
            except Exception as e:
                print(f"[Session] 解析二维码响应失败：{e}")

        def on_response(response):
            asyncio.create_task(process_response(response))

        # 1. 先设置监听器
        page.on("response", on_response)

        # 2. 导航到闲鱼首页（会触发二维码接口）
        print("[Session] 正在访问闲鱼首页...")
        await self.chrome_manager.navigate("https://www.goofish.com")

        # 3. 等待 API 响应
        try:
            await asyncio.wait_for(capture_event.wait(), timeout=timeout)
            print(f"[Session] 已获取二维码 URL: {captured_data['url'][:80]}...")

            # 4. 生成二维码图片（Base64 + ASCII + R2上传）
            qr_result = await self._generate_qr_base64(captured_data["url"])
            ascii_qr = self._generate_ascii_qr(captured_data["url"])

            return {
                "url": captured_data["url"],
                "public_url": qr_result.get("public_url", ""),
                "text": captured_data["url"],
                "ck": captured_data.get("ck"),
                "t": captured_data.get("t"),
            }

        except asyncio.TimeoutError:
            print(f"[Session] 等待二维码响应超时")
            return None

    async def _get_qr_code_from_dom(self) -> Optional[Dict[str, Any]]:
        """
        从 DOM 获取二维码 URL（降级方案）

        Returns:
            二维码数据包
        """
        page = self.chrome_manager.page
        if not page:
            return None

        try:
            # 更精确的选择器，专门针对闲鱼登录二维码
            qr_src = await page.evaluate("""() => {
                // 优先查找登录二维码相关的图片
                const selectors = [
                    // 闲鱼登录页二维码容器内的图片
                    '.qrcode img', '.qr-code img', '.login-qrcode img',
                    // 包含 qrcodeCheck 的图片（闲鱼官方二维码 URL 特征）
                    'img[src*="qrcodeCheck"]', 'img[src*="qrCode"]',
                    // 二维码容器
                    'img[class*="qrcode"]', 'img[class*="qr-code"]',
                ];

                for (const selector of selectors) {
                    const img = document.querySelector(selector);
                    if (img && img.src && img.src.includes('alicdn.com')) {
                        // 排除小图标（<50x50）
                        if (img.width >= 50 && img.height >= 50) {
                            return img.src;
                        }
                    }
                }

                // 备选：查找所有符合条件的图片
                const imgs = document.querySelectorAll('img');
                for (let img of imgs) {
                    const src = img.src || '';
                    // 闲鱼二维码通常包含这些特征
                    if (src.includes('qrcodeCheck') ||
                        src.includes('passport.goofish.com') ||
                        (src.includes('alicdn.com') &&
                         img.width >= 100 && img.width <= 300 &&
                         img.height >= 100 && img.height <= 300)) {
                        return src;
                    }
                }

                return null;
            }""")

            if qr_src:
                if qr_src.startswith("http://"):
                    qr_src = qr_src.replace("http://", "https://")

                print(f"[Session] 从 DOM 获取到二维码 URL: {qr_src[:80]}...")
                result = await self._generate_qr_base64(qr_src)
                return {
                    "url": qr_src,
                    "base64": result.get("base64", ""),
                    "ascii": self._generate_ascii_qr(qr_src),
                    "text": qr_src,
                }

            print("[Session] 从 DOM 未找到二维码")
            return None

        except Exception as e:
            print(f"[Session] 从 DOM 获取二维码失败：{e}")
            return None

    async def _generate_qr_base64(self, content: str) -> Dict[str, str]:
        """
        生成二维码图片并上传到 R2

        Args:
            content: 二维码内容（URL）

        Returns:
            {'public_url': 'https://...'}
        """
        try:
            import qrcode
            from PIL import Image
            import asyncio

            qr = qrcode.QRCode(version=1, box_size=10, border=4)
            qr.add_data(content)
            qr.make(fit=True)

            img = qr.make_image(fill_color="black", back_color="white")

            buffer = io.BytesIO()
            img.save(buffer, format="PNG")
            img_bytes = buffer.getvalue()

            print(f"[Session] 二维码图片已生成，大小：{len(img_bytes)} bytes")

            public_url = ""
            try:
                from src.utils import upload_qr_code

                loop = asyncio.get_event_loop()
                token = (
                    content.split("lgToken=")[1].split("&")[0]
                    if "lgToken=" in content
                    else ""
                )
                public_url = await loop.run_in_executor(
                    None, upload_qr_code, img_bytes, token
                )
            except Exception as e:
                print(f"[Session] R2 上传失败: {e}")

            return {
                "public_url": public_url or "",
            }

        except ImportError as e:
            print(f"[Session] 生成二维码图片失败：缺少依赖 ({e})")
            return {"public_url": ""}
        except Exception as e:
            print(f"[Session] 生成二维码图片失败：{e}")
            return {"public_url": ""}

    def _generate_ascii_qr(self, content: str) -> str:
        """
        生成 ASCII 二维码

        Args:
            content: 二维码内容（URL）

        Returns:
            ASCII 二维码字符串，失败返回空字符串
        """
        try:
            import qrcode
            import io

            # 生成二维码
            qr = qrcode.QRCode(version=1, box_size=1, border=1)
            qr.add_data(content)
            qr.make(fit=True)

            # 输出到字符串
            output = io.StringIO()
            qr.print_ascii(invert=True, out=output)
            ascii_qr = output.getvalue()

            return ascii_qr

        except ImportError:
            print("[Session] qrcode 库未安装，跳过 ASCII 二维码生成")
            return ""
        except Exception as e:
            print(f"[Session] 生成 ASCII 二维码失败：{e}")
            return ""

    async def _show_qr_code(self):
        """获取并显示登录二维码（兼容旧方法）"""
        try:
            # 使用新的 _get_qr_code 方法
            qr_data = await self._get_qr_code()

            if qr_data:
                print(f"[QR] 二维码 URL: {qr_data['url'][:80]}...")

                # 优先显示 ASCII 二维码
                if qr_data.get("ascii"):
                    _print_qr_header()
                    print(qr_data["ascii"])
                    _print_qr_footer()
                elif qr_data.get("base64"):
                    # 使用 Base64 显示
                    show_qr_in_terminal(qr_data["base64"])
                else:
                    # 降级显示 URL
                    _show_qr_url(qr_data["url"])
            else:
                print("[QR] 未找到二维码元素，请在浏览器窗口扫码")
                try:
                    await self.chrome_manager.page.screenshot(
                        path="/tmp/xianyu-login.png"
                    )
                    print("[QR] 已保存登录页面截图：/tmp/xianyu-login.png")
                except:
                    pass

        except Exception as e:
            print(f"[QR] 获取二维码失败：{e}")
            print("[QR] 请在浏览器窗口扫码登录")

    async def get_token(self) -> Optional[str]:
        """获取 Token (优先从缓存，过期则扫码)"""
        token = self.load_cached_token()
        if token:
            if await self.chrome_manager.ensure_running():
                if await self.check_login_status():
                    return token
                print("[Session] 缓存 Token 无效，需要重新登录")

        print("[Session] 需要扫码登录")
        return await self.login()

    # ==================== 签名方法 ====================

    def _md5(self, text: str) -> str:
        """计算 MD5 哈希"""
        return hashlib.md5(text.encode("utf-8")).hexdigest()

    def _generate_sign(self, data: Dict[str, Any], full_cookie: str) -> Dict[str, str]:
        """
        生成 MTOP 签名

        Args:
            data: 请求数据
            full_cookie: 完整 cookie 值

        Returns:
            包含签名和相关参数的字典
        """
        # 从完整 cookie 中提取时间戳
        if "_" in full_cookie:
            token_part, timestamp = full_cookie.rsplit("_", 1)
        else:
            timestamp = str(int(time.time() * 1000))

        data_str = json.dumps(data)

        # 签名字符串：token&timestamp&appKey&dataStr
        token = token_part if "_" in full_cookie else full_cookie
        sign_str = f"{token}&{timestamp}&{self.APP_KEY}&{data_str}"
        sign = self._md5(sign_str)

        return {"sign": sign, "t": timestamp, "appKey": self.APP_KEY, "data": data_str}


# 便捷函数
async def login(
    chrome_manager: Optional[AsyncChromeManager] = None, timeout: int = 15
) -> Dict[str, Any]:
    """
    便捷函数：扫码登录获取 Token

    Args:
        chrome_manager: 浏览器管理器实例（可选）
        timeout: 等待二维码 API 超时时间（秒），默认 15 秒

    Returns:
        字典，包含：
        - success: bool
        - token: str (登录成功时返回)
        - qr_code: Dict (需要扫码时返回，包含 url/base64/ascii/text)
        - message: str
        - expired: bool (是否已过期)
    """
    async with SessionManager(chrome_manager) as session:
        return await session.login(timeout=timeout)


async def refresh_token(
    chrome_manager: Optional[AsyncChromeManager] = None,
) -> Optional[Dict[str, str]]:
    """便捷函数：刷新 token"""
    async with SessionManager(chrome_manager) as session:
        return await session.refresh_token()


async def check_cookie_valid(
    chrome_manager: Optional[AsyncChromeManager] = None,
) -> bool:
    """便捷函数：检查 cookie 有效性"""
    async with SessionManager(chrome_manager) as session:
        return await session.check_cookie_valid()
