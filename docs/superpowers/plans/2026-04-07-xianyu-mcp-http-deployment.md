# 闲鱼 MCP HTTP/SSE 部署实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将闲鱼 MCP Server 从 Stdio 模式改造为 HTTP/SSE 模式，支持 Docker 部署和远程访问。

**Architecture:** 使用 MCP SDK 内置的 FastMCP 类，注册现有 6 个工具，通过 SSE (`/sse`) 和 HTTP (`/mcp`) 端点提供服务。Chrome 浏览器通过 Docker 网络连接。

**Tech Stack:** Python 3.11, MCP SDK FastMCP, uvicorn, Docker, Chrome CDP

---

## 文件改动清单

| 文件 | 操作 | 职责 |
|------|------|------|
| `mcp_server/http_server.py` | 新建 | FastMCP HTTP/SSE 服务入口，注册 6 个工具 |
| `docker/Dockerfile` | 修改 | 更新启动命令为 HTTP Server，添加 curl |
| `docker-compose.yml` | 修改 | 更新 build context，添加健康检查 |
| `docker/entrypoint.sh` | 删除 | 不再需要（直接 CMD 启动） |

---

### Task 1: 创建 HTTP Server 入口

**Files:**
- Create: `mcp_server/http_server.py`

- [ ] **Step 1: 创建 http_server.py 基础结构**

```python
"""
mcp_server/http_server.py - 闲鱼 MCP Server HTTP/SSE 入口
使用 FastMCP 实现 SSE 和 HTTP 传输
"""

import os
import sys
import json
from dataclasses import asdict

from mcp.server.fastmcp import FastMCP

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import XianyuApp
from src.browser import AsyncChromeManager

# 配置：从环境变量读取
CDP_HOST = os.environ.get("CDP_HOST", "chrome-headless")
CDP_PORT = int(os.environ.get("CDP_PORT", "9222"))
MCP_HOST = os.environ.get("MCP_HOST", "0.0.0.0")
MCP_PORT = int(os.environ.get("MCP_PORT", "8080"))

print(f"[MCP HTTP] 配置: CDP={CDP_HOST}:{CDP_PORT}, 服务端口={MCP_PORT}")

# 全局 XianyuApp 实例（懒加载）
_app: XianyuApp | None = None


def get_app() -> XianyuApp:
    """获取或创建 XianyuApp 实例"""
    global _app
    if _app is None:
        browser = AsyncChromeManager(
            host=CDP_HOST,
            port=CDP_PORT,
            auto_start=False  # Docker 环境下不自动启动本地浏览器
        )
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
```

- [ ] **Step 2: 注册 xianyu_login 工具**

```python
@mcp.tool()
async def xianyu_login() -> str:
    """扫码登录闲鱼账号，获取 Token。Token 有效期约 24 小时。

    返回：
    - 登录成功：{"success": true, "token": "..."}
    - 需要扫码：{"success": true, "qr_code": {...}, "need_qr": true}
    - 登录失败：{"success": false, "message": "..."}
    """
    app = get_app()
    result = await app.login(timeout=30)
    return json.dumps(result, ensure_ascii=False)
```

- [ ] **Step 3: 注册 xianyu_search 工具**

```python
@mcp.tool()
async def xianyu_search(
    keyword: str,
    rows: int = 30,
    min_price: float | None = None,
    max_price: float | None = None,
    free_ship: bool = False,
    sort_field: str = "",
    sort_order: str = ""
) -> str:
    """通过关键词搜索闲鱼商品，返回商品列表（包含标题、价格、曝光度、发布时间、链接等），默认按曝光度倒序排列。

    参数：
    - keyword: 搜索关键词（必填）
    - rows: 每页数量，默认 30
    - min_price: 最低价格（可选）
    - max_price: 最高价格（可选）
    - free_ship: 是否只看包邮，默认 false
    - sort_field: 排序字段：pub_time（发布时间）或 price（价格）
    - sort_order: 排序方向：ASC（升序）或 DESC（降序）
    """
    app = get_app()
    await app.browser.ensure_running()

    results = await app.search(
        keyword=keyword,
        rows=rows,
        min_price=min_price,
        max_price=max_price,
        free_ship=free_ship,
        sort_field=sort_field,
        sort_order=sort_order
    )

    items = [asdict(item) for item in results]
    result = {
        "success": True,
        "total": len(items),
        "items": items
    }
    return json.dumps(result, ensure_ascii=False, indent=2)
```

