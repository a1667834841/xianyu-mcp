# 镜像重建与 MCP 端到端回归手册

## 文档目的

本文档用于规范每次修改 `xianyu-mcp` 后的标准回归流程，确保以下链路都仍然可用：

- Docker 镜像可重新构建
- `browser` / `mcp-server` 容器可正常重启并挂载既有数据目录
- `/sse`、`/rest/*` 调试接口可访问
- MCP 初始化、列工具、工具调用链完整可用

适用场景：

- 修改了 `src/`、`mcp_server/`、`docker/`、`docker-compose.yml`
- 更新了镜像依赖、启动参数、登录态处理、搜索链路、二维码链路
- 需要确认本地重建后跑的确实是新镜像，而不是旧容器里的旧版本

## 本次已验证通过的基线

以下步骤已在 `2026-04-11` 于仓库根目录实际执行并验证：

- `docker compose build mcp-server`
- `docker compose up -d --force-recreate browser mcp-server`
- `curl -N --max-time 5 http://127.0.0.1:8080/sse`
- `curl --max-time 15 -X POST http://127.0.0.1:8080/rest/search -H "Content-Type: application/json" -d '{"keyword":"iphone","rows":2}'`
- `curl --max-time 60 http://127.0.0.1:8080/rest/show_qr`
- 通过 `/sse` + `/messages/?session_id=...` 实际完成 `initialize`、`tools/list`、`tools/call`
- `tools/call` 已覆盖：`xianyu_check_session`、`xianyu_search`、`xianyu_refresh_token`、`xianyu_show_qr`、`xianyu_login`

本次观察到的现象：

- `/sse` 会立即返回 `event: endpoint`，随后因连接保持被 `curl --max-time` 主动超时，这属于正常现象
- `rest/search` 返回 `200` 且成功返回搜索结果
- `rest/show_qr` 在冷启动后可能需要约 `15s+` 才返回二维码 JSON
- `xianyu_check_session` 返回了 `valid=false`，但工具链路本身是通的，说明当前问题是登录态过期，不是服务不可用

## 前置条件

### 环境要求

- 已安装 Docker 和 Docker Compose
- 在当前仓库根目录执行命令
- 本机 `8080`、`9222` 端口未被其他服务占用

### 端口约定

- `browser` 暴露 `9222`
- `mcp-server` 暴露 `8080`
- MCP SSE 入口：`http://127.0.0.1:8080/sse`
- MCP 消息入口：`http://127.0.0.1:8080/messages/?session_id=<session_id>`

### 数据目录

默认数据目录来自 `docker-compose.yml`：

- 浏览器池数据：`${XIANYU_HOST_DATA_DIR:-./data}/browser-pool`
- 多用户数据根目录：`${XIANYU_HOST_DATA_DIR:-./data}/users`
- 用户注册表：`${XIANYU_HOST_DATA_DIR:-./data}/registry`

其中用户级登录态和 Cookie 快照会保存在 `${XIANYU_HOST_DATA_DIR:-./data}/users/<user_id>/...` 下。

这些目录不要在回归前随意删除，否则会把既有登录态、用户槽位映射和浏览器池状态一起清掉。

### 登录态说明

- 多用户 MCP 回归前，先确认本次要验证的 `user_id`
- `xianyu_check_session --user-id <user_id>` 返回 `valid=true`：说明该用户登录态可直接复用
- 返回 `valid=false`：说明该用户 Cookie 已过期，但只要 `show_qr`、`login` 能正常给出二维码，仍可判定二维码链路通过
- `xianyu_login` 与 `xianyu_show_qr` 的目标，是验证指定用户的二维码生成和返回链路，不要求回归时必须现场扫码

## 重新编译镜像步骤

在仓库根目录执行：

```bash
docker compose build mcp-server
```

通过标准：

- 构建结束时出现 `mcp-server  Built`
- 没有出现依赖安装失败、Dockerfile 语法错误、上下文缺失等错误

## 重启与旧容器处理

### 标准重启

```bash
docker compose up -d --force-recreate browser mcp-server
docker compose ps
```

通过标准：

- `browser` 为 `Up`
- `mcp-server` 为 `Up`，随后进入 `(healthy)`

### 如果遇到旧容器冲突

若出现容器名或端口冲突，先用 `docker ps` 确认当前 compose 项目实际生成的容器名。

例如默认项目名下，常见容器名可能是 `xianyu-mcp-server-1`、`xianyu-browser-1`；在其他 worktree 或目录下，前缀可能不同。

确认后可执行：

```bash
docker rm -f <实际的 mcp-server 容器名> <实际的 browser 容器名>
docker compose up -d browser mcp-server
docker compose ps
```

仅在确认这些容器就是当前项目对应容器时使用上述命令。

## 健康检查：`/sse`

执行：

```bash
curl -N --max-time 5 http://127.0.0.1:8080/sse
```

本次实际看到的关键信息：

