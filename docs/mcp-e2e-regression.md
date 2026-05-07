# MCP 端到端测试规范

## 项目概述

闲鱼 MCP 服务，提供登录、搜索、发布等功能。

| 功能 | 实现方式 |
|------|----------|
| 登录 | 纯 HTTP API |
| 搜索 | HTTP MTOP API |
| 发布 | HTTP API |

服务默认端口: `8080`

如果实例临时运行在其他端口，例如 `18090`，所有示例命令都应通过 `MCP_DEV_URL` 或实际 REST 地址显式覆盖；不要把临时端口当成默认配置。

---

## 强制原则

端到端测试必须验证真实运行链路：**启动服务，再通过 MCP API 或 REST API 调用功能**。

禁止把临时 Python 脚本直接调用 `HttpClient`、`WebSocketClient` 等底层类的结果，作为端到端测试通过依据。这类脚本只能作为定位问题的辅助 smoke test，不能替代服务级验证。

每次声称端到端能力可用前，必须至少完成以下验证：

- 启动 `mcp_server.http_server` 或目标 MCP 服务进程。
- 通过服务暴露的 MCP API 或 REST API 调用登录、会话检查、搜索、WebSocket/对话等目标能力。
- 记录请求命令、响应摘要和退出状态。
- 若服务/API 调用失败，先定位服务层、路由层、参数 schema、环境变量、持久化路径等真实链路问题，再考虑底层类调试。

底层类直接调用只能回答“底层接口是否可能工作”，不能回答“MCP 服务是否可用”。端到端结论必须来自服务进程和 MCP/REST API 调用结果。
### MCP 验证客户端

以后验证 MCP 工具统一使用 `./scripts/mcp-dev`。该脚本会优先请求 `/mcp`，如果服务只暴露 SSE，则自动回退到 `/sse` + `/messages/?session_id=...` 的标准 MCP 初始化与 `tools/call` 流程。

标准命令：

```bash
./scripts/mcp-dev call xianyu_check_session
./scripts/mcp-dev call xianyu_search --keyword 手机壳 --rows 3
./scripts/mcp-dev call xianyu_ws_status
./scripts/mcp-dev call xianyu_list_conversations --limit 5
```


---

## 测试流程示例（登录）

### 1. 启动服务

```bash
python3 -m mcp_server.http_server
```

### 2. 获取二维码

```bash
curl -X POST http://localhost:8080/rest/login
```

**验证点**:
- 返回 `success: true`
- 包含 `qr_code.public_url`（图片链接）

### 3. 轮询状态（可选）

```bash
curl -X POST http://localhost:8080/rest/login_poll \
  -H "Content-Type: application/json" \
  -d '{"t": "<从步骤2获取>", "ck": "<从步骤2获取>"}'
```

---

## 测试判定标准

### 必须验证

| 项目 | 方法 |
|------|------|
| 服务启动 | 无报错，进程存活 |
| REST 接口 | 返回 JSON，`success: true/false` 有意义 |
| MCP 工具 | 返回结构化结果，无 500 错误 |
| 真实链路 | 通过服务进程暴露的 MCP API 或 REST API 调用，不能用底层类脚本替代 |

### 通过条件

- 服务正常启动，无崩溃
- 接口返回有效 JSON（业务错误不算失败）
- 工具调用链路通畅
- 登录、会话、搜索、WebSocket/对话等目标能力经过 MCP API 或 REST API 验证

### 失败条件

- 服务启动报错或崩溃
- 接口返回 500 或无响应
- 工具调用报错且非业务原因
- 只通过临时 Python 脚本直接调用底层类验证，未启动服务或未调用 MCP/REST API

---

## MCP 工具端到端测试案例

以下案例均使用 `./scripts/mcp-dev` 脚本进行验证。执行前请确保已启动 `mcp_server.http_server`。

### 1. xianyu_login (登录)
```bash
./scripts/mcp-dev call xianyu_login
```
**验证点**:
- 返回 `success: true`
- 若已登录：`logged_in: true`
- 若未登录：`logged_in: false` 且包含 `qr_code.public_url`

### 2. xianyu_check_session (检查会话)
```bash
./scripts/mcp-dev call xianyu_check_session
```
**验证点**:
- 返回 `valid: true` 表示登录态有效
- 返回 `valid: false` 表示登录态过期（业务正常结果）

### 3. xianyu_refresh_token (刷新 Token)
```bash
./scripts/mcp-dev call xianyu_refresh_token
```
**验证点**:
- 返回 `success: true`
- 包含 `message` 和 `method` (通常为 "http")

### 4. xianyu_search (搜索商品)
```bash
./scripts/mcp-dev call xianyu_search --keyword 手机壳 --rows 3
```
**验证点**:
- 返回商品列表数组（JSON 数组格式）
- 包含 `item_id`, `title`, `price`, `detail_url` 等字段

