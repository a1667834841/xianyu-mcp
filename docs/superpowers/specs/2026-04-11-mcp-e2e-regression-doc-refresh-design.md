# MCP E2E Regression Doc Refresh Design

## Goal

重构 `docs/mcp-e2e-regression.md`，保留镜像重建和底层健康检查内容，同时把业务级 MCP 回归部分改为基于 `scripts/mcp-dev` 的命令流程，减少手写 Python 脚本。

## Scope

本次只改文档，不改服务实现。

涉及内容：

- 保留镜像构建、容器重启、`/sse` 健康检查等底层验证步骤
- 保留必要的 REST 调试说明
- 将“MCP E2E 验证”部分从手写 Python SSE 客户端改为 `mcp-dev` 命令序列
- 增加说明：
  - `mcp-dev` 适合业务级 MCP 回归
  - 原始 `/sse` 检查适合部署和协议排障

不包含：

- 删除所有底层 `curl` 示例
- 改动 `scripts/mcp-dev`
- 新增新的回归脚本

## Recommended Structure

文档分两层：

1. 部署与底层健康检查
2. 业务级 MCP 回归

其中：

- 第 1 层继续使用 `docker compose`、`curl /sse`、必要时 `/rest/*`
- 第 2 层改为 `./scripts/mcp-dev call ...`

## Business-Level MCP Regression Commands

业务级回归推荐覆盖：

- `xianyu_list_users`
- `xianyu_check_session`
- `xianyu_show_qr`
- `xianyu_search`
- 如有需要补充 `xianyu_refresh_token`

示例形式：

```bash
./scripts/mcp-dev call xianyu_list_users
./scripts/mcp-dev call xianyu_check_session --user-id user-001
./scripts/mcp-dev call xianyu_show_qr --user-id user-001
./scripts/mcp-dev call xianyu_search --user-id user-001 --keyword 机械键盘 --rows 3
```

## Rationale

这样改的好处是：

- 日常回归更简单
- 多用户场景更自然
- 文档不再要求维护一段手写 MCP 客户端脚本
- 同时保留镜像和协议层排障手段

## Acceptance Criteria

- `docs/mcp-e2e-regression.md` 仍保留部署/健康检查内容
- 原“MCP E2E 验证”主流程被 `mcp-dev` 命令替代
- 文档清楚区分“底层检查”和“业务级回归”
- 读者能直接复制命令完成常见 MCP 回归
