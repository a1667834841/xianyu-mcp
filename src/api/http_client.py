import hashlib
import json
import time
import logging
import asyncio
import os
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import requests

from .types import Conversation, ChatMessage, TextContent, ImageContent

logger = logging.getLogger(__name__)

_env_loaded = False
_captcha_recovery_lock: asyncio.Lock | None = None
_captcha_recovery_task: asyncio.Task | None = None

def _load_env():
    """加载 .env 文件"""
    global _env_loaded
    if _env_loaded:
        return
    
    env_paths = [
        Path(__file__).parent.parent.parent / ".env",
        Path("/opt/dockercompose/xianyu/.env"),
    ]
    
    for env_path in env_paths:
        if env_path.exists():
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        if key and not os.environ.get(key):
                            os.environ[key] = value
            logger.info(f"[HttpClient] 已加载环境变量: {env_path}")
            _env_loaded = True
            break


def get_data_dir() -> Path:
    """获取数据目录，支持环境变量配置"""
    default_dir = Path.home() / ".claude" / "xianyu-tokens"
    data_dir = os.environ.get("XIANYU_DATA_DIR")
    if not data_dir:
        data_root = os.environ.get("XIANYU_DATA_ROOT")
        if data_root:
            user_id = os.environ.get("XIANYU_USER_ID", "default")
            data_dir = str(Path(data_root) / user_id / "tokens")
        else:
            data_dir = str(default_dir)
    return Path(data_dir)


def _parse_full_cookie(full_cookie: str) -> Dict[str, str]:
    cookies: Dict[str, str] = {}
    for part in full_cookie.split(";"):
        token = part.strip()
        if not token or "=" not in token:
            continue
        key, value = token.split("=", 1)
        key = key.strip()
        if not key:
            continue
        cookies[key] = value.strip()
    return cookies


def load_local_auth() -> Dict[str, str]:
    """从本地加载 cookies"""
    data = load_local_auth_data()
    return data.get("cookies", data) if data else {}


