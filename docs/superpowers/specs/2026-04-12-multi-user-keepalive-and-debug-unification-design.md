# Multi-User Keepalive And Debug Unification Design

## Goal

统一当前闲鱼 MCP 的运行模型：

- 保留调试能力
- 移除单用户 `default` 运行时对保活和调试结果的干扰
- 让保活只服务于多用户体系
- 让调试入口与正式 MCP 工具共用同一套多用户 runtime 和状态来源
- 删除冗余的 `show_qr` 能力，统一到 `login`

## Current Problem

当前代码同时存在两套路径：

1. 多用户主路径：`mcp_server/http_server.py` -> `MultiUserManager`
2. 单用户兼容路径：`mcp_server/server.py` 和 `http_server.py:get_app()` -> `XianyuApp`

这导致以下问题：

- `default` 用户通过单用户路径自动启动 keepalive
- `user-001` 等多用户通过 `MultiUserManager` 查询状态
- `get_user_status()` 中的 `keepalive_running`、`last_keepalive_at`、`last_cookie_updated_at` 与真实运行态不一致
- 调试入口和正式 MCP 看到的不是同一套状态
- `xianyu_show_qr` / `/rest/show_qr` 与 `login` 语义重复

## Scope

本次设计包含：

- 多用户 keepalive 生命周期收口到 `MultiUserManager`
- 调试入口改为多用户模型
- stdio MCP 入口不再启动单用户 `default` runtime
- 删除 `xianyu_show_qr` 和 `/rest/show_qr`
- 将登录和二维码语义统一到 `login`
- 更新相关文档与回归流程

本次设计不包含：

- 改造浏览器池调度策略
- 新增新的用户状态持久化存储结构
- 调整搜索、发布等业务逻辑本身

## Design Decisions

### 1. Keepalive only belongs to multi-user runtime

- 不再允许单用户 `get_app()` 自行启动后台保活
- 每个 `user_id` 对应一个 runtime
- 每个 runtime 最多一个 keepalive 任务
- `default` 不再作为隐式保活用户

### 2. Debug entrypoints use the same runtime as production tools

以下调试能力保留，但内部统一走 `MultiUserManager`：

- stdio MCP 工具入口
- `/rest/check_session`
- `/rest/login`
- `/rest/search`
- `xianyu_browser_overview`

这些入口支持：

- 显式传 `user_id`
- 不传 `user_id` 时自动选一个 `ready` 且 `enabled` 的用户
- 返回实际命中的 `user_id`、`slot_id` 和选择方式

### 3. Login becomes the only QR entry

- `xianyu_login` 成为唯一登录入口
- 如果目标用户已登录，直接返回已登录状态
- 如果目标用户未登录，直接返回二维码
- 删除 `xianyu_show_qr`
- 删除 `/rest/show_qr`

### 4. Auto-selection rules for debug entrypoints

对支持自动选用户的调试入口：

- 传入 `user_id` 时使用显式用户
- 未传 `user_id` 时，从 `ready` 且 `enabled` 用户中选取
- 若没有可用用户，返回结构化错误 `no_available_user`

对登录入口：

- 传入 `user_id` 时，操作该用户
- 未传 `user_id` 时，只允许选择尚未登录成功的用户
- 自动选择顺序按注册表顺序挑选第一个 `enabled=true` 且不处于 `ready + cookie_valid=true` 的用户
- 如果所有用户都已登录成功且 Cookie 有效，则返回 `no_available_user`
- 不自动创建新用户

## Runtime Architecture

### MultiUserManager responsibilities

`MultiUserManager` 成为唯一的保活编排入口，负责：

- 创建/获取用户 runtime
- 启动和停止用户 keepalive
- 同步所有已就绪用户的 keepalive 状态
- 维护可查询的运行时状态

建议新增或收敛的职责边界：

- `ensure_keepalive(user_id)`
- `stop_keepalive(user_id)`
- `sync_keepalives_for_ready_users()`
- `resolve_debug_user(user_id | None)`
- `resolve_login_user(user_id | None)`

### stdio MCP behavior

如果保留 `mcp_server/server.py`，它不再维护单独的单用户 `XianyuApp`。

改为：

- 作为多用户实现的薄包装层，复用 `MultiUserManager`
- 暴露与 HTTP MCP 一致的工具语义
- 不在进程启动时自动创建单用户 app
- 不在启动阶段自动启动 `default` keepalive

### Service startup behavior

服务启动后：

1. 初始化 `MultiUserManager`
2. 遍历注册表中 `enabled` 用户
3. 检查其 session 状态
4. 对 `valid=true` 的用户启动 keepalive
5. 对 `valid=false` 的用户保留 `pending_login`

此时不再启动任何单用户 `default` keepalive。

## Keepalive Lifecycle

### Start conditions

以下场景确保启动对应用户的 keepalive：

- `login(user_id)` 成功并进入 `ready`
- `check_session(user_id)` 返回 `valid=true`
- `refresh_token(user_id)` 成功
- 服务启动后的 ready 用户同步

### Stop conditions

以下场景停止对应用户的 keepalive：

- `check_session(user_id)` 返回 `valid=false`
- 用户被禁用
- 用户 runtime 被显式关闭
- 服务 shutdown

### Keepalive state source of truth

`get_user_status()` 返回的以下字段必须和真实运行态一致：