```text
event: endpoint
data: /messages/?session_id=e037bea255db4151ae9fd4aaf560fff8
curl: (28) Operation timed out after 5001 milliseconds with 81 bytes received
```

判定规则：

- 只要看到了 `event: endpoint` 和 `session_id`，就算 `/sse` 通过
- `curl` 因 `--max-time` 超时退出是正常的，因为 SSE 本来就是长连接

## REST 调试验证

这一组 `/rest/*` 接口主要用于底层调试和兼容性检查。

注意：当前项目主线已经是多用户 MCP 模型，而 `/rest/check_session`、`/rest/search`、`/rest/show_qr` 仍是未显式传 `user_id` 的单用户调试接口。因此这部分只能证明服务进程、浏览器连接和基础链路正常，不等价于多用户 MCP 主流程已完成验证。

### 1. `/rest/check_session`

执行：

```bash
curl --max-time 10 http://127.0.0.1:8080/rest/check_session
```

本次实际返回示例：

```json
{"success":true,"valid":false,"message":"Cookie 已过期","last_updated_at":"2026-04-10 17:31:19"}
```

判定规则：

- 返回 `200` 且 JSON 可解析，说明接口链路正常
- `valid` 为 `true` 或 `false` 都可以，关键是接口本身可用

### 2. `/rest/search`

执行：

```bash
curl --max-time 15 -X POST http://127.0.0.1:8080/rest/search \
  -H "Content-Type: application/json" \
  -d '{"keyword":"iphone","rows":2}'
```

本次实际返回特征：

- `success=true`
- `requested=2`
- `total=2`
- `stop_reason="target_reached"`
- 返回了 2 条商品结果

判定规则：

- 返回 `200` 且 `success=true`
- `items` 非空，或至少能看见明确的业务错误信息而不是 500/超时

### 3. `/rest/show_qr`

执行：

```bash
curl --max-time 60 http://127.0.0.1:8080/rest/show_qr
```

本次实际返回示例：

```json
{"success":true,"logged_in":false,"qr_code":{"url":"https://passport.goofish.com/qrcodeCheck.htm?lgToken=...","public_url":"https://img.ggball.top/xianyu/qr-....png"},"message":"请扫码登录。扫码后浏览器会自动跳转，然后请调用 check_session 确认登录状态"}
```

判定规则：

- 返回 `200`
- 已登录时可返回 `logged_in=true`
- 未登录时返回 `qr_code` 也算通过
- 冷启动时可能比 `/rest/search` 慢，建议给 `60s` 超时

## 业务级 MCP 回归

这一节用于验证真实 MCP 工具链路是否可用，重点是业务级回归，而不是手工验证底层协议报文。

如果你要排查部署、容器、协议握手问题，优先看前面的镜像重建、`/sse` 健康检查和 `/rest/*` 调试步骤；如果这些都正常，日常回归建议直接使用 `scripts/mcp-dev`。

注意：当前项目已经是多用户结构，业务级回归应先确定要验证的 `user_id`，再执行后续命令。

### 验证目标

推荐至少覆盖以下工具：

1. `xianyu_list_users`
2. `xianyu_check_session`
3. `xianyu_show_qr`
4. `xianyu_search`
5. 如有需要，再补 `xianyu_refresh_token`

推荐前置检查：

1. 先执行 `./scripts/mcp-dev call xianyu_list_users`
2. 从返回结果里选一个已存在的 `user_id`，例如 `user-001`
3. 后续所有需要用户上下文的命令都显式传 `--user-id <user_id>`

### 推荐命令流程

在仓库根目录执行：

```bash
./scripts/mcp-dev call xianyu_list_users
./scripts/mcp-dev call xianyu_check_session --user-id user-001
./scripts/mcp-dev call xianyu_show_qr --user-id user-001
./scripts/mcp-dev call xianyu_check_session --user-id user-001
./scripts/mcp-dev call xianyu_search --user-id user-001 --keyword 机械键盘 --rows 3
```

如果你要回归 E2E 栈而不是默认本地端口，带上 `MCP_DEV_URL`：

```bash
MCP_DEV_URL=http://127.0.0.1:18090/mcp ./scripts/mcp-dev call xianyu_list_users
MCP_DEV_URL=http://127.0.0.1:18090/mcp ./scripts/mcp-dev call xianyu_check_session --user-id user-001
MCP_DEV_URL=http://127.0.0.1:18090/mcp ./scripts/mcp-dev call xianyu_show_qr --user-id user-001
MCP_DEV_URL=http://127.0.0.1:18090/mcp ./scripts/mcp-dev call xianyu_search --user-id user-001 --keyword 机械键盘 --rows 3
```

补充说明：

- `scripts/mcp-dev` 默认请求 `http://127.0.0.1:${MCP_HOST_PORT:-8080}/mcp`
- 如果该 `/mcp` 地址返回 `404`，脚本会自动回退到对应的 `/sse` 流程
- 命令行参数使用 `--kebab-case value`，脚本会自动转换成 MCP 请求里的 `snake_case`

