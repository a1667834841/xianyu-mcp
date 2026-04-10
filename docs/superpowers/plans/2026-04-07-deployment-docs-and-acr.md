# 部署文档与阿里云镜像收敛 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 保留当前可运行的 Docker Compose/MCP 链路，同时把忽略规则、Compose、部署文档和 skill 文档收敛到一套适合推送远程仓库的状态。

**Architecture:** 以现有 `docker-compose.yml` 为中心，不改动 MCP 核心逻辑，只在配置层和文档层做最小必要调整。`mcp-server` 服务同时保留 `build` 和远程 `image`，README 和 Docker 文档统一引导用户走 `Docker Compose + HTTP/SSE` 主路径，旧的本地 `stdio` 方案降级为兼容模式说明。

**Tech Stack:** Docker Compose, Python MCP server, Markdown docs, `.gitignore`

---

## 文件改动清单

| 文件 | 操作 | 职责 |
|------|------|------|
| `.gitignore` | 修改 | 忽略 `.env`、本地数据和常见运行产物 |
| `docker-compose.yml` | 修改 | 给 `mcp-server` 增加远程镜像入口并保留本地 build |
| `.env.example` | 修改 | 提供与当前 HTTP/SSE + Compose 一致的示例变量 |
| `README.md` | 修改 | 统一主部署路径与 MCP 接入说明 |
| `docker/README.md` | 修改 | 写完整部署、ACR、排障文档 |
| `.claude/skills/xianyu-skill/SKILL.md` | 修改 | 更新 Docker Compose 场景下的前置条件说明 |

---

### Task 1: 收敛忽略规则与 Compose 配置

**Files:**
- Modify: `.gitignore`
- Modify: `docker-compose.yml`
- Modify: `.env.example`

- [ ] **Step 1: 更新 `.gitignore`，明确忽略本地环境与运行数据**

将 `.gitignore` 调整为至少包含下面这些规则，保留现有 Python/IDE 忽略项不动：

```gitignore
# 环境变量
.env
.env.local

# 本地运行数据
data/

# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
*.egg-info/
.eggs/

# 虚拟环境
.venv/
venv/

# IDE
.idea/
.vscode/
*.swp
*.swo

# 日志
*.log

# 临时文件
*.tmp
.DS_Store
```

- [ ] **Step 2: 检查 `.gitignore` 结果是否符合本轮约束**

Run: `read .gitignore` 并人工确认：

- `.env` 仍被忽略
- `.env.example` 未被忽略
- `data/` 被忽略

Expected: 文件仍保留 `.env` 忽略规则，且没有误伤示例文件。

- [ ] **Step 3: 给 `mcp-server` 增加远程镜像入口，同时保留本地 build**

把 `docker-compose.yml` 中 `mcp-server` 服务改成下面的结构，其他环境变量、卷挂载、健康检查和 `browser` 服务保持原样：

