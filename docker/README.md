# 闲鱼 MCP Server Docker 部署指南

> **前提**：本指南假设你在项目根目录（即 `docker-compose.yml` 所在目录）执行命令。`docker/` 子目录仅存放 Dockerfile，不存放 compose 文件。

## 部署方式

### 方式一：本地构建部署

适合本地开发、调试 Dockerfile 或需要基于当前代码重新构建镜像的场景。

```bash
docker compose build mcp-server
docker compose up -d
docker compose ps
```

### 方式二：远程镜像部署

适合服务器直接拉取已发布镜像进行部署。

默认镜像：`registry.cn-hangzhou.aliyuncs.com/ggball/xianyu-mcp:latest`

```bash
docker login --username=ggball0227 registry.cn-hangzhou.aliyuncs.com
docker compose pull
docker compose up -d
docker compose ps
```

> `docker compose pull` 会拉取两个服务的镜像（`browser` 和 `mcp-server`），其中 `mcp-server` 来自阿里云 ACR，`browser` 镜像地址在 `docker-compose.yml` 中已指定。

## 服务说明

- 浏览器容器服务名为 `browser`
- MCP Server 服务名为 `mcp-server`
- MCP Server 默认通过 `CDP_HOST=browser` 连接 `9222` 端口

常用环境变量：

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `CDP_HOST` | 浏览器容器主机名 | `browser` |
| `CDP_PORT` | 浏览器 CDP 端口 | `9222` |
| `MCP_HOST` | MCP Server 监听地址 | `0.0.0.0` |
| `MCP_PORT` | MCP Server 监听端口 | `8080` |
| `XIANYU_HOST_DATA_DIR` | 宿主机数据目录 | `./data` |
| `XIANYU_USER_ID` | 当前用户目录名 | `default` |

### 浏览器池环境变量

新增环境变量：

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `BROWSER_POOL_SIZE` | Chrome 槽位数量 | `1` |
| `BROWSER_CDP_START_PORT` | 浏览器池起始 CDP 端口 | `9222` |
| `BROWSER_PROFILE_ROOT` | 浏览器池 profile 根目录 | `/data/browser-pool` |

浏览器容器会一次性拉起多个 Chrome 进程：

- `slot-1 -> browser:9222`
- `slot-2 -> browser:9223`
- `slot-3 -> browser:9224`

持久化目录：

- 浏览器 Profile：`${XIANYU_HOST_DATA_DIR}/users/${XIANYU_USER_ID}/chrome-profile`
- Cookie 快照：`${XIANYU_HOST_DATA_DIR}/users/${XIANYU_USER_ID}/tokens/token.json`

## 阿里云 ACR 发布镜像

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

如果部署机器位于阿里云 VPC 网络，可使用 `registry-vpc.cn-hangzhou.aliyuncs.com` 提升推送和拉取速度。

## 首次登录与健康检查

服务启动后先做健康检查：

```bash
curl --max-time 5 http://localhost:8080/sse
curl --max-time 5 http://localhost:8080/rest/check_session
```

- `/sse` 返回 `event: endpoint` 代表 MCP SSE 入口可用
- `rest/check_session` 可快速检查当前 Cookie 是否有效
- 首次登录需要通过 MCP 调用 `xianyu_login` 获取二维码并扫码
- 扫码完成后，再调用 `xianyu_check_session` 或访问 `rest/check_session` 确认登录状态

## 运维命令

```bash
docker compose ps
docker compose logs mcp-server
docker compose logs browser
docker compose restart mcp-server
docker compose restart browser
```

## 排障

### 1. `mcp-server` 无法连接浏览器

- 确认 `browser` 容器已启动：`docker compose ps`
- 确认 `CDP_HOST` 没有被错误改成旧名称
- 查看日志：`docker compose logs browser`、`docker compose logs mcp-server`

### 2. `/sse` 无响应或超时

- 先执行 `docker compose ps`，确认 `mcp-server` 已正常运行
- 再执行 `curl --max-time 5 http://localhost:8080/sse`
- 如果仍失败，查看 `docker compose logs mcp-server`

### 3. 登录态失效

- 执行 `curl --max-time 5 http://localhost:8080/rest/check_session`
- 如果返回未登录，重新通过 MCP 调用 `xianyu_login` 获取二维码扫码
- 确认宿主机数据目录挂载未丢失，避免浏览器 Profile 和 token 文件被重置

### 4. 需要重新部署镜像

```bash
docker compose pull
docker compose up -d
docker compose ps
```
