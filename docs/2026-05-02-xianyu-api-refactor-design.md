# 闲鱼 MCP 服务 API 重构设计文档

- **日期**: 2026-05-02
- **状态**: Draft
- **作者**: AI Assistant

## 1. 概述

本项目旨在将现有的闲鱼 MCP 服务从基于 Playwright 浏览器自动化的架构，重构为以 **HTTP MTOP API** 和 **WebSocket** 为核心的架构。

**核心变更：**
1.  **单用户模式**：移除多用户管理（MultiUserManager），改为全局单例模式。
2.  **API 优先**：所有功能（搜索、详情、登录、会话）默认使用 HTTP API 或 WebSocket 实现。
3.  **浏览器降级**：仅 `publish`（发布）和 `refresh_token`（刷新 Cookie）在 API 失败时，降级使用 Playwright 浏览器自动化。
4.  **新增会话功能**：增加创建对话、获取对话列表、获取消息历史和发送消息的能力。
5.  **移除调试工具**：移除 `xianyu_browser_overview` 和 `xianyu_debug_snapshot`。

## 2. 架构设计

### 2.1 目录结构
```
src/
├── api/                          # 新增：统一 API 层
│   ├── __init__.py
│   ├── client.py                # XianyuApiClient：统一入口，管理单例
│   ├── http_client.py           # HttpClient：MTOP API 调用、签名生成
│   ├── websocket_pool.py        # WebSocketPool：连接管理、消息收发
│   ├── conversation_manager.py  # ConversationManager：会话逻辑封装
│   └── types.py                 # 数据类型定义（Message, Conversation 等）
├── browser_bridge.py            # 浏览器桥接：仅用于发布和刷新 Cookie 的 fallback
├── session.py                   # 会话管理：Cookie 存储、Token 刷新逻辑
├── settings.py                  # 配置管理
└── mcp_server/
    ├── server.py                # STDIO MCP Server
    └── http_server.py           # HTTP/SSE MCP Server
```

### 2.2 架构图
```
┌───────────────────────────────────────────────────┐
│              MCP Server (11 个工具)                │
├───────────────────────────────────────────────────┤
│           XianyuApiClient (单例全局入口)            │
│                                                   │
│   ┌────────────────┐   ┌────────────────────────┐ │
│   │   HttpClient   │   │   WebSocketPool        │ │
│   │ (MTOP API 优先) │   │ (连接池 + 实时消息)     │ │
│   └───────┬────────┘   └────────────────────────┘ │
│           │ (API 失败)                             │
│           ▼                                       │
│   ┌───────────────────────────────────────────┐   │
│   │        BrowserBridge (浏览器兜底)           │   │
│   │   (仅用于: 发布商品、刷新 Cookie)           │   │
│   └───────────────────────────────────────────┘   │
├───────────────────────────────────────────────────┤
│           SessionManager (登录态管理)               │
└───────────────────────────────────────────────────┘
```

## 3. 核心逻辑

### 3.1 API-First + Fallback 机制
针对 `publish` 和 `refresh_token`，实现统一的降级策略：

```python
# 伪代码示例
async def publish(self, ...):
    try:
        # 1. 优先尝试 HTTP API
        result = await self.http_client.publish_api(...)
        if result.success:
            return result
    except Exception as e:
        logger.warning(f"API 发布失败，降级到浏览器: {e}")
    
    # 2. 降级到浏览器自动化
    return await self.browser_bridge.publish_via_browser(...)
```

### 3.2 会话管理
*   **创建对话**：调用 `mtop.idle.trade.conversation.create` API。
*   **获取对话列表**：调用 `mtop.taobao.idle.message.conversation.list` API。
*   **获取消息历史**：调用 `mtop.taobao.idle.message.record.get` API。
*   **发送消息**：通过 `WebSocketPool` 实时发送。

### 3.3 WebSocket 连接池
*   单用户维护一个长连接。
*   支持断线自动重连。
*   支持消息回调注册。

## 4. MCP 工具定义

### 4.1 工具总览

