# MCP Dev CLI Design

## Goal

提供一个统一的本地调试命令 `scripts/mcp-dev`，用于直接调用 HTTP/SSE 部署中的 MCP 方法，替代反复手写临时 Python 或 `docker exec` 调试代码。

## Problem

当前多用户功能虽然已经可用，但验证流程仍然偏原始：

- 调 MCP 方法时，经常需要临时写 Python
- 接口层、管理器层、容器层的调试入口不统一
- 日常验证缺少一个稳定、可复用、可记忆的命令形式

这会让排查和回归测试依赖上下文记忆，而不是依赖一个固定工具。

## Scope

第一版只解决“通用调用器”问题：

- 新增 `scripts/mcp-dev`
- 支持 `call <tool-name> [--key value ...]`
- 默认先通过 HTTP 请求本地 MCP `/mcp` 入口，若返回 404 则自动回退到 `/sse`
- 将命令行参数转换为 JSON 参数对象
- 输出格式化 JSON
- 错误时返回非 0 退出码

第一版不包含：

- 交互式界面
- 自动补全
- 容器内直连 manager 的调试模式
- 一组固定别名子命令

## Recommended Approach

采用“HTTP + SSE 回退型 CLI”。

脚本默认直接请求本地 `mcp-server` 暴露的 `/mcp` 入口；如果该入口返回 404，则自动回退到 `/sse` 并按 MCP over SSE 流程完成 `initialize`、`notifications/initialized` 和 `tools/call`。这样既优先走更直接的 HTTP 路径，也兼容只暴露 SSE 的服务端实现，避免出现“脚本能跑、真实 MCP 不能跑”的偏差。

## Interface

命令格式：

```bash
./scripts/mcp-dev call <tool-name> [--key value ...]
```

示例：

```bash
./scripts/mcp-dev call xianyu_list_users
./scripts/mcp-dev call xianyu_show_qr --user-id user-001
./scripts/mcp-dev call xianyu_check_session --user-id user-002
./scripts/mcp-dev call xianyu_search --user-id user-001 --keyword 机械键盘 --rows 5
```

参数转换规则：

- `--user-id user-001` -> `{"user_id": "user-001"}`
- `--rows 5` -> `{"rows": 5}`
- `--free-ship true` -> `{"free_ship": true}`
- `--max-price null` -> `{"max_price": null}`

默认目标地址：

```text
http://127.0.0.1:${MCP_HOST_PORT:-8080}/mcp
```

可以通过环境变量覆盖，例如：

- `MCP_DEV_URL`
- 或继续复用 `MCP_HOST_PORT`

## Architecture

脚本职责尽量单一：

1. 解析命令行
2. 识别工具名
3. 解析 `--key value` 参数对
4. 推断基础类型（字符串、整数、浮点、布尔、null）
5. 先向 `/mcp` 发送 MCP HTTP 请求
6. 若 `/mcp` 返回 404，则自动回退到 `/sse`
7. 发送请求并打印结果

脚本不负责业务逻辑，也不感知具体某个 MCP 方法的参数 schema。它只做“通用请求转发器”。

## Output Rules

- 成功：优先输出 `result.content` 中的 text；若无 text，则输出 `result.structuredContent`；若仍无则回退输出非 text `content`
- 失败：打印错误正文到 stderr，并返回非 0
- 参数错误：打印简短用法并返回非 0

## Error Handling

脚本至少需要处理以下错误：

- 缺少 `call` 子命令
- 缺少工具名
- `--key` 后没有值
- 出现不合法参数形式
- HTTP 连接失败
- MCP 返回错误对象或非 2xx
- 返回体不是合法 JSON

## Testing Strategy

测试重点放在两层：

1. 参数解析与类型推断
2. HTTP 请求封装与响应处理

建议通过单元测试覆盖：

- 无参数调用
- snake_case 参数名转换
- `int` / `float` / `bool` / `null` 推断
- HTTP 成功返回
- `structuredContent` 成功返回
- `/mcp` 返回 404 后自动回退 `/sse`
- HTTP 错误返回
- 参数缺失错误

## Expected Outcome

完成后，后续验证 MCP 方法时应从“写临时 Python”切换为“执行统一命令”。

典型收益：

- 调试路径更稳定
- 回归测试更容易复现
- 团队成员更容易共享同一套验证方式