```yaml
services:
  browser:
    image: registry.cn-hangzhou.aliyuncs.com/ggball/chrome-headless-shell-zh:latest
    container_name: xianyu-browser
    restart: unless-stopped
    ports:
      - "9222:9222"
    environment:
      - HTTP_PROXY=${HTTP_PROXY:-}
      - HTTPS_PROXY=${HTTPS_PROXY:-}
      - NO_PROXY=${NO_PROXY:-localhost,127.0.0.1}
      - XIANYU_USER_ID=${XIANYU_USER_ID:-default}
    command:
      - --user-data-dir=/data/users/${XIANYU_USER_ID:-default}/chrome-profile
      - --disable-dev-shm-usage
    volumes:
      - ${XIANYU_HOST_DATA_DIR:-./data}/users/${XIANYU_USER_ID:-default}/chrome-profile:/data/users/${XIANYU_USER_ID:-default}/chrome-profile
    shm_size: 2g
    networks:
      - xianyu-net

  mcp-server:
    image: ${XIANYU_MCP_IMAGE:-registry.cn-hangzhou.aliyuncs.com/ggball/xianyu-mcp:${XIANYU_MCP_IMAGE_TAG:-latest}}
    build:
      context: .
      dockerfile: docker/Dockerfile
    container_name: xianyu-mcp
    restart: unless-stopped
    ports:
      - "8080:8080"
    environment:
      - CDP_HOST=${CDP_HOST:-browser}
      - CDP_PORT=${CDP_PORT:-9222}
      - MCP_HOST=${MCP_HOST:-0.0.0.0}
      - MCP_PORT=${MCP_PORT:-8080}
      - XIANYU_DATA_ROOT=/data/users
      - XIANYU_USER_ID=${XIANYU_USER_ID:-default}
      - XIANYU_KEEPALIVE_ENABLED=${XIANYU_KEEPALIVE_ENABLED:-true}
      - XIANYU_KEEPALIVE_INTERVAL_MINUTES=${XIANYU_KEEPALIVE_INTERVAL_MINUTES:-10}
      - XIANYU_SEARCH_MAX_STALE_PAGES=${XIANYU_SEARCH_MAX_STALE_PAGES:-3}
      - CF_ACCOUNT_ID=${CF_ACCOUNT_ID:-}
      - CF_ACCESS_KEY_ID=${CF_ACCESS_KEY_ID:-}
      - CF_SECRET_ACCESS_KEY=${CF_SECRET_ACCESS_KEY:-}
      - CF_BUCKET_NAME=${CF_BUCKET_NAME:-blog}
      - CF_PUBLIC_DOMAIN=${CF_PUBLIC_DOMAIN:-https://img.ggball.top}
    volumes:
      - ${XIANYU_HOST_DATA_DIR:-./data}/users/${XIANYU_USER_ID:-default}/tokens:/data/users/${XIANYU_USER_ID:-default}/tokens
    healthcheck:
      test: ["CMD-SHELL", "curl -f -s --max-time 3 http://localhost:8080/sse | head -1 | grep -q 'event: endpoint' || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 15s
    depends_on:
      - browser
    networks:
      - xianyu-net

networks:
  xianyu-net:
    driver: bridge
```

- [ ] **Step 4: 更新 `.env.example`，改成当前 Compose/HTTP/SSE 真实变量**

将 `.env.example` 改成与当前实际部署一致的最小示例：

```dotenv
# 闲鱼 MCP Server 环境变量示例

# ==================== 镜像配置 ====================
# 生产环境可直接 pull 远程镜像；本地开发也可使用 docker compose build
XIANYU_MCP_IMAGE=registry.cn-hangzhou.aliyuncs.com/ggball/xianyu-mcp:latest
XIANYU_MCP_IMAGE_TAG=latest

# ==================== 数据目录 ====================
XIANYU_HOST_DATA_DIR=./data
XIANYU_USER_ID=default

# ==================== 浏览器 / MCP 配置 ====================
CDP_HOST=browser
CDP_PORT=9222
MCP_HOST=0.0.0.0
MCP_PORT=8080

# ==================== 运行参数 ====================
XIANYU_KEEPALIVE_ENABLED=true
XIANYU_KEEPALIVE_INTERVAL_MINUTES=10
XIANYU_SEARCH_MAX_STALE_PAGES=3

# ==================== Cloudflare R2（按需填写） ====================
CF_ACCOUNT_ID=
CF_ACCESS_KEY_ID=
CF_SECRET_ACCESS_KEY=
CF_BUCKET_NAME=blog
CF_PUBLIC_DOMAIN=https://img.ggball.top
```

- [ ] **Step 5: 验证 Compose 配置仍然可解析**

Run: `docker compose config`

Expected:

- 命令退出码为 0
- `mcp-server` 同时显示 `image` 和 `build`
- `CDP_HOST` 仍默认是 `browser`

---

### Task 2: 收敛根 README 为主部署入口

**Files:**
- Modify: `README.md`

- [ ] **Step 1: 重写 README 的部署主路径说明**

将 `README.md` 中“安装”“迁移部署”“MCP Server 模式”相关部分收敛成以下结构：

