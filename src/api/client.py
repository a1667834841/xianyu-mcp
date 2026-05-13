import asyncio
import logging
import time
from datetime import datetime
from typing import Dict, Any, Optional, List

from .http_client import HttpClient
from .websocket_client import WebSocketClient
from .websocket_pool import WebSocketPool
from .hook_notifier import HookNotifier
from .types import Conversation
from src.settings import load_settings_for_user
from src.sourcing_service import SourcingService

logger = logging.getLogger(__name__)


def _format_display_time(value: str | None) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return value
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return value
    return parsed.strftime("%Y-%m-%d %H:%M:%S")


class XianyuApiClient:
    """闲鱼统一 API 客户端"""

    def __init__(self, user_id: str, data_root=None, config_path=None):
        self.user_id = user_id
        self.data_root = data_root
        self.config_path = config_path
        self.settings = load_settings_for_user(
            user_id,
            data_root=data_root,
            config_path=config_path,
        )
        self._token_dir = self.settings.storage.token_file.parent
        self.http_client = HttpClient(cookies=None, device_id="", data_dir=self._token_dir)
        hook_notifier = HookNotifier(self.settings.hook)
        self.ws_client = WebSocketClient(
            self.http_client,
            user_id=self.user_id,
            hook_notifier=hook_notifier,
        )
        self.websocket_pool = WebSocketPool()
        
        self.ws_status = "disconnected"
        self.ws_last_error = None
        self.ws_started_at = None
        self._ws_start_task = None
    
    async def initialize(self, cookies: Dict[str, str], device_id: str):
        """初始化客户端"""
        if self._ws_start_task and not self._ws_start_task.done():
            self._ws_start_task.cancel()
            try:
                await self._ws_start_task
            except asyncio.CancelledError:
                pass

        if self.ws_client and self.ws_client.is_connected:
            await self.ws_client.stop()

        self.settings = load_settings_for_user(
            self.user_id,
            data_root=self.data_root,
            config_path=self.config_path,
        )
        self._token_dir = self.settings.storage.token_file.parent
        self.http_client = HttpClient(cookies=cookies, device_id=device_id, data_dir=self._token_dir)
        hook_notifier = HookNotifier(self.settings.hook)
        self.ws_client = WebSocketClient(
            self.http_client,
            user_id=self.user_id,
            hook_notifier=hook_notifier,
        )
        
        self.ws_status = "disconnected"
        self.ws_last_error = None
        self.ws_started_at = None
        self._ws_start_task = None
    
    async def login(self, timeout: int = 300) -> Dict[str, Any]:
        """登录 - 纯 HTTP 获取二维码（不依赖浏览器）"""
        if not self.http_client:
            return {"success": False, "message": "客户端未初始化"}
        session = await self.http_client.check_session()
        if session.get("valid"):
            return {
                "success": True,
                "logged_in": True,
                "message": session.get("message", "Cookie 有效"),
            }
        return await self.http_client.login(timeout=timeout)

    async def show_qrcode(self) -> Dict[str, Any]:
        """直接生成登录二维码，不检查已有登录态。"""
        if not self.http_client:
            return {"success": False, "message": "客户端未初始化"}
        return await self.http_client.login()
    
    async def login_poll(self, t: str, ck: str) -> Dict[str, Any]:
        """轮询扫码状态"""
        if not self.http_client:
            return {"success": False, "message": "客户端未初始化"}
        return await self.http_client.login_poll(t=t, ck=ck)
    
    async def check_session(self) -> Dict[str, Any]:
        """检查会话"""
        if not self.http_client:
            return {"valid": False}
        return await self.http_client.check_session()
    
    async def refresh_token(self) -> Dict[str, Any]:
        """刷新 Token，仅使用 HTTP 路径"""
        if not self.http_client:
            return {"success": False}

        try:
            result = await self.http_client.refresh_token()
        except Exception as e:
            return {"success": False, "method": "http", "message": str(e)}

        result["method"] = "http"
        return result
    
    async def search(self, keyword: str, rows: int = 30, **kwargs) -> List[Dict]:
        """搜索商品"""
        if not self.http_client:
            return []
        return await self.http_client.search(keyword=keyword, rows=rows, **kwargs)
    
    async def get_detail(self, item_url: str) -> Dict[str, Any]:
        """获取商品详情"""
        if not self.http_client:
            return {}
        
        item_id = self._extract_item_id(item_url)
        if not item_id:
            return {}
        
        return await self.http_client.get_item_detail(item_id=item_id)
    
    async def publish(
        self,
        images_paths: List[str] = None,
        title: str = "",
        description: str = "",
        price: Dict[str, float] = None,
        shipping: str = "包邮",
        self_pickup: bool = False,
        post_price: float = 0,
        **kwargs,
    ) -> Dict[str, Any]:
        """发布商品，仅使用 HTTP API"""
        if not self.http_client:
            return {"success": False, "message": "客户端未初始化"}

        if not images_paths:
            return {"success": False, "message": "需要提供图片路径"}

        if not title:
            return {"success": False, "message": "需要提供商品标题"}

        try:
            result = await self.http_client.publish(
                images_paths=images_paths,
                title=title,
                description=description,
                price=price,
                shipping=shipping,
                self_pickup=self_pickup,
                post_price=post_price,
            )
        except Exception as e:
            return {"success": False, "method": "http", "message": str(e)}

        result["method"] = "http"
        return result

    async def publish_from_item_url(self, item_url: str) -> Dict[str, Any]:
        """输入商品链接后自动解析并发布。"""
        service = SourcingService(publish_client=self)
        return await service.publish_from_item_url(item_url)

    async def create_conversation(self, item_url: str, seller_id: str = "") -> Dict[str, Any]:
        """创建对话"""
        if not self.http_client:
            return {
                "success": False,
                "error_code": "CLIENT_NOT_INITIALIZED",
                "item_id": "",
                "message": "客户端未初始化",
            }

        item_id = self._extract_item_id(item_url)
        if not item_id:
            return {
                "success": False,
                "error_code": "INVALID_ITEM_URL",
                "item_id": "",
                "message": "无效的商品链接",
            }

        resolved_seller_id = seller_id
        if not resolved_seller_id:
            detail = await self.http_client.get_item_detail(item_id=item_id)
            seller = detail.get("sellerDO", {}) if isinstance(detail, dict) else {}
            raw_seller_id = seller.get("sellerId")
            if raw_seller_id is not None:
                resolved_seller_id = str(raw_seller_id)

        if not resolved_seller_id:
            return {
                "success": False,
                "error_code": "SELLER_ID_UNAVAILABLE",
                "item_id": item_id,
                "message": "无法获取卖家 ID",
            }

        current_user_id = self.http_client.cookies.get("unb")
        if current_user_id and str(resolved_seller_id) == current_user_id:
            return {
                "success": False,
                "error_code": "CANNOT_CREATE_CONVERSATION_WITH_SELF",
                "item_id": item_id,
                "message": "无法与自己创建对话，商品为当前账号发布",
            }

        await self.ensure_ws_started(reason="create_conversation")
        if not self.ws_is_connected():
            return {
                "success": False,
                "error_code": "CONVERSATION_CREATE_FAILED",
                "item_id": item_id,
                "message": "创建对话失败",
            }

        result = await self.ws_client.create_conversation(
            seller_id=resolved_seller_id,
            item_id=item_id,
        )
        if not result.get("success"):
            return {
                "success": False,
                "error_code": "CONVERSATION_CREATE_FAILED",
                "item_id": item_id,
                "message": "创建对话失败",
            }

        conversation_id = result.get("conversation_id", "")
        greeting = self.settings.messaging.create_conversation_greeting
        send_result = await self.ws_send_message(
            target_id=resolved_seller_id,
            content=greeting,
            image_url="",
            conversation_id=conversation_id,
        )
        if not send_result.get("success"):
            return {
                "success": False,
                "error_code": "GREETING_SEND_FAILED",
                "conversation_id": conversation_id,
                "item_id": item_id,
                "message": f"默认问候语发送失败: {send_result.get('message', '未知错误')}",
            }

        return {
            "success": True,
            "conversation_id": conversation_id,
            "item_id": item_id,
            "message": "对话已创建并已发送问候语",
        }
    
    async def list_conversations(self, limit: int = 20, offset: int = 0) -> List[Conversation]:
        """获取对话列表（通过 WebSocket LWP）"""
        if not self.ws_client or not self.ws_client.is_connected:
            # WebSocket 未连接，返回缓存
            cached = self.ws_client.cache.get_conversations(limit=limit)
            return cached
        
        result = await self.ws_client.get_conversation_list(page_size=limit)
        if result.get("success"):
            conversations = result.get("conversations", [])
            return [Conversation(
                conversation_id=c["cid"],
                user_id=c["cid"],
                user_nick=c.get("peer_user_name", ""),
                last_message=c.get("last_message", ""),
                last_message_time=c.get("last_message_time", 0) / 1000 if c.get("last_message_time") else 0,
                unread_count=c.get("unread_count", 0),
            ) for c in conversations]
        
        # 失败时返回缓存
        return self.ws_client.cache.get_conversations(limit=limit)
    
    async def get_messages(
        self, 
        conversation_id: str, 
        limit: int = 50,
        before_timestamp: Optional[int] = None
    ) -> Dict[str, Any]:
        """获取消息历史（通过 WebSocket LWP）"""
        if not self.ws_client or not self.ws_client.is_connected:
            # WebSocket 未连接，返回缓存
            cached = self.ws_client.cache.get_messages(conversation_id, limit=limit)
            return {"messages": cached, "has_more": False, "source": "cache"}
        
        anchor = before_timestamp if before_timestamp else None
        result = await self.ws_client.get_message_history(
            chat_id=conversation_id,
            anchor=anchor,
            count=limit
        )
        
        if result.get("success"):
            messages = result.get("messages", [])
            return {
                "messages": messages,
                "has_more": result.get("hasMore", False),
                "next_cursor": result.get("nextCursor"),
                "source": "websocket"
            }
        
        # 失败时返回缓存
        cached = self.ws_client.cache.get_messages(conversation_id, limit=limit)
        return {"messages": cached, "has_more": False, "source": "cache"}
    
    async def send_message(
        self, 
        conversation_id: str, 
        content: str = "",
        image_url: str = ""
    ) -> bool:
        """发送消息"""
        if not self.websocket_pool:
            return False
        
        from .types import TextContent, ImageContent
        
        if image_url:
            message = ImageContent(type="image", image_url=image_url)
        else:
            message = TextContent(type="text", text=content)
        
        return await self.websocket_pool.send_message(
            conversation_id=conversation_id,
            to_user_id="",
            message=message,
        )
    
    @staticmethod
    def _extract_item_id(item_url: str) -> str:
        """从 URL 提取 item_id"""
        if "item?id=" in item_url:
            return item_url.split("item?id=")[-1].split("&")[0]
        if "?id=" in item_url:
            return item_url.split("?id=")[-1].split("&")[0]
        if "&id=" in item_url:
            return item_url.split("&id=")[-1].split("&")[0]
        return ""
    
    def get_ws_status(self) -> Dict[str, Any]:
        """返回 WebSocket 当前状态快照。"""
        connected = bool(self.ws_client and self.ws_client.is_connected)
        internal_error = getattr(self.ws_client, "last_error", None) if self.ws_client else None
        if not connected and internal_error and not getattr(self.ws_client, "_running", False):
            self.ws_status = "failed"
            self.ws_last_error = internal_error
        status = "connected" if connected else self.ws_status
        return {
            "connected": connected,
            "status": status,
            "last_error": self.ws_last_error,
            "started_at": _format_display_time(self.ws_started_at),
        }

    async def ensure_ws_started(self, reason: str) -> Dict[str, Any]:
        """幂等地确保 WebSocket 后台启动。"""
        if self.ws_client and self.ws_client.is_connected:
            self.ws_status = "connected"
            return {"success": True, "status": "connected", "reason": reason}

        if self._ws_start_task and not self._ws_start_task.done():
            self.ws_status = "starting"
            return {"success": True, "status": "starting", "reason": reason}

        self.ws_status = "starting"
        self.ws_last_error = None
        self.ws_started_at = time.strftime("%Y-%m-%d %H:%M:%S")
        self._ws_start_task = asyncio.create_task(self._run_ws_start(reason, self.ws_client))
        return {"success": True, "status": "starting", "reason": reason}

    async def _run_ws_start(self, reason: str, ws_client=None) -> None:
        ws_client = ws_client or self.ws_client
        logger.info(f"Starting WebSocket connection (reason: {reason})")
        try:
            success = await ws_client.connect()
            if ws_client is not self.ws_client:
                logger.info(f"Ignoring stale WebSocket start result (reason: {reason})")
                return
            if not success:
                self.ws_status = "failed"
                self.ws_last_error = "WebSocket connect returned false"
                logger.error(f"WebSocket connection failed (reason: {reason})")
                return

            for _ in range(30):
                if ws_client is not self.ws_client:
                    logger.info(f"Ignoring stale WebSocket start poll (reason: {reason})")
                    return
                if ws_client.is_connected:
                    self.ws_status = "connected"
                    self.ws_last_error = None
                    logger.info(f"WebSocket connected successfully (reason: {reason})")
                    return
                internal_error = getattr(ws_client, "last_error", None)
                if internal_error and not getattr(ws_client, "_running", False):
                    self.ws_status = "failed"
                    self.ws_last_error = internal_error
                    logger.error(f"WebSocket initialization failed (reason: {reason}): {internal_error}")
                    return
                await asyncio.sleep(1)

            self.ws_status = "failed"
            self.ws_last_error = "WebSocket initialization timed out"
            logger.error(f"WebSocket initialization timed out (reason: {reason})")
        except Exception as exc:
            self.ws_status = "failed"
            self.ws_last_error = str(exc)
            logger.error(f"WebSocket start error (reason: {reason}): {exc}")
    
    async def start_ws_listener(self) -> Dict[str, Any]:
        """确保 WebSocket 监听启动。"""
        try:
            return await self.ensure_ws_started(reason="manual")
        except Exception as e:
            self.ws_status = "failed"
            self.ws_last_error = str(e)
            return {"success": False, "status": "failed", "message": str(e)}

    async def stop_ws_listener(self) -> Dict[str, Any]:
        """停止 WebSocket 监听"""
        try:
            await self.ws_client.stop()
            self.ws_status = "disconnected"
            self.ws_last_error = None
            return {"success": True, "message": "监听已停止"}
        except Exception as e:
            self.ws_status = "failed"
            self.ws_last_error = str(e)
            return {"success": False, "message": str(e)}

    async def ws_send_message(self, target_id: str, content: str = "", image_url: str = "", conversation_id: str = "") -> Dict[str, Any]:
        """通过 WebSocket 发送消息"""
        try:
            start_result = await self.ensure_ws_started(reason="send_message")
            if not self.ws_is_connected():
                message = start_result.get("message") or start_result.get("last_error") or start_result.get("status", "unknown")
                return {"success": False, "message": f"WebSocket 未连接: {message}"}
            success = await self.ws_client.send_message(target_id, content, image_url, conversation_id)
            return {"success": success, "message": "消息已发送" if success else "发送失败"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def ws_is_connected(self) -> bool:
        return bool(self.ws_client and self.ws_client.is_connected)

    def ws_on_message(self, handler):
        self.ws_client.on_message(handler)

    async def close(self):
        """关闭客户端"""
        if self.http_client:
            self.http_client.close()
        if self.websocket_pool:
            await self.websocket_pool.stop()
