# 闲鱼 Skills 安装说明

Skills 是 AI 客户端的技能扩展，帮助 AI 更好地理解和使用闲鱼 MCP 工具。

## 安装方式

### OpenCode

OpenCode 会自动扫描项目根目录下的 `skills/` 目录：

```bash
# 确保项目结构如下
skills/xianyu-skill/SKILL.md
```

无需额外配置，OpenCode 会自动加载。

### Claude Code

Claude Code 支持两种 Skills 存放位置：

| 路径 | 说明 |
|------|------|
| `.claude/skills/<name>/SKILL.md` | 项目级（推荐） |
| `~/.claude/skills/<name>/SKILL.md` | 全局 |

本项目已将 Skills 同时放在：
- `skills/xianyu-skill/SKILL.md` （OpenCode 格式）
- `.claude/skills/xianyu-skill/SKILL.md` （Claude Code 格式）

两种客户端均可自动识别。

## Skills 内容

详见 [SKILL.md](./SKILL.md)

## 验证安装

### OpenCode

```
help skills
```

应看到 `xianyu-skill` 在可用列表中。

### Claude Code

Claude Code 会根据任务自动调用 Skills，无需手动验证。

## 相关文档

- [OpenCode 安装指南](../../docs/opencode-setup.md)
- [Claude Code 安装指南](../../docs/claude-code-setup.md)
- [Skills 安装详解](../../docs/skills-setup.md)