def load_local_auth_data() -> Dict[str, Any]:
    """从本地加载完整鉴权数据"""
    data_dir = get_data_dir()
    auth_file = data_dir / "auth.json"
    if auth_file.exists():
        try:
            data = json.loads(auth_file.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            logger.warning(f"本地鉴权文件损坏")

    legacy_file = data_dir / "token.json"
    if legacy_file.exists():
        try:
            data = json.loads(legacy_file.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                if isinstance(data.get("cookies"), dict):
                    return data
                full_cookie = data.get("full_cookie")
                if isinstance(full_cookie, str) and full_cookie.strip():
                    return {
                        "cookies": _parse_full_cookie(full_cookie),
                        "updated_at": data.get("updated_at"),
                        "expires_at": data.get("expires_at"),
                        "device_id": data.get("device_id"),
                    }
        except json.JSONDecodeError:
            logger.warning("本地 legacy token 文件损坏")
    return {}


def save_local_auth(cookies: Dict[str, str]):
    """持久化 cookies 到本地"""
    data_dir = get_data_dir()
    auth_file = data_dir / "auth.json"
    existing = load_local_auth_data()
    
    data_dir.mkdir(parents=True, exist_ok=True)
    
    now = datetime.now()
    expires_at = now + timedelta(hours=24)
    
    data = {
        "cookies": cookies,
        "updated_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
    }
    if existing.get("device_id"):
        data["device_id"] = existing["device_id"]
    
    auth_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"[HttpClient] Cookie 已保存到: {auth_file}")


class HttpClient:
    """闲鱼 HTTP MTOP API 客户端"""
    
    BASE_URL = "https://h5api.m.goofish.com"
    APP_KEY = "34839810"
    
    def __init__(self, cookies: Dict[str, str] = None, device_id: str = ""):
        auth_data = {}
        if cookies is None:
            auth_data = load_local_auth_data()
            cookies = auth_data.get("cookies", auth_data)
        self.cookies = cookies
        fallback_device_id = f"web_{cookies.get('unb', 'new')}" if isinstance(cookies, dict) else "web_new"
        self.device_id = device_id or auth_data.get("device_id") or fallback_device_id
        self.session = requests.Session()
        if cookies:
            self.session.cookies.update(cookies)
        self._token = ""
        self._full_cookie = ""
        self._poll_params = {}
    
    def update_token(self, token: str, full_cookie: str):
        """更新 token 和 cookie（从浏览器获取后）"""
        self._token = token
        self._full_cookie = full_cookie
        if full_cookie:
            self.session.cookies.set("_m_h5_tk", full_cookie.split("_")[0] if "_" in full_cookie else full_cookie)
    
    def _generate_sign(self, token: str, timestamp: str, data_str: str) -> str:
        """生成 MTOP 签名"""
        sign_str = f"{token}&{timestamp}&{self.APP_KEY}&{data_str}"
        return hashlib.md5(sign_str.encode()).hexdigest()
    
    def _extract_token_from_cookie(self, cookie_str: str) -> str:
        """从 Cookie 中提取 Token"""
        if not cookie_str:
            return ""
        for item in cookie_str.split(";"):
            item = item.strip()
            if item.startswith("_m_h5_tk="):
                token_part = item.split("=", 1)[1]
                if "__" in token_part:
                    return token_part.split("__", 1)[0]
                if "_" in token_part:
                    last_underscore = token_part.rfind("_")
                    if last_underscore > 0:
                        return token_part[:last_underscore]
                return token_part
        return ""
    
    async def _send_request(
        self, 
        api: str, 
        data: Dict[str, Any], 
        v: str = "1.0",
        retry_on_captcha: bool = True
    ) -> Dict[str, Any]:
        """发送 MTOP API 请求并自动保存 cookies
        
        Args:
            api: API 名称
            data: 请求数据
            v: 版本号
            retry_on_captcha: 是否在验证码触发时自动处理并重试
        """
        cookie_str = "; ".join([f"{k}={v}" for k, v in self.cookies.items()])
        
        token = self._extract_token_from_cookie(cookie_str)
        timestamp = str(int(time.time() * 1000))
        
        data_str = json.dumps(data, separators=(',', ':'))
        sign = self._generate_sign(token, timestamp, data_str)
        
        params = {
            "jsv": "2.7.2",
            "appKey": self.APP_KEY,
            "t": timestamp,
            "sign": sign,
            "v": v,
            "type": "originaljson",
            "accountSite": "xianyu",
            "dataType": "json",
            "timeout": "20000",
            "api": api,
            "sessionOption": "AutoLoginOnly",
        }
        
        url = f"{self.BASE_URL}/h5/{api.lower()}/{v}/"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept": "application/json",
            "Referer": "https://www.goofish.com/",
            "Origin": "https://www.goofish.com",
            "Cookie": cookie_str,
            "Content-Type": "application/x-www-form-urlencoded",
        }
        
        try:
            # 使用 POST 方法（myfish 使用 POST）
            resp = self.session.post(url, params=params, data={"data": data_str}, headers=headers, timeout=30)
            resp.raise_for_status()
            
            # 每次请求后保存 cookies
            self._save_cookies_from_response(resp)
            
            result = resp.json()
            
            # 检测验证码触发
            if retry_on_captcha and self._need_captcha(result):
                verification_url = result.get('data', {}).get('url', '')
                
                logger.warning(f"[HttpClient] 触发滑块验证: {verification_url[:100]}")
                
                # 处理滑块验证
                if await self._handle_captcha(verification_url):
                    # 重试原请求（不再次触发验证码处理）
                    logger.info("[HttpClient] 验证成功，重试请求")
                    return await self._send_request(api, data, v, retry_on_captcha=False)
                else:
                    logger.error("[HttpClient] 验证失败，返回原错误")
            
            # 检测需要重新登录
            elif retry_on_captcha and self._need_relogin(result):
                logger.warning("[HttpClient] 需要重新登录（风控触发）")
                # 不自动处理，返回错误让用户手动登录
            
            return result
            
        except Exception as e:
            logger.error(f"MTOP API 请求失败：{e}")
            raise
    
    def _need_captcha(self, resp: Dict[str, Any]) -> bool:
        """检测是否需要滑块验证
        
        注意：RGV587_ERROR 可能是登录过期，不是验证码
        
        Args:
            resp: API 响应
            
        Returns:
            bool: 是否需要验证码
        """
        keywords = [
            'FAIL_SYS_USER_VALIDATE',
        ]
        
        # 检查是否有验证码 URL（punish 参数）
        url = resp.get('data', {}).get('url', '')
        if 'punish' in url and 'captcha' in url:
            return True
        
        # 检查 ret 数组
        ret = resp.get('ret', [])
        ret_str = str(ret)
        
        for keyword in keywords:
            if keyword in ret_str:
                return True
        
        return False
    
    def _need_relogin(self, resp: Dict[str, Any]) -> bool:
        """检测是否需要重新登录
        
        Args:
            resp: API 响应
            
        Returns:
            bool: 是否需要重新登录
        """
        ret = resp.get('ret', [])
        ret_str = str(ret)
        
        # RGV587_ERROR 且包含登录页面 URL
        if 'RGV587_ERROR' in ret_str:
            url = resp.get('data', {}).get('url', '')
            if 'mini_login.htm' in url:
                return True
        
        return False
    
    async def _handle_captcha(self, verification_url: str) -> bool:
        """处理滑块验证
        
        Args:
            verification_url: 验证码 URL
            
        Returns:
            bool: 验证是否成功
        """
        if not verification_url:
            logger.error("[HttpClient] 验证 URL 为空")
            return False

        global _captcha_recovery_lock
        global _captcha_recovery_task
        if _captcha_recovery_lock is None:
            _captcha_recovery_lock = asyncio.Lock()
        
        try:
            async with _captcha_recovery_lock:
                if _captcha_recovery_task and not _captcha_recovery_task.done():
                    task = _captcha_recovery_task
                else:
                    from .captcha_handler import CaptchaHandler

                    handler = CaptchaHandler(self)
                    _captcha_recovery_task = asyncio.create_task(
                        handler.handle(verification_url, max_retries=3)
                    )
                    task = _captcha_recovery_task

            try:
                return await task
            finally:
                async with _captcha_recovery_lock:
                    if _captcha_recovery_task is task and task.done():
                        _captcha_recovery_task = None
            
        except ImportError as e:
            logger.error(f"[HttpClient] 无法导入 CaptchaHandler: {e}")
            return False
        except Exception as e:
            logger.error(f"[HttpClient] 处理验证码失败: {e}")
            return False
    
    def _save_cookies_to_file(self):
        """保存 cookies 到 auth.json"""
        try:
            save_local_auth(self.cookies)
            logger.debug("[HttpClient] cookies 已保存到文件")
        except Exception as e:
            logger.warning(f"[HttpClient] 保存 cookies 失败: {e}")
    
    def _save_cookies_from_response(self, resp):
        """从响应中保存所有 cookies"""
        cookie_updated = False
        
        # 从 resp.cookies 保存
        for cookie in resp.cookies:
            if self.cookies.get(cookie.name) != cookie.value:
                self.session.cookies.set(cookie.name, cookie.value)
                self.cookies[cookie.name] = cookie.value
                cookie_updated = True
        
        # 从 Set-Cookie header 保存
        try:
            for header in resp.raw.headers.getlist("Set-Cookie"):
                try:
                    pure_cookie = header.split(";")[0].strip()
                    if "=" in pure_cookie:
                        k, v = pure_cookie.split("=", 1)
                        k = k.strip()
                        v = v.strip()
                        if self.cookies.get(k) != v:
                            self.session.cookies.set(k, v)
                            self.cookies[k] = v
                            cookie_updated = True
                except Exception:
                    continue
        except Exception:
            pass
        
        if cookie_updated:
            save_local_auth(self.cookies)
    
    async def search(self, keyword: str, rows: int = 30, **kwargs) -> List[Dict]:
        """搜索商品"""
        api = "mtop.taobao.idlemtopsearch.pc.search/1.0"
        
        data = {
            "keyword": keyword,
            "pageNumber": 1,
            "rowsPerPage": rows,
            "searchReqFromPage": "pcSearch",
        }
        
        if kwargs.get("min_price"):
            data["propValueStr"] = {"price": f"{kwargs['min_price']}-{kwargs.get('max_price', '')}"}
        
        if kwargs.get("sort_field"):
            data["sortField"] = kwargs["sort_field"]
            data["sortValue"] = kwargs.get("sort_order", "DESC")
        
        resp = await self._send_request(api, data)
        
        if resp.get("ret") and "FAIL_SYS_SESSION_EXPIRED" in resp["ret"][0]:
            raise Exception("SESSION_EXPIRED: Session 过期")
        
        result_list = resp.get("data", {}).get("resultList", [])
        items = []
        
        for item_data in result_list:
            try:
                ex_content = item_data["data"]["item"]["main"]["exContent"]
                click_param = item_data["data"]["item"]["main"].get("clickParam", {}).get("args", {})
                
                item_id = ex_content.get("itemId") or click_param.get("item_id")
                if not item_id:
                    continue
                
                price = click_param.get("price") or click_param.get("displayPrice")
                if not price and ex_content.get("price"):
                    price = ex_content["price"][0].get("text", "")
                
                items.append({
                    "item_id": item_id,
                    "title": ex_content.get("title", ""),
                    "price": price or "",
                    "detail_url": f"https://www.goofish.com/item?id={item_id}",
                })
            except (KeyError, IndexError):
                continue
        
        return items
    
    async def suggest_keywords(self, input_words: str) -> List[str]:
        """获取搜索关键词建议"""
        api = "mtop.taobao.idlemtopsearch.pc.search.suggest/1.0"
        
        data = {
            "inputWords": input_words,
            "searchReqFromPage": "xyPcHome",
            "bucketId": 30,
            "type": 0,
        }
        
        resp = await self._send_request(api, data)
        
        keywords = []
        seen = set()
        
        def visit(value):
            if isinstance(value, dict):
                for key in ("suggest", "keyword", "showText", "text", "word", "value"):
                    candidate = value.get(key)
                    if isinstance(candidate, str):
                        normalized = candidate.strip()
                        if normalized and normalized not in seen:
                            seen.add(normalized)
                            keywords.append(normalized)
                for nested in value.values():
                    visit(nested)
            elif isinstance(value, list):
                for item in value:
                    visit(item)
        
        visit(resp.get("data", {}))
        return keywords
    
    async def get_item_detail(self, item_id: str) -> Dict[str, Any]:
        """获取商品详情"""
        api = "mtop.taobao.idle.pc.detail/1.0"
        data = {"itemId": str(item_id)}
        
        resp = await self._send_request(api, data)
        return resp.get("data", {})
    
    async def create_conversation(self, seller_id: str, item_id: str = "") -> str:
        """创建对话"""
        api = "mtop.idle.trade.conversation.create/1.0"
        data = {
            "sellerId": seller_id,
            "itemId": item_id or "891198795482",
        }
        
        resp = await self._send_request(api, data)
        return resp.get("data", {}).get("conversationId", "")

    async def list_conversations(self, limit: int = 20, offset: int = 0) -> List[Conversation]:
        """获取对话列表"""
        api = "mtop.taobao.idle.message.conversation.list/1.0"
        data = {
            "limit": limit,
            "offset": offset,
        }
        
        resp = await self._send_request(api, data)
        conv_list = resp.get("data", {}).get("conversationList", [])
        
        conversations = []
        for conv_data in conv_list:
            try:
                conv = Conversation(
                    conversation_id=conv_data["conversationId"],
                    user_id=conv_data["userId"],
                    user_nick=conv_data["userNick"],
                    last_message=conv_data.get("lastMessage"),
                    last_message_time=conv_data.get("lastMessageTime", 0) / 1000.0,
                    unread_count=conv_data.get("unreadCount", 0),
                )
                conversations.append(conv)
            except (KeyError, TypeError):
                continue
        
        return conversations

    async def get_message_history(
        self, 
        conversation_id: str, 
        limit: int = 50,
        before_timestamp: Optional[int] = None
    ) -> Dict[str, Any]:
        """获取消息历史"""
        api = "mtop.taobao.idle.message.record.get/1.0"
        data = {
            "conversationId": conversation_id,
            "limit": limit,
        }
        
        if before_timestamp:
            data["beforeTimestamp"] = before_timestamp
        
        resp = await self._send_request(api, data)
        msg_list = resp.get("data", {}).get("messageList", [])
        
        messages = []
        for msg_data in msg_list:
            try:
                content_type = msg_data["content"].get("type", "text")
                if content_type == "text":
                    content = TextContent(type="text", text=msg_data["content"].get("text", ""))
                elif content_type == "image":
                    content = ImageContent(
                        type="image",
                        image_url=msg_data["content"].get("imageUrl", ""),
                    )
                else:
                    content = TextContent(type="text", text=str(msg_data["content"]))
                
                msg = ChatMessage(
                    message_id=msg_data["messageId"],
                    conversation_id=conversation_id,
                    sender_id=msg_data["senderId"],
                    receiver_id=msg_data["receiverId"],
                    content=content,
                    timestamp=msg_data.get("timestamp", 0) / 1000.0,
                )
                messages.append(msg)
            except (KeyError, TypeError):
                continue
        
        return {
            "messages": messages,
            "has_more": resp.get("data", {}).get("hasMore", False),
        }
    
    async def refresh_token(self) -> Dict[str, Any]:
        """刷新 Token - 通过调用 API 刷新 _m_h5_tk"""
        try:
            await self._get_m_h5_tk()
            if "_m_h5_tk" in self.cookies:
                return {"success": True, "message": "Token 已刷新"}
            return {"success": False, "message": "刷新失败"}
        except Exception as e:
            return {"success": False, "message": str(e)}
    
    async def get_access_token(self) -> str:
        """获取 WebSocket accessToken"""
        api = "mtop.taobao.idlemessage.pc.login.token"
        data = {
            "appKey": "444e9908a51d1cb236a27862abc769c9",
            "deviceId": self.device_id or "default_device",
        }

        resp = await self._send_request(api, data)
        token = resp.get("data", {}).get("accessToken", "")
        if token:
            self._token = token
            return token

        return ""
    
    def _get_login_params(self) -> Dict[str, str]:
        """获取登录参数 - 访问 mini_login.htm 获取初始 cookie 和参数"""
        import re
        
        url = "https://passport.goofish.com/mini_login.htm"
        self._poll_params = {
            "lang": "zh_cn",
            "appName": "xianyu",
            "appEntrance": "web",
            "styleType": "vertical",
            "bizDomain": "xianyu",
            "notLoadSsoView": "false",
            "notKeepLogin": "false",
            "isMobile": "false",
            "qrCodeFirst": "false",
        }
        params = self._poll_params.copy()
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
        
        resp = self.session.get(url, params=params, headers=headers, timeout=30)
        
        # 保存初始 cookies
        self._save_cookies_from_response(resp)
        
        view_data_match = re.search(r'window\.viewData\s*=\s*(\{[^;]+\});', resp.text)
        if not view_data_match:
            return {}
        
        view_data_str = view_data_match.group(1)
        view_data_str = view_data_str.replace("'", '"')
        try:
            view_data = json.loads(view_data_str)
        except json.JSONDecodeError:
            return {}
        
        return {
            "appName": view_data.get("appName", "xianyu"),
            "appEntrance": view_data.get("appEntrance", "web"),
            "_csrf_token": view_data.get("_csrf_token", ""),
            "styleType": view_data.get("styleType", "xianyu_web"),
            "bizDomain": view_data.get("bizDomain", "xianyu"),
        }
    
    async def login(self, timeout: int = 300) -> Dict[str, Any]:
        """登录 - 纯 HTTP 获取二维码 URL 并上传到 R2"""
        _load_env()
        try:
            login_params = self._get_login_params()
            if not login_params:
                return {"success": False, "message": "获取登录参数失败"}
            
            url = "https://passport.goofish.com/newlogin/qrcode/generate.do"
            params = {
                "appName": login_params.get("appName", "xianyu"),
                "appEntrance": login_params.get("appEntrance", "web"),
                "styleType": login_params.get("styleType", "xianyu_web"),
                "bizDomain": login_params.get("bizDomain", "xianyu"),
                "_csrf_token": login_params.get("_csrf_token", ""),
            }
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "application/json",
                "Referer": "https://passport.goofish.com/mini_login.htm",
            }
            
            resp = self.session.get(url, params=params, headers=headers, timeout=30)
            result = resp.json()
            
            content_data = result.get("content", {}).get("data", {})
            
            if not content_data.get("codeContent"):
                return {"success": False, "message": "生成二维码失败"}
            
            self._login_t = content_data.get("t", "")
            self._login_ck = content_data.get("ck", "")
            
            qr_url = content_data.get("codeContent", "")
            
            public_url = ""
            try:
                import qrcode
                import io
                
                qr = qrcode.QRCode(version=1, box_size=10, border=4)
                qr.add_data(qr_url)
                qr.make(fit=True)
                
                img = qr.make_image(fill_color="black", back_color="white")
                
                buffer = io.BytesIO()
                img.save(buffer, format="PNG")
                img_bytes = buffer.getvalue()
                
                if img_bytes:
                    from src.utils import upload_qr_code
                    
                    token = str(self._login_t)[:16] if self._login_t else ""
                    public_url = upload_qr_code(img_bytes, token)
                    if public_url:
                        logger.info(f"[Login] 二维码已上传到 R2: {public_url}")
            except ImportError as e:
                logger.warning(f"[Login] 缺少 qrcode 库: {e}")
            except Exception as e:
                logger.warning(f"[Login] 生成或上传二维码失败: {e}")
            
            return {
                "success": True,
                "logged_in": False,
                "qr_code": {
                    "public_url": public_url or "",
                    "url": qr_url,
                },
                "t": self._login_t,
                "ck": self._login_ck,
                "message": "请扫码登录",
            }
            
        except Exception as e:
            logger.error(f"登录失败: {e}")
            return {"success": False, "message": str(e)}
    
    async def _get_m_h5_tk(self) -> bool:
        """获取 _m_h5_tk token（MTOP 签名必需）"""
        try:
            # 调用首页 API 获取 _m_h5_tk
            url = "https://h5api.m.goofish.com/h5/mtop.gaia.nodejs.gaia.idle.data.gw.v2.index.get/1.0/"
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Accept": "application/json",
                "Referer": "https://www.goofish.com/",
                "Origin": "https://www.goofish.com",
            }
            
            cookie_str = "; ".join([f"{k}={v}" for k, v in self.cookies.items()])
            headers["Cookie"] = cookie_str
            
            timestamp = str(int(time.time() * 1000))
            params = {
                "jsv": "2.7.2",
                "appKey": "34839810",
                "t": timestamp,
                "sign": "",
                "v": "1.0",
                "type": "originaljson",
                "dataType": "json",
                "api": "mtop.gaia.nodejs.gaia.idle.data.gw.v2.index.get",
            }
            
            resp = self.session.get(url, params=params, headers=headers, timeout=30)
            self._save_cookies_from_response(resp)
            
            # 检查是否获取到 _m_h5_tk
            if "_m_h5_tk" in self.cookies:
                logger.info(f"[HttpClient] 已获取 _m_h5_tk: {self.cookies['_m_h5_tk'][:20]}...")
                return True
            
            logger.warning("[HttpClient] 未获取到 _m_h5_tk")
            return False
        except Exception as e:
            logger.warning(f"[HttpClient] 获取 _m_h5_tk 失败: {e}")
            return False
    
    async def login_poll(self, t: str, ck: str) -> Dict[str, Any]:
        """轮询扫码状态"""
        try:
            url = "https://passport.goofish.com/newlogin/qrcode/query.do"
            
            self._poll_params["t"] = t
            self._poll_params["ck"] = ck
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Accept": "application/json",
                "Referer": "https://passport.goofish.com/mini_login.htm",
            }
            
            resp = self.session.post(url, data=self._poll_params, headers=headers, timeout=30)
            result = resp.json()
            
            content_data = result.get("content", {}).get("data", {})
            
            if content_data.get("iframeRedirect"):
                return {
                    "success": False,
                    "logged_in": False,
                    "status": "ERROR",
                    "redirect_url": content_data["iframeRedirect"],
                    "message": "需要处理跳转",
                }
            
            status = content_data.get("qrCodeStatus", content_data.get("status", ""))
            
            if status == "CONFIRMED":
                self._save_cookies(resp)
                # 登录成功后获取 _m_h5_tk
                await self._get_m_h5_tk()
                return {
                    "success": True,
                    "logged_in": True,
                    "status": "CONFIRMED",
                    "message": "登录成功",
                }
            elif status == "SCANED":
                return {
                    "success": True,
                    "logged_in": False,
                    "status": "SCANED",
                    "message": "已扫码，请确认",
                }
            elif status == "EXPIRED":
                return {
                    "success": False,
                    "logged_in": False,
                    "status": "EXPIRED",
                    "message": "二维码已过期",
                }
            else:
                return {
                    "success": True,
                    "logged_in": False,
                    "status": status or "WAITING",
                    "message": "等待扫码",
                }
            
        except Exception as e:
            logger.error(f"轮询失败: {e}")
            return {"success": False, "message": str(e)}
    
    def _save_cookies(self, resp):
        """从响应中保存 cookies 并持久化（登录专用）"""
        self._save_cookies_from_response(resp)
    
    async def check_session(self) -> Dict[str, Any]:
        """检查会话是否有效"""
        try:
            saved_cookies = load_local_auth()
            if saved_cookies:
                self.cookies = saved_cookies
                self.session.cookies.clear()
                self.session.cookies.update(saved_cookies)
            
            if not self.cookies:
                return {"valid": False, "message": "无 Cookie"}
            
            api = "mtop.idle.web.user.page.nav/1.0"
            data = {"self": True}
            
            try:
                result = await self._send_request(api, data)
                user_data = result.get("data", {})
                if user_data:
                    return {"valid": True, "message": "Cookie 有效"}
                return {"valid": False, "message": "Cookie 无效"}
            except Exception as e:
                if "SESSION_EXPIRED" in str(e) or "TOKEN_EMPTY" in str(e):
                    return {"valid": False, "message": "Cookie 已过期"}
                return {"valid": False, "message": str(e)}
        except Exception as e:
            return {"valid": False, "message": str(e)}
    
    async def upload_media(self, image_path: str) -> Dict[str, Any]:
        """上传图片到闲鱼"""
        upload_url = "https://stream-upload.goofish.com/api/upload.api"
        params = {
            "floderId": "0",
            "appkey": "xy_chat",
            "_input_charset": "utf-8",
        }
        
        import os
        import tempfile
        
        temp_file = None
        if image_path.startswith(("http://", "https://")):
            try:
                import urllib.request
                req = urllib.request.Request(image_path, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=30) as response:
                    content = response.read()
                suffix = os.path.splitext(image_path.split("?")[0])[1] or ".jpg"
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
                temp_file.write(content)
                temp_file.close()
                image_path = temp_file.name
            except Exception as e:
                raise RuntimeError(f"下载图片失败: {e}")

        try:
            filename = os.path.basename(image_path)
            with open(image_path, "rb") as f:
                files = {"file": (filename, f, "image/png")}
                resp = self.session.post(upload_url, params=params, files=files, timeout=30)
                resp.raise_for_status()
                return resp.json()
        finally:
            if temp_file:
                os.unlink(temp_file.name)
    
    async def get_public_channel(self, title: str, images_info: List[Dict]) -> Dict[str, Any]:
        """获取商品分类推荐"""
        api = "mtop.taobao.idle.kgraph.property.recommend/2.0"
        
        image_infos = []
        for info in images_info:
            image_infos.append({
                "extraInfo": {"isH": "false", "isT": "false", "raw": "false"},
                "isQrCode": False,
                "url": info["url"],
                "heightSize": info["height"],
                "widthSize": info["width"],
                "major": True,
                "type": 0,
                "status": "done",
            })
        
        data = {
            "title": title,
            "lockCpv": False,
            "multiSKU": False,
            "publishScene": "mainPublish",
            "scene": "newPublishChoice",
            "description": title,
            "imageInfos": image_infos,
            "uniqueCode": str(int(time.time() * 1000000)),
        }
        
        return await self._send_request(api, data)
    
    async def get_default_location(self, longitude: float = 118.78, latitude: float = 31.92) -> Dict[str, Any]:
        """获取默认发货地址"""
        api = "mtop.taobao.idle.local.poi.get/1.0"
        data = {"longitude": longitude, "latitude": latitude}
        return await self._send_request(api, data)
    
    async def publish(
        self,
        images_paths: List[str],
        title: str,
        price: Optional[Dict[str, float]] = None,
        shipping: str = "包邮",
        self_pickup: bool = False,
        post_price: float = 0,
    ) -> Dict[str, Any]:
        """发布商品
        
        Args:
            images_paths: 图片路径列表
            title: 商品标题/描述
            price: 价格 {"current_price": 100, "original_price": 200}
            shipping: 物流选项（包邮/按距离计费/一口价/无需邮寄）
            self_pickup: 是否支持自提
            post_price: 一口价物流费用
        """
        try:
            # 1. 上传图片
            images_info = []
            for image_path in images_paths:
                res = await self.upload_media(image_path)
                image_obj = res.get("object", {})
                if "pix" not in image_obj:
                    return {"success": False, "message": f"图片上传失败: {res}"}
                
                width, height = map(int, image_obj["pix"].split("x"))
                images_info.append({
                    "url": image_obj["url"],
                    "height": height,
                    "width": width,
                })
            
            # 2. 获取分类推荐
            channel_res = await self.get_public_channel(title, images_info)
            cat_predict = channel_res.get("data", {}).get("categoryPredictResult", {})
            
            # 3. 获取默认地址
            location_res = await self.get_default_location()
            common_addrs = location_res.get("data", {}).get("commonAddresses", [])
            
            # 4. 构建发布数据
            image_info_list = []
            for info in images_info:
                image_info_list.append({
                    "extraInfo": {"isH": "false", "isT": "false", "raw": "false"},
                    "isQrCode": False,
                    "url": info["url"],
                    "heightSize": info["height"],
                    "widthSize": info["width"],
                    "major": True,
                    "type": 0,
                    "status": "done",
                })
            
            data = {
                "freebies": False,
                "itemTypeStr": "b",
                "quantity": "1",
                "simpleItem": "true",
                "imageInfoDOList": image_info_list,
                "itemTextDTO": {
                    "desc": title,
                    "title": title,
                    "titleDescSeparate": False,
                },
                "itemLabelExtList": [],
                "itemPriceDTO": {},
                "userRightsProtocols": [{"enable": False, "serviceCode": "SKILL_PLAY_NO_MIND"}],
                "itemPostFeeDTO": {
                    "canFreeShipping": False,
                    "supportFreight": False,
                    "onlyTakeSelf": False,
                },
                "itemAddrDTO": {},
                "defaultPrice": False,
                "itemCatDTO": {
                    "catId": str(cat_predict.get("catId", "")),
                    "catName": str(cat_predict.get("catName", "")),
                    "channelCatId": str(cat_predict.get("channelCatId", "")),
                    "tbCatId": str(cat_predict.get("tbCatId", "")),
                },
                "uniqueCode": str(int(time.time() * 1000000)),
                "sourceId": "pcMainPublish",
                "bizcode": "pcMainPublish",
                "publishScene": "pcMainPublish",
            }
            
            # 处理物流设置
            if shipping == "包邮":
                data["itemPostFeeDTO"].update({"canFreeShipping": True, "supportFreight": True})
            elif shipping == "按距离计费":
                data["itemPostFeeDTO"].update({"supportFreight": True, "templateId": "-100"})
            elif shipping == "一口价":
                data["itemPostFeeDTO"].update({
                    "supportFreight": True,
                    "templateId": "0",
                    "postPriceInCent": str(int(post_price * 100)),
                })
            elif shipping == "无需邮寄":
                data["itemPostFeeDTO"]["templateId"] = "0"
            
            if self_pickup:
                data["itemPostFeeDTO"]["onlyTakeSelf"] = True
            
            # 处理价格
            if price:
                if price.get("current_price", 0) > 0:
                    data["itemPriceDTO"]["priceInCent"] = str(int(price["current_price"] * 100))
                if price.get("original_price", 0) > 0:
                    data["itemPriceDTO"]["origPriceInCent"] = str(int(price["original_price"] * 100))
            else:
                data["defaultPrice"] = True
            
            # 处理地址
            if common_addrs:
                loc = common_addrs[0]
                data["itemAddrDTO"] = {
                    "area": loc.get("area"),
                    "city": loc.get("city"),
                    "divisionId": loc.get("divisionId"),
                    "gps": f"{loc.get('longitude')},{loc.get('latitude')}",
                    "poiId": loc.get("poiId"),
                    "poiName": loc.get("poi"),
                    "prov": loc.get("prov"),
                }
            
            # 5. 发布商品
            api = "mtop.idle.pc.idleitem.publish/1.0"
            result = await self._send_request(api, data)
            
            if result.get("ret") and "SUCCESS" in result["ret"][0]:
                item_id = result.get("data", {}).get("itemId", "")
                return {
                    "success": True,
                    "item_id": item_id,
                    "item_url": f"https://www.goofish.com/item?id={item_id}",
                    "message": "发布成功",
                }
            
            return {"success": False, "message": result.get("ret", ["未知错误"])}
            
        except Exception as e:
            logger.error(f"发布失败: {e}")
            return {"success": False, "message": str(e)}
    
    def close(self):
        """关闭会话"""
        self.session.close()