### 5. xianyu_suggest_keywords (搜索联想词)
```bash
./scripts/mcp-dev call xianyu_suggest_keywords --input-words 手机
```
**验证点**:
- 返回关键词数组
- 数组元素为字符串

### 6. xianyu_publish (发布商品)
```bash
# 使用本地图片发布
./scripts/mcp-dev call xianyu_publish --images-paths "/tmp/test.png" --title "测试商品" --current-price 10.0
# 或使用网络图片发布 (需网络连通)
# ./scripts/mcp-dev call xianyu_publish --images-paths "https://example.com/test.png" --title "测试商品" --current-price 10.0
```
**验证点**:
- 返回 `success: true`
- 包含 `item_id` 和 `item_url`
- **注意**: 此命令会真实发布商品到闲鱼，请谨慎使用。

### 7. xianyu_get_detail (获取商品详情)
```bash
./scripts/mcp-dev call xianyu_get_detail --item-url "https://www.goofish.com/item?id=1047155930582"
```
**验证点**:
- 返回完整的商品详情 JSON
- 包含 `itemDO`, `sellerDO` 等字段

### 7.1 xianyu_publish_from_item_url (按商品链接铺货)
```bash
./scripts/mcp-dev call xianyu_publish_from_item_url --item-url "https://www.goofish.com/item?id=1047155930582"
```
**验证点**:
- 返回 `success: true/false`
- 成功时包含 `source_platform`, `source_item_url`, `published_item_id`, `published_item_url`
- 失败时包含 `failed_step`, `message`, `logs`
- `logs` 至少覆盖 `select_source_adapter`, `parse_item`, `publish_item`
- **注意**: 此命令会走真实铺货链路，请谨慎使用。

### 8. xianyu_ws_send (发送消息)
```bash
./scripts/mcp-dev call xianyu_ws_send --target-id 60971615689 --conversation-id 60971615689 --content 你好
```
**验证点**:
- 返回 `success: true`
- 返回 `message: 消息已发送`
- `target_id` 和 `conversation_id` 保持字符串类型（脚本已修复纯数字转 int 问题）

### 9. xianyu_ws_status (WebSocket 状态)
```bash
./scripts/mcp-dev call xianyu_ws_status
```
**验证点**:
- 返回 `connected: true/false`
- 返回 `status: connected/starting/disconnected/failed`
- 返回 `started_at` 时间戳

### 10. xianyu_list_conversations (获取对话列表)
```bash
./scripts/mcp-dev call xianyu_list_conversations --limit 10
```
**验证点**:
- 返回 `success: true`
- 返回 `source: websocket` 或 `source: cache`
- 返回 `conversations` 数组，包含 `conversation_id`, `user_nick`, `last_message` 等

### 11. xianyu_get_messages (获取消息历史)
```bash
./scripts/mcp-dev call xianyu_get_messages --conversation-id 60971615689 --limit 5
```
**验证点**:
- 返回 `success: true`
- 返回 `source: websocket` 或 `source: cache`
- 返回 `messages` 数组，包含 `message_id`, `sender_name`, `content`, `timestamp` 等

---

## 注意事项

1. **业务错误不算测试失败**: 如 `valid=false`（登录态过期）是正常业务结果
2. **冷启动慢**: 首次请求可能需要 3-10 秒，属于正常
3. **ASGI 错误**: 服务关闭时的 ASGI 错误不影响功能

---

## 2026-05-05 真实联调记录

本次真实联调通过 MCP 服务链路完成，覆盖了两类运行方式：

- 临时实例监听在 `18090`，命令显式带 `MCP_DEV_URL`
- 默认实例监听在 `8080`，直接使用 `scripts/mcp-dev`

这不改变默认端口仍为 `8080` 的事实。

### 12 个 MCP 方法回归结果（默认 `8080` 实例）

| 方法 | 结果 | 摘要 |
|------|------|------|
| `xianyu_login` | 成功 | `logged_in: true` |
| `xianyu_check_session` | 成功 | `valid: true` |
| `xianyu_refresh_token` | 成功 | `success: true`, `method: http` |
| `xianyu_search` | 成功 | 返回 3 条真实商品 |
| `xianyu_suggest_keywords` | 成功 | 返回联想词数组 |
| `xianyu_publish` | 成功 | 真实发布成功，见下文 |
| `xianyu_get_detail` | 成功 | 返回真实商品详情 |
| `xianyu_publish_from_item_url` | 未回归 | 新增按链接铺货工具，待补真实链路验证 |
| `xianyu_ws_send` | 成功 | 真实发送成功，见下文 |
| `xianyu_ws_status` | 成功 | `connected: true` |
| `xianyu_list_conversations` | 成功 | `source: websocket` |
| `xianyu_get_messages` | 成功 | `source: websocket`，返回真实消息历史 |

### 默认 `8080` 实例的真实消息发送

