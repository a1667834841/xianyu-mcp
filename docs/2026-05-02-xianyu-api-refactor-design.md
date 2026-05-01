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
