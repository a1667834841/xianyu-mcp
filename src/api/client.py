import logging
from typing import Dict, Any, Optional, List

from .http_client import HttpClient
from .websocket_client import WebSocketClient
from .websocket_pool import WebSocketPool
from .types import Conversation
from src.browser_bridge import BrowserBridge

logger = logging.getLogger(__name__)


class XianyuApiClient:
    """闲鱼统一 API 客户端（单例）"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self.http_client = HttpClient(cookies=None, device_id="")
        self.ws_client = WebSocketClient(self.http_client)
        self.websocket_pool = WebSocketPool()
        self.browser_bridge = BrowserBridge()
        
        self._initialized = True
    
    def initialize(self, cookies: Dict[str, str], device_id: str):
        """初始化客户端"""
        self.http_client = HttpClient(cookies=cookies, device_id=device_id)
        
        self.browser_bridge = BrowserBridge()
    
    async def login(self, timeout: int = 300) -> Dict[str, Any]:
        """登录 - 纯 HTTP 获取二维码（不依赖浏览器）"""
        if not self.http_client:
            return {"success": False, "message": "客户端未初始化"}
        return await self.http_client.login(timeout=timeout)
    
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
        """刷新 Token，API 优先，失败降级浏览器"""
        if not self.http_client:
            return {"success": False}
        
        try:
            result = await self.http_client.refresh_token()
            if result.get("success"):
                result["method"] = "http"
                return result
        except Exception as e:
            logger.warning(f"API 刷新失败，降级到浏览器: {e}")
        
        if self.browser_bridge:
            return await self.browser_bridge.refresh_via_browser()
        
        return {"success": False, "method": "none"}
    
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
        price: Dict[str, float] = None,
        shipping: str = "包邮",
        self_pickup: bool = False,
        post_price: float = 0,
        **kwargs
    ) -> Dict[str, Any]:
        """发布商品
        
        Args:
            images_paths: 图片路径列表
            title: 商品标题
            price: 价格 {"current_price": 100, "original_price": 200}
            shipping: 物流选项
            self_pickup: 是否支持自提
            post_price: 物流费用
        """
        if not self.http_client:
            return {"success": False, "message": "客户端未初始化"}
        
        if not images_paths:
            return {"success": False, "message": "需要提供图片路径"}
        
        if not title:
            return {"success": False, "message": "需要提供商品标题"}
        
        return await self.http_client.publish(
            images_paths=images_paths,
            title=title,
            price=price,
            shipping=shipping,
            self_pickup=self_pickup,
            post_price=post_price,
        )
    
    async def create_conversation(self, item_url: str, seller_id: str = "") -> str:
        """创建对话"""
        if not self.http_client:
            return ""
        
        item_id = self._extract_item_id(item_url)
        return await self.http_client.create_conversation(
            seller_id=seller_id, 
            item_id=item_id
        )
    
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
        return ""
    
    async def start_ws_listener(self) -> Dict[str, Any]:
        """启动 WebSocket 监听"""
        try:
            success = await self.ws_client.connect()
            return {"success": success, "message": "监听已启动" if success else "启动失败"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    async def stop_ws_listener(self) -> Dict[str, Any]:
        """停止 WebSocket 监听"""
        try:
            await self.ws_client.stop()
            return {"success": True, "message": "监听已停止"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    async def ws_send_message(self, target_id: str, content: str = "", image_url: str = "", conversation_id: str = "") -> Dict[str, Any]:
        """通过 WebSocket 发送消息"""
        try:
            success = await self.ws_client.send_message(target_id, content, image_url, conversation_id)
            return {"success": success, "message": "消息已发送" if success else "发送失败"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def ws_is_connected(self) -> bool:
        return self.ws_client.is_connected

    def ws_on_message(self, handler):
        self.ws_client.on_message(handler)

    async def close(self):
        """关闭客户端"""
        if self.http_client:
            self.http_client.close()
        if self.websocket_pool:
            await self.websocket_pool.stop()
