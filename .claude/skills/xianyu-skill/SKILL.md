---
name: xianyu-skill
description: Use when managing one or more Xianyu accounts via MCP, especially when you need to create or inspect users, verify login state, search products, copy-publish listings, or troubleshoot session issues.
---

# 闲鱼 MCP 工具参考

## 架构

单用户模式，所有业务走 HTTP MTOP API 或 WebSocket RPC，浏览器仅用于滑块/风控。接口失败直接返回错误，不做隐式浏览器降级。

## 所有工具

调用方式：通过 MCP Streamable HTTP 接口调用，curl 直接 POST JSON-RPC 到 `/mcp`。

**前置步骤**（首次调用前需建立会话）：
```bash
# 1. initialize 建立会话
curl -s -X POST http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","clientInfo":{"name":"curl","version":"1.0"},"capabilities":{}}}'

# 2. notifications/initialized 确认初始化完成
curl -s -X POST http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}'
```

之后共用同一 curl 格式调用各工具：

```bash
curl -s -X POST http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "<工具名>",
      "arguments": { <参数> }
    }
  }'
```

### `xianyu_login`
HTTP 扫码登录。返回 `logged_in: true` 或 `logged_in: false` + `qr_code.public_url`。**只把 `public_url` 发给用户扫码**，不传 `qr_code.url`。
```bash
curl -s -X POST http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"xianyu_login","arguments":{}}}'
```

### `xianyu_check_session`
检查登录态。返回 `valid: true/false`。无参数。
```bash
curl -s -X POST http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"xianyu_check_session","arguments":{}}}'
```

### `xianyu_refresh_token`
刷新 Token，纯 HTTP。返回 `method: "http"`。无参数。
```bash
curl -s -X POST http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"xianyu_refresh_token","arguments":{}}}'
```

### `xianyu_search`
关键词搜索商品。参数：`keyword`(必填)、`rows`(默认30)、`min_price`/`max_price`、`free_ship`、`sort_field`(仅`pub_time`/`price`)、`sort_order`。不支持按曝光度排序，需二次处理 `exposure_score`。`rows>30` 自动翻页，结果去重。
```bash
curl -s -X POST http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"xianyu_search","arguments":{"keyword":"手机壳","rows":10}}}'
```

### `xianyu_suggest_keywords`
搜索联想词。参数：`input_words`(默认`"x"`)。返回字符串数组。
```bash
curl -s -X POST http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"xianyu_suggest_keywords","arguments":{"input_words":"手机"}}}'
```

### `xianyu_get_detail`
商品详情。参数：`item_url`。返回完整 `itemDO`/`sellerDO`。
```bash
curl -s -X POST http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"xianyu_get_detail","arguments":{"item_url":"https://www.goofish.com/item?id=1047155930582"}}}'
```

### `xianyu_publish`
HTTP 发布商品，**无浏览器降级，无 `item_url` 参数**。必填：`images_paths`(逗号分隔)、`title`。可选：`current_price`、`original_price`、`shipping`(默认包邮)、`self_pickup`、`post_price`。返回 `method: "http"`。
```bash
curl -s -X POST http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"xianyu_publish","arguments":{"images_paths":"/path/to/img1.jpg,/path/to/img2.jpg","title":"商品标题","current_price":100}}}'
```

### `xianyu_create_conversation`
创建对话，WebSocket RPC。参数：`item_url`。自动检测是否自己商品（返回 `CANNOT_CREATE_CONVERSATION_WITH_SELF`），创建后自动发送问候语。
```bash
curl -s -X POST http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"xianyu_create_conversation","arguments":{"item_url":"https://www.goofish.com/item?id=1047155930582"}}}'
```

### `xianyu_ws_send`
发送消息。必填：`target_id`。可选：`content`、`image_url`、`conversation_id`。
```bash
curl -s -X POST http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"xianyu_ws_send","arguments":{"target_id":"660749856","content":"你好","conversation_id":"61066151753"}}}'
```

### `xianyu_ws_status`
WebSocket 连接状态。返回 `connected`/`status`/`last_error`/`started_at`。
```bash
curl -s -X POST http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"xianyu_ws_status","arguments":{}}}'
```

### `xianyu_get_access_token`
获取 WebSocket token，纯 HTTP。返回 `access_token_masked`。
```bash
curl -s -X POST http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"xianyu_get_access_token","arguments":{}}}'
```

### `xianyu_list_conversations`
对话列表，优先 WS RPC，失败回退缓存。参数：`limit`(默认20)。返回 `source: "websocket"` 或 `"cache"`。
```bash
curl -s -X POST http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"xianyu_list_conversations","arguments":{"limit":10}}}'
```

### `xianyu_get_messages`
消息历史，优先 WS RPC，失败回退缓存。必填：`conversation_id`(从`xianyu_list_conversations`获取)。可选：`limit`(默认50)。
```bash
curl -s -X POST http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"xianyu_get_messages","arguments":{"conversation_id":"61066151753","limit":5}}}'
```

**自定义端口：** 将 URL 中的 `8080` 替换为实际端口，如 `http://localhost:18091/mcp`。

## 常见错误

| 错误 | 正确做法 |
|---|---|
| `publish` 传 `item_url` | 用 `images_paths` + `title` |
| 以为搜索可排序曝光度 | 搜索后按 `exposure_score` 本地排序 |
| `create_conversation` 对自己商品 | 系统自动返回 `CANNOT_CREATE_CONVERSATION_WITH_SELF` |
| `qr_code.public_url` 为空仍发码 | 告知用户不可展示，引导重试 |
| `publish` 成功=已上架 | 特殊类目可能为草稿 |

## 典型流程

**搜索并联系卖家：** `search` → `get_detail` → `create_conversation` → `ws_send`

**登录：** `login`(发`public_url`给用户扫码) → `check_session`

**发布：** `check_session` → `publish(images_paths, title, current_price)`
