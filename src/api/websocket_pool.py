import json
import asyncio
import logging
from typing import Dict, Any, List, Callable, Optional
import websockets

from .types import Message, TextContent, ImageContent

logger = logging.getLogger(__name__)


class WebSocketPool:
    """WebSocket 连接池"""
    
    WS_URL = "wss://wss.goofish.com"
    
    def __init__(self):
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self._running = False
        self._message_handlers: List[Callable] = []
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 10
    
    async def connect(self, cookies_str: str) -> bool:
        """连接 WebSocket"""
        try:
            headers = {"Cookie": cookies_str}
            self.ws = await websockets.connect(
                self.WS_URL,
                additional_headers=headers,
            )
            self._running = True
            self._reconnect_attempts = 0
            
            asyncio.create_task(self._listen_messages())
            
            logger.info("WebSocket 连接成功")
            return True
        except Exception as e:
            logger.error(f"WebSocket 连接失败: {e}")
            return False
    
    async def _listen_messages(self):
        """监听消息"""
        if not self.ws:
            return
        
        try:
            async for message in self.ws:
                if not self._running:
                    break
                try:
                    data = json.loads(message)
                    await self._handle_message(data)
                except json.JSONDecodeError:
                    logger.warning(f"收到非 JSON 消息: {message}")
        except websockets.ConnectionClosed:
            logger.info("WebSocket 连接关闭")
            if self._reconnect_attempts < self._max_reconnect_attempts:
                await self._reconnect()
        except Exception as e:
            logger.error(f"监听消息出错: {e}")
    
    async def _handle_message(self, data: Dict[str, Any]):
        """处理收到的消息"""
        msg_type = data.get("type", "")
        if msg_type == "message":
            from .types import ChatMessage
            message = ChatMessage(
                message_id=data.get("messageId", ""),
                conversation_id=data.get("cid", ""),
                sender_id=data.get("sendUserId", ""),
                receiver_id=data.get("receiveUserId", ""),
                content=TextContent(type="text", text=str(data.get("content", {}))),
                timestamp=data.get("timestamp", 0),
            )
            
            for handler in self._message_handlers:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(message)
                    else:
                        handler(message)
                except Exception as e:
                    logger.error(f"消息处理失败: {e}")
    
    async def _reconnect(self):
        """重连"""
        self._reconnect_attempts += 1
        logger.info(f"尝试重连 ({self._reconnect_attempts}/{self._max_reconnect_attempts})")
        
        await asyncio.sleep(2 ** self._reconnect_attempts)
        
        # TODO: 获取 cookie 并重连
        # await self.connect(cookies_str)
    
    async def send_message(
        self, 
        conversation_id: str, 
        to_user_id: str, 
        message: Message
    ) -> bool:
        """发送消息"""
        if not self.ws:
            return False
        
        try:
            send_msg = {
                "type": "send",
                "cid": conversation_id,
                "toUserId": to_user_id,
                "content": self._serialize_message(message),
            }
            await self.ws.send(json.dumps(send_msg))
            return True
        except Exception as e:
            logger.error(f"发送消息失败: {e}")
            return False
    
    def _serialize_message(self, message: Message) -> Dict[str, Any]:
        """序列化消息"""
        if isinstance(message, TextContent):
            return {"type": "text", "text": message.text}
        elif isinstance(message, ImageContent):
            return {
                "type": "image",
                "imageUrl": message.image_url,
                "width": message.width,
                "height": message.height,
            }
        return {}
    
    def on_message(self, handler: Callable):
        """注册消息处理器"""
        self._message_handlers.append(handler)
    
    async def stop(self):
        """停止客户端"""
        self._running = False
        if self.ws:
            await self.ws.close()
            self.ws = None