```md
## 快速开始

### 1. 准备环境

```bash
cp .env.example .env
# 按需填写 Cloudflare R2 配置；如果已有 .env，保留现有内容即可
```

### 2. 启动服务

```bash
docker compose up -d
docker compose ps
```

### 3. 验证服务

```bash
curl --max-time 5 http://localhost:8080/sse
curl --max-time 5 http://localhost:8080/rest/check_session
```

### 4. 首次登录

首次使用时调用 `xianyu_login` 获取二维码，扫码后再调用 `xianyu_check_session` 确认登录状态。
```

注意：保留已有功能说明和数据目录说明，只替换主部署叙事，不重写整个 README。

- [ ] **Step 2: 修正 README 中的旧入口、旧脚本和旧路径**

在 `README.md` 中完成以下收敛：

- 删除 `/Users/wuwenjing/...` 这类写死路径
- 删除不存在的 `run-mcp.sh` 引用
- 把旧的 `python -m mcp_server.server` 主路径改为“兼容/调试模式”
- 增加 HTTP/SSE MCP 接入说明，明确：

```json
{
  "mcpServers": {
    "xianyu-http": {
      "url": "http://127.0.0.1:8080/sse"
    }
  }
}
```

并在相邻说明中补一句：若客户端支持 Streamable HTTP，也可使用 `http://127.0.0.1:8080/mcp`。

- [ ] **Step 3: 为 README 增加远程镜像部署说明**

在 `README.md` 增加简洁的小节，内容至少包括：

```md
### 使用远程镜像部署

```bash
docker login --username=ggball0227 registry.cn-hangzhou.aliyuncs.com
docker compose pull
docker compose up -d
```

默认镜像：`registry.cn-hangzhou.aliyuncs.com/ggball/xianyu-mcp:latest`
```

- [ ] **Step 4: 检查 README 不再引用错误名称**

Run: `grep` 检查以下关键词在 `README.md` 中的残留情况：

- `run-mcp.sh`
- `/Users/wuwenjing`
- `chrome-headless`

Expected:

- 不再出现 `run-mcp.sh`
- 不再出现写死开发机路径
- 若出现 `chrome-headless`，只能是在历史/兼容说明外且必须改成当前实际命名；默认应不再作为主部署服务名

---

### Task 3: 重写 Docker 部署文档并加入阿里云 ACR 说明

**Files:**
- Modify: `docker/README.md`

- [ ] **Step 1: 把 `docker/README.md` 改成完整部署指南**

将 `docker/README.md` 重组为以下结构：

```md
# 闲鱼 MCP Server Docker 部署指南

## 部署方式

### 方式一：本地构建部署

```bash
docker compose build mcp-server
docker compose up -d
docker compose ps
```

### 方式二：远程镜像部署

```bash
docker login --username=ggball0227 registry.cn-hangzhou.aliyuncs.com
docker compose pull
docker compose up -d
docker compose ps
```
```

- [ ] **Step 2: 在 Docker 文档中加入阿里云 ACR 发布步骤**

加入以下命令模板，并把仓库地址固定为用户给出的 ACR 地址：

```bash
# 登录阿里云 ACR
docker login --username=ggball0227 registry.cn-hangzhou.aliyuncs.com

# 构建本地镜像
docker compose build mcp-server

# 查看镜像
docker images | grep xianyu-mcp

# 打 tag
docker tag xianyu-mcp-server:latest registry.cn-hangzhou.aliyuncs.com/ggball/xianyu-mcp:latest

# 推送镜像
docker push registry.cn-hangzhou.aliyuncs.com/ggball/xianyu-mcp:latest
```

并额外加入 VPC Registry 提示：

```md
如果部署机器位于阿里云 VPC 网络，可使用 `registry-vpc.cn-hangzhou.aliyuncs.com` 提升推送/拉取速度。
```

- [ ] **Step 3: 修正文档中的服务名和日志命令**

把旧文档中的错误服务名收敛为当前实际名称：

```bash
docker compose logs mcp-server
docker compose logs browser
```

并在 CDP 说明里明确：

```md
浏览器容器服务名为 `browser`，MCP Server 默认通过 `CDP_HOST=browser` 连接 9222 端口。
```

- [ ] **Step 4: 在 Docker 文档中加入首次扫码和健康检查说明**

增加以下内容：

```bash
# 健康检查
curl --max-time 5 http://localhost:8080/sse
curl --max-time 5 http://localhost:8080/rest/check_session
```

