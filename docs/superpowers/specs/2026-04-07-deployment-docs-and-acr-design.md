# 部署文档与阿里云镜像收敛设计

## 背景

当前项目已经具备 Docker Compose 启动能力，`mcp-server` 也已切到 HTTP/SSE 入口，但仓库内仍同时存在旧版本地 `stdio` 文档、过时脚本引用、旧服务命名和未收敛的部署说明，导致“能运行”和“别人能照文档部署”之间仍有明显落差。

本轮目标不是重构业务逻辑，而是在不影响当前可运行环境的前提下，把项目整理到适合推送云端仓库、并可按统一文档部署的状态。

## 目标

1. 保留本地 `.env` 文件，不删除、不改写现有值。
2. 把 `.env` 加入忽略规则，避免后续误提交到远程仓库。
3. 统一项目主部署路径为 `Docker Compose + HTTP/SSE MCP`。
4. 让 `docker-compose.yml` 同时支持本地构建和远程镜像部署。
5. 补齐阿里云 ACR 镜像构建、tag、push、pull、部署说明。
6. 更新 MCP skill 文档，使其能说明 Docker Compose 场景下的接入前提。

## 非目标

1. 不删除现有 `.env`。
2. 不轮换现有密钥。
3. 不修改 MCP 核心业务逻辑。
4. 不在本轮直接推送 git 远程仓库。
5. 不在本轮直接推送阿里云镜像。

## 方案对比

### 方案 A：双模式 Compose（推荐）

在 `docker-compose.yml` 中同时保留 `image` 和 `build`。文档统一说明：

- 本地开发可 `docker compose build mcp-server && docker compose up -d`
- 服务器部署可 `docker compose pull && docker compose up -d`

优点：

- 不破坏当前本地开发链路
- 远程镜像部署简单
- 不需要拆两份 compose 文件

缺点：

- Compose 和文档会比单模式多一点说明

### 方案 B：纯远程镜像模式

`docker-compose.yml` 只保留远程镜像。

优点：

- 线上部署最简单

缺点：

- 本地开发调试不方便
- 与当前代码仓内开发习惯不匹配

### 方案 C：只改文档不改 Compose

优点：

- 改动最小

缺点：

- 入口仍分裂
- 不能真正解决“仓库可直接推送并让别人照文档部署”的问题

## 决策

采用方案 A：双模式 Compose。

镜像 tag 文档默认使用 `latest`，与用户当前发布习惯保持一致。

## 设计

### 1. 配置与忽略规则

调整 `.gitignore`，确保以下内容默认不纳入版本控制：

- `.env`
- 本地数据目录
- 本地产物与缓存目录（在不影响现有仓库结构的前提下只做必要补充）

保留 `.env.example` 作为示例配置文件。`.env` 本地继续生效，但默认不参与入库。

### 2. Docker Compose 入口

`docker-compose.yml` 调整为：

- `mcp-server` 同时保留 `build` 和 `image`
- 默认镜像地址为 `registry.cn-hangzhou.aliyuncs.com/ggball/xianyu-mcp:${XIANYU_MCP_IMAGE_TAG:-latest}`
- 保持现有 `browser` 服务、端口和挂载方式不变
- 不改变当前服务健康检查思路

预期使用方式：

- 本地开发：优先 `build`
- 服务器部署：优先 `pull`

### 3. README 主路径统一

`README.md` 收敛为统一的主叙事：

1. 项目功能概览
2. 推荐部署方式：Docker Compose
3. 快速开始
4. 首次登录与扫码
5. MCP 接入说明
6. 开发/兼容模式补充说明

需要修正的内容包括：

- 删除或弱化旧版本地 `stdio + 手工 Chrome` 作为主路径的描述
- 替换写死的开发机路径
- 替换不存在的 `run-mcp.sh` 引用
- 明确 `/sse` 和 `/mcp` 的用途

### 4. Docker 专项文档

`docker/README.md` 作为部署专页，覆盖：

1. 本地 build 部署
2. 远程镜像部署
3. 阿里云 ACR 登录
4. tag / push / pull 示例
5. 首次扫码登录说明
6. 常见故障排查

需要修正：

- 服务名从旧文档中的 `chrome-headless` 收敛为当前 compose 实际命名
- 日志命令、服务名、连接关系与实际文件保持一致

### 5. MCP Skill 文档

更新 `.claude/skills/xianyu-skill/SKILL.md` 的前置条件描述：

- 推荐场景为 Docker Compose 已启动
- MCP Server 已按项目文档接入 Claude/OpenCode
- 本地手工 Chrome 启动改为兼容模式说明，而不是默认主路径

本轮只更新说明，不增加新的 skill 行为。

## 数据流与使用流

### 本地开发流

1. 开发者修改代码
2. 运行 `docker compose build mcp-server`
3. 运行 `docker compose up -d`
4. Claude/OpenCode 通过 MCP HTTP/SSE 或兼容配置接入

### 服务器部署流

1. 本地构建镜像
2. tag 为阿里云 ACR 地址
3. push 到远程镜像仓库
4. 服务器 `docker compose pull`
5. 服务器 `docker compose up -d`

## 错误处理与风险

1. `.env` 已存在且正在被当前环境使用，因此本轮只忽略，不删除。
2. 仓库当前不是 git repo，因此无法在本地完成“写 spec 后提交”这一步；若后续在真实 git 仓库目录执行，可再补提交。
3. 使用 `latest` 作为默认 tag 简单，但回滚能力较弱；本轮接受该取舍，并在文档中提示生产环境可自行替换为固定 tag。
4. 若部署机器无法访问阿里云公网 Registry，可在文档中补充 VPC Registry 域名说明。

## 测试与验证

实施后需要验证：

1. `docker compose config`
2. `docker compose build mcp-server`
3. `docker compose up -d`
4. `curl --max-time 5 http://localhost:8080/sse`
5. `curl --max-time 5 http://localhost:8080/rest/check_session`
6. 与本轮修改相关的文档路径、脚本名、服务名引用一致性检查

## 实施范围

预计修改文件：

- `.gitignore`
- `docker-compose.yml`
- `README.md`
- `docker/README.md`
- `.env.example`
- `.claude/skills/xianyu-skill/SKILL.md`

## 完成标准

1. `.env` 保留且被忽略。
2. 文档不再引用不存在的脚本和错误服务名。
3. 文档默认引导用户走 Docker Compose 主路径。
4. Compose 同时可用于本地 build 和远程镜像部署。
5. 阿里云 ACR 推送和部署说明可直接照抄执行。
