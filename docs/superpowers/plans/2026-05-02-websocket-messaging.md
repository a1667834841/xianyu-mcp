# WebSocket 消息收发实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现闲鱼 WebSocket 消息收发功能，集成到 MCP 服务

**Architecture:** 基于 myfish 实现，新建 WebSocketClient 和 MessageCodec，通过 MCP 工具暴露接口

**Tech Stack:** websockets, pydantic, asyncio, FastMCP

---

## 文件结构

| 文件 | 负责 |
|------|------|
| `src/api/message_codec.py` | 消息编码/解码（文本、图片） |
| `src/api/websocket_client.py` | WebSocket 连接、注册、心跳、收发 |
| `src/api/client.py` | 添加 WebSocket 相关方法 |
| `mcp_server/http_server.py` | 添加 MCP 工具 |

---

### Task 1: 创建消息编码/解码模块

**Files:**
- Create: `src/api/message_codec.py`

- [ ] **Step 1: 创建 message_codec.py 文件**

```python
"""消息编码/解码模块"""
import base64
import json
from typing import Dict, Any, List, Tuple
from pydantic import BaseModel


class TextContent(BaseModel):
    type: str = "text"
    text: str


class ImageContent(BaseModel):
    type: str = "image"
    image_url: str
    width: int = 0
    height: int = 0


class MessageSegment(BaseModel):
    """消息段"""
    content: TextContent | ImageContent


def encode_text(text: str) -> Tuple[Dict[str, Any], int]:
    """编码文本消息"""
    return {
        "contentType": 1,
        "text": {"text": text},
    }, 1


def encode_image(image_url: str, width: int = 100, height: int = 100) -> Tuple[Dict[str, Any], int]:
    """编码图片消息"""
    return {
        "contentType": 2,
        "image": {
            "pics": [
                {
                    "type": 0,
                    "url": image_url,
                    "width": width,
                    "height": height,
                }
            ]
        },
    }, 2


def encode_message(content: str, image_url: str = "") -> Tuple[Dict[str, Any], int]:
    """编码消息（文本或图片）"""
    if image_url:
        return encode_image(image_url)
    return encode_text(content)


def encode_custom_message(content: str, image_url: str = "") -> str:
    """编码为 custom 格式（base64）"""
    payload, custom_type = encode_message(content, image_url)
    return base64.b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8")


def decode_message(data: Dict[str, Any]) -> List[MessageSegment]:
    """解码消息"""
    content_type = data.get("contentType", 0)
    segments = []
    
    if content_type == 1:  # 文本
        text = data.get("text", {}).get("text", "")
        if text:
            segments.append(MessageSegment(content=TextContent(text=text)))
    
    elif content_type == 2:  # 图片
        pics = data.get("image", {}).get("pics", [])
        for pic in pics:
            segments.append(MessageSegment(
                content=ImageContent(
                    image_url=pic.get("url", ""),
                    width=pic.get("width", 0),
                    height=pic.get("height", 0),
                )
            ))
    
    elif content_type == 101:  # 自定义/富文本
        custom_data = data.get("custom", {}).get("data", "")
        if custom_data:
            try:
                decoded = base64.b64decode(custom_data).decode("utf-8")
                for item in json.loads(decoded):
                    if item.get("type") == "text":
                        segments.append(MessageSegment(content=TextContent(text=item.get("text", ""))))
                    elif item.get("type") == "image":
                        segments.append(MessageSegment(content=ImageContent(
                            image_url=item.get("image_url", ""),
                            width=item.get("width", 0),
                            height=item.get("height", 0),
                        )))
            except Exception:
                pass
    
    return segments
```

- [ ] **Step 2: 提交 message_codec.py**

```bash
git add src/api/message_codec.py
git commit -m "feat: 添加消息编码/解码模块"
```

---

### Task 2: 创建 WebSocket 客户端

**Files:**
- Create: `src/api/websocket_client.py`
- Modify: `src/api/http_client.py`（添加 get_access_token 方法）

- [ ] **Step 1: 在 http_client.py 添加 get_access_token 方法**

在 `src/api/http_client.py` 的 `refresh_token` 方法后添加：

```python
async def get_access_token(self) -> str:
    """获取 WebSocket accessToken"""
    api = "mtop.taobao.idlemessage.pc.login.token/1.0"
    data = {
        "appKey": "444e9908a51d1cb236a27862abc769c9",
        "deviceId": self.device_id or "default_device",
    }
    
    resp = await self._send_request(api, data)
    return resp.get("data", {}).get("accessToken", "")
```

