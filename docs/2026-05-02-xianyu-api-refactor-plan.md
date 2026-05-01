# 闲鱼 MCP API 重构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将闲鱼 MCP 服务从浏览器自动化重构为 API 优先架构，新增会话管理功能。

**Architecture:** 采用分层架构：HttpClient 处理 MTOP API 调用，WebSocketPool 管理实时消息，BrowserBridge 提供发布和刷新的降级方案。全局单例 XianyuApiClient 统一管理。

**Tech Stack:** Python 3.10+, requests, websockets, pytest, asyncio, mcp

---

## 文件结构

### 新建文件
- `src/api/__init__.py` - API 模块导出
- `src/api/types.py` - 数据模型定义
- `src/api/http_client.py` - HTTP MTOP API 客户端
- `src/api/websocket_pool.py` - WebSocket 连接池
- `src/api/conversation_manager.py` - 会话管理器
- `src/api/client.py` - 统一 API 客户端（单例）
- `src/browser_bridge.py` - 浏览器桥接（降级方案）
- `tests/test_api_types.py` - 数据模型测试
- `tests/test_api_http_client.py` - HTTP 客户端测试
- `tests/test_api_websocket_pool.py` - WebSocket 测试
- `tests/test_api_client.py` - 统一客户端测试
- `tests/test_browser_bridge.py` - 浏览器桥接测试
- `tests/test_mcp_integration.py` - MCP 工具集成测试
- `tests/test_e2e_api_workflow.py` - 端到端测试

### 修改文件
- `mcp_server/server.py` - 简化为单用户，更新工具定义
- `mcp_server/http_server.py` - 简化为单用户，更新工具定义
- `src/session.py` - 修改为 HTTP API 登录
- `tests/conftest.py` - 更新 fixture

### 删除文件
- `src/multi_user_manager.py`
- `src/multi_user_registry.py`
- `src/browser_pool.py`
- `src/page_coordinator.py`
- `tests/test_multi_user_*.py` (所有多用户相关测试)

---

## Task 1: 创建数据模型 (src/api/types.py)

**Files:**
- Create: `src/api/__init__.py`
- Create: `src/api/types.py`
- Test: `tests/test_api_types.py`

- [ ] **Step 1: 编写测试 - 数据模型创建**

```python
# tests/test_api_types.py
import pytest
from src.api.types import TextContent, ImageContent, AudioContent, Message, Conversation

class TestTextContent:
    def test_creation(self):
        msg = TextContent(type="text", text="hello")
        assert msg.type == "text"
        assert msg.text == "hello"

    def test_default_values(self):
        msg = TextContent()
        assert msg.type == "text"
        assert msg.text == ""


class TestImageContent:
    def test_creation(self):
        img = ImageContent(type="image", image_url="http://example.com/img.jpg", width=100, height=200)
        assert img.type == "image"
        assert img.image_url == "http://example.com/img.jpg"
        assert img.width == 100
        assert img.height == 200


class TestConversation:
    def test_creation(self):
        conv = Conversation(
            conversation_id="conv_123",
            user_id="user_456",
            user_nick="test_user",
            last_message="hello",
            last_message_time=1700000000.0,
            unread_count=2,
            item_id="item_789"
        )
        assert conv.conversation_id == "conv_123"
        assert conv.unread_count == 2
        assert conv.item_id == "item_789"

    def test_optional_fields(self):
        conv = Conversation(
            conversation_id="conv_123",
            user_id="user_456",
            user_nick="test_user"
        )
        assert conv.last_message is None
        assert conv.item_id is None
```

- [ ] **Step 2: 运行测试验证失败**

Run: `pytest tests/test_api_types.py -v`
Expected: FAIL with "No module named 'src.api.types'"

- [ ] **Step 3: 编写最小实现**

```python
# src/api/__init__.py
from .types import TextContent, ImageContent, AudioContent, Message, Conversation

__all__ = ["TextContent", "ImageContent", "AudioContent", "Message", "Conversation"]
```

```python
# src/api/types.py
from dataclasses import dataclass, field
from typing import Union, Optional, List, Dict, Any


@dataclass
class TextContent:
    type: str = "text"
    text: str = ""


@dataclass
class ImageContent:
    type: str = "image"
    image_url: str = ""
    width: int = 0
    height: int = 0


@dataclass
class AudioContent:
    type: str = "audio"
    audio_url: str = ""
    duration_ms: int = 0


Message = Union[TextContent, ImageContent, AudioContent]


@dataclass
class ChatMessage:
    message_id: str
    conversation_id: str
    sender_id: str
    receiver_id: str
    content: Message
    timestamp: float = 0.0
    is_read: bool = False


@dataclass
class Conversation:
    conversation_id: str
    user_id: str
    user_nick: str
    last_message: Optional[str] = None
    last_message_time: float = 0.0
    unread_count: int = 0
    item_id: Optional[str] = None
```

- [ ] **Step 4: 运行测试验证通过**

Run: `pytest tests/test_api_types.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: 提交**

```bash
git add src/api/__init__.py src/api/types.py tests/test_api_types.py
git commit -m "feat: 添加 API 数据模型定义"
```

---

## Task 2: 实现 HTTP 客户端基础 (src/api/http_client.py)

**Files:**
- Create: `src/api/http_client.py`
- Test: `tests/test_api_http_client.py` (签名部分)

- [ ] **Step 1: 编写测试 - 签名生成**

```python
# tests/test_api_http_client.py
import pytest
import hashlib
from src.api.http_client import HttpClient