```bash
python3 scripts/mcp-dev call xianyu_ws_send --target-id 60971615689 --conversation-id 60971615689 --content "8080端口MCP真实回归测试，请忽略"
```

返回：

```json
{
  "success": true,
  "message": "消息已发送"
}
```

### 默认 `8080` 实例的真实商品发布

```bash
python3 scripts/mcp-dev call xianyu_publish --images-paths "/opt/dockercompose/xianyu/.worktrees/feature-refactor-api/docs/xianyu-logo_001.jpg" --title "8080端口MCP发布回归测试请忽略" --current-price 1
```

返回：

```json
{
  "success": true,
  "item_id": "1050061932866",
  "item_url": "https://www.goofish.com/item?id=1050061932866",
  "message": "发布成功",
  "method": "http"
}
```

### 默认 `8080` 实例的按商品链接铺货

```bash
python3 scripts/mcp-dev call xianyu_publish_from_item_url --item-url "https://www.goofish.com/item?id=1047155930582"
```

预期返回结构：

```json
{
  "success": true,
  "source_platform": "xianyu",
  "source_item_url": "https://www.goofish.com/item?id=1047155930582",
  "published_item_id": "<new-item-id>",
  "published_item_url": "https://www.goofish.com/item?id=<new-item-id>",
  "selected_price": 88.0,
  "logs": [
    {
      "step": "select_source_adapter",
      "status": "success"
    },
    {
      "step": "parse_item",
      "status": "success"
    },
    {
      "step": "publish_item",
      "status": "success"
    }
  ]
}
```

说明：

- 当前首版仅支持闲鱼商品链接。
- 若任一步失败，会返回 `failed_step` 和完整 `logs`，用于排查。
- 若源商品存在规格价格，系统会取最低规格价作为发布价。

### 默认 `8080` 实例的 WebSocket 修复验证

本次修复针对滑块验证误判和拖动不稳定问题，关键改动包括：

- `SliderSolver` 不再把“验证码容器消失”直接当成功
- `CaptchaHandler` 在滑块成功后会刷新页面并复验是否仍存在滑块
- `SliderSolver` 复用已检测到的验证码 frame，减少 iframe/上下文抖动
- 拖动逻辑从 `hover + sleep` 改为显式 `mouse.move/down/up` 轨迹

验证命令：

```bash
python3 scripts/mcp-dev call xianyu_ws_status
```

返回：

```json
{
  "connected": true,
  "status": "connected",
  "last_error": null,
  "started_at": "2026-05-05T16:46:54"
}
```

### 默认 `8080` 实例的 HTTP keepalive 保活行为

当前 MCP 主服务链路已接入独立的 HTTP keepalive 任务，不再依赖旧的浏览器页面 `goto/reload` 保活方案。

保活规则：

- 默认每 `4` 小时执行一次 HTTP 续活（`240` 分钟）
- 可通过配置覆盖间隔
- HTTP 续活若触发风控，则自动走浏览器滑块恢复
- 单次保活周期内，滑块恢复最多重试 `3` 次
- `3` 次全部失败后，停止该 keepalive 任务

聚焦验证命令：

```bash
pytest tests/test_http_keepalive.py tests/test_api_client.py tests/test_http_server_unit.py tests/test_settings.py -q
python3 scripts/mcp-dev call xianyu_check_session
python3 scripts/mcp-dev call xianyu_ws_status
```

验证结果：

- `82 passed`
- MCP 服务仍能正常启动
- session 校验正常
- WebSocket 连接正常

### 真实消息发送

```bash
MCP_DEV_URL="http://127.0.0.1:18090/mcp" python3 scripts/mcp-dev call xianyu_ws_send --target-id 60971615689 --conversation-id 60971615689 --content "MCP真实联调测试，请忽略"
```

返回：

```json
{
  "success": true,
  "message": "消息已发送"
}
```

### 真实商品发布

```bash
MCP_DEV_URL="http://127.0.0.1:18090/mcp" python3 scripts/mcp-dev call xianyu_publish --images-paths "/opt/dockercompose/xianyu/.worktrees/feature-refactor-api/docs/xianyu-logo_001.jpg" --title "MCP发布联调测试商品请忽略" --current-price 1
```

返回：

```json
{
  "success": true,
  "item_id": "1047453179489",
  "item_url": "https://www.goofish.com/item?id=1047453179489",
  "message": "发布成功",
  "method": "http"
}
```

### 按商品链接铺货

```bash
MCP_DEV_URL="http://127.0.0.1:18090/mcp" python3 scripts/mcp-dev call xianyu_publish_from_item_url --item-url "https://www.goofish.com/item?id=1047155930582"
```

预期行为：

- 返回结构与默认 `8080` 实例一致
- 成功时返回新发布商品 ID 和 URL
- 失败时返回 `failed_step` 与步骤日志