- [ ] **Step 2: 创建 websocket_client.py 文件**

```python
"""WebSocket 客户端"""
import asyncio
import json
import time
import uuid
import logging
from typing import Dict, Any, Optional, Callable, List
import websockets

from .message_codec import encode_custom_message, decode_message, MessageSegment

logger = logging.getLogger(__name__)


def generate_mid() -> str:
    """生成消息 ID"""
    return str(uuid.uuid4())


def generate_uuid() -> str:
    """生成 UUID"""
    return str(uuid.uuid4())


class WebSocketClient:
    """闲鱼 WebSocket 客户端"""
    
    WS_URL = "wss://wss-goofish.dingtalk.com/"
    APP_KEY = "444e9908a51d1cb236a27862abc769c9"
    
    def __init__(self, http_client):
        self.http_client = http_client
        self.ws: Optional[websockets.ClientConnection] = None
        self._running = False
        self._my_id: str = ""
        self._device_id: str = ""
        self._on_message_handlers: List[Callable] = []
        self._bg_tasks: List[asyncio.Task] = []
    
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
    
    async def _init_connection(self) -> bool:
        """初始化 WebSocket 连接"""
        if not self.ws:
            return False
        
        # 获取 accessToken
        token = await self.http_client.get_access_token()
        if not token:
            logger.error("无法获取 accessToken")
            return False
        
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
        
        logger.info("WebSocket 连接初始化成功")
        return True
    
    async def _heart_beat_loop(self):
        """心跳循环"""
        if not self.ws:
            return
        try:
            while self._running:
                await self.ws.send(json.dumps({"lwp": "/!", "headers": {"mid": generate_mid()}}))
                await asyncio.sleep(15)
        except asyncio.CancelledError:
            pass
    
    async def _keep_token_alive_loop(self):
        """保持 token 有效"""
        try:
            while self._running:
                await asyncio.sleep(600)
                try:
                    await self.http_client.get_access_token()
                except Exception:
                    pass
        except asyncio.CancelledError:
            pass
    
    async def _handle_raw_message(self, message_str: str):
        """处理原始消息"""
        try:
            message_dict = json.loads(message_str)
            await self._send_ack(message_dict)
            
            if "syncPushPackage" not in message_str:
                return
            
            body = message_dict.get("body", {})
            push_package = body.get("syncPushPackage", {})
            data_list = push_package.get("data", [])
            
            for item in data_list:
                raw_data = item.get("data")
                if not raw_data:
                    continue
                
                # 尝试解析
                try:
                    parsed = json.loads(raw_data)
                except json.JSONDecodeError:
                    try:
                        decoded = raw_data.encode().decode()
                        parsed = json.loads(decoded)
                    except Exception:
                        continue
                
                # 解析消息
                try:
                    msg_body = parsed.get("1", {})
                    cid_raw = msg_body.get("2", "")
                    cid = cid_raw.split("@")[0] if cid_raw else ""
                    timestamp = msg_body.get("5", 0)
                    
                    sender_info = msg_body.get("10", {})
                    sender_id = sender_info.get("senderUserId", "")
                    sender_name = sender_info.get("reminderTitle", "")
                    
                    content_data = msg_body.get("6", {})
                    
                    # 跳过自己发送的消息
                    if str(sender_id) == str(self._my_id):
                        continue
                    
                    segments = decode_message(content_data)
                    if not segments:
                        continue
                    
                    # 构建消息事件
                    event = {
                        "cid": cid,
                        "sender_id": sender_id,
                        "sender_name": sender_name,
                        "timestamp": timestamp / 1000 if timestamp else 0,
                        "segments": [seg.model_dump() for seg in segments],
                    }
                    
                    logger.info(f"收到消息: {sender_name}({sender_id}): {segments[0].content.text if segments else ''}")
                    
                    # 调用处理器
                    for handler in self._on_message_handlers:
                        try:
                            if asyncio.iscoroutinefunction(handler):
                                await handler(event)
                            else:
                                handler(event)
                        except Exception as e:
                            logger.error(f"消息处理器错误: {e}")
                
                except Exception as e:
                    logger.debug(f"解析消息失败: {e}")
        
        except Exception as e:
            logger.error(f"处理原始消息错误: {e}")
    
    async def send_message(
        self,
        target_id: str,
        content: str = "",
        image_url: str = "",
        cid: str = "",
    ) -> bool:
        """发送消息"""
        if not self.ws or not self._running:
            logger.error("WebSocket 未连接")
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
            logger.info(f"消息已发送 -> {target_id}")
            return True
        
        except Exception as e:
            logger.error(f"发送消息失败: {e}")
            return False
    
    def on_message(self, handler: Callable):
        """注册消息处理器"""
        self._on_message_handlers.append(handler)
    
    async def start(self) -> bool:
        """启动 WebSocket 客户端"""
        if self._running:
            return True
        
        headers = self._get_headers()
        
        try:
            logger.info("尝试连接 WebSocket...")
            async with websockets.connect(self.WS_URL, additional_headers=headers) as ws:
                self.ws = ws
                self._running = True
                
                if not await self._init_connection():
                    self._running = False
                    return False
                
                # 启动后台任务
                self._bg_tasks.append(asyncio.create_task(self._heart_beat_loop()))
                self._bg_tasks.append(asyncio.create_task(self._keep_token_alive_loop()))
                
                # 监听消息
                async for message_str in ws:
                    if not self._running:
                        break
                    await self._handle_raw_message(message_str)
        
        except websockets.ConnectionClosed:
            logger.warning("WebSocket 断开，3秒后重连...")
            await asyncio.sleep(3)
            return await self.start()
        
        except Exception as e:
            logger.error(f"WebSocket 错误: {e}")
            self._running = False
            return False
        
        return True
    
    async def stop(self):
        """停止 WebSocket 客户端"""
        self._running = False
        
        for task in self._bg_tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        
        self._bg_tasks = []
        
        if self.ws:
            await self.ws.close()
            self.ws = None
        
        logger.info("WebSocket 已停止")
    
    def is_connected(self) -> bool:
        """检查连接状态"""
        return self._running and self.ws is not None
```

