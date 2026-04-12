# Skills 安装详解

本项目的 Skills 定义了 AI 如何使用闲鱼 MCP 工具的最佳实践。

## 什么是 Skills

Skills 是一个包含 `SKILL.md` 文件的目录，用于：
- 指导 AI 在什么场景下使用哪些工具
- 提供工具使用的核心规则和常见错误提醒
- 推荐标准工作流程

## 目录结构

```
skills/
└── xianyu-skill/
    ├── SKILL.md          # 技能定义文件
    └── README.md         # 安装说明
```

## 安装方式

### 方式一：随项目克隆（推荐）

克隆项目后 Skills 自动可用：

```bash
git clone https://github.com/<your-username>/xianyu-mcp.git
cd xianyu-mcp
```

OpenCode 和 Claude Code 都会自动扫描并加载。

### 方式二：独立安装

如需在其他项目中使用，可复制 Skills 目录：

```bash
# 复制到任意项目的 skills 目录
cp -r skills/xianyu-skill /path/to/your-project/skills/

# 或复制到 Claude Code 全局目录
cp -r skills/xianyu-skill ~/.claude/skills/
```

## 客户端支持

| 客户端 | Skills 路径 | 自动发现 |
|--------|-------------|---------|
| OpenCode | `skills/<name>/SKILL.md` | ✅ |
| OpenCode | `.claude/skills/<name>/SKILL.md` | ✅ |
| Claude Code | `.claude/skills/<name>/SKILL.md` | ✅ |
| Claude Code | `~/.claude/skills/<name>/SKILL.md` | ✅ |

本项目 Skills 同时存在于两个位置，确保两种客户端都能识别。

## Skills 内容概要

`SKILL.md` 定义了以下内容：

### 核心规则

1. **先选用户，再做操作** - 大多数操作需明确 `user_id`
2. **多用户场景不能省略 user_id** - 避免随机选择账号
3. **搜索不能按曝光度排序** - 需要二次排序
4. **发布成功≠上架** - 特殊类目可能保存为草稿

### 工具速查

| 工具 | 用途 |
|------|------|
| `xianyu_list_users` | 查看全部用户 |
| `xianyu_create_user` | 创建新用户 |
| `xianyu_login` | 发起登录 |
| `xianyu_check_session` | 检查登录态 |
| `xianyu_search` | 搜索商品 |
| `xianyu_publish` | 复制发布商品 |

### 推荐流程

```
查看用户 → 选择账号 → 检查登录态 → 执行操作
```

## 验证安装

### OpenCode

```bash
# 在 OpenCode 中执行
help skills
```

应看到 `xianyu-skill` 在列表中。

### Claude Code

Claude Code 会在需要时自动调用 Skills。可通过自然语言验证：

```
帮我查看当前闲鱼用户
```

如果 AI 正确调用 `xianyu_list_users` 并遵循 Skills 规则，说明安装成功。

## 相关文档

- [OpenCode 安装指南](./opencode-setup.md)
- [Claude Code 安装指南](./claude-code-setup.md)
- [Skills 技能定义](../skills/xianyu-skill/SKILL.md)