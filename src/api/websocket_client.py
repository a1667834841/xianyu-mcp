"""WebSocket 客户端 - 支持并发 RPC 请求和消息监听"""
import asyncio
import json
import time
import logging
import random
import base64
import re
from typing import Dict, Any, Optional, Callable, List
import websockets

from .message_codec import encode_custom_message, decode_message, MessageSegment
from .conversation_cache import ConversationCache
from .types import ChatMessage, Conversation

logger = logging.getLogger(__name__)


def generate_mid() -> str:
    """生成消息 ID（LWP 格式）"""
    random_part = random.randint(0, 999)
    timestamp = int(time.time() * 1000)
    return f"{random_part}{timestamp} 0"


def generate_uuid() -> str:
    """生成 UUID（LWP 格式）"""
    timestamp = int(time.time() * 1000)
    random_part = random.randint(0, 9999)
    return f"-{timestamp}{random_part}"


class WebSocketClient:
    """闲鱼 WebSocket 客户端 - 支持并发 RPC 请求"""
    
    WS_URL = "wss://wss-goofish.dingtalk.com/"
    APP_KEY = "444e9908a51d1cb236a27862abc769c9"
    HEARTBEAT_INTERVAL = 15
    MAX_SAFE_INTEGER = 9007199254740991
    
    def __init__(self, http_client, user_id: str = "", hook_notifier=None):
        self.http_client = http_client
        self.user_id = user_id
        self.hook_notifier = hook_notifier
        self.ws: Optional[websockets.ClientConnection] = None
        self.cache = ConversationCache()
        
        self._running = False
        self._connected = False
        self._my_id: str = ""
        self._device_id: str = ""
        
        self._on_message_handlers: List[Callable] = []
        self._pending_requests: Dict[str, asyncio.Future] = {}  # MID -> Future
        
        self._bg_tasks: List[asyncio.Task] = []
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 10
        self.last_error: Optional[str] = None
    
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
        """连接 WebSocket（快速返回，后台初始化）"""
        try:
            headers = self._get_headers()
            
            logger.info("[WebSocket] 尝试连接...")
            self.ws = await websockets.connect(
                self.WS_URL,
                additional_headers=headers,
                ping_interval=None,
            )
            
            self._running = True
            self.last_error = None
            self._reconnect_attempts = 0
            
            # 启动后台任务：消息循环 + 异步初始化 + 心跳
            self._bg_tasks.append(asyncio.create_task(self._message_loop()))
            self._bg_tasks.append(asyncio.create_task(self._async_init()))
            self._bg_tasks.append(asyncio.create_task(self._heart_beat_loop()))
            self._bg_tasks.append(asyncio.create_task(self._keep_token_alive_loop()))
            
            logger.info("[WebSocket] 已连接，后台初始化中...")
            return True
        
        except Exception as e:
            logger.error(f"[WebSocket] 连接错误: {e}")
            self._running = False
            self._connected = False
            self.last_error = str(e)
            self.ws = None
            return False
    
    async def _async_init(self):
        """后台异步初始化"""
        try:
            # 等待一小段时间让消息循环启动
            await asyncio.sleep(0.5)
            
            if not await self._init_connection():
                logger.error("[WebSocket] 初始化失败")
                self.last_error = self.last_error or "WebSocket 初始化失败"
                self._running = False
                if self.ws:
                    await self.ws.close()
                self.ws = None
                return
            
            self._connected = True
            logger.info("[WebSocket] 初始化成功")
            
        except Exception as e:
            logger.error(f"[WebSocket] 异步初始化错误: {e}")
            self._running = False
            self._connected = False
            self.last_error = str(e)
    
    async def _init_connection(self) -> bool:
        """初始化连接 - 发送注册和同步消息"""
        if not self.ws:
            return False
        
        token = await self.http_client.get_access_token()
        if not token:
            logger.error("[WebSocket] 无法获取 accessToken")
            self.last_error = "accessToken 获取失败"
            return False
        
        logger.info("[WebSocket] 获取 accessToken 成功")
        
        self._my_id = self.http_client.cookies.get("unb", "")
        self._device_id = self.http_client.device_id
        
        # 发送注册消息
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
        
        # 发送同步状态
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
    
    async def _message_loop(self):
        """消息循环（后台任务）"""
        try:
            while self._running and self.ws:
                try:
                    message_str = await asyncio.wait_for(self.ws.recv(), timeout=1.0)
                    await self._handle_raw_message(message_str)
                except asyncio.TimeoutError:
                    continue
                except websockets.ConnectionClosed:
                    logger.warning("[WebSocket] 连接断开")
                    self._connected = False
                    if self._running:
                        await asyncio.sleep(3)
                        await self._reconnect()
                    break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"[WebSocket] 消息循环错误: {e}")
    
    async def _reconnect(self):
        """重连"""
        if self._reconnect_attempts >= self._max_reconnect_attempts:
            logger.error("[WebSocket] 达到最大重连次数")
            self._running = False
            return
        
        self._reconnect_attempts += 1
        logger.info(f"[WebSocket] 第 {self._reconnect_attempts} 次重连...")
        
        # 关闭旧连接
        if self.ws:
            try:
                await self.ws.close()
            except:
                pass
            self.ws = None
        
        self._connected = False
        
        # 重新连接
        if await self.connect():
            self._reconnect_attempts = 0
            logger.info("[WebSocket] 重连成功")
    
    async def _heart_beat_loop(self):
        """心跳循环"""
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
        """保持 token 有效"""
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
            
            # 检查是否是 RPC 响应
            mid = message_dict.get("headers", {}).get("mid", "")
            if mid in self._pending_requests:
                future = self._pending_requests[mid]
                if message_dict.get("code") in [200, 0]:
                    future.set_result({
                        "success": True,
                        "body": message_dict.get("body", {}),
                        "raw": message_dict
                    })
                else:
                    future.set_result({
                        "success": False,
                        "error": f"服务器错误: {message_dict.get('message', message_dict.get('code'))}",
                        "code": message_dict.get("code"),
                        "raw": message_dict
                    })
                if message_dict.get("lwp") == "/r/SingleChatConversation/create":
                    logger.info(f"[WebSocket RPC] create conversation raw response: {json.dumps(message_dict, ensure_ascii=False)}")
                del self._pending_requests[mid]
                logger.info(f"[WebSocket RPC] 收到响应 MID={mid}")
                return
            
            # 发送 ACK
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
            if len(data_list) == 1:
                logger.info(f"[WebSocket] 单条推送原文: {json.dumps(data_list[0], ensure_ascii=False)}")
            
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
                    
                    asyncio.create_task(self._dispatch_message_received_hook(event))
                    
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
    
    async def _dispatch_message_received_hook(self, event: Dict[str, Any]) -> None:
        notifier = self.hook_notifier
        if notifier is None:
            return
        if not self.user_id:
            return
        if not event.get("cid") or not event.get("sender_id"):
            return
        if not notifier.is_event_enabled("message.received"):
            return

        try:
            await notifier.notify(
                event_name="message.received",
                user_id=self.user_id,
                event=event,
            )
        except Exception as exc:
            logger.warning(
                "Hook notify raised error: event=%s user_id=%s conversation_id=%s error=%s",
                "message.received",
                self.user_id,
                event.get("cid", ""),
                exc,
            )

    async def send_rpc(self, lwp_path: str, body: List[Any], timeout: int = 15000) -> Dict[str, Any]:
        """通过 WebSocket 发送 RPC 请求并等待响应"""
        if not self.ws or not self._connected:
            return {"success": False, "error": "WebSocket 未连接"}
        
        mid = generate_mid()
        payload = {
            "lwp": lwp_path,
            "headers": {"mid": mid},
            "body": body
        }
        
        logger.info(f"[WebSocket RPC] 发送: {lwp_path}, MID: {mid}")
        
        # 创建 Future 等待响应
        future = asyncio.Future()
        self._pending_requests[mid] = future
        
        try:
            await self.ws.send(json.dumps(payload))
            
            result = await asyncio.wait_for(future, timeout=timeout / 1000)
            return result
        except asyncio.TimeoutError:
            del self._pending_requests[mid]
            return {"success": False, "error": f"请求超时 ({timeout}ms)"}
        except Exception as e:
            del self._pending_requests[mid]
            return {"success": False, "error": str(e)}
    
    async def get_conversation_list(self, max_sort_index: int = None, page_size: int = 20) -> Dict[str, Any]:
        """获取会话列表（通过 WebSocket LWP 协议）"""
        if max_sort_index is None:
            max_sort_index = self.MAX_SAFE_INTEGER
        
        result = await self.send_rpc(
            "/r/Conversation/listNewestPagination",
            [max_sort_index, page_size]
        )
        
        if not result.get("success"):
            return result
        
        body = result.get("body", {})
        conversations = []
        
        user_convs = body.get("userConvs", [])
        for item in user_convs:
            try:
                user_conv = item.get("singleChatUserConversation", {})
                last_msg = user_conv.get("lastMessage", {}).get("message", {})
                
                cid = last_msg.get("cid", "")
                chat_id = cid.split("@")[0] if "@" in cid else cid
                
                if not chat_id:
                    continue
                
                last_message = ""
                custom = last_msg.get("content", {}).get("custom", {})
                if custom.get("summary"):
                    last_message = custom["summary"]
                
                peer_name = last_msg.get("extension", {}).get("reminderTitle", "")
                
                item_id = ""
                reminder_url = last_msg.get("extension", {}).get("reminderUrl", "")
                if reminder_url:
                    match = re.search(r"itemId=(\d+)", reminder_url)
                    if match:
                        item_id = match.group(1)
                
                conv_data = {
                    "cid": chat_id,
                    "peer_user_name": peer_name,
                    "last_message": last_message,
                    "last_message_time": last_msg.get("createAt", 0),
                    "unread_count": user_conv.get("redPoint", 0),
                    "sort_index": user_conv.get("modifyTime", 0),
                    "item_id": item_id,
                }
                
                conversations.append(conv_data)
                
                # 更新缓存
                conv = Conversation(
                    conversation_id=chat_id,
                    user_id=chat_id,
                    user_nick=peer_name,
                    last_message=last_message,
                    last_message_time=last_msg.get("createAt", 0) / 1000 if last_msg.get("createAt") else 0,
                    unread_count=user_conv.get("redPoint", 0),
                )
                self.cache.update_conversation(conv)
            
            except Exception as e:
                logger.warning(f"[WebSocket] 解析会话失败: {e}")
        
        has_more = body.get("hasMore", len(conversations) >= page_size)
        next_sort_index = None
        if conversations:
            next_sort_index = conversations[-1].get("sort_index")
        
        return {
            "success": True,
            "conversations": conversations,
            "hasMore": has_more,
            "nextSortIndex": next_sort_index,
        }
    
    async def get_message_history(self, chat_id: str, anchor: int = None, count: int = 20) -> Dict[str, Any]:
        """获取消息历史（通过 WebSocket LWP 协议）"""
        if not chat_id:
            return {"success": False, "error": "chat_id 不能为空"}
        
        if anchor is None:
            anchor = self.MAX_SAFE_INTEGER
        
        cid = f"{chat_id}@goofish" if "@" not in chat_id else chat_id
        
        result = await self.send_rpc(
            "/r/MessageManager/listUserMessages",
            [cid, False, anchor, count, False]
        )
        
        if not result.get("success"):
            return result
        
        body = result.get("body", {})
        messages = []
        
        models = body.get("userMessageModels", [])
        for model in models:
            try:
                msg = model.get("message", {})
                
                sender_id = msg.get("extension", {}).get("senderUserId", "")
                sender_name = msg.get("extension", {}).get("reminderTitle", "")
                
                content = ""
                content_type = 0
                custom = msg.get("content", {}).get("custom", {})
                
                if custom.get("summary"):
                    content = custom["summary"]
                    content_type = custom.get("contentType", 1)
                
                raw_data = custom.get("data")
                if not content and raw_data:
                    try:
                        decoded = base64.b64decode(raw_data).decode("utf-8")
                        parsed = json.loads(decoded)
                        if parsed.get("text", {}).get("text"):
                            content = parsed["text"]["text"]
                    except Exception:
                        pass
                
                if not content:
                    continue
                
                msg_data = {
                    "message_id": msg.get("messageId", ""),
                    "sender_id": sender_id,
                    "sender_name": sender_name,
                    "content": content,
                    "content_type": content_type,
                    "timestamp": msg.get("createAt", 0),
                    "read_status": model.get("readStatus", 0),
                }
                
                messages.append(msg_data)
                
                # 更新缓存
                from .types import TextContent
                chat_msg = ChatMessage(
                    message_id=msg.get("messageId", ""),
                    conversation_id=chat_id,
                    sender_id=sender_id,
                    receiver_id=self._my_id,
                    content=TextContent(type="text", text=content),
                    timestamp=msg.get("createAt", 0) / 1000 if msg.get("createAt") else 0,
                    is_read=model.get("readStatus", 0) == 1,
                )
                self.cache.add_message(chat_id, chat_msg)
            
            except Exception as e:
                logger.warning(f"[WebSocket] 解析消息失败: {e}")
        
        next_cursor = body.get("nextCursor", 0)
        has_more = len(messages) >= count and next_cursor > 0
        
        return {
            "success": True,
            "chat_id": chat_id,
            "messages": messages,
            "nextCursor": next_cursor,
            "hasMore": has_more,
        }

    async def create_conversation(self, seller_id: str, item_id: str) -> Dict[str, Any]:
        """通过 WebSocket RPC 创建单聊会话。"""
        if not self.ws or not self._running:
            logger.error("[WebSocket] WebSocket 未连接")
            return {"success": False, "error": "WebSocket 未连接"}
        if not self._my_id:
            self._my_id = self.http_client.cookies.get("unb", "")
        if not self._my_id or not seller_id or not item_id:
            return {"success": False, "error": "缺少创建对话必要参数"}

        body = [
            {
                "pairFirst": f"{self._my_id}@goofish",
                "pairSecond": f"{seller_id}@goofish",
                "bizType": "1",
                "extension": {"itemId": str(item_id), "orderId": "", "source": ""},
                "ctx": {"appVersion": "1.0", "platform": "web"},
            }
        ]

        result = await self.send_rpc("/r/SingleChatConversation/create", body)
        logger.info(f"[WebSocket RPC] create conversation parsed result: {json.dumps(result, ensure_ascii=False)}")
        if not result.get("success"):
            return result

        body_payload = result.get("body")
        cid = ""
        if isinstance(body_payload, dict):
            single_chat = body_payload.get("singleChatConversation", {})
            if isinstance(single_chat, dict):
                cid = single_chat.get("cid", "")
            if not cid:
                cid = body_payload.get("cid", "")
        elif isinstance(body_payload, list) and body_payload:
            cid = body_payload[0].get("cid", "")

        conversation_id = cid.split("@")[0] if "@" in cid else cid
        if not conversation_id:
            return {"success": False, "error": "响应中缺少 conversation_id", "raw": body_payload}

        return {"success": True, "conversation_id": conversation_id}
    
    async def send_message(
        self,
        target_id: str,
        content: str = "",
        image_url: str = "",
        cid: str = "",
    ) -> bool:
        """发送消息"""
        if not self.ws or not self._running:
            logger.error("[WebSocket] WebSocket 未连接")
            return False
        
        try:
            # 构建消息内容 (匹配参考实现格式)
            if image_url:
                msg_content = {
                    "contentType": 2,
                    "image": {"pics": [{"type": 0, "url": image_url, "width": 100, "height": 100}]}
                }
            else:
                msg_content = {
                    "contentType": 1,
                    "text": {"text": content}
                }
            
            encoded_data = base64.b64encode(json.dumps(msg_content).encode("utf-8")).decode("utf-8")
            _cid = cid if cid else target_id
            
            body = [
                {
                    "uuid": generate_uuid(),
                    "cid": f"{_cid}@goofish",
                    "conversationType": 1,
                    "content": {
                        "contentType": 101,
                        "custom": {
                            "type": 1,
                            "data": encoded_data
                        }
                    },
                    "redPointPolicy": 0,
                    "extension": {"extJson": "{}"},
                    "ctx": {"appVersion": "1.0", "platform": "web"},
                    "mtags": {},
                    "msgReadStatusSetting": 1,
                },
                {"actualReceivers": [f"{target_id}@goofish", f"{self._my_id}@goofish"]}
            ]
            
            result = await self.send_rpc("/r/MessageSend/sendByReceiverScope", body)
            if result.get("success"):
                logger.info(f"[WebSocket] 消息发送成功 -> {target_id}")
                return True
            else:
                logger.error(f"[WebSocket] 消息发送失败: {result.get('error')}")
                return False
        
        except Exception as e:
            logger.error(f"[WebSocket] 发送消息异常: {e}")
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
            sender_nick=event.get("sender_name", ""),
            receiver_id=self._my_id,
            receiver_nick="",
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
        
        # 清理 pending requests
        for mid, future in self._pending_requests.items():
            future.cancel()
        self._pending_requests.clear()
        
        # 取消后台任务
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
