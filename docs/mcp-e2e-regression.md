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

### 通过条件

- 服务正常启动，无崩溃
- 接口返回有效 JSON（业务错误不算失败）
- 工具调用链路通畅

### 失败条件

- 服务启动报错或崩溃
- 接口返回 500 或无响应
- 工具调用报错且非业务原因

---

## 注意事项

1. **业务错误不算测试失败**: 如 `valid=false`（登录态过期）是正常业务结果
2. **冷启动慢**: 首次请求可能需要 3-10 秒，属于正常
3. **ASGI 错误**: 服务关闭时的 ASGI 错误不影响功能