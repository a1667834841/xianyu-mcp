"""WebSocket 客户端 - 基于 myfish 协议实现实时消息收发"""
import json
import asyncio
import logging
import time
from typing import Dict, Any, List, Callable, Optional
import websockets

from .message_codec import encode_message, encode_custom_message, decode_message, MessageSegment

logger = logging.getLogger(__name__)


class WebSocketClient:
    """闲鱼 WebSocket 客户端 - myfish 协议"""
    
    WS_URL = "wss://wss-goofish.dingtalk.com/"
    HEARTBEAT_INTERVAL = 15
    
    def __init__(self, http_client):
        self.http_client = http_client
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self._running = False
        self._connected = False
        self._access_token = ""
        self._message_handlers: List[Callable] = []
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 10
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._listen_task: Optional[asyncio.Task] = None
        self._last_sync_index = 0
    
    async def connect(self) -> bool:
        """连接 WebSocket 并注册"""
        try:
            self._access_token = await self.http_client.get_access_token()
            if not self._access_token:
                logger.error("[WebSocket] 获取 accessToken 失败")
                return False
            
            logger.info(f"[WebSocket] 获取 accessToken 成功: {self._access_token[:20]}...")
            
            self.ws = await websockets.connect(
                self.WS_URL,
                additional_headers={"Origin": "https://www.goofish.com"},
                ping_interval=None,
            )
            
            self._running = True
            self._reconnect_attempts = 0
            
            reg_msg = self._build_reg_message()
            await self.ws.send(json.dumps(reg_msg))
            logger.info("[WebSocket] 发送注册消息")
            
            reg_response = await asyncio.wait_for(self.ws.recv(), timeout=10)
            reg_data = json.loads(reg_response)
            
            if reg_data.get("code") == 0 or reg_data.get("success"):
                self._connected = True
                logger.info("[WebSocket] 注册成功")
                
                await self._send_sync_status()
                
                self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
                self._listen_task = asyncio.create_task(self._listen_messages())
                
                return True
            else:
                logger.error(f"[WebSocket] 注册失败: {reg_data}")
                return False
                
        except asyncio.TimeoutError:
            logger.error("[WebSocket] 注册超时")
            return False
        except Exception as e:
            logger.error(f"[WebSocket] 连接失败: {e}")
            return False
    
    def _build_reg_message(self) -> Dict[str, Any]:
        """构建注册消息"""
        cookie_str = "; ".join([f"{k}={v}" for k, v in self.http_client.cookies.items()])
        
        return {
            "operation": "/reg",
            "body": {
                "accessToken": self._access_token,
                "cookie": cookie_str,
                "deviceId": self.http_client.device_id or "default_device",
            }
        }
    
    async def _send_sync_status(self) -> bool:
        """发送同步状态请求"""
        if not self.ws or not self._connected:
            return False
        
        try:
            sync_msg = {
                "operation": "/r/SyncStatus/ackDiff",
                "body": {
                    "syncIndex": self._last_sync_index,
                    "syncMode": "diff",
                }
            }
            await self.ws.send(json.dumps(sync_msg))
            logger.info(f"[WebSocket] 发送同步状态请求: syncIndex={self._last_sync_index}")
            return True
        except Exception as e:
            logger.error(f"[WebSocket] 发送同步状态失败: {e}")
            return False
    
    async def _heartbeat_loop(self):
        """心跳循环"""
        while self._running and self._connected:
            try:
                await asyncio.sleep(self.HEARTBEAT_INTERVAL)
                
                if self.ws and self._connected:
                    heartbeat_msg = {
                        "operation": "/h",
                        "body": {}
                    }
                    await self.ws.send(json.dumps(heartbeat_msg))
                    logger.debug("[WebSocket] 发送心跳")
                    
            except websockets.ConnectionClosed:
                logger.warning("[WebSocket] 心跳时连接已关闭")
                self._connected = False
                if self._running and self._reconnect_attempts < self._max_reconnect_attempts:
                    await self._reconnect()
                break
            except Exception as e:
                logger.error(f"[WebSocket] 心跳出错: {e}")
    
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
                    logger.warning(f"[WebSocket] 收到非 JSON 消息: {message[:100]}")
                    
        except websockets.ConnectionClosed:
            logger.info("[WebSocket] 连接关闭")
            self._connected = False
            if self._running and self._reconnect_attempts < self._max_reconnect_attempts:
                await self._reconnect()
        except Exception as e:
            logger.error(f"[WebSocket] 监听出错: {e}")
            self._connected = False
    
    async def _handle_message(self, data: Dict[str, Any]):
        """处理收到的消息"""
        operation = data.get("operation", "")
        body = data.get("body", {})
        
        if operation == "/h":
            logger.debug("[WebSocket] 收到心跳响应")
            return
        
        if operation == "/p/syncPushPackage":
            await self._handle_sync_push_package(body)
            return
        
        if operation == "/r/SyncStatus/ackDiff":
            sync_index = body.get("syncIndex", 0)
            self._last_sync_index = sync_index
            logger.debug(f"[WebSocket] 同步状态更新: syncIndex={sync_index}")
            return
        
        if operation.startswith("/r/MessageSend"):
            await self._handle_send_response(body)
            return
        
        logger.debug(f"[WebSocket] 收到未知消息类型: {operation}")
    
    async def _handle_sync_push_package(self, body: Dict[str, Any]):
        """处理同步推送包"""
        messages = body.get("messages", [])
        sync_index = body.get("syncIndex", 0)
        
        self._last_sync_index = sync_index
        
        logger.info(f"[WebSocket] 收到 {len(messages)} 条推送消息, syncIndex={sync_index}")
        
        for msg_data in messages:
            try:
                content_data = msg_data.get("content", {})
                segments = decode_message(content_data)
                
                message_info = {
                    "message_id": msg_data.get("messageId", ""),
                    "conversation_id": msg_data.get("cid", ""),
                    "sender_id": msg_data.get("fromUserId", ""),
                    "receiver_id": msg_data.get("toUserId", ""),
                    "timestamp": msg_data.get("timestamp", 0) / 1000.0,
                    "segments": segments,
                    "raw": msg_data,
                }
                
                for handler in self._message_handlers:
                    try:
                        if asyncio.iscoroutinefunction(handler):
                            await handler(message_info)
                        else:
                            handler(message_info)
                    except Exception as e:
                        logger.error(f"[WebSocket] 消息处理器出错: {e}")
                        
            except Exception as e:
                logger.error(f"[WebSocket] 解析消息失败: {e}")
        
        await self._send_ack(sync_index)
    
    async def _send_ack(self, sync_index: int):
        """发送确认"""
        if not self.ws:
            return
        
        try:
            ack_msg = {
                "operation": "/p/syncPushPackage/ack",
                "body": {
                    "syncIndex": sync_index,
                }
            }
            await self.ws.send(json.dumps(ack_msg))
            logger.debug(f"[WebSocket] 发送 ACK: syncIndex={sync_index}")
        except Exception as e:
            logger.error(f"[WebSocket] 发送 ACK 失败: {e}")
    
    async def _handle_send_response(self, body: Dict[str, Any]):
        """处理发送响应"""
        success = body.get("success", False)
        message_id = body.get("messageId", "")
        
        if success:
            logger.info(f"[WebSocket] 消息发送成功: messageId={message_id}")
        else:
            error_msg = body.get("errorMessage", "未知错误")
            logger.error(f"[WebSocket] 消息发送失败: {error_msg}")
    
    async def send_message(
        self,
        conversation_id: str,
        to_user_id: str,
        content: str = "",
        image_url: str = "",
    ) -> Dict[str, Any]:
        """发送消息"""
        if not self.ws or not self._connected:
            return {"success": False, "message": "WebSocket 未连接"}
        
        try:
            encoded_content, content_type = encode_message(content, image_url)
            
            custom_data = encode_custom_message(content, image_url)
            
            send_msg = {
                "operation": "/r/MessageSend/sendByReceiverScope",
                "body": {
                    "cid": conversation_id,
                    "toUserId": to_user_id,
                    "content": {
                        "contentType": content_type,
                        **encoded_content,
                    },
                    "custom": {
                        "data": custom_data,
                    },
                    "timestamp": int(time.time() * 1000),
                }
            }
            
            await self.ws.send(json.dumps(send_msg))
            logger.info(f"[WebSocket] 发送消息到对话 {conversation_id}")
            
            return {"success": True, "message": "消息已发送"}
            
        except Exception as e:
            logger.error(f"[WebSocket] 发送消息失败: {e}")
            return {"success": False, "message": str(e)}
    
    async def _reconnect(self):
        """重连"""
        self._reconnect_attempts += 1
        self._connected = False
        
        wait_time = min(2 ** self._reconnect_attempts, 60)
        logger.info(f"[WebSocket] 尝试重连 ({self._reconnect_attempts}/{self._max_reconnect_attempts}), 等待 {wait_time}s")
        
        await asyncio.sleep(wait_time)
        
        if self.ws:
            try:
                await self.ws.close()
            except Exception:
                pass
            self.ws = None
        
        success = await self.connect()
        if success:
            logger.info("[WebSocket] 重连成功")
            self._reconnect_attempts = 0
        else:
            logger.warning(f"[WebSocket] 重连失败 ({self._reconnect_attempts}/{self._max_reconnect_attempts})")
    
    def on_message(self, handler: Callable):
        """注册消息处理器"""
        self._message_handlers.append(handler)
    
    def remove_message_handler(self, handler: Callable):
        """移除消息处理器"""
        if handler in self._message_handlers:
            self._message_handlers.remove(handler)
    
    @property
    def is_connected(self) -> bool:
        """检查是否已连接"""
        return self._connected and self.ws is not None
    
    async def stop(self):
        """停止客户端"""
        self._running = False
        self._connected = False
        
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None
        
        if self._listen_task:
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass
            self._listen_task = None
        
        if self.ws:
            try:
                await self.ws.close()
            except Exception:
                pass
            self.ws = None
        
        logger.info("[WebSocket] 客户端已停止")