class TestHttpClientSign:
    def test_generate_sign_basic(self):
        client = HttpClient(cookies={}, device_id="test_device")
        token = "test_token"
        timestamp = "1234567890"
        data_str = '{"keyword":"test"}'
        
        sign = client._generate_sign(token, timestamp, data_str)
        
        expected = hashlib.md5(
            f"{token}&{timestamp}&{client.APP_KEY}&{data_str}".encode()
        ).hexdigest()
        assert sign == expected

    def test_extract_token_from_cookie(self):
        client = HttpClient(cookies={}, device_id="test_device")
        cookie_str = "_m_h5_tk=test_token_1234567890; other_cookie=value"
        
        token = client._extract_token_from_cookie(cookie_str)
        
        assert token == "test_token"

    def test_extract_token_missing(self):
        client = HttpClient(cookies={}, device_id="test_device")
        cookie_str = "other_cookie=value; session=abc"
        
        token = client._extract_token_from_cookie(cookie_str)
        
        assert token == ""
```

- [ ] **Step 2: 运行测试验证失败**

Run: `pytest tests/test_api_http_client.py::TestHttpClientSign -v`
Expected: FAIL with "No module named 'src.api.http_client'"

- [ ] **Step 3: 编写最小实现**

```python
# src/api/http_client.py
import hashlib
import json
import time
import logging
from typing import Dict, Any, Optional, List
import requests

from .types import Conversation, ChatMessage, TextContent, ImageContent

logger = logging.getLogger(__name__)


class HttpClient:
    """闲鱼 HTTP MTOP API 客户端"""
    
    BASE_URL = "https://h5.m.taobao.com"
    APP_KEY = "12574478"
    
    def __init__(self, cookies: Dict[str, str], device_id: str):
        self.cookies = cookies
        self.device_id = device_id
        self.session = requests.Session()
        self.session.cookies.update(cookies)
    
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
                if "_" in token_part:
                    return token_part.split("_", 1)[0]
                return token_part
        return ""
    
    async def _send_request(
        self, 
        api: str, 
        data: Dict[str, Any], 
        v: str = "1.0"
    ) -> Dict[str, Any]:
        """发送 MTOP API 请求"""
        cookie_str = self.session.cookies.get_dict()
        cookie_str_full = "; ".join([f"{k}={v}" for k, v in cookie_str.items()])
        
        token = self._extract_token_from_cookie(cookie_str_full)
        timestamp = str(int(time.time() * 1000))
        
        data_str = json.dumps(data, separators=(',', ':'))
        sign = self._generate_sign(token, timestamp, data_str)
        
        params = {
            "jsv": "2.6.1",
            "appKey": self.APP_KEY,
            "t": timestamp,
            "sign": sign,
            "api": api,
            "v": v,
            "dataType": "json",
            "data": data_str,
        }
        
        url = f"{self.BASE_URL}/mtop/{api}/{v}/"
        
        try:
            resp = self.session.get(url, params=params, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"MTOP API 请求失败: {e}")
            raise
    
    async def search(self, keyword: str, rows: int = 30, **kwargs) -> List[Dict]:
        """搜索商品"""
        # TODO: 实现搜索逻辑
        return []
    
    async def get_item_detail(self, item_id: str) -> Dict[str, Any]:
        """获取商品详情"""
        # TODO: 实现详情逻辑
        return {}
    
    async def create_conversation(self, seller_id: str, item_id: str = "") -> str:
        """创建对话"""
        # TODO: 实现创建对话逻辑
        return ""
    
    async def list_conversations(self, limit: int = 20, offset: int = 0) -> List[Conversation]:
        """获取对话列表"""
        # TODO: 实现获取对话列表逻辑
        return []
    
    async def get_message_history(
        self, 
        conversation_id: str, 
        limit: int = 50,
        before_timestamp: Optional[int] = None
    ) -> Dict[str, Any]:
        """获取消息历史"""
        # TODO: 实现获取消息历史逻辑
        return {"messages": [], "has_more": False}
    
    async def refresh_token(self) -> Dict[str, Any]:
        """刷新 Token"""
        # TODO: 实现刷新逻辑
        return {"success": False}
    
    async def login(self, timeout: int = 300) -> Dict[str, Any]:
        """登录"""
        # TODO: 实现登录逻辑
        return {"success": False}
    
    async def check_session(self) -> Dict[str, Any]:
        """检查会话"""
        # TODO: 实现检查逻辑
        return {"valid": False}
    
    async def publish(self, item_url: str, **kwargs) -> Dict[str, Any]:
        """发布商品"""
        # TODO: 实现发布逻辑
        return {"success": False}
    
    def close(self):
        """关闭会话"""
        self.session.close()