| 工具名称 | 状态 | 实现方式 | 描述 |
|---------|------|---------|------|
| `xianyu_login` | 重构 | HTTP API | 扫码登录 |
| `xianyu_check_session` | 重构 | HTTP API | 检查登录态 |
| `xianyu_refresh_token` | 重构 | HTTP API + 浏览器 fallback | 刷新 Token |
| `xianyu_search` | 重构 | HTTP MTOP API | 搜索商品 |
| `xianyu_suggest_keywords` | 重构 | HTTP API | 搜索联想词 |
| `xianyu_get_detail` | 重构 | HTTP MTOP API | 获取商品详情 |
| `xianyu_publish` | 重构 | HTTP API + 浏览器 fallback | 发布商品 |
| `xianyu_create_conversation` | **新增** | HTTP API | 创建对话 |
| `xianyu_list_conversations` | **新增** | HTTP API | 获取对话列表 |
| `xianyu_get_messages` | **新增** | HTTP API | 获取消息历史 |
| `xianyu_send_message` | **新增** | WebSocket | 发送消息 |

### 4.2 详细定义

#### 1. `xianyu_login`
*   **描述**: 登录闲鱼账号，返回二维码 URL。
*   **参数**: `timeout` (int, optional)
*   **返回**: `success`, `logged_in`, `qr_code_url`, `message`

#### 2. `xianyu_check_session`
*   **描述**: 检查当前用户登录态是否有效。
*   **参数**: 无
*   **返回**: `valid`, `last_updated_at`

#### 3. `xianyu_refresh_token`
*   **描述**: 刷新登录 Token，优先 HTTP，失败降级浏览器。
*   **参数**: 无
*   **返回**: `success`, `method`, `message`

#### 4. `xianyu_search`
*   **描述**: 搜索商品，使用 HTTP MTOP API。
*   **参数**: `keyword` (str), `rows` (int), `min_price`, `max_price`, `free_ship` (bool), `sort_field`, `sort_order`
*   **返回**: `items` (array), `total`, `engine_used`

#### 5. `xianyu_suggest_keywords`
*   **描述**: 获取搜索联想词。
*   **参数**: `input_words` (str)
*   **返回**: `keywords` (array)

#### 6. `xianyu_get_detail`
*   **描述**: 获取商品详情，使用 HTTP MTOP API。
*   **参数**: `item_url` (str)
*   **返回**: `item_id`, `title`, `description`, `price`, `images`, `seller`

#### 7. `xianyu_publish`
*   **描述**: 发布商品，优先 HTTP，失败降级浏览器。
*   **参数**: `item_url` (str), `title`, `description`, `price`, `original_price`, `condition`
*   **返回**: `success`, `item_id`, `method`, `publish_state`

#### 8. `xianyu_create_conversation` (新增)
*   **描述**: 创建对话，通过商品链接与卖家发起对话。
*   **参数**: `item_url` (str), `seller_id` (str, optional)
*   **返回**: `success`, `conversation_id`, `message`

#### 9. `xianyu_list_conversations` (新增)
*   **描述**: 获取对话列表。
*   **参数**: `limit` (int), `offset` (int)
*   **返回**: `conversations` (array), `total`

#### 10. `xianyu_get_messages` (新增)
*   **描述**: 获取对话的消息历史记录。
*   **参数**: `conversation_id` (str), `limit` (int), `before_timestamp` (int)
*   **返回**: `messages` (array), `has_more` (bool)

#### 11. `xianyu_send_message` (新增)
*   **描述**: 发送消息到指定对话，支持文本和图片。
*   **参数**: `conversation_id` (str), `content` (str, optional), `image_url` (str, optional)
*   **返回**: `success`, `message_id`, `message`

## 5. 数据模型

### 5.1 Message
```python
@dataclass
class Message:
    message_id: str
    conversation_id: str
    sender_id: str
    receiver_id: str
    content: Union[TextContent, ImageContent]
    timestamp: float
```

### 5.2 Conversation
```python
@dataclass
class Conversation:
    conversation_id: str
    user_id: str
    user_nick: str
    last_message: Optional[str]
    last_message_time: float
    unread_count: int
    item_id: Optional[str]
```

## 6. 错误处理与降级策略

1.  **HTTP 错误**: 捕获 `requests.HTTPError`，根据状态码判断是否重试或降级。
2.  **签名错误**: 若 MTOP API 返回签名错误（如 `403` 或特定错误码），自动触发 `refresh_token` 或降级浏览器。
3.  **WebSocket 断开**: 自动重连，重连期间消息暂存队列。