- [ ] **Step 3: 提交 WebSocket 客户端**

```bash
git add src/api/message_codec.py src/api/websocket_client.py src/api/http_client.py
git commit -m "feat: 添加 WebSocket 客户端和消息编码模块"
```

---

### Task 3: 集成到 XianyuApiClient

**Files:**
- Modify: `src/api/client.py`

- [ ] **Step 1: 在 client.py 导入 WebSocketClient**

在 `src/api/client.py` 文件顶部添加导入：

```python
from .websocket_client import WebSocketClient
```

- [ ] **Step 2: 在 XianyuApiClient.__init__ 添加 WebSocketClient**

修改 `__init__` 方法：

```python
def __init__(self):
    if self._initialized:
        return
    
    self.http_client = HttpClient(cookies=None, device_id="")
    self.websocket_pool = WebSocketPool()
    self.browser_bridge = BrowserBridge()
    self.ws_client = WebSocketClient(self.http_client)  # 新增
    
    self._initialized = True
```

- [ ] **Step 3: 添加 WebSocket 相关方法**

在 `close` 方法前添加：

```python
async def start_ws_listener(self) -> Dict[str, Any]:
    """启动 WebSocket 监听"""
    try:
        success = await self.ws_client.start()
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

async def ws_send_message(
    self,
    target_id: str,
    content: str = "",
    image_url: str = "",
    conversation_id: str = "",
) -> Dict[str, Any]:
    """通过 WebSocket 发送消息"""
    try:
        success = await self.ws_client.send_message(
            target_id=target_id,
            content=content,
            image_url=image_url,
            cid=conversation_id,
        )
        return {"success": success, "message": "消息已发送" if success else "发送失败"}
    except Exception as e:
        return {"success": False, "message": str(e)}

def ws_is_connected(self) -> bool:
    """检查 WebSocket 连接状态"""
    return self.ws_client.is_connected()

def ws_on_message(self, handler):
    """注册消息处理器"""
    self.ws_client.on_message(handler)
```

- [ ] **Step 4: 提交 client.py 修改**

```bash
git add src/api/client.py
git commit -m "feat: 集成 WebSocket 客户端到 XianyuApiClient"
```

---

### Task 4: 添加 MCP 工具

**Files:**
- Modify: `mcp_server/http_server.py`

- [ ] **Step 1: 在 http_server.py 添加 MCP 工具**

在 `xianyu_get_detail` 工具后添加：

