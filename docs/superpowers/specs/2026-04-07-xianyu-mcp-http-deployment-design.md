# 闲鱼 MCP Server HTTP/SSE 部署设计

日期: 2026-04-07
状态: 已批准

## 背景

当前闲鱼 MCP Server 使用 Stdio 模式（通过 stdin/stdout 与 Claude 通信），仅支持本地访问。需要改造为 HTTP/SSE 模式，支持 Docker 部署和远程访问。

## 目标

1. 支持 SSE (Server-Sent Events) 传输方式
2. 支持 Streamable HTTP 传输方式
3. Docker 化部署，便于远程访问
4. 保持现有业务逻辑不变

## 技术方案

### 传输方式选择

使用 MCP SDK 内置的 **FastMCP** 类，直接支持 SSE 和 HTTP：

- SSE 端点: `/sse` - 客户端连接入口
- 消息端点: `/messages/` - POST 消息处理
- HTTP 端点: `/mcp` - Streamable HTTP 入口

### 架构设计

```
┌─────────────────────────────────────────────────────────────────┐
│                        Docker Compose                            │
│  ┌─────────────────────┐     ┌─────────────────────────────────┐│
│  │   chrome-headless   │     │        mcp-server               ││
│  │   (端口 9222)       │────▶│  FastMCP (端口 8080)            ││
│  │   内网暴露          │     │  ├── /sse (SSE 入口)            ││
│  │                     │     │  ├── /messages/ (POST 消息)     ││
│  │                     │     │  └── /mcp (Streamable HTTP)     ││
│  │                     │     │  XianyuApp (业务逻辑)           ││
│  └─────────────────────┘     └─────────────────────────────────┘│
│                               └─────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
         │
         │ HTTP/SSE (无认证)
         ▼
┌─────────────────────────────────────────────────────────────────┐
│                      客户端（Claude Code 等）                     │
│  MCP 客户端配置:                                                 │
│  {                                                               │
│    "url": "http://server-ip:8080/sse",                           │
│    "transport": "sse"                                            │
│  }                                                               │
└─────────────────────────────────────────────────────────────────┘
```

### 关键配置

| 配置项 | 值 | 说明 |
|-------|-----|-----|
| 服务端口 | 8080 | 单端口模式 |
| SSE 路径 | `/sse` | SSE 连接入口 |
| 消息路径 | `/messages/` | POST 消息端点 |
| HTTP 路径 | `/mcp` | Streamable HTTP 端点 |
| 认证 | 无 | 内网信任 |
| Chrome 连接 | CDP over Docker Network | chrome-headless:9222 |

## 文件改动

### 新增文件

```
mcp_server/
├── http_server.py    # FastMCP HTTP/SSE 服务入口
```

### 保留文件

```
mcp_server/
├── server.py         # Stdio 模式（向后兼容）
src/                  # 业务逻辑（不变）
```

### 更新文件

```
docker/Dockerfile     # 修改启动命令
docker-compose.yml    # 添加健康检查
requirements.txt      # 确保依赖完整
```

## 核心实现

### http_server.py

```python
"""
闲鱼 MCP Server HTTP/SSE 入口
使用 FastMCP 实现 SSE 和 HTTP 传输
"""

import os
import sys
from mcp.server.fastmcp import FastMCP

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import XianyuApp
from src.browser import AsyncChromeManager

# 配置
CDP_HOST = os.environ.get("CDP_HOST", "chrome-headless")
CDP_PORT = int(os.environ.get("CDP_PORT", "9222"))
MCP_HOST = os.environ.get("MCP_HOST", "0.0.0.0")
MCP_PORT = int(os.environ.get("MCP_PORT", "8080"))

# 全局 XianyuApp 实例
_app: XianyuApp | None = None

def get_app() -> XianyuApp:
    global _app
    if _app is None:
        browser = AsyncChromeManager(host=CDP_HOST, port=CDP_PORT, auto_start=False)
        _app = XianyuApp(browser)
    return _app

# 创建 FastMCP 服务
mcp = FastMCP(
    name="xianyu-mcp",
    host=MCP_HOST,
    port=MCP_PORT,
    sse_path="/sse",
    message_path="/messages/",
    streamable_http_path="/mcp",
)

# 注册工具
@mcp.tool()
async def xianyu_login() -> dict:
    """扫码登录闲鱼账号，获取 Token。Token 有效期约 24 小时。"""
    app = get_app()
    return await app.login(timeout=30)

@mcp.tool()
async def xianyu_search(keyword: str, rows: int = 30, ...) -> dict:
    """通过关键词搜索闲鱼商品..."""
    ...

# 启动
if __name__ == "__main__":
    mcp.run(transport="sse")
```

### Dockerfile 更新

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制代码
COPY src/ ./src/
COPY mcp_server/ ./mcp_server/

EXPOSE 8080

CMD ["python", "-m", "mcp_server.http_server"]
```

### docker-compose.yml 更新

```yaml
services:
  mcp-server:
    build:
      context: .
      dockerfile: docker/Dockerfile
    ports:
      - "8080:8080"
    environment:
      - CDP_HOST=chrome-headless
      - CDP_PORT=9222
    healthcheck:
      test: ["CMD-SHELL", "curl -f http://localhost:8080/sse || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 3
    depends_on:
      - chrome-headless

  chrome-headless:
    # 保持现有配置
```

## 数据流

### SSE 连接流程

1. 客户端 GET `/sse` 建立 SSE 流
2. 服务端返回 `event: endpoint` 包含 session_id
3. 客户端 POST `/messages/?session_id=xxx` 发送 JSON-RPC 请求
4. 服务端处理请求，通过 SSE 流返回响应

### 工具调用流程

```
客户端 ── POST /messages/ ──▶ FastMCP ──▶ XianyuApp ──▶ Chrome CDP
        (JSON-RPC call_tool)                                  │
                                                              │
客户端 ── SSE event ────────────◀─────────────────────────────┘
        (tool result)
```

## 错误处理

| 错误类型 | 处理方式 |
|---------|---------|
| Chrome 连接失败 | 返回错误信息，提示检查 Chrome 服务 |
| Session 无效 | 返回 400 错误 |
| JSON-RPC 解析失败 | 返回 Parse error (-32700) |
| 工具调用失败 | 返回 isError=True 的 CallToolResult |
| Token 过期 | 提示调用 xianyu_login |

## 测试要点

1. SSE 连接建立和 session_id 获取
2. JSON-RPC initialize 流程
3. tools/list 和 tools/call 调用
4. Chrome CDP 连接和浏览器操作
5. Docker 健康检查

## 客户端配置示例

Claude Code MCP 配置:

```json
{
  "mcpServers": {
    "xianyu": {
      "url": "http://localhost:8080/sse",
      "transport": "sse"
    }
  }
}
```

或使用 Streamable HTTP:

```json
{
  "mcpServers": {
    "xianyu": {
      "url": "http://localhost:8080/mcp",
      "transport": "http"
    }
  }
}
```