## 7. 测试策略

### 7.1 单元测试

#### 7.1.1 `src/api/types.py` 测试
**文件**: `tests/test_api_types.py`

```python
import pytest
from src.api.types import TextContent, ImageContent, Message, Conversation

class TestMessageTypes:
    def test_text_content_creation(self):
        msg = TextContent(type="text", text="hello")
        assert msg.type == "text"
        assert msg.text == "hello"

    def test_image_content_creation(self):
        img = ImageContent(type="image", image_url="http://example.com/img.jpg", width=100, height=200)
        assert img.type == "image"
        assert img.width == 100
        assert img.height == 200

    def test_conversation_creation(self):
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
```

#### 7.1.2 `src/api/http_client.py` 测试
**文件**: `tests/test_api_http_client.py`

```python
import pytest
import hashlib
from unittest.mock import AsyncMock, patch, MagicMock
from src.api.http_client import HttpClient

class TestHttpClientSign:
    """测试签名生成"""

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


class TestHttpClientSearch:
    """测试搜索 API"""

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
            assert result[0].item_id == "123"
            assert result[0].title == "测试商品"

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

    @pytest.mark.asyncio
    async def test_search_network_error(self):
        client = HttpClient(cookies={}, device_id="test_device")
        
        with patch.object(client, "_send_request", new_callable=AsyncMock) as mock_send:
            mock_send.side_effect = Exception("Network error")
            
            with pytest.raises(Exception) as exc_info:
                await client.search(keyword="test", rows=30)
            
            assert "Network error" in str(exc_info.value)


class TestHttpClientDetail:
    """测试商品详情 API"""

    @pytest.mark.asyncio
    async def test_get_item_detail_success(self):
        client = HttpClient(cookies={}, device_id="test_device")
        
        mock_response = {
            "ret": ["SUCCESS::调用成功"],
            "data": {
                "itemDO": {
                    "itemId": "123456",
                    "title": "测试商品",
                    "desc": "商品描述",
                    "minPrice": 10000,
                    "maxPrice": 20000,
                    "imageInfos": [{"url": "http://example.com/img.jpg"}],
                }
            },
        }
        
        with patch.object(client, "_send_request", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = mock_response
            
            result = await client.get_item_detail(item_id="123456")
            
            assert result.item_id == "123456"
            assert result.title == "测试商品"
            assert result.min_price == 100.0


class TestHttpClientConversation:
    """测试会话 API"""

    @pytest.mark.asyncio
    async def test_create_conversation(self):
        client = HttpClient(cookies={}, device_id="test_device")
        
        mock_response = {
            "ret": ["SUCCESS::调用成功"],
            "data": {
                "conversationId": "conv_123",
            },
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
            assert result["messages"][0].message_id == "msg_123"
            assert result["has_more"] == False
```

#### 7.1.3 `src/api/websocket_pool.py` 测试
**文件**: `tests/test_api_websocket_pool.py`

```python
import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from src.api.websocket_pool import WebSocketPool
from src.api.types import TextContent

class TestWebSocketPool:
    """测试 WebSocket 连接池"""

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
        
        result = await pool.send_message(conversation_id="conv_123", to_user_id="user_456", message=message)
        
        assert result == True
        pool.ws.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_message_no_connection(self):
        pool = WebSocketPool()
        pool.ws = None
        
        message = TextContent(type="text", text="hello")
        
        result = await pool.send_message(conversation_id="conv_123", to_user_id="user_456", message=message)
        
        assert result == False

    @pytest.mark.asyncio
    async def test_message_callback(self):
        pool = WebSocketPool()
        
        received_messages = []
        
        async def on_message(msg):
            received_messages.append(msg)
        
        pool.on_message(on_message)
        assert len(pool._message_handlers) == 1

    @pytest.mark.asyncio
    async def test_auto_reconnect(self):
        pool = WebSocketPool()
        
        mock_ws = AsyncMock()
        with patch("websockets.connect", new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = mock_ws
            
            await pool.connect(cookies_str="test_cookie")
            
            # 模拟连接断开
            mock_ws.__aenter__.side_effect = Exception("Connection closed")
            
            # 验证重连逻辑
            with patch.object(pool, "_should_reconnect", return_value=True):
                await pool._reconnect()
                assert mock_connect.call_count == 2  # 初始连接 + 重连
```