说明：

- `/sse` 返回 `event: endpoint` 代表 MCP SSE 入口可用
- `rest/check_session` 可快速检查当前 Cookie 是否有效
- 首次登录需要通过 MCP 调用 `xianyu_login` 获取二维码并扫码

- [ ] **Step 5: 检查 Docker 文档中的命名是否一致**

Run: `grep` 检查以下关键词在 `docker/README.md` 中的残留情况：

- `chrome-headless`
- `docker-compose`

Expected:

- 不再把 `chrome-headless` 当成当前服务名
- 命令统一为 `docker compose`

---

### Task 4: 更新 MCP Skill 文档前置条件

**Files:**
- Modify: `.claude/skills/xianyu-skill/SKILL.md`

- [ ] **Step 1: 把 Docker Compose 场景设为推荐前置条件**

将 skill 文档中“前置条件”部分改成类似下面的说明：

```md
## 前置条件

**推荐环境：Docker Compose 部署**

- [ ] 已在项目根目录执行 `docker compose up -d`
- [ ] `mcp-server` 服务可通过 `http://127.0.0.1:8080/sse` 访问
- [ ] 已按项目 README 完成 MCP 接入配置

**兼容模式：本地 stdio / 手工 Chrome**

如果没有使用 Docker Compose，也可以手动启动本地 Chrome 调试端口并运行 stdio 版 MCP Server；该模式仅用于本地调试，不再作为默认部署方式。
```

- [ ] **Step 2: 保留现有工具说明，只修改环境入口叙事**

检查 skill 文档，确保以下内容不变：

- 登录检查流程
- 二维码字段说明
- 各工具的入参和返回值说明

只收敛“前置条件”和“默认部署模式”的叙事，不改工具协议本身。

- [ ] **Step 3: 检查 skill 文档是否与 README 一致**

Run: 人工对照 `README.md` 与 `.claude/skills/xianyu-skill/SKILL.md`

Expected:

- 两者都把 Docker Compose 作为推荐路径
- 两者都没有把“手工启动本地 Chrome”写成默认主路径

---

### Task 5: 统一验证本轮改动

**Files:**
- Verify: `.gitignore`
- Verify: `docker-compose.yml`
- Verify: `.env.example`
- Verify: `README.md`
- Verify: `docker/README.md`
- Verify: `.claude/skills/xianyu-skill/SKILL.md`

- [ ] **Step 1: 验证 Compose 配置**

Run: `docker compose config`

Expected:

- exit code 为 0
- `mcp-server` 既有 `image` 又有 `build`
- `browser` 和 `mcp-server` 服务都还在

- [ ] **Step 2: 验证镜像仍可构建**

Run: `docker compose build mcp-server`

Expected: 构建成功，没有因为 compose 字段调整导致失败。

- [ ] **Step 3: 验证服务可启动**

Run: `docker compose up -d && docker compose ps`

Expected:

- `xianyu-browser` 为 `Up`
- `xianyu-mcp` 为 `Up`，并最终达到 `healthy`

- [ ] **Step 4: 验证 HTTP/SSE 与会话探活**

Run: `curl -i --max-time 5 http://localhost:8080/sse`

Expected: 返回 `HTTP/1.1 200 OK`，响应体包含 `event: endpoint`。

Run: `curl -i --max-time 5 http://localhost:8080/rest/check_session`

Expected: 返回 `HTTP/1.1 200 OK`，响应体是 JSON，包含 `success` 和 `valid` 字段。

- [ ] **Step 5: 验证文档关键词收敛结果**

Run: 用内容搜索检查这些旧关键词：

- `run-mcp.sh`
- `/Users/wuwenjing`
- `chrome-headless`

Expected:

- 不再出现在主文档和 Docker 文档中作为当前部署入口
- 若仍存在，只能出现在历史设计文档或实现计划中，不影响用户阅读的主文档

- [ ] **Step 6: 如果用户要求提交，再准备 git 提交**

Run: 仅在用户明确要求提交时执行 git 状态检查和提交；本计划默认不提交。

Expected: 保持本轮工作以文件修改和验证为止。