```python


@mcp.tool()
async def xianyu_start_listener(user_id: str | None = None) -> str:
    """启动 WebSocket 消息监听"""
    client = get_client()
    result = await client.start_ws_listener()
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
async def xianyu_stop_listener(user_id: str | None = None) -> str:
    """停止 WebSocket 消息监听"""
    client = get_client()
    result = await client.stop_ws_listener()
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
async def xianyu_ws_send(
    user_id: str | None = None,
    target_id: str = "",
    content: str = "",
    image_url: str = "",
    conversation_id: str = "",
) -> str:
    """通过 WebSocket 发送消息
    
    Args:
        target_id: 目标用户 ID（卖家或买家）
        content: 文本消息内容
        image_url: 图片 URL（可选）
        conversation_id: 对话 ID（可选）
    """
    client = get_client()
    if not target_id:
        return json.dumps({"success": False, "message": "需要提供 target_id"}, ensure_ascii=False)
    
    result = await client.ws_send_message(
        target_id=target_id,
        content=content,
        image_url=image_url,
        conversation_id=conversation_id,
    )
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
async def xianyu_ws_status(user_id: str | None = None) -> str:
    """检查 WebSocket 连接状态"""
    client = get_client()
    connected = client.ws_is_connected()
    return json.dumps({"connected": connected}, ensure_ascii=False)


@mcp.tool()
async def xianyu_get_access_token(user_id: str | None = None) -> str:
    """获取 WebSocket accessToken（调试用）"""
    client = get_client()
    try:
        token = await client.http_client.get_access_token()
        return json.dumps({"success": True, "access_token": token[:20] + "..." if token else ""}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "message": str(e)}, ensure_ascii=False)
```

- [ ] **Step 2: 提交 MCP 工具**

```bash
git add mcp_server/http_server.py
git commit -m "feat: 添加 WebSocket MCP 工具"
```

---

### Task 5: 测试验证

**Files:**
- 无新文件

- [ ] **Step 1: 重启服务**

```bash
screen -S mcp -X quit
cd /opt/dockercompose/xianyu/.worktrees/feature-refactor-api
screen -dmS mcp python3 -m mcp_server.http_server
sleep 3
```

- [ ] **Step 2: 测试获取 accessToken**

```bash
MCP_DEV_URL="http://localhost:8080/mcp" ./scripts/mcp-dev call xianyu_get_access_token
```

预期输出: `{"success": true, "access_token": "xxx..."}`

- [ ] **Step 3: 测试启动监听**

```bash
MCP_DEV_URL="http://localhost:8080/mcp" ./scripts/mcp-dev call xianyu_start_listener
```

预期输出: `{"success": true, "message": "监听已启动"}`

- [ ] **Step 4: 测试连接状态**

```bash
MCP_DEV_URL="http://localhost:8080/mcp" ./scripts/mcp-dev call xianyu_ws_status
```

预期输出: `{"connected": true}`

- [ ] **Step 5: 测试发送消息（需要目标用户 ID）**

```bash
MCP_DEV_URL="http://localhost:8080/mcp" ./scripts/mcp-dev call xianyu_ws_send --target_id 2812414526 --content "你好，请问商品还在吗？"
```

预期输出: `{"success": true, "message": "消息已发送"}`

- [ ] **Step 6: 测试停止监听**

```bash
MCP_DEV_URL="http://localhost:8080/mcp" ./scripts/mcp-dev call xianyu_stop_listener
```

预期输出: `{"success": true, "message": "监听已停止"}`

---

## 测试命令汇总

```bash
# 1. 获取 accessToken
MCP_DEV_URL="http://localhost:8080/mcp" ./scripts/mcp-dev call xianyu_get_access_token

# 2. 启动监听
MCP_DEV_URL="http://localhost:8080/mcp" ./scripts/mcp-dev call xianyu_start_listener

# 3. 检查状态
MCP_DEV_URL="http://localhost:8080/mcp" ./scripts/mcp-dev call xianyu_ws_status

# 4. 发送消息
MCP_DEV_URL="http://localhost:8080/mcp" ./scripts/mcp-dev call xianyu_ws_send --target_id <seller_id> --content "你好"

# 5. 停止监听
MCP_DEV_URL="http://localhost:8080/mcp" ./scripts/mcp-dev call xianyu_stop_listener
```

---

## 注意事项

1. WebSocket 连接需要有效的 accessToken，由 `mtop.taobao.idlemessage.pc.login.token` API 获取
2. 发送消息需要目标用户 ID（可通过 `xianyu_get_detail` 获取卖家 ID）
3. 消息接收通过注册处理器实现，目前仅打印日志
4. WebSocket 断开后会自动重连（3 秒延迟）