#### 7.1.4 `src/api/client.py` 测试
**文件**: `tests/test_api_client.py`

```python
import pytest
from unittest.mock import AsyncMock, patch
from src.api.client import XianyuApiClient

class TestXianyuApiClient:
    """测试统一 API 客户端"""

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
        
        # API 失败
        with patch.object(client.http_client, "publish", new_callable=AsyncMock) as mock_api:
            mock_api.side_effect = Exception("API failed")
            
            # 浏览器成功
            with patch.object(client.browser_bridge, "publish_via_browser", new_callable=AsyncMock) as mock_browser:
                mock_browser.return_value = {"success": True, "method": "browser"}
                
                result = await client.publish(item_url="http://example.com/item/123")
                
                assert result["success"] == True
                assert result["method"] == "browser"

    @pytest.mark.asyncio
    async def test_refresh_token_api_first_then_fallback(self):
        """测试刷新 Token 优先使用 API，失败后降级浏览器"""
        client = XianyuApiClient()
        
        # API 失败
        with patch.object(client.http_client, "refresh_token", new_callable=AsyncMock) as mock_api:
            mock_api.side_effect = Exception("API failed")
            
            # 浏览器成功
            with patch.object(client.browser_bridge, "refresh_via_browser", new_callable=AsyncMock) as mock_browser:
                mock_browser.return_value = {"success": True, "method": "browser"}
                
                result = await client.refresh_token()
                
                assert result["success"] == True
                assert result["method"] == "browser"
```

#### 7.1.5 `src/browser_bridge.py` 测试
**文件**: `tests/test_browser_bridge.py`

```python
import pytest
from unittest.mock import AsyncMock, patch
from src.browser_bridge import BrowserBridge

class TestBrowserBridge:
    """测试浏览器桥接"""

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

### 7.2 集成测试

#### 7.2.1 MCP 工具集成测试
**文件**: `tests/test_mcp_integration.py`

```python
import pytest
import json
from unittest.mock import AsyncMock, patch
from mcp_server.server import call_tool

