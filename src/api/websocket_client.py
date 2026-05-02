"""WebSocket 客户端 - 基于 myfish 协议实现实时消息收发"""
import asyncio
import json
import time
import uuid
import logging
from typing import Dict, Any, Optional, Callable, List
import websockets

from .message_codec import encode_custom_message, decode_message, MessageSegment
from .conversation_cache import ConversationCache
from .types import ChatMessage, Conversation

logger = logging.getLogger(__name__)


def generate_mid() -> str:
    """生成消息 ID"""
    return str(uuid.uuid4())


def generate_uuid() -> str:
    """生成 UUID"""
    return str(uuid.uuid4())


class WebSocketClient:
    """闲鱼 WebSocket 客户端 - myfish 协议"""
    
    WS_URL = "wss://wss-goofish.dingtalk.com/"
    APP_KEY = "444e9908a51d1cb236a27862abc769c9"
    HEARTBEAT_INTERVAL = 15
    
    def __init__(self, http_client):
        self.http_client = http_client
        self.ws: Optional[websockets.ClientConnection] = None
        self.cache = ConversationCache()
        self._running = False
        self._connected = False
        self._my_id: str = ""
        self._device_id: str = ""
        self._on_message_handlers: List[Callable] = []
        self._bg_tasks: List[asyncio.Task] = []
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 10
    
    def _get_headers(self) -> Dict[str, str]:
        """获取 WebSocket headers"""
        cookie_str = "; ".join([f"{k}={v}" for k, v in self.http_client.cookies.items()])
        return {
            "Cookie": cookie_str,
            "Host": "wss-goofish.dingtalk.com",
            "Connection": "Upgrade",
            "Pragma": "no-cache",
            "Cache-Control": "no-cache",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/133.0.0.0 Safari/537.36",
            "Origin": "https://www.goofish.com",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
    
    async def _send_ack(self, message: Dict[str, Any]):
        """发送 ACK 确认"""
        if not self.ws:
            return
        req_headers = message.get("headers", {})
        ack = {
            "code": 200,
            "headers": {
                "mid": req_headers.get("mid", generate_mid()),
                "sid": req_headers.get("sid", ""),
            },
        }
        for key in ["app-key", "ua", "dt"]:
            if key in req_headers:
                ack["headers"][key] = req_headers[key]
        try:
            await self.ws.send(json.dumps(ack))
        except Exception as e:
            logger.error(f"ACK 发送失败: {e}")
    
    async def connect(self) -> bool:
        """连接 WebSocket 并注册"""
        try:
            headers = self._get_headers()
            
            logger.info("[WebSocket] 尝试连接...")
            async with websockets.connect(
                self.WS_URL,
                additional_headers=headers,
                ping_interval=None,
            ) as ws:
                self.ws = ws
                self._running = True
                self._reconnect_attempts = 0
                
                if not await self._init_connection():
                    self._running = False
                    return False
                
                self._connected = True
                logger.info("[WebSocket] 连接并注册成功")
                
                self._bg_tasks.append(asyncio.create_task(self._heart_beat_loop()))
                self._bg_tasks.append(asyncio.create_task(self._keep_token_alive_loop()))
                
                async for message_str in ws:
                    if not self._running:
                        break
                    await self._handle_raw_message(message_str)
        
        except websockets.ConnectionClosed:
            logger.warning("[WebSocket] 连接断开，3秒后重连...")
            self._connected = False
            if self._running and self._reconnect_attempts < self._max_reconnect_attempts:
                await asyncio.sleep(3)
                self._reconnect_attempts += 1
                return await self.connect()
        
        except Exception as e:
            logger.error(f"[WebSocket] 错误: {e}")
            self._running = False
            self._connected = False
            return False
        
        return True
    
    async def _init_connection(self) -> bool:
        """初始化 WebSocket 连接 - 发送注册和同步消息"""
        if not self.ws:
            return False
        
        token = await self.http_client.get_access_token()
        if not token:
            logger.error("[WebSocket] 无法获取 accessToken")
            return False
        
        logger.info(f"[WebSocket] 获取 accessToken 成功: {token[:20]}...")
        
        self._my_id = self.http_client.cookies.get("unb", "")
        self._device_id = self.http_client.device_id
        
        reg_msg = {
            "lwp": "/reg",
            "headers": {
                "cache-header": "app-key token ua wv",
                "app-key": self.APP_KEY,
                "token": token,
                "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/133.0.0.0 Safari/537.36 DingTalk(2.1.5)",
                "dt": "j",
                "wv": "im:3,au:3,sy:6",
                "sync": "0,0;0;0;",
                "did": self._device_id,
                "mid": generate_mid(),
            },
        }
        await self.ws.send(json.dumps(reg_msg))
        logger.info("[WebSocket] 发送注册消息")
        
        current_time = int(time.time() * 1000)
        sync_msg = {
            "lwp": "/r/SyncStatus/ackDiff",
            "headers": {"mid": generate_mid()},
            "body": [
                {
                    "pipeline": "sync",
                    "tooLong2Tag": "PNM,1",
                    "channel": "sync",
                    "topic": "sync",
                    "highPts": 0,
                    "pts": current_time * 1000,
                    "seq": 0,
                    "timestamp": current_time,
                }
            ],
        }
        await self.ws.send(json.dumps(sync_msg))
        logger.info("[WebSocket] 发送同步状态请求")
        
        return True
    
    async def _heart_beat_loop(self):
        """心跳循环 - 每 15 秒发送心跳"""
        try:
            while self._running:
                if self.ws and self._connected:
                    heartbeat_msg = {
                        "lwp": "/!",
                        "headers": {"mid": generate_mid()},
                    }
                    await self.ws.send(json.dumps(heartbeat_msg))
                    logger.debug("[WebSocket] 发送心跳")
                await asyncio.sleep(self.HEARTBEAT_INTERVAL)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"[WebSocket] 心跳出错: {e}")
    
    async def _keep_token_alive_loop(self):
        """保持 token 有效 - 每 10 分钟刷新 accessToken"""
        try:
            while self._running:
                await asyncio.sleep(600)
                try:
                    token = await self.http_client.get_access_token()
                    if token:
                        logger.debug("[WebSocket] accessToken 已刷新")
                except Exception as e:
                    logger.warning(f"[WebSocket] 刷新 accessToken 失败: {e}")
        except asyncio.CancelledError:
            pass
    
    async def _handle_raw_message(self, message_str: str):
        """处理原始消息"""
        try:
            message_dict = json.loads(message_str)
            await self._send_ack(message_dict)
            
            lwp = message_dict.get("lwp", "")
            
            if lwp == "/!":
                logger.debug("[WebSocket] 收到心跳响应")
                return
            
            if "syncPushPackage" not in message_str:
                return
            
            body = message_dict.get("body", {})
            push_package = body.get("syncPushPackage", {})
            data_list = push_package.get("data", [])
            
            logger.info(f"[WebSocket] 收到 {len(data_list)} 条推送消息")
            
            for item in data_list:
                raw_data = item.get("data")
                if not raw_data:
                    continue
                
                try:
                    parsed = json.loads(raw_data)
                except json.JSONDecodeError:
                    try:
                        decoded = raw_data.encode().decode()
                        parsed = json.loads(decoded)
                    except Exception:
                        continue
                
                try:
                    msg_body = parsed.get("1", {})
                    cid_raw = msg_body.get("2", "")
                    cid = cid_raw.split("@")[0] if cid_raw else ""
                    timestamp = msg_body.get("5", 0)
                    
                    sender_info = msg_body.get("10", {})
                    sender_id = sender_info.get("senderUserId", "")
                    sender_name = sender_info.get("reminderTitle", "")
                    
                    content_data = msg_body.get("6", {})
                    
                    if str(sender_id) == str(self._my_id):
                        continue
                    
                    segments = decode_message(content_data)
                    if not segments:
                        continue
                    
                    event = {
                        "cid": cid,
                        "sender_id": sender_id,
                        "sender_name": sender_name,
                        "timestamp": timestamp / 1000 if timestamp else 0,
                        "segments": [seg.model_dump() for seg in segments],
                    }
                    
                    logger.info(f"[WebSocket] 收到消息: {sender_name}({sender_id}): {segments[0].content.text if hasattr(segments[0].content, 'text') else ''}")
                    
                    self._update_cache_from_event(event, segments)
                    
                    for handler in self._on_message_handlers:
                        try:
                            if asyncio.iscoroutinefunction(handler):
                                await handler(event)
                            else:
                                handler(event)
                        except Exception as e:
                            logger.error(f"[WebSocket] 消息处理器错误: {e}")
                
                except Exception as e:
                    logger.debug(f"[WebSocket] 解析消息失败: {e}")
        
        except Exception as e:
            logger.error(f"[WebSocket] 处理原始消息错误: {e}")
    
    async def send_message(
        self,
        target_id: str,
        content: str = "",
        image_url: str = "",
        cid: str = "",
    ) -> bool:
        """发送消息
        
        Args:
            target_id: 目标用户 ID（卖家或买家）
            content: 文本消息内容
            image_url: 图片 URL（可选）
            cid: 对话 ID（可选，默认使用 target_id）
        """
        if not self.ws or not self._running:
            logger.error("[WebSocket] WebSocket 未连接")
            return False
        
        try:
            encoded_data = encode_custom_message(content, image_url)
            _cid = cid if cid else target_id
            
            msg = {
                "lwp": "/r/MessageSend/sendByReceiverScope",
                "headers": {"mid": generate_mid()},
                "body": [
                    {
                        "uuid": generate_uuid(),
                        "cid": f"{_cid}@goofish",
                        "conversationType": 1,
                        "content": {
                            "contentType": 101,
                            "custom": {"type": 2, "data": encoded_data},
                        },
                        "redPointPolicy": 0,
                        "extension": {"extJson": "{}"},
                        "ctx": {"appVersion": "1.0", "platform": "web"},
                        "mtags": {},
                        "msgReadStatusSetting": 1,
                    },
                    {"actualReceivers": [f"{target_id}@goofish", f"{self._my_id}@goofish"]},
                ],
            }
            
            await self.ws.send(json.dumps(msg))
            logger.info(f"[WebSocket] 消息已发送 -> {target_id}")
            return True
        
        except Exception as e:
            logger.error(f"[WebSocket] 发送消息失败: {e}")
            return False
    
    def on_message(self, handler: Callable):
        """注册消息处理器"""
        self._on_message_handlers.append(handler)
    
    def remove_message_handler(self, handler: Callable):
        """移除消息处理器"""
        if handler in self._on_message_handlers:
            self._on_message_handlers.remove(handler)
    
    def _update_cache_from_event(self, event: Dict[str, Any], segments: List[MessageSegment]):
        """从事件更新缓存"""
        conv = Conversation(
            conversation_id=event["cid"],
            user_id=event["sender_id"],
            user_nick=event["sender_name"],
            last_message=self._extract_message_text(segments),
            last_message_time=event["timestamp"],
            unread_count=0,
        )
        self.cache.update_conversation(conv)
        
        msg = ChatMessage(
            message_id="",
            conversation_id=event["cid"],
            sender_id=event["sender_id"],
            receiver_id=self._my_id,
            content=segments[0].content if segments else None,
            timestamp=event["timestamp"],
            is_read=False,
        )
        self.cache.add_message(event["cid"], msg)
    
    def _extract_message_text(self, segments: List[MessageSegment]) -> str:
        """提取消息文本摘要"""
        if not segments:
            return "[未知消息类型]"
        content = segments[0].content
        if hasattr(content, 'text') and content.text:
            return content.text[:50]
        elif hasattr(content, 'image_url') and content.image_url:
            return "[图片]"
        else:
            return "[未知消息类型]"
    
    @property
    def is_connected(self) -> bool:
        """检查连接状态"""
        return self._connected and self.ws is not None
    
    async def stop(self):
        """停止 WebSocket 客户端"""
        self._running = False
        self._connected = False
        
        for task in self._bg_tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        
        self._bg_tasks = []
        
        if self.ws:
            try:
                await self.ws.close()
            except Exception:
                pass
            self.ws = None
        
        logger.info("[WebSocket] 客户端已停止")