- [ ] **Step 4: 注册 xianyu_publish 工具**

```python
@mcp.tool()
async def xianyu_publish(
    item_url: str,
    new_price: float | None = None,
    new_description: str | None = None,
    condition: str = "全新"
) -> str:
    """根据商品链接复制发布商品。自动获取对标商品数据（标题、描述、图片、分类等），填充发布表单。潮玩盲盒等特殊类目会自动保存草稿。

    参数：
    - item_url: 对标商品链接，如 https://www.goofish.com/item?id=123456789
    - new_price: 新商品价格（可选，默认使用原价）
    - new_description: 新商品描述（可选，默认使用原描述）
    - condition: 成色，默认全新，可选：全新、几乎全新、9成新、8成新、7成新
    """
    app = get_app()
    await app.browser.ensure_running()

    result = await app.publish(
        item_url=item_url,
        new_price=new_price,
        new_description=new_description,
        condition=condition
    )

    response = {
        "success": result.get("success"),
        "item_id": result.get("item_id"),
        "error": result.get("error"),
        "message": "表单填充完成，请检查浏览器窗口" if result.get("success") else result.get("error")
    }

    if result.get("item_data"):
        item_data = result["item_data"]
        response["captured_item"] = {
            "title": item_data.get("title", "")[:50],
            "price": item_data.get("min_price"),
            "images": len(item_data.get("image_urls", [])),
            "category": item_data.get("category")
        }

    return json.dumps(response, ensure_ascii=False)
```

- [ ] **Step 5: 注册 xianyu_refresh_token 工具**

```python
@mcp.tool()
async def xianyu_refresh_token() -> str:
    """刷新闲鱼 Token。通过访问闲鱼首页获取最新的 Token，当 Token 过期或需要更新时调用。

    返回：
    - 成功：{"success": true, "token": "...", "message": "Token 刷新成功"}
    - 失败：{"success": false, "message": "Token 刷新失败，请检查浏览器是否已登录"}
    """
    app = get_app()
    result = await app.refresh_token()

    if result:
        response = {
            "success": True,
            "token": result["token"],
            "full_cookie": result["full_cookie"],
            "message": "Token 刷新成功"
        }
    else:
        response = {
            "success": False,
            "message": "Token 刷新失败，请检查浏览器是否已登录"
        }

    return json.dumps(response, ensure_ascii=False)
```

- [ ] **Step 6: 注册 xianyu_check_session 工具**

```python
@mcp.tool()
async def xianyu_check_session() -> str:
    """检查闲鱼 Cookie 是否有效。调用用户信息接口验证当前登录状态。

    返回：
    - {"success": true, "valid": true/false, "message": "..."}
    """
    app = get_app()
    is_valid = await app.check_session()

    response = {
        "success": True,
        "valid": is_valid,
        "message": "Cookie 有效" if is_valid else "Cookie 已过期，需要重新登录"
    }

    return json.dumps(response, ensure_ascii=False)
```

- [ ] **Step 7: 注册 xianyu_show_qr 工具**

```python
@mcp.tool()
async def xianyu_show_qr() -> str:
    """显示登录二维码。访问闲鱼首页，如果未登录则显示二维码；如果已登录则直接返回。用户扫码后浏览器会自动跳转完成登录。

    返回：
    - 未登录：{"success": true, "qr_code": {...}, "message": "请扫码登录"}
    - 已登录：{"success": true, "logged_in": true, "message": "已登录"}
    """
    app = get_app()
    result = await app.show_qr_code()
    return json.dumps(result, ensure_ascii=False)
```

- [ ] **Step 8: 添加启动入口**

```python
if __name__ == "__main__":
    print(f"[MCP HTTP] 启动闲鱼 MCP Server (SSE 模式)")
    print(f"[MCP HTTP] SSE 端点: http://{MCP_HOST}:{MCP_PORT}/sse")
    print(f"[MCP HTTP] HTTP 端点: http://{MCP_HOST}:{MCP_PORT}/mcp")
    mcp.run(transport="sse")
```