class TestMCPToolsIntegration:
    """测试 MCP 工具集成"""

    @pytest.mark.asyncio
    async def test_xianyu_login_success(self):
        """测试登录工具"""
        with patch("mcp_server.http_server.get_manager") as mock_manager:
            mock_mgr = AsyncMock()
            mock_mgr.login.return_value = {
                "success": True,
                "logged_in": False,
                "qr_code_url": "https://example.com/qr"
            }
            mock_manager.return_value = mock_mgr
            
            result = await call_tool("xianyu_login", {"timeout": 300})
            
            assert len(result.content) == 1
            data = json.loads(result.content[0].text)
            assert data["success"] == True
            assert data["qr_code_url"] == "https://example.com/qr"

    @pytest.mark.asyncio
    async def test_xianyu_search_success(self):
        """测试搜索工具"""
        with patch("mcp_server.http_server.get_manager") as mock_manager:
            mock_mgr = AsyncMock()
            mock_mgr.search.return_value = {
                "items": [
                    {
                        "item_id": "123",
                        "title": "测试商品",
                        "price": "¥100",
                    }
                ],
                "total": 1,
                "engine_used": "http_api"
            }
            mock_manager.return_value = mock_mgr
            
            result = await call_tool("xianyu_search", {"keyword": "iPhone", "rows": 30})
            
            data = json.loads(result.content[0].text)
            assert len(data["items"]) == 1
            assert data["items"][0]["item_id"] == "123"

    @pytest.mark.asyncio
    async def test_xianyu_create_conversation(self):
        """测试创建对话工具"""
        with patch("mcp_server.http_server.get_manager") as mock_manager:
            mock_mgr = AsyncMock()
            mock_mgr.create_conversation.return_value = {
                "success": True,
                "conversation_id": "conv_123",
                "message": "对话创建成功"
            }
            mock_manager.return_value = mock_mgr
            
            result = await call_tool("xianyu_create_conversation", {
                "item_url": "http://example.com/item/123"
            })
            
            data = json.loads(result.content[0].text)
            assert data["success"] == True
            assert data["conversation_id"] == "conv_123"

    @pytest.mark.asyncio
    async def test_xianyu_list_conversations(self):
        """测试获取对话列表工具"""
        with patch("mcp_server.http_server.get_manager") as mock_manager:
            mock_mgr = AsyncMock()
            mock_mgr.list_conversations.return_value = {
                "conversations": [
                    {
                        "conversation_id": "conv_123",
                        "user_nick": "test_user",
                        "unread_count": 2,
                    }
                ],
                "total": 1
            }
            mock_manager.return_value = mock_mgr
            
            result = await call_tool("xianyu_list_conversations", {"limit": 20})
            
            data = json.loads(result.content[0].text)
            assert len(data["conversations"]) == 1
            assert data["conversations"][0]["user_nick"] == "test_user"

    @pytest.mark.asyncio
    async def test_xianyu_send_message(self):
        """测试发送消息工具"""
        with patch("mcp_server.http_server.get_manager") as mock_manager:
            mock_mgr = AsyncMock()
            mock_mgr.send_message.return_value = {
                "success": True,
                "message_id": "msg_123",
                "message": "消息发送成功"
            }
            mock_manager.return_value = mock_mgr
            
            result = await call_tool("xianyu_send_message", {
                "conversation_id": "conv_123",
                "content": "hello"
            })
            
            data = json.loads(result.content[0].text)
            assert data["success"] == True
            assert data["message_id"] == "msg_123"

    @pytest.mark.asyncio
    async def test_xianyu_publish_api_fallback_to_browser(self):
        """测试发布工具 API 失败降级浏览器"""
        with patch("mcp_server.http_server.get_manager") as mock_manager:
            mock_mgr = AsyncMock()
            mock_mgr.publish.return_value = {
                "success": True,
                "item_id": "item_123",
                "method": "browser",
                "publish_state": "published"
            }
            mock_manager.return_value = mock_mgr
            
            result = await call_tool("xianyu_publish", {
                "item_url": "http://example.com/item/123",
                "title": "测试商品",
                "price": 100.0
            })
            
            data = json.loads(result.content[0].text)
            assert data["success"] == True
            assert data["method"] == "browser"

    @pytest.mark.asyncio
    async def test_unknown_tool_error(self):
        """测试未知工具返回错误"""
        result = await call_tool("unknown_tool", {})
        
        assert result.isError == True
        assert "未知工具" in result.content[0].text
```

#### 7.2.2 端到端集成测试
**文件**: `tests/test_e2e_api_workflow.py`

```python
import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from src.api.client import XianyuApiClient

class TestEndToEndWorkflow:
    """端到端工作流测试"""

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
            mock_list.return_value = [
                {"conversation_id": "conv_123", "user_nick": "test_user"}
            ]
            
            list_result = await client.list_conversations(limit=20)
            assert len(list_result) == 1

        # 3. 获取消息历史
        with patch.object(client.http_client, "get_message_history", new_callable=AsyncMock) as mock_history:
            mock_history.return_value = {
                "messages": [{"message_id": "msg_123", "content": {"type": "text", "text": "hello"}}],
                "has_more": False
            }
            
            history_result = await client.get_messages(conversation_id="conv_123", limit=50)
            assert len(history_result["messages"]) == 1

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

### 7.3 测试运行配置

**pytest.ini**:
```ini
[pytest]
testpaths = tests
asyncio_mode = auto
markers =
    unit: 单元测试
    integration: 集成测试
    e2e: 端到端测试
```

**运行命令**:
```bash
# 运行所有测试
pytest -v

# 仅运行单元测试
pytest -v -m unit

# 仅运行集成测试
pytest -v -m integration

# 运行端到端测试
pytest -v -m e2e

# 生成覆盖率报告
pytest --cov=src --cov-report=html
```

## 8. 实施计划

### 阶段 1：基础设施（1-2 天）
1.  创建 `src/api/` 目录和类型定义
2.  实现 `HttpClient` 基础框架（签名、请求发送）
3.  编写单元测试

### 阶段 2：核心功能（3-5 天）
1.  实现搜索、详情 API
2.  实现会话管理 API
3.  实现 WebSocket 连接池
4.  编写集成测试

### 阶段 3：降级与完善（6-7 天）
1.  实现 `BrowserBridge`
2.  实现 MCP 工具层
3.  端到端测试
4.  文档更新
