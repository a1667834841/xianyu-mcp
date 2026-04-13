# OpenCode 闲鱼 MCP + Skills 安装指南

本文档介绍如何在 OpenCode 中接入闲鱼 MCP Server 和闲鱼 Skills。

## 前置条件

- 闲鱼 MCP Server 已通过 Docker Compose 部署
- MCP Server 可通过 `http://127.0.0.1:8080/sse` 访问

## 安装 MCP Server

### 1. 配置 opencode.json

在项目根目录创建或编辑 `opencode.json`：

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "xianyu": {
      "type": "remote",
      "url": "http://127.0.0.1:8080/sse",
      "enabled": true
    }
  }
}
```

### 2. 配置说明

| 字段 | 值 | 说明 |
|------|-----|------|
| `type` | `remote` | 远程 MCP 服务器 |
| `url` | `http://127.0.0.1:8080/sse` | MCP Server 的 SSE 端点 |
| `enabled` | `true` | 启动时启用 |

### 3. 验证 MCP 连接

```bash
opencode mcp list
```

应看到 `xianyu` 服务器已启用。

## 安装 Skills

OpenCode Skills 通过 `SKILL.md` 文件定义。对 OpenCode 而言，可直接发现的路径如下：

| 路径 | 说明 |
|------|------|
| `.opencode/skills/<name>/SKILL.md` | 项目级 |
| `~/.config/opencode/skills/<name>/SKILL.md` | 全局 |

本项目当前维护的 Skills 源文件位于：

```
.claude/skills/
├── xianyu-skill/SKILL.md
└── xianyu-hot-product-analysis/SKILL.md
```

仓库内维护源位于 `.claude/skills/`。如需在 OpenCode 中使用，需要将对应技能目录额外复制或安装到 OpenCode 的 skill 目录，例如 `~/.config/opencode/skills/`。

### SKILL.md 格式

每个 `SKILL.md` 必须以 YAML frontmatter 开头：

```yaml
---
name: xianyu-skill
description: Use when managing one or more Xianyu accounts via MCP
---
```

| 字段 | 必填 | 说明 |
|------|------|------|
| `name` | ✅ | 技能名称，1-64字符，小写字母数字 |
| `description` | ✅ | 技能描述，1-1024字符 |

## 验证安装

### 检查 MCP

```bash
opencode mcp list
```

### 检查 Skills

Skills 通过 `skill` 工具按需加载。OpenCode 会自动显示其已安装 skill 目录中的可用技能列表。

## 使用示例

登录并搜索商品：

```
帮我登录闲鱼账号
```

```
搜索盲盒商品，rows=5
```

## MCP Dev CLI

本地调试 MCP 时，可以直接调用 `scripts/mcp-dev`：

```bash
./scripts/mcp-dev call xianyu_list_users
./scripts/mcp-dev call xianyu_login --user-id user-001
./scripts/mcp-dev call xianyu_check_session --user-id user-001
./scripts/mcp-dev call xianyu_search --user-id user-001 --keyword 机械键盘 --rows 5
```

- 默认请求地址为 `http://127.0.0.1:${MCP_HOST_PORT:-8080}/mcp`
- 命令行参数使用 `--kebab-case value` 形式，脚本自动转换为 `snake_case`

## 常见问题

| 问题 | 解决方案 |
|------|---------|
| MCP 连接失败 | 检查 `docker compose ps` 确认服务运行中 |
| Skills 未加载 | 确认 SKILL.md 文件名大小写正确，frontmatter 包含 name/description |
| Token 过期 | 调用 `xianyu_login` 重新扫码登录 |

## 相关文档

- [闲鱼 MCP Server 部署指南](../docker/README.md)
- [Skills 安装详解](./skills-setup.md)
- [OpenCode MCP 官方文档](https://opencode.ai/docs/zh-cn/mcp-servers/)
- [OpenCode Skills 官方文档](https://opencode.ai/docs/zh-cn/skills/)