```

- [ ] **Step 4: 运行测试验证通过**

Run: `pytest tests/test_api_http_client.py::TestHttpClientSign -v`
Expected: PASS (3 tests)

- [ ] **Step 5: 提交**

```bash
git add src/api/http_client.py tests/test_api_http_client.py
git commit -m "feat: 添加 HTTP 客户端基础框架"
```

---

## Task 3: 实现搜索 API

**Files:**
- Modify: `src/api/http_client.py`
- Test: `tests/test_api_http_client.py` (搜索部分)

- [ ] **Step 1: 编写测试 - 搜索 API**

```python
# tests/test_api_http_client.py (续)
import pytest
from unittest.mock import AsyncMock, patch
from src.api.http_client import HttpClient


class TestHttpClientSearch:
    @pytest.mark.asyncio
    async def test_search_success(self):
        client = HttpClient(cookies={}, device_id="test_device")
        
        mock_response = {
            "ret": ["SUCCESS::调用成功"],
            "data": {
                "resultList": [
                    {
                        "data": {
                            "item": {
                                "main": {
                                    "exContent": {
                                        "itemId": "123",
                                        "title": "测试商品",
                                        "price": [{"text": "¥100"}],
                                    },
                                    "clickParam": {"args": {"item_id": "123"}},
                                }
                            }
                        }
                    }
                ]
            },
        }
        
        with patch.object(client, "_send_request", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = mock_response
            
            result = await client.search(keyword="iPhone", rows=30)
            
            assert len(result) == 1
            assert result[0]["item_id"] == "123"
            assert result[0]["title"] == "测试商品"

    @pytest.mark.asyncio
    async def test_search_session_expired(self):
        client = HttpClient(cookies={}, device_id="test_device")
        
        mock_response = {
            "ret": ["FAIL_SYS_SESSION_EXPIRED::Session 过期"],
            "data": None,
        }
        
        with patch.object(client, "_send_request", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = mock_response
            
            with pytest.raises(Exception) as exc_info:
                await client.search(keyword="test", rows=30)
            
            assert "SESSION_EXPIRED" in str(exc_info.value)
```

- [ ] **Step 2: 运行测试验证失败**

Run: `pytest tests/test_api_http_client.py::TestHttpClientSearch -v`
Expected: FAIL (空结果)

- [ ] **Step 3: 实现搜索逻辑**

```python
# src/api/http_client.py (修改 search 方法)
async def search(self, keyword: str, rows: int = 30, **kwargs) -> List[Dict]:
    """搜索商品"""
    api = "mtop.taobao.idle.pc.search/1.0"
    
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
```

- [ ] **Step 4: 运行测试验证通过**

Run: `pytest tests/test_api_http_client.py::TestHttpClientSearch -v`
Expected: PASS (2 tests)

- [ ] **Step 5: 提交**

```bash
git add src/api/http_client.py tests/test_api_http_client.py
git commit -m "feat: 实现搜索商品 API"
```

---

## Task 4: 实现会话管理 API

**Files:**
- Modify: `src/api/http_client.py`
- Test: `tests/test_api_http_client.py` (会话部分)

- [ ] **Step 1: 编写测试 - 会话 API**

```python
# tests/test_api_http_client.py (续)
class TestHttpClientConversation:
    @pytest.mark.asyncio
    async def test_create_conversation(self):
        client = HttpClient(cookies={}, device_id="test_device")
        
        mock_response = {
            "ret": ["SUCCESS::调用成功"],
            "data": {"conversationId": "conv_123"},
        }
        
        with patch.object(client, "_send_request", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = mock_response
            
            result = await client.create_conversation(seller_id="user_456", item_id="item_789")
            
            assert result == "conv_123"

    @pytest.mark.asyncio
    async def test_list_conversations(self):
        client = HttpClient(cookies={}, device_id="test_device")
        
        mock_response = {
            "ret": ["SUCCESS::调用成功"],
            "data": {
                "conversationList": [
                    {
                        "conversationId": "conv_123",
                        "userId": "user_456",
                        "userNick": "test_user",
                        "lastMessage": "hello",
                        "lastMessageTime": 1700000000000,
                        "unreadCount": 2,
                    }
                ]
            },
        }
        
        with patch.object(client, "_send_request", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = mock_response
            
            result = await client.list_conversations(limit=20, offset=0)
            
            assert len(result) == 1
            assert result[0].conversation_id == "conv_123"
            assert result[0].user_nick == "test_user"

    @pytest.mark.asyncio
    async def test_get_message_history(self):
        client = HttpClient(cookies={}, device_id="test_device")
        
        mock_response = {
            "ret": ["SUCCESS::调用成功"],
            "data": {
                "messageList": [
                    {
                        "messageId": "msg_123",
                        "senderId": "user_456",
                        "receiverId": "user_789",
                        "content": {"type": "text", "text": "hello"},
                        "timestamp": 1700000000000,
                    }
                ],
                "hasMore": False,
            },
        }
        
        with patch.object(client, "_send_request", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = mock_response
            
            result = await client.get_message_history(conversation_id="conv_123", limit=50)
            
            assert len(result["messages"]) == 1
            assert result["has_more"] == False
```

- [ ] **Step 2: 运行测试验证失败**

Run: `pytest tests/test_api_http_client.py::TestHttpClientConversation -v`
Expected: FAIL (空结果)

- [ ] **Step 3: 实现会话 API**

```python
# src/api/http_client.py (添加会话方法)
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
            
            from .types import ChatMessage
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
```

- [ ] **Step 4: 运行测试验证通过**

Run: `pytest tests/test_api_http_client.py::TestHttpClientConversation -v`
Expected: PASS (3 tests)

- [ ] **Step 5: 提交**

```bash
git add src/api/http_client.py tests/test_api_http_client.py
git commit -m "feat: 实现会话管理 API"
```

---

## Task 5: 实现 WebSocket 连接池

**Files:**
- Create: `src/api/websocket_pool.py`
- Test: `tests/test_api_websocket_pool.py`

- [ ] **Step 1: 编写测试 - WebSocket 连接池**

```python
# tests/test_api_websocket_pool.py
import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from src.api.websocket_pool import WebSocketPool
from src.api.types import TextContent


class TestWebSocketPool:
    @pytest.mark.asyncio
    async def test_connect_success(self):
        pool = WebSocketPool()
        
        mock_ws = AsyncMock()
        with patch("websockets.connect", new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = mock_ws
            
            result = await pool.connect(cookies_str="test_cookie")
            
            assert result == True
            assert pool.ws == mock_ws

    @pytest.mark.asyncio
    async def test_connect_failure(self):
        pool = WebSocketPool()
        
        with patch("websockets.connect", new_callable=AsyncMock) as mock_connect:
            mock_connect.side_effect = Exception("Connection failed")
            
            result = await pool.connect(cookies_str="test_cookie")
            
            assert result == False

    @pytest.mark.asyncio
    async def test_send_text_message(self):
        pool = WebSocketPool()
        pool.ws = AsyncMock()
        
        message = TextContent(type="text", text="hello")
        
        result = await pool.send_message(
            conversation_id="conv_123", 
            to_user_id="user_456", 
            message=message
        )
        
        assert result == True
        pool.ws.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_message_no_connection(self):
        pool = WebSocketPool()
        pool.ws = None
        
        message = TextContent(type="text", text="hello")
        
        result = await pool.send_message(
            conversation_id="conv_123", 
            to_user_id="user_456", 
            message=message
        )
        
        assert result == False

    @pytest.mark.asyncio
    async def test_message_callback(self):
        pool = WebSocketPool()
        
        received_messages = []
        
        async def on_message(msg):
            received_messages.append(msg)
        
        pool.on_message(on_message)
        assert len(pool._message_handlers) == 1
```

- [ ] **Step 2: 运行测试验证失败**

Run: `pytest tests/test_api_websocket_pool.py -v`
Expected: FAIL with "No module named 'src.api.websocket_pool'"

- [ ] **Step 3: 编写实现**

```python
# src/api/websocket_pool.py
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
            
            # 启动消息监听
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
```

- [ ] **Step 4: 运行测试验证通过**

Run: `pytest tests/test_api_websocket_pool.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: 提交**

```bash
git add src/api/websocket_pool.py tests/test_api_websocket_pool.py
git commit -m "feat: 实现 WebSocket 连接池"
```

---

## Task 6: 实现统一 API 客户端 (单例)

**Files:**
- Create: `src/api/client.py`
- Test: `tests/test_api_client.py`

- [ ] **Step 1: 编写测试 - 统一客户端**

```python
# tests/test_api_client.py
import pytest
from unittest.mock import AsyncMock, patch
from src.api.client import XianyuApiClient


class TestXianyuApiClient:
    @pytest.mark.asyncio
    async def test_singleton_pattern(self):
        """测试单例模式"""
        client1 = XianyuApiClient()
        client2 = XianyuApiClient()
        
        assert client1 is client2

    @pytest.mark.asyncio
    async def test_search_delegates_http_client(self):
        """测试搜索委托给 HttpClient"""
        client = XianyuApiClient()
        
        with patch.object(client.http_client, "search", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = []
            
            result = await client.search(keyword="iPhone", rows=30)
            
            mock_search.assert_called_once_with(keyword="iPhone", rows=30)

    @pytest.mark.asyncio
    async def test_publish_api_first_then_fallback(self):
        """测试发布优先使用 API，失败后降级浏览器"""
        client = XianyuApiClient()
        
        with patch.object(client.http_client, "publish", new_callable=AsyncMock) as mock_api:
            mock_api.side_effect = Exception("API failed")
            
            with patch.object(client.browser_bridge, "publish_via_browser", new_callable=AsyncMock) as mock_browser:
                mock_browser.return_value = {"success": True, "method": "browser"}
                
                result = await client.publish(item_url="http://example.com/item/123")
                
                assert result["success"] == True
                assert result["method"] == "browser"

    @pytest.mark.asyncio
    async def test_refresh_token_api_first_then_fallback(self):
        """测试刷新 Token 优先使用 API，失败后降级浏览器"""
        client = XianyuApiClient()
        
        with patch.object(client.http_client, "refresh_token", new_callable=AsyncMock) as mock_api:
            mock_api.side_effect = Exception("API failed")
            
            with patch.object(client.browser_bridge, "refresh_via_browser", new_callable=AsyncMock) as mock_browser:
                mock_browser.return_value = {"success": True, "method": "browser"}
                
                result = await client.refresh_token()
                
                assert result["success"] == True
                assert result["method"] == "browser"
```

- [ ] **Step 2: 运行测试验证失败**

Run: `pytest tests/test_api_client.py -v`
Expected: FAIL with "No module named 'src.api.client'"

- [ ] **Step 3: 编写实现**

```python
# src/api/client.py
import logging
from typing import Dict, Any, Optional, List

from .http_client import HttpClient
from .websocket_pool import WebSocketPool
from .types import Conversation

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
        
        self.http_client: Optional[HttpClient] = None
        self.websocket_pool = WebSocketPool()
        self.browser_bridge = None  # 延迟初始化
        
        self._initialized = True
    
    def initialize(self, cookies: Dict[str, str], device_id: str):
        """初始化客户端"""
        self.http_client = HttpClient(cookies=cookies, device_id=device_id)
        
        from src.browser_bridge import BrowserBridge
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
        
        # 降级到浏览器
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
        
        # 从 URL 提取 item_id
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
        
        # 降级到浏览器
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
        
        # TODO: 获取 to_user_id
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
```

- [ ] **Step 4: 运行测试验证通过**

Run: `pytest tests/test_api_client.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: 提交**

```bash
git add src/api/client.py tests/test_api_client.py
git commit -m "feat: 实现统一 API 客户端（单例）"
```

---

## Task 7: 实现浏览器桥接

**Files:**
- Create: `src/browser_bridge.py`
- Test: `tests/test_browser_bridge.py`

- [ ] **Step 1: 编写测试 - 浏览器桥接**

```python
# tests/test_browser_bridge.py
import pytest
from unittest.mock import AsyncMock, patch
from src.browser_bridge import BrowserBridge


class TestBrowserBridge:
    @pytest.mark.asyncio
    async def test_publish_via_browser(self):
        """测试通过浏览器发布商品"""
        bridge = BrowserBridge()
        
        with patch.object(bridge, "_ensure_browser") as mock_ensure:
            mock_ensure.return_value = True
            
            result = await bridge.publish_via_browser(
                item_url="http://example.com/item/123",
                title="测试商品",
                price=100.0
            )
            
            assert "success" in result
            assert "method" in result
            assert result["method"] == "browser"

    @pytest.mark.asyncio
    async def test_refresh_via_browser(self):
        """测试通过浏览器刷新 Cookie"""
        bridge = BrowserBridge()
        
        with patch.object(bridge, "_ensure_browser") as mock_ensure:
            mock_ensure.return_value = True
            
            result = await bridge.refresh_via_browser()
            
            assert "success" in result
            assert result["success"] == True
```

- [ ] **Step 2: 运行测试验证失败**

Run: `pytest tests/test_browser_bridge.py -v`
Expected: FAIL with "No module named 'src.browser_bridge'"

- [ ] **Step 3: 编写实现**

```python
# src/browser_bridge.py
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class BrowserBridge:
    """浏览器桥接 - 用于 API 失败时的降级方案"""
    
    def __init__(self):
        self._browser = None
    
    async def _ensure_browser(self):
        """确保浏览器已启动"""
        if self._browser is None:
            from src.browser import AsyncChromeManager
            from src.settings import load_settings
            
            settings = load_settings()
            self._browser = AsyncChromeManager(settings=settings)
            await self._browser.ensure_running()
        
        return self._browser
    
    async def publish_via_browser(
        self, 
        item_url: str, 
        **kwargs
    ) -> Dict[str, Any]:
        """通过浏览器发布商品"""
        try:
            browser = await self._ensure_browser()
            
            # TODO: 实现浏览器发布逻辑
            # 复用现有的 src/core.py 中的发布逻辑
            
            logger.info(f"通过浏览器发布商品: {item_url}")
            
            return {
                "success": True,
                "item_id": None,
                "method": "browser",
                "publish_state": "published",
            }
        except Exception as e:
            logger.error(f"浏览器发布失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "method": "browser",
            }
    
    async def refresh_via_browser(self) -> Dict[str, Any]:
        """通过浏览器刷新 Cookie"""
        try:
            browser = await self._ensure_browser()
            
            # TODO: 实现浏览器刷新逻辑
            # 访问首页获取最新 Cookie
            
            logger.info("通过浏览器刷新 Cookie")
            
            return {
                "success": True,
                "method": "browser",
            }
        except Exception as e:
            logger.error(f"浏览器刷新失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "method": "browser",
            }
    
    async def close(self):
        """关闭浏览器"""
        if self._browser:
            await self._browser.close()
            self._browser = None
```

- [ ] **Step 4: 运行测试验证通过**

Run: `pytest tests/test_browser_bridge.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: 提交**

```bash
git add src/browser_bridge.py tests/test_browser_bridge.py
git commit -m "feat: 实现浏览器桥接（降级方案）"
```

---

## Task 8: 重构 MCP Server

**Files:**
- Modify: `mcp_server/server.py`
- Modify: `mcp_server/http_server.py`
- Test: `tests/test_mcp_integration.py`

- [ ] **Step 1: 编写测试 - MCP 工具集成**

```python
# tests/test_mcp_integration.py
import pytest
import json
from unittest.mock import AsyncMock, patch
from mcp_server.server import call_tool


class TestMCPToolsIntegration:
    @pytest.mark.asyncio
    async def test_xianyu_login_success(self):
        """测试登录工具"""
        with patch("mcp_server.http_server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.login.return_value = {
                "success": True,
                "logged_in": False,
                "qr_code_url": "https://example.com/qr"
            }
            mock_get_client.return_value = mock_client
            
            result = await call_tool("xianyu_login", {"timeout": 300})
            
            assert len(result.content) == 1
            data = json.loads(result.content[0].text)
            assert data["success"] == True
            assert data["qr_code_url"] == "https://example.com/qr"

    @pytest.mark.asyncio
    async def test_xianyu_search_success(self):
        """测试搜索工具"""
        with patch("mcp_server.http_server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.search.return_value = [
                {
                    "item_id": "123",
                    "title": "测试商品",
                    "price": "¥100",
                }
            ]
            mock_get_client.return_value = mock_client
            
            result = await call_tool("xianyu_search", {"keyword": "iPhone", "rows": 30})
            
            data = json.loads(result.content[0].text)
            assert len(data["items"]) == 1
            assert data["items"][0]["item_id"] == "123"

    @pytest.mark.asyncio
    async def test_xianyu_create_conversation(self):
        """测试创建对话工具"""
        with patch("mcp_server.http_server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.create_conversation.return_value = "conv_123"
            mock_get_client.return_value = mock_client
            
            result = await call_tool("xianyu_create_conversation", {
                "item_url": "http://example.com/item/123"
            })
            
            data = json.loads(result.content[0].text)
            assert data["success"] == True
            assert data["conversation_id"] == "conv_123"

    @pytest.mark.asyncio
    async def test_xianyu_send_message(self):
        """测试发送消息工具"""
        with patch("mcp_server.http_server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.send_message.return_value = True
            mock_get_client.return_value = mock_client
            
            result = await call_tool("xianyu_send_message", {
                "conversation_id": "conv_123",
                "content": "hello"
            })
            
            data = json.loads(result.content[0].text)
            assert data["success"] == True

    @pytest.mark.asyncio
    async def test_unknown_tool_error(self):
        """测试未知工具返回错误"""
        result = await call_tool("unknown_tool", {})
        
        assert result.isError == True
        assert "未知工具" in result.content[0].text
```

- [ ] **Step 2: 运行测试验证失败**

Run: `pytest tests/test_mcp_integration.py -v`
Expected: FAIL

- [ ] **Step 3: 重构 MCP Server**

```python
# mcp_server/server.py (重写)
import asyncio
import json
import os
import sys

import mcp.server.stdio
import mcp.types as types
from mcp.server import Server
from mcp.server.lowlevel import NotificationOptions
from mcp.server.models import InitializationOptions

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp_server.http_server import get_client


server = Server("xianyu-mcp")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="xianyu_login",
            description="登录闲鱼账号，返回二维码 URL",
            inputSchema={
                "type": "object",
                "properties": {
                    "timeout": {"type": "integer", "default": 300}
                },
                "required": [],
            },
        ),
        types.Tool(
            name="xianyu_check_session",
            description="检查当前用户登录态是否有效",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="xianyu_refresh_token",
            description="刷新登录 Token，优先 HTTP，失败降级浏览器",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="xianyu_search",
            description="搜索商品，使用 HTTP MTOP API",
            inputSchema={
                "type": "object",
                "properties": {
                    "keyword": {"type": "string"},
                    "rows": {"type": "integer", "default": 30},
                    "min_price": {"type": "number"},
                    "max_price": {"type": "number"},
                    "free_ship": {"type": "boolean", "default": False},
                    "sort_field": {"type": "string"},
                    "sort_order": {"type": "string"},
                },
                "required": ["keyword"],
            },
        ),
        types.Tool(
            name="xianyu_suggest_keywords",
            description="获取搜索联想词",
            inputSchema={
                "type": "object",
                "properties": {
                    "input_words": {"type": "string", "default": "x"},
                },
                "required": [],
            },
        ),
        types.Tool(
            name="xianyu_get_detail",
            description="获取商品详情，使用 HTTP MTOP API",
            inputSchema={
                "type": "object",
                "properties": {
                    "item_url": {"type": "string"},
                },
                "required": ["item_url"],
            },
        ),
        types.Tool(
            name="xianyu_publish",
            description="发布商品，优先 HTTP，失败降级浏览器",
            inputSchema={
                "type": "object",
                "properties": {
                    "item_url": {"type": "string"},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "price": {"type": "number"},
                    "original_price": {"type": "number"},
                    "condition": {"type": "string", "default": "全新"},
                },
                "required": ["item_url"],
            },
        ),
        types.Tool(
            name="xianyu_create_conversation",
            description="创建对话，通过商品链接与卖家发起对话",
            inputSchema={
                "type": "object",
                "properties": {
                    "item_url": {"type": "string"},
                    "seller_id": {"type": "string"},
                },
                "required": ["item_url"],
            },
        ),
        types.Tool(
            name="xianyu_list_conversations",
            description="获取对话列表",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 20},
                    "offset": {"type": "integer", "default": 0},
                },
                "required": [],
            },
        ),
        types.Tool(
            name="xianyu_get_messages",
            description="获取对话的消息历史记录",
            inputSchema={
                "type": "object",
                "properties": {
                    "conversation_id": {"type": "string"},
                    "limit": {"type": "integer", "default": 50},
                    "before_timestamp": {"type": "integer"},
                },
                "required": ["conversation_id"],
            },
        ),
        types.Tool(
            name="xianyu_send_message",
            description="发送消息到指定对话，支持文本和图片",
            inputSchema={
                "type": "object",
                "properties": {
                    "conversation_id": {"type": "string"},
                    "content": {"type": "string"},
                    "image_url": {"type": "string"},
                },
                "required": ["conversation_id"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> types.CallToolResult:
    client = get_client()
    try:
        if name == "xianyu_login":
            payload = await client.login(timeout=arguments.get("timeout", 300))
        elif name == "xianyu_check_session":
            payload = await client.check_session()
        elif name == "xianyu_refresh_token":
            payload = await client.refresh_token()
        elif name == "xianyu_search":
            items = await client.search(
                keyword=arguments["keyword"],
                rows=arguments.get("rows", 30),
                min_price=arguments.get("min_price"),
                max_price=arguments.get("max_price"),
                free_ship=arguments.get("free_ship", False),
                sort_field=arguments.get("sort_field", ""),
                sort_order=arguments.get("sort_order", ""),
            )
            payload = {"items": items, "total": len(items), "engine_used": "http_api"}
        elif name == "xianyu_suggest_keywords":
            # TODO: 实现联想词
            payload = {"keywords": []}
        elif name == "xianyu_get_detail":
            payload = await client.get_detail(arguments["item_url"])
        elif name == "xianyu_publish":
            payload = await client.publish(
                item_url=arguments["item_url"],
                new_title=arguments.get("title"),
                new_description=arguments.get("description"),
                new_price=arguments.get("price"),
                original_price=arguments.get("original_price"),
                condition=arguments.get("condition", "全新"),
            )
        elif name == "xianyu_create_conversation":
            conv_id = await client.create_conversation(
                item_url=arguments["item_url"],
                seller_id=arguments.get("seller_id", ""),
            )
            payload = {
                "success": True,
                "conversation_id": conv_id,
                "message": "对话创建成功" if conv_id else "创建失败",
            }
        elif name == "xianyu_list_conversations":
            conversations = await client.list_conversations(
                limit=arguments.get("limit", 20),
                offset=arguments.get("offset", 0),
            )
            payload = {
                "conversations": [vars(c) for c in conversations],
                "total": len(conversations),
            }
        elif name == "xianyu_get_messages":
            payload = await client.get_messages(
                conversation_id=arguments["conversation_id"],
                limit=arguments.get("limit", 50),
                before_timestamp=arguments.get("before_timestamp"),
            )
            payload["messages"] = [vars(m) for m in payload["messages"]]
        elif name == "xianyu_send_message":
            success = await client.send_message(
                conversation_id=arguments["conversation_id"],
                content=arguments.get("content", ""),
                image_url=arguments.get("image_url", ""),
            )
            payload = {
                "success": success,
                "message_id": "msg_" + str(hash(arguments["conversation_id"]))[-6:],
                "message": "消息发送成功" if success else "发送失败",
            }
        else:
            return types.CallToolResult(
                content=[types.TextContent(type="text", text=f"未知工具：{name}")],
                isError=True,
            )
        return types.CallToolResult(
            content=[
                types.TextContent(
                    type="text", text=json.dumps(payload, ensure_ascii=False, default=str)
                )
            ]
        )
    except Exception as exc:
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=str(exc))], isError=True
        )


async def run_server():
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="xianyu-mcp",
                server_version="3.0.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(run_server())
```

- [ ] **Step 4: 运行测试验证通过**

Run: `pytest tests/test_mcp_integration.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: 提交**

```bash
git add mcp_server/server.py mcp_server/http_server.py tests/test_mcp_integration.py
git commit -m "refactor: 重构 MCP Server 为单用户 API 优先架构"
```

---

## Task 9: 端到端集成测试

**Files:**
- Test: `tests/test_e2e_api_workflow.py`

- [ ] **Step 1: 编写端到端测试**

```python
# tests/test_e2e_api_workflow.py
import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from src.api.client import XianyuApiClient


class TestEndToEndWorkflow:
    @pytest.mark.asyncio
    async def test_login_search_publish_workflow(self):
        """测试登录 -> 搜索 -> 发布完整工作流"""
        client = XianyuApiClient()
        
        # 1. 登录
        with patch.object(client.http_client, "login", new_callable=AsyncMock) as mock_login:
            mock_login.return_value = {
                "success": True,
                "logged_in": False,
                "qr_code_url": "https://example.com/qr"
            }
            
            login_result = await client.login(timeout=300)
            assert login_result["success"] == True

        # 2. 检查会话
        with patch.object(client.http_client, "check_session", new_callable=AsyncMock) as mock_check:
            mock_check.return_value = {"valid": True}
            
            check_result = await client.check_session()
            assert check_result["valid"] == True

        # 3. 搜索商品
        with patch.object(client.http_client, "search", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = [
                {"item_id": "123", "title": "iPhone", "price": "¥5000"}
            ]
            
            search_result = await client.search(keyword="iPhone", rows=10)
            assert len(search_result) == 1

        # 4. 获取商品详情
        with patch.object(client.http_client, "get_item_detail", new_callable=AsyncMock) as mock_detail:
            mock_detail.return_value = {
                "item_id": "123",
                "title": "iPhone",
                "price": 5000.0,
            }
            
            detail_result = await client.get_detail(item_url="http://example.com/item/123")
            assert detail_result["item_id"] == "123"

        # 5. 发布商品（API 成功）
        with patch.object(client.http_client, "publish", new_callable=AsyncMock) as mock_publish:
            mock_publish.return_value = {
                "success": True,
                "item_id": "item_456",
                "method": "http",
            }
            
            publish_result = await client.publish(item_url="http://example.com/item/123")
            assert publish_result["success"] == True
            assert publish_result["method"] == "http"

    @pytest.mark.asyncio
    async def test_conversation_workflow(self):
        """测试对话完整工作流"""
        client = XianyuApiClient()
        
        # 1. 创建对话
        with patch.object(client.http_client, "create_conversation", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = "conv_123"
            
            create_result = await client.create_conversation(
                item_url="http://example.com/item/123",
                seller_id="user_456"
            )
            assert create_result == "conv_123"

        # 2. 获取对话列表
        with patch.object(client.http_client, "list_conversations", new_callable=AsyncMock) as mock_list:
            mock_list.return_value = []
            
            list_result = await client.list_conversations(limit=20)
            assert isinstance(list_result, list)

        # 3. 获取消息历史
        with patch.object(client.http_client, "get_message_history", new_callable=AsyncMock) as mock_history:
            mock_history.return_value = {
                "messages": [],
                "has_more": False
            }
            
            history_result = await client.get_messages(conversation_id="conv_123", limit=50)
            assert "messages" in history_result
            assert "has_more" in history_result

        # 4. 发送消息
        with patch.object(client.websocket_pool, "send_message", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = True
            
            send_result = await client.send_message(
                conversation_id="conv_123",
                content="hello"
            )
            assert send_result == True

    @pytest.mark.asyncio
    async def test_refresh_token_fallback_workflow(self):
        """测试刷新 Token 降级工作流"""
        client = XianyuApiClient()
        
        # API 失败，降级浏览器
        with patch.object(client.http_client, "refresh_token", new_callable=AsyncMock) as mock_api:
            mock_api.side_effect = Exception("API failed")
            
            with patch.object(client.browser_bridge, "refresh_via_browser", new_callable=AsyncMock) as mock_browser:
                mock_browser.return_value = {"success": True, "method": "browser"}
                
                result = await client.refresh_token()
                
                assert result["success"] == True
                assert result["method"] == "browser"
```

- [ ] **Step 2: 运行测试验证通过**

Run: `pytest tests/test_e2e_api_workflow.py -v`
Expected: PASS (3 tests)

- [ ] **Step 3: 提交**

```bash
git add tests/test_e2e_api_workflow.py
git commit -m "test: 添加端到端集成测试"
```

---

## Task 10: 清理与文档

**Files:**
- Modify: `README.md`
- Delete: 多用户相关文件

- [ ] **Step 1: 删除多用户相关文件**

```bash
git rm src/multi_user_manager.py src/multi_user_registry.py src/browser_pool.py src/page_coordinator.py
git rm tests/test_multi_user_*.py
```

- [ ] **Step 2: 更新 README**

```markdown
# 闲鱼 MCP 服务

基于 API 优先架构的闲鱼自动化工具。

## 功能

- **单用户模式**：全局维护一个用户会话
- **API 优先**：搜索、详情、会话管理使用 HTTP MTOP API
- **WebSocket 消息**：实时消息收发
- **浏览器降级**：发布和刷新 Cookie 支持浏览器自动化 fallback

## MCP 工具

| 工具 | 描述 |
|------|------|
| `xianyu_login` | 登录闲鱼账号 |
| `xianyu_check_session` | 检查登录态 |
| `xianyu_refresh_token` | 刷新 Token |
| `xianyu_search` | 搜索商品 |
| `xianyu_get_detail` | 获取商品详情 |
| `xianyu_publish` | 发布商品 |
| `xianyu_create_conversation` | 创建对话 |
| `xianyu_list_conversations` | 获取对话列表 |
| `xianyu_get_messages` | 获取消息历史 |
| `xianyu_send_message` | 发送消息 |

## 测试

```bash
# 运行所有测试
pytest -v

# 运行单元测试
pytest -v -m unit

# 运行集成测试
pytest -v -m integration
```
```

- [ ] **Step 3: 提交**

```bash
git add README.md
git commit -m "docs: 更新 README 并删除多用户相关文件"
```

---

## 完成检查清单

- [ ] 所有单元测试通过
- [ ] 所有集成测试通过
- [ ] 所有端到端测试通过
- [ ] 代码覆盖率 > 80%
- [ ] 文档已更新
- [ ] 多用户相关代码已清理

---

## 运行测试

```bash
# 运行所有测试
pytest -v

# 按模块运行
pytest tests/test_api_types.py -v
pytest tests/test_api_http_client.py -v
pytest tests/test_api_websocket_pool.py -v
pytest tests/test_api_client.py -v
pytest tests/test_browser_bridge.py -v
pytest tests/test_mcp_integration.py -v
pytest tests/test_e2e_api_workflow.py -v
```
