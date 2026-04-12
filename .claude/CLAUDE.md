# Claude Code 配置：superpowers

核心使用 superpowers 插件进行思考与流程控制。

## 核心原则

1. 流程归 superpowers：plan、brainstorm、debug、TDD、verify、code review
2. 独立 reviewer 通道：verification 和 code-review 分两个 pass，不能在同一上下文里合并
3. 证据优先：没有测试/截图/验证报告不算完成
4. 创造性工作先 brainstorm：任何新功能、重构、架构变更前先调用 brainstorming
5. 最短路径优先：能用一个 skill 解决的，不升级为完整闭环

## 任务分流

### 只读任务
分析、解释、架构说明、代码阅读 —— 直接处理。
真实 bug 排查但尚未修改 —— 用 systematic-debugging。

### 轻量任务
单文件或小范围修改、明确 bug 修复、配置/文案调整、小测试补充。
跳过完整 brainstorming / writing-plans / worktrees / 重 review 链。
直接实现 + 定向验证。

### 中任务
多文件但边界清晰，新功能或明确的重构。
简短 brainstorming + 短 writing-plans + 实现 + verification。

### 大任务
跨模块、共享逻辑、新架构、公共 API 变更。
完整闭环：brainstorming → writing-plans → executing-plans + worktrees + TDD → verification → code-review → finishing-branch

## Subagent 策略

一定派子代理：
- 用户明说 "并行 / parallel / dispatch"
- 2-4 个边界清晰、独立验证、无共享状态的子任务
- 纯只读的多目标研究

一定不派：
- 任务有顺序依赖
- 多个子任务改同一文件 / contract / shared types
- package.json / lockfile / 根配置 / CI / schema / 总入口 默认串行
- 单一目标的 bug 修复
- 根因未明的调试

## 安全护栏

- rm -rf / force-push / git reset --hard 必须先过 careful / guard
- 调试敏感模块时用 freeze <dir> 限定可改范围
- 密钥/凭证/API Key 不得硬编码
- 不用不可信输入拼接 shell 命令

## Change Delivery Gate

声明完成、准备 commit / push / PR 之前必须满足：

1. 已完成相关验证，并如实报告结果
2. 已过对应质量门禁（review / verification）
3. 关键验证无法执行时必须明确说明原因
4. 禁止虚构命令输出
5. 没有验证证据，不得声称"通过" / "完成"

## superpowers Skills 使用

只走 superpowers：
- brainstorming / writing-plans / executing-plans
- test-driven-development / systematic-debugging / verification-before-completion
- requesting-code-review / receiving-code-review
- subagent-driven-development / using-git-worktrees
- finishing-a-development-branch

## 回复语言

**每次回答必须使用中文!**