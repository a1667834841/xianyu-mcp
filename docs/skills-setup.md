# Skills 安装详解

本项目的 Skills 定义了 AI 如何使用闲鱼 MCP 工具的最佳实践。

## 什么是 Skills

Skills 是一个包含 `SKILL.md` 文件的目录，用于：
- 指导 AI 在什么场景下使用哪些工具
- 提供工具使用的核心规则和常见错误提醒
- 推荐标准工作流程

## 目录结构

```
.opencode/skills/                   # OpenCode 项目级 Skills
├── xianyu-skill/
│   └── SKILL.md                    # 闲鱼操作技能
└── xianyu-hot-product-analysis/
    └── SKILL.md                    # 热门商品分析技能

.claude/skills/                     # Claude Code 兼容 Skills
├── xianyu-skill/
│   └── SKILL.md
└── xianyu-hot-product-analysis/
    └── SKILL.md
```

## Skills 发现路径

OpenCode 自动扫描以下路径：

| 客户端 | 项目级路径 | 全局路径 |
|--------|-----------|---------|
| OpenCode | `.opencode/skills/<name>/SKILL.md` | `~/.config/opencode/skills/<name>/SKILL.md` |
| Claude Code | `.claude/skills/<name>/SKILL.md` | `~/.claude/skills/<name>/SKILL.md` |
| Agents 兼容 | `.agents/skills/<name>/SKILL.md` | `~/.agents/skills/<name>/SKILL.md` |

克隆项目后 Skills 自动可用，无需额外配置。

## SKILL.md 格式要求

每个 `SKILL.md` 必须以 YAML frontmatter 开头：

```yaml
---
name: xianyu-skill
description: Use when managing one or more Xianyu accounts via MCP
---
```

| 字段 | 必填 | 规则 |
|------|------|------|
| `name` | ✅ | 1-64字符，仅小写字母数字，可用单个连字符分隔 |
| `description` | ✅ | 1-1024字符，足够具体让 AI 能正确选择 |

名称正则：`^[a-z0-9]+(-[a-z0-9]+)*$`

## Skills 内容概要

### xianyu-skill

核心规则：

1. **先选用户，再做操作** - 大多数操作需明确 `user_id`
2. **多用户场景不能省略 user_id** - 避免随机选择账号
3. **搜索不能按曝光度排序** - 需要二次排序
4. **发布成功≠上架** - 特殊类目可能保存为草稿

工具速查：

| 工具 | 用途 |
|------|------|
| `xianyu_list_users` | 查看全部用户 |
| `xianyu_create_user` | 创建新用户 |
| `xianyu_login` | 发起登录 |
| `xianyu_check_session` | 检查登录态 |
| `xianyu_search` | 搜索商品 |
| `xianyu_publish` | 复制发布商品 |

### xianyu-hot-product-analysis

用于分析热门商品，识别用户痛点、关键词和曝光驱动因素。

## 验证安装

### OpenCode

OpenCode 会自动显示可用技能列表，通过 `skill` 工具按需加载。

### Claude Code

Claude Code 会在需要时自动调用 Skills。可通过自然语言验证：

```
帮我查看当前闲鱼用户
```

如果 AI 正确调用 `xianyu_list_users` 并遵循 Skills 规则，说明安装成功。

## 独立安装

如需在其他项目中使用，可复制 Skills 目录：

```bash
# 复制到 OpenCode 全局目录
cp -r .opencode/skills/xianyu-skill ~/.config/opencode/skills/

# 或复制到 Claude Code 全局目录
cp -r .claude/skills/xianyu-skill ~/.claude/skills/
```

## 常见问题

| 问题 | 解决方案 |
|------|---------|
| Skills 未加载 | 确认 SKILL.md 文件名大小写正确 |
| frontmatter 无效 | 确保 name/description 字段存在且符合规则 |
| 技能名称冲突 | 确保各技能名称在所有位置中唯一 |

## 相关文档

- [OpenCode 安装指南](./opencode-setup.md)
- [Claude Code 安装指南](./claude-code-setup.md)
- [OpenCode Skills 官方文档](https://opencode.ai/docs/zh-cn/skills/)