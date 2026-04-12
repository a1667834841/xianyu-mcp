# Claude Code 闲鱼 MCP + Skills 安装指南

本文档介绍如何在 Claude Code 中接入闲鱼 MCP Server 和闲鱼 Skills。

## 前置条件

- 闲鱼 MCP Server 已通过 Docker Compose 部署
- MCP Server 可通过 `http://127.0.0.1:8080/sse` 访问

## 安装 MCP Server

Claude Code 支持远程 HTTP/SSE MCP Server。

### 方式一：命令行配置（推荐）

```bash
# 添加到项目级配置
claude mcp add-json --scope local '{"mcpServers": {"xianyu": {"url": "http://127.0.0.1:8080/sse", "transport": "http"}}}'

# 或添加到全局配置
claude mcp add-json --scope user '{"mcpServers": {"xianyu": {"url": "http://127.0.0.1:8080/sse", "transport": "http"}}}'
```

### 方式二：手动编辑配置文件

#### 项目级配置

编辑项目根目录的 `.mcp.json`：

```json
{
  "mcpServers": {
    "xianyu": {
      "url": "http://127.0.0.1:8080/sse",
      "transport": "http"
    }
  }
}
```

#### 全局配置

编辑 `~/.claude.json`：

```json
{
  "mcpServers": {
    "xianyu": {
      "url": "http://127.0.0.1:8080/sse",
      "transport": "http"
    }
  }
}
```

### 配置说明

| 字段 | 说明 |
|------|------|
| `url` | MCP Server 的 SSE 端点 |
| `transport` | 传输类型，远程 HTTP Server 使用 `http` |

### 验证配置

在 Claude Code 中运行：

```
/mcp
```

应该看到 `xianyu` 服务器已启用。

## 安装 Skills

项目已包含闲鱼 Skills 文件：

```
skills/xianyu-skill/SKILL.md
.claude/skills/xianyu-skill/SKILL.md
```

Claude Code 会自动发现并加载 `.claude/skills/` 目录下的 Skills。

### Skills 存放位置

Claude Code 支持以下 Skills 存放路径：

| 路径 | 说明 |
|------|------|
| `.claude/skills/<name>/SKILL.md` | 项目级（推荐） |
| `~/.claude/skills/<name>/SKILL.md` | 全局 |

本项目 Skills 同时存在于两个位置，确保 OpenCode 和 Claude Code 都能识别。

## 验证安装

### 检查 MCP 状态

```
/mcp list
```

或

```
/doctor
```

### 检查 Skills

Skills 无需手动加载，Claude Code 会根据需要自动调用 `skill` 工具。

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
- [Claude Code MCP 官方文档](https://docs.claude.com/en/docs/mcp)
