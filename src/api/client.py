import logging
from typing import Dict, Any, Optional, List

from .http_client import HttpClient
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
        
        self.http_client = HttpClient(cookies={}, device_id="")
        self.websocket_pool = WebSocketPool()
        self.browser_bridge = BrowserBridge()
        
        self._initialized = True
    
    def initialize(self, cookies: Dict[str, str], device_id: str):
        """初始化客户端"""
        self.http_client = HttpClient(cookies=cookies, device_id=device_id)
        
        self.browser_bridge = BrowserBridge()
    
    async def login(self, timeout: int = 300) -> Dict[str, Any]:
        """登录"""
        if not self.http_client:
            return {"success": False, "message": "客户端未初始化"}
        return await self.http_client.login(timeout=timeout)
    
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
    
    async def publish(self, item_url: str, **kwargs) -> Dict[str, Any]:
        """发布商品，API 优先，失败降级浏览器"""
        if not self.http_client:
            return {"success": False}
        
        try:
            result = await self.http_client.publish(item_url=item_url, **kwargs)
            if result.get("success"):
                result["method"] = "http"
                return result
        except Exception as e:
            logger.warning(f"API 发布失败，降级到浏览器: {e}")
        
        if self.browser_bridge:
            return await self.browser_bridge.publish_via_browser(item_url=item_url, **kwargs)
        
        return {"success": False, "method": "none"}
    
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
        """获取对话列表"""
        if not self.http_client:
            return []
        return await self.http_client.list_conversations(limit=limit, offset=offset)
    
    async def get_messages(
        self, 
        conversation_id: str, 
        limit: int = 50,
        before_timestamp: Optional[int] = None
    ) -> Dict[str, Any]:
        """获取消息历史"""
        if not self.http_client:
            return {"messages": [], "has_more": False}
        return await self.http_client.get_message_history(
            conversation_id=conversation_id,
            limit=limit,
            before_timestamp=before_timestamp,
        )
    
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
    
    async def close(self):
        """关闭客户端"""
        if self.http_client:
            self.http_client.close()
        if self.websocket_pool:
            await self.websocket_pool.stop()