- `keepalive_running`
- `last_keepalive_at`
- `last_keepalive_status`
- `last_cookie_updated_at`
- `last_error`

状态来源规则：

- `keepalive_running` 基于真实 keepalive task 是否存在且未结束
- `last_keepalive_at` 在每次 keepalive `run_once()` 成功执行后更新
- `last_keepalive_status` 记录 `ok` 或 `error`
- `last_cookie_updated_at` 在 cookie 成功保存后更新
- `last_error` 保存最近一次保活或 session 相关异常

## Debug Interface Behavior

### `/rest/check_session`

- 支持 `user_id` 可选参数
- 显式传入时检查指定用户
- 未传时自动选一个 `ready` 用户
- 返回：
  - `success`
  - `user_id`
  - `slot_id`
  - `selected_by`
  - `valid`
  - `last_updated_at`

### `/rest/login`

- 替代原 `/rest/show_qr`
- 支持 `user_id` 可选参数
- 显式传入时对指定用户执行 `login`
- 未传时按登录入口规则自动选一个尚未登录成功的用户
- 返回：
  - `success`
  - `user_id`
  - `slot_id`
  - `selected_by`
  - `logged_in`
  - `qr_code`（如果未登录）
  - `message`

### `/rest/search`

- 支持 `user_id` 可选参数
- 未传时自动选一个 `ready` 用户
- 返回搜索结果时同时返回实际命中的 `user_id`、`slot_id`、`selected_by`

### `xianyu_browser_overview`

- 不再走单用户 `get_app()`
- 优先支持指定 `user_id` 查看对应 runtime 的浏览器页面
- 未传 `user_id` 时返回所有已初始化 runtime 的 overview 汇总
- 为了避免副作用，未传 `user_id` 时不创建新的 runtime
- 无论哪种模式，都不能再触发单用户 `default` keepalive

## API and Contract Changes

### Remove

- MCP 工具：`xianyu_show_qr`
- REST 调试接口：`/rest/show_qr`

### Keep

- `xianyu_login`
- `xianyu_check_session`
- `xianyu_search`
- `xianyu_publish`
- `xianyu_browser_overview`
- `/rest/login`
- `/rest/check_session`
- `/rest/search`

### Response additions

调试入口统一补充：

- `user_id`
- `slot_id`
- `selected_by: "explicit" | "auto"`

### Breaking change

这是一次有意的破坏性变更：

- `tools/list` 中不再出现 `xianyu_show_qr`
- `/rest/show_qr` 不再存在
- 所有文档和回归命令改用 `login`

## Migration Plan

### Code migration

1. 去掉 `http_server.py` 中对单用户 `get_app()` 的依赖
2. 收敛 keepalive 的启动与状态维护到 `MultiUserManager`
3. 删除 `xianyu_show_qr` 和 `/rest/show_qr`
4. 将 `xianyu_browser_overview` 改为多用户实现
5. 为调试入口补充自动选用户逻辑

### Documentation migration

需要同步更新：

- `README.md`
- `docs/mcp-e2e-regression.md`
- `docs/mcp-dev-cheatsheet.md`
- `docs/opencode-setup.md`
- `docs/claude-code-setup.md`
- `.claude/skills/xianyu-skill/SKILL.md`

文档更新要求：

- 不再提 `show_qr`
- 所有登录流程统一表述为：`login -> 未登录返回二维码 -> 扫码后 check_session`
- E2E 回归中二维码链路验证改为 `xianyu_login`
- 明确调试入口已是多用户模型，不再依赖 `default`

## Risks

### 1. Existing clients may still call `xianyu_show_qr`

影响：调用方会因工具不存在而失败。

处理方式：

- 文档同步更新
- 回归中明确验证工具列表变化

### 2. Auto-selected debug user may be non-deterministic

影响：不传 `user_id` 时不同请求可能落到不同 ready 用户。

处理方式：

- 响应中始终回传实际使用的 `user_id`
- 文档中建议需要稳定复现时显式传 `user_id`

### 3. Keepalive state may still drift if writes are incomplete

影响：`get_user_status()` 仍可能和真实状态不一致。

处理方式：

- 所有 keepalive 和 session 关键路径统一回写 runtime 状态
- 验证中覆盖状态一致性检查

## Validation

实现后至少验证以下内容：

1. `xianyu_show_qr` 已从工具列表删除
2. `/rest/show_qr` 已不存在
3. `xianyu_login(user_id)` 对未登录用户返回二维码
4. `xianyu_login(user_id)` 对已登录用户直接返回已登录状态
5. 调试入口不传 `user_id` 时自动选择可用用户
6. 若没有可用用户，返回 `no_available_user`
7. 多用户 ready 用户的 keepalive 会自动启动
8. `default` 用户不再因为兼容层入口被隐式保活
9. `get_user_status(user_id)` 中的 keepalive 与 cookie 时间字段与真实运行态一致
10. 相关文档与回归步骤已全部切换到 `login`

## Acceptance Criteria

- 系统不再依赖单用户 `default` runtime 作为保活来源
- 保活只在多用户 runtime 中运行，并绑定真实 `user_id`
- 调试入口与正式 MCP 工具共享同一套多用户状态和浏览器上下文
- `xianyu_show_qr` 与 `/rest/show_qr` 被删除
- `login` 成为唯一二维码入口
- 文档、技能说明、回归手册与代码行为一致
