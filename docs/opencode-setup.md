# OpenCode 闲鱼 MCP + Skills 安装指南

本文档介绍如何在 OpenCode 中接入闲鱼 MCP Server 和闲鱼 Skills。

## 前置条件

- 闲鱼 MCP Server 已通过 Docker Compose 部署
- MCP Server 可通过 `http://127.0.0.1:8080/sse` 访问

## 安装 MCP Server

### 1. 创建/编辑 OpenCode 配置文件

在项目根目录创建或编辑 `opencode.json`：

```bash
# 如果不存在则创建
touch opencode.json
```

添加以下内容：

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

### 3. 验证配置

重启 OpenCode 或在新会话中，OpenCode 会自动连接 MCP Server。

## 安装 Skills

项目已包含闲鱼 Skills 文件，无需额外安装：

```
.claude/skills/xianyu-skill/SKILL.md
```

OpenCode 会自动发现并加载 Skills。

### Skills 存放位置

OpenCode 支持以下 Skills 存放路径（项目级）：

| 路径 | 说明 |
|------|------|
| `.opencode/skills/<name>/SKILL.md` | OpenCode 原生格式 |
| `.claude/skills/<name>/SKILL.md` | Claude Code 兼容格式 |

本项目已使用 `.claude/skills/xianyu-skill/SKILL.md`，OpenCode 可自动识别。

## 验证安装

### 检查 MCP 连接

在 OpenCode 中输入：

```
/mcp list
```

应该看到 `xianyu` 服务器已启用。

### 检查 Skills

```
help skills
```

应该看到 `xianyu-skill` 在可用技能列表中。

## 使用示例

登录并搜索商品：

```
帮我登录闲鱼账号
```

```
搜索盲盒商品，rows=5
```

## 常见问题

| 问题 | 解决方案 |
|------|---------|
| MCP 连接失败 | 检查 `docker compose ps` 确认服务运行中 |
| Skills 未加载 | 确认 SKILL.md 文件名大小写正确 |
| Token 过期 | 调用 `xianyu_login` 重新扫码登录 |

## 相关文档

- [闲鱼 MCP Server 部署指南](../docker/README.md)
- [OpenCode MCP 文档](https://opencode.ai/docs/zh-cn/mcp-servers)
- [OpenCode Skills 文档](https://opencode.ai/docs/zh-cn/skills)