### 判定规则

- `xianyu_list_users` 能正常返回用户和槽位信息，说明基础工具调用可用
- `xianyu_check_session` 返回结构化结果即可；`valid=true` 或 `valid=false` 都不影响链路判定
- `xianyu_show_qr` 在未登录时能返回二维码信息，就说明二维码链路可用
- `xianyu_search` 能返回商品结果，说明业务侧主链路可用
- 如果需要验证续期链路，再补跑 `xianyu_refresh_token`

### 本次推荐回归结果示例

按照上述命令流程，预期应观察到：

- `xianyu_list_users` 返回已配置用户列表
- `xianyu_check_session` 返回 `success=true`，并带当前登录态信息
- `xianyu_show_qr` 返回 `success=true`；未登录时包含 `qr_code`，已登录时可能直接返回已登录状态
- `xianyu_search` 返回 `success=true`，并包含商品结果

如果上述命令失败，但前面的 `/sse` 检查是正常的，再进一步排查 `scripts/mcp-dev` 指向的地址、目标用户数据目录和当前登录态。

## `xianyu_publish` 的验证边界

`xianyu_publish` 需要单独说明边界，不应和上述基础回归混为一谈。

可以验证的内容：

- MCP `tools/list` 中存在 `xianyu_publish`
- MCP `tools/call` 到 `xianyu_publish` 的请求链路是通的
- 发布链路验证时必须指定一个已存在且可用的 `user_id`
- 浏览器可被拉起，对标商品页可被访问，表单填充逻辑开始执行

不能仅靠一次基础回归就保证的内容：

- 是否真正发布成功
- 是否成功上传所有图片
- 是否被闲鱼页面结构变化影响
- 是否被闲鱼风控拦截
- 是否因登录态、类目特殊规则、发布页草稿逻辑而中断

因此，`xianyu_publish` 的标准表述应为：

- 基础回归阶段：验证工具调用链是否打通
- 真实发布成功与否：受登录态、页面结构、图片上传、闲鱼风控等外部因素影响，需要单独按场景验证

## 结果判定标准

### 通过

满足以下全部条件：

- 镜像可成功重建
- `browser`、`mcp-server` 容器正常启动，`mcp-server` 进入 `healthy`
- `/sse` 返回 `event: endpoint` 和有效 `session_id`
- `/rest/check_session`、`/rest/search`、`/rest/show_qr` 均可返回有效 JSON
- 业务级 MCP 回归命令可成功覆盖：
  `xianyu_list_users`、`xianyu_check_session`、`xianyu_show_qr`、`xianyu_search`

### 部分通过

满足以下情况之一：

- 基础链路都通，但当前登录态过期，`check_session` 返回 `valid=false`
- `show_qr` 能返回二维码，但未现场扫码确认登录
- 业务级 MCP 回归通过，但 `xianyu_publish` 未做真实发布验证

### 失败

满足以下任一情况：

- 镜像构建失败
- 容器无法启动或 `mcp-server` 长时间不进入 `healthy`
- `/sse` 无法返回 `event: endpoint`
- `/rest/search`、`/rest/show_qr`、`/rest/check_session` 持续 500 或无响应
- `scripts/mcp-dev` 关键命令持续失败
- 关键工具调用直接报错，且不是登录态过期这类业务外部因素

## 故障排查

### 1. 容器名冲突

典型现象：

- `docker compose up -d` 提示容器名已被占用

处理方法：

```bash
docker rm -f xianyu-mcp xianyu-browser
docker compose up -d browser mcp-server
docker compose ps
```

### 2. SSE 超时误判

典型现象：

- `curl --max-time 5 http://127.0.0.1:8080/sse` 最后显示 `curl: (28) Operation timed out`

这不一定是故障。只要在超时前已经看到：

```text
event: endpoint
data: /messages/?session_id=...
```

就说明 SSE 已经正常工作，超时只是因为连接被故意保持。

### 3. 旧容器跑旧镜像

典型现象：

- 明明改了代码，但回归结果与预期完全不符
- `docker compose up -d` 后服务没真正重建

处理方法：

```bash
docker compose build mcp-server
docker compose up -d --force-recreate browser mcp-server
docker compose ps
docker compose logs --tail 100 mcp-server
```

关注点：

- 是否出现新的容器创建时间
- 日志中的启动信息是否与当前版本一致
- 是否仍在运行旧容器而没有被 recreate

### 4. `/rest/check_session` 冷启动慢

典型现象：

- 重启后第一次请求 `check_session` 超时
- 但 `/sse`、`/rest/search` 或 MCP 工具调用是正常的

排查建议：

- 先确认 `docker compose ps` 中 `mcp-server` 已 `healthy`
- 再看 `docker compose logs --tail 100 mcp-server`
- 首次请求可把超时从 `10s` 提高到 `30s`
- 不要因为第一次慢就直接判定服务挂了