- [ ] **Step 9: 本地验证 HTTP Server 启动**

```bash
cd /opt/dockercompose/xianyu
timeout 5 .venv/bin/python -m mcp_server.http_server 2>&1 || echo "启动测试完成"
```

Expected: 看到 `[MCP HTTP] 启动闲鱼 MCP Server (SSE 模式)` 和 uvicorn 启动日志

---

### Task 2: 更新 Dockerfile

**Files:**
- Modify: `docker/Dockerfile`
- Delete: `docker/entrypoint.sh`

- [ ] **Step 1: 更新 Dockerfile**

修改 `docker/Dockerfile` 内容为：

```dockerfile
# 闲鱼 MCP Server Dockerfile
# HTTP/SSE 模式，浏览器通过 CDP 连接外部 Chrome

FROM python:3.11-slim

WORKDIR /app

# 安装系统依赖（Playwright 需要的库 + curl 用于健康检查）
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxkbcommon0 \
    libatspi2.0-0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制代码
COPY src/ ./src/
COPY mcp_server/ ./mcp_server/

# 创建数据目录
RUN mkdir -p /data/tokens /data/chrome-profile

# 暴露端口
EXPOSE 8080

# 直接启动 HTTP Server（不再需要 entrypoint.sh）
CMD ["python", "-m", "mcp_server.http_server"]
```

- [ ] **Step 2: 删除不再需要的 entrypoint.sh**

```bash
rm docker/entrypoint.sh
```

- [ ] **Step 3: 验证 Dockerfile 语法**

```bash
docker build -f docker/Dockerfile --no-cache -t xianyu-mcp-test . 2>&1 | tail -20
```

Expected: 构建成功，看到 `Successfully built ...`

---

### Task 3: 更新 docker-compose.yml

**Files:**
- Modify: `docker-compose.yml`

- [ ] **Step 1: 更新 docker-compose.yml**

修改为：

```yaml
version: '3.8'

services:
  mcp-server:
    build:
      context: .
      dockerfile: docker/Dockerfile
    container_name: xianyu-mcp
    restart: unless-stopped
    ports:
      - "8080:8080"
    environment:
      - CDP_HOST=${CDP_HOST:-chrome-headless}
      - CDP_PORT=${CDP_PORT:-9222}
      - MCP_HOST=${MCP_HOST:-0.0.0.0}
      - MCP_PORT=${MCP_PORT:-8080}
    volumes:
      - ./data/tokens:/data/tokens
      - ./data/chrome-profile:/data/chrome-profile
    depends_on:
      - chrome-headless
    healthcheck:
      test: ["CMD-SHELL", "curl -f http://localhost:8080/sse || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s
    networks:
      - xianyu-net

  chrome-headless:
    image: registry.cn-hangzhou.aliyuncs.com/ggball/chrome-headless-shell-zh:latest
    container_name: chrome-headless
    restart: unless-stopped
    expose:
      - "9222"
    command:
      - --headless=new
      - --disable-gpu
      - --remote-debugging-address=0.0.0.0
      - --remote-debugging-port=9222
      - --no-sandbox
    volumes:
      - ./data/chrome-profile:/data/chrome-profile
    networks:
      - xianyu-net

networks:
  xianyu-net:
    driver: bridge
```

- [ ] **Step 2: 创建数据目录**

```bash
mkdir -p data/tokens data/chrome-profile
```

---

### Task 4: 验证 Docker 构建和运行

**Files:**
- Test: Docker 集成测试

- [ ] **Step 1: 构建镜像**

```bash
docker-compose build --no-cache 2>&1 | tail -30
```

Expected: 构建成功

- [ ] **Step 2: 启动服务**

```bash
docker-compose up -d
docker-compose ps
```

Expected: 两个容器状态为 `running`

- [ ] **Step 3: 验证 SSE 端点**

```bash
curl -s http://localhost:8080/sse --max-time 5 | head -5 || echo "SSE 响应超时（正常）"
```

Expected: 看到 `event: endpoint` 和 session_id

- [ ] **Step 4: 验证健康检查**

```bash
docker inspect xianyu-mcp --format='{{.State.Health.Status}}'
```

Expected: `healthy`

