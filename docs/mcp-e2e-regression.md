# MCP 端到端测试规范

## 项目概述

闲鱼 MCP 服务，提供登录、搜索、发布等功能。

| 功能 | 实现方式 |
|------|----------|
| 登录 | 纯 HTTP API |
| 搜索 | HTTP MTOP API |
| 发布 | HTTP API + 浏览器降级 |

服务端口: `8080`

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

## 注意事项

1. **业务错误不算测试失败**: 如 `valid=false`（登录态过期）是正常业务结果
2. **冷启动慢**: 首次请求可能需要 3-10 秒，属于正常
3. **ASGI 错误**: 服务关闭时的 ASGI 错误不影响功能
