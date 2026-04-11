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
- 在仓库根目录 `/opt/dockercompose/xianyu` 执行命令
- 本机 `8080`、`9222` 端口未被其他服务占用

### 端口约定

- `browser` 暴露 `9222`
- `mcp-server` 暴露 `8080`
- MCP SSE 入口：`http://127.0.0.1:8080/sse`
- MCP 消息入口：`http://127.0.0.1:8080/messages/?session_id=<session_id>`

### 数据目录

默认数据目录来自 `docker-compose.yml`：

- 浏览器 Profile：`${XIANYU_HOST_DATA_DIR:-./data}/users/${XIANYU_USER_ID:-default}/chrome-profile`
- Token/Cookie 快照：`${XIANYU_HOST_DATA_DIR:-./data}/users/${XIANYU_USER_ID:-default}/tokens`

这些目录不要在回归前随意删除，否则会把既有登录态一起清掉。

### 登录态说明

- `xianyu_check_session` / `/rest/check_session` 返回 `valid=true`：说明当前登录态可直接复用
- 返回 `valid=false`：说明 Cookie 已过期，但只要 `show_qr`、`login` 能正常给出二维码，仍可判定二维码链路通过
- `xianyu_login` 与 `xianyu_show_qr` 的目标，是验证二维码生成和返回链路，不要求回归时必须现场扫码

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

若出现容器名冲突，例如 `xianyu-mcp` 或 `xianyu-browser` 已存在，可执行：

```bash
docker rm -f xianyu-mcp xianyu-browser
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

## MCP E2E 验证

这一节是真正的 MCP 端到端回归，不是只测 REST 包装接口。

### 验证目标

必须依次验证：

1. 通过 `/sse` 获取 `session_id`
2. 调用 `initialize`
3. 调用 `tools/list`
4. 调用 `tools/call`
5. 至少覆盖以下工具：
   `xianyu_check_session`、`xianyu_search`、`xianyu_refresh_token`、`xianyu_show_qr`、`xianyu_login`

### 推荐执行脚本

在仓库根目录执行以下脚本：

```bash
python3 - <<'PY'
import json, queue, threading, time
import requests

base = 'http://127.0.0.1:8080'
q = queue.Queue()
state = {'session_id': None}

resp = requests.get(f'{base}/sse', stream=True, timeout=(5, 120))
resp.raise_for_status()


def reader():
    event = None
    data_lines = []
    for raw in resp.iter_lines(decode_unicode=True):
        if raw is None:
            continue
        line = raw.strip()
        if not line:
            if event or data_lines:
                data = '\n'.join(data_lines)
                q.put((event, data))
                if event == 'endpoint' and 'session_id=' in data:
                    state['session_id'] = data.split('session_id=')[1]
                event = None
                data_lines = []
            continue
        if line.startswith('event:'):
            event = line.split(':', 1)[1].strip()
        elif line.startswith('data:'):
            data_lines.append(line.split(':', 1)[1].strip())


threading.Thread(target=reader, daemon=True).start()


def wait_for(predicate, timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            evt, data = q.get(timeout=1)
        except queue.Empty:
            continue
        print(f'SSE event={evt} data={data[:200]}')
        if predicate(evt, data):
            return evt, data
    raise TimeoutError('wait_for timeout')


wait_for(lambda e, d: e == 'endpoint' and 'session_id=' in d, timeout=10)
session_id = state['session_id']
print('SESSION_ID=', session_id)
post_url = f'{base}/messages/?session_id={session_id}'


def send(payload):
    r = requests.post(post_url, json=payload, timeout=30)
    print('POST', payload['method'], r.status_code)
    r.raise_for_status()


send({
    'jsonrpc': '2.0',
    'id': 1,
    'method': 'initialize',
    'params': {
        'protocolVersion': '2024-11-05',
        'clientInfo': {'name': 'regression-doc', 'version': '1.0'},
        'capabilities': {}
    }
})
wait_for(lambda e, d: '"id":1' in d, timeout=30)

send({'jsonrpc': '2.0', 'method': 'notifications/initialized', 'params': {}})
time.sleep(1)

send({'jsonrpc': '2.0', 'id': 3, 'method': 'tools/list', 'params': {}})
_, data = wait_for(lambda e, d: '"id":3' in d and 'xianyu_search' in d, timeout=30)
msg = json.loads(data)
print('TOOLS=', [tool['name'] for tool in msg['result']['tools']])

calls = [
    (4, 'xianyu_check_session', {}),
    (5, 'xianyu_search', {'keyword': 'iphone', 'rows': 2}),
    (6, 'xianyu_refresh_token', {}),
    (7, 'xianyu_show_qr', {}),
    (8, 'xianyu_login', {}),
]

for req_id, name, arguments in calls:
    send({
        'jsonrpc': '2.0',
        'id': req_id,
        'method': 'tools/call',
        'params': {'name': name, 'arguments': arguments}
    })
    _, data = wait_for(lambda e, d, req_id=req_id: f'"id":{req_id}' in d, timeout=120)
    msg = json.loads(data)
    content = msg['result'].get('content', [])
    text = content[0].get('text') if content else ''
    print(f'TOOL {name} RESULT {text[:500]}')

resp.close()
PY
```

### 本次实际回归结果

本次执行时，实际观察到：

- `initialize` 返回成功
- `tools/list` 返回 6 个工具：
  `xianyu_login`、`xianyu_search`、`xianyu_publish`、`xianyu_refresh_token`、`xianyu_check_session`、`xianyu_show_qr`
- `xianyu_check_session` 返回 `success=true`，且当前登录态为 `valid=false`
- `xianyu_search` 返回 `success=true`，可正常返回商品列表
- `xianyu_refresh_token` 返回 `success=true`
- `xianyu_show_qr` 返回 `success=true`，包含 `qr_code.url` 与 `qr_code.public_url`
- `xianyu_login` 返回 `success=true`，同样可返回扫码二维码数据

## `xianyu_publish` 的验证边界

`xianyu_publish` 需要单独说明边界，不应和上述基础回归混为一谈。

可以验证的内容：

- MCP `tools/list` 中存在 `xianyu_publish`
- MCP `tools/call` 到 `xianyu_publish` 的请求链路是通的
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
- MCP `initialize`、`tools/list` 成功
- MCP `tools/call` 成功覆盖：
  `xianyu_check_session`、`xianyu_search`、`xianyu_refresh_token`、`xianyu_show_qr`、`xianyu_login`

### 部分通过

满足以下情况之一：

- 基础链路都通，但当前登录态过期，`check_session` 返回 `valid=false`
- `show_qr` / `login` 能返回二维码，但未现场扫码确认登录
- MCP 链路通过，但 `xianyu_publish` 未做真实发布验证

### 失败

满足以下任一情况：

- 镜像构建失败
- 容器无法启动或 `mcp-server` 长时间不进入 `healthy`
- `/sse` 无法返回 `event: endpoint`
- `/rest/search`、`/rest/show_qr`、`/rest/check_session` 持续 500 或无响应
- `initialize`、`tools/list`、`tools/call` 任一步无法完成
- `tools/list` 缺少应有工具，或关键工具调用直接报错

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