- [ ] **Step 5: 查看日志确认启动**

```bash
docker-compose logs mcp-server | head -20
```

Expected: 看到 `[MCP HTTP] 启动闲鱼 MCP Server (SSE 模式)` 和 uvicorn 启动日志

---

### Task 5: MCP 客户端集成测试

**Files:**
- Test: Python MCP 客户端测试脚本

- [ ] **Step 1: 创建测试脚本**

创建 `tests/test_http_mcp.py`：

```python
"""
HTTP MCP 客户端集成测试
验证 SSE 连接和工具调用
"""

import requests
import json
import time


def test_sse_connection():
    """测试 SSE 连接建立"""
    resp = requests.get('http://localhost:8080/sse', stream=True, timeout=5)
    assert resp.status_code == 200

    session_id = None
    for line in resp.iter_lines(decode_unicode=True):
        if line and 'session_id=' in line:
            session_id = line.split('session_id=')[1]
            break

    assert session_id is not None
    print(f"✓ SSE 连接成功，session_id: {session_id}")
    return session_id


def test_initialize(session_id):
    """测试 MCP initialize 流程"""
    post_url = f'http://localhost:8080/messages/?session_id={session_id}'

    init_request = {
        'jsonrpc': '2.0',
        'id': 1,
        'method': 'initialize',
        'params': {
            'protocolVersion': '2024-11-05',
            'clientInfo': {'name': 'test-client', 'version': '1.0'},
            'capabilities': {}
        }
    }

    resp = requests.post(post_url, json=init_request, timeout=3)
    assert resp.status_code == 202
    print(f"✓ initialize 请求发送成功")


def test_tools_list(session_id):
    """测试 tools/list 调用"""
    post_url = f'http://localhost:8080/messages/?session_id={session_id}'

    request = {
        'jsonrpc': '2.0',
        'id': 2,
        'method': 'tools/list',
        'params': {}
    }

    resp = requests.post(post_url, json=request, timeout=3)
    assert resp.status_code == 202
    print(f"✓ tools/list 请求发送成功")


def test_xianyu_check_session(session_id):
    """测试 xianyu_check_session 工具"""
    post_url = f'http://localhost:8080/messages/?session_id={session_id}'

    request = {
        'jsonrpc': '2.0',
        'id': 3,
        'method': 'tools/call',
        'params': {
            'name': 'xianyu_check_session',
            'arguments': {}
        }
    }

    resp = requests.post(post_url, json=request, timeout=5)
    assert resp.status_code == 202
    print(f"✓ xianyu_check_session 调用请求发送成功")


if __name__ == "__main__":
    print("=" * 50)
    print("HTTP MCP 客户端集成测试")
    print("=" * 50)

    session_id = test_sse_connection()
    test_initialize(session_id)
    time.sleep(1)
    test_tools_list(session_id)
    time.sleep(1)
    test_xianyu_check_session(session_id)

    print("=" * 50)
    print("所有测试通过！")
    print("=" * 50)
```

- [ ] **Step 2: 运行集成测试**

```bash
docker-compose up -d
sleep 5
.venv/bin/python tests/test_http_mcp.py
```

Expected: 看到 `所有测试通过！`

---

### Task 6: 清理和提交

- [ ] **Step 1: 停止并清理 Docker 服务**

```bash
docker-compose down
```

- [ ] **Step 2: 验证文件结构**

```bash
ls -la mcp_server/
ls -la docker/
ls -la tests/
```

Expected:
- `mcp_server/http_server.py` 存在
- `docker/entrypoint.sh` 不存在
- `tests/test_http_mcp.py` 存在

- [ ] **Step 3: 提交代码**

```bash
git add mcp_server/http_server.py docker/Dockerfile docker-compose.yml tests/test_http_mcp.py docs/
git status
```

---

## 客户端配置说明

完成部署后，客户端配置方式：

**SSE 模式：**
```json
{
  "mcpServers": {
    "xianyu": {
      "url": "http://server-ip:8080/sse",
      "transport": "sse"
    }
  }
}
```

**HTTP 模式：**
```json
{
  "mcpServers": {
    "xianyu": {
      "url": "http://server-ip:8080/mcp",
      "transport": "http"
    }
  }
}
```