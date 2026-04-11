# 多用户浏览器池设计

日期：2026-04-11

## 背景

当前项目采用单用户运行模型：

- `src/settings.py` 只解析一个 `user_id`
- `mcp_server/http_server.py` 只维护一个全局 `XianyuApp` 实例
- 浏览器部署为单个 `browser` 容器、单个 CDP 端口、单个 Chrome Profile
- Cookie 保活、搜索、发布、会话检查都围绕同一套登录态工作

这套架构适合单账号，但无法满足以下新需求：

- 同一个服务长期维护多个闲鱼账号
- 同时保活多个账号的 Cookie
- 能看到每个账号的 Cookie / 登录状态
- `publish` 必须指定账号执行
- `search` 可以不指定账号，由系统从可用账号中随机挑一个执行
- 业务操作一次只允许一个账号执行，避免多账号任务并发造成资源争用和行为混乱

用户还明确要求尽量保留单个浏览器容器，不希望按“一用户一容器”扩展。

## 目标

本次设计目标如下：

1. 在单个 `browser` 容器中同时承载多个独立 Chrome 实例
2. 每个账号拥有独立的浏览器实例、独立的 Profile、独立的 Cookie 持久化
3. 支持通过 HTTP/SSE 接口动态新增用户，并通过扫码完成登录
4. 每个已登录用户都能独立启动 Cookie 保活
5. 对外暴露每个用户的状态查询能力，包括登录态、Cookie 情况、保活状态和错误信息
6. `publish` 强制要求 `user_id`
7. `search` 支持可选 `user_id`，不传时从可用用户中随机选择一个
8. 任意时刻只允许一个业务操作执行，保活任务不受该限制

## 非目标

本次不做以下内容：

- 不做账号管理页面
- 不做自动扩容浏览器池；浏览器实例数量由启动配置决定
- 不做单 Chrome 多 `BrowserContext` 多账号方案
- 不做“一用户一 Docker 容器”方案
- 不改变搜索算法、发布流程和现有业务语义本身
- 不在本期实现用户删除、槽位迁移、热扩容浏览器进程池

## 方案选型

### 方案 A：单浏览器容器，多 Chrome 进程池（推荐）

在一个 `browser` 容器里启动固定数量的 Chrome 进程槽位。每个槽位固定绑定：

- 一个 `slot_id`
- 一个 CDP 端口
- 一个独立 Profile 目录
- 一个绑定到该槽位的 `user_id`（未占用时为空）

优点：

- 满足“多个用户同时保活”
- 保持单容器部署形态
- 每个用户仍是独立浏览器实例，隔离足够强
- 代码层依旧可以沿用“单用户实例 + 外层调度”思路

缺点：

- 浏览器容器内部需要管理多个 Chrome 子进程
- 浏览器池容量固定，新增用户超过槽位数时需要扩容配置并重启容器

### 方案 B：一用户一浏览器容器

优点：

- 隔离最强
- 每个账号的日志、资源和进程边界最清晰

缺点：

- 运维对象随用户数增长
- 与“尽量保留单个浏览器容器”的诉求不符

### 方案 C：单 Chrome，多 Context / 多页面

优点：

- 部署最简单

缺点：

- 登录态、Cookie、保活目标隔离不足
- 容易出现串号、状态污染和排障困难

结论：采用方案 A。

## 总体架构

系统拆分为四层：

1. 浏览器池层
2. 多用户调度层
3. 单用户业务层
4. HTTP/SSE/MCP 接口层

### 浏览器池层

浏览器容器在启动时按配置拉起固定数量的 Chrome 进程槽位。每个槽位对外暴露一个独立的 CDP 端点。

例如：

- `slot-1` -> `browser:9222`
- `slot-2` -> `browser:9223`
- `slot-3` -> `browser:9224`

每个槽位使用独立 Profile，互不共享 Cookie、页面状态或登录态。

### 多用户调度层

新增 `MultiUserManager` 作为服务内唯一的多用户编排入口，负责：

- 管理用户注册表
- 管理槽位分配和绑定关系
- 按 `user_id` 获取或创建单用户运行时实例
- 启停每个用户的保活任务
- 聚合所有用户状态
- 为业务操作提供全局串行控制

### 单用户业务层

保留当前 `XianyuApp`、`SessionManager`、`AsyncChromeManager`、`CookieKeepaliveService` 的单用户职责。

每个用户对应一套独立的单用户运行时：

- `AppSettings`
- `AsyncChromeManager`
- `SessionManager`
- `XianyuApp`
- `CookieKeepaliveService`

### 接口层

HTTP/SSE/MCP 入口不再直接持有单例 `_app`，而是持有单例 `MultiUserManager`。所有请求都先进入 manager，再路由到指定用户或随机选中的用户实例。

## 浏览器池模型

### 槽位定义

每个浏览器槽位包含以下固定属性：

- `slot_id`，例如 `slot-1`
- `cdp_host`，当前部署中统一为 `browser`
- `cdp_port`，例如 `9222`
- `profile_dir`，例如 `/data/browser-pool/slot-1/profile`
- `assigned_user_id`，未占用时为空
- `status`，例如 `idle`、`assigned`、`unhealthy`

### 容量配置

浏览器容器启动时通过环境变量配置进程池大小和起始端口：

- `BROWSER_POOL_SIZE`
- `BROWSER_CDP_START_PORT`

例如：

- `BROWSER_POOL_SIZE=3`
- `BROWSER_CDP_START_PORT=9222`

则容器需要启动 3 个 Chrome 实例，端口分别为 `9222`、`9223`、`9224`。

### 槽位分配规则

- 新用户创建时，从空闲槽位中分配一个槽位
- 一旦用户绑定槽位，该绑定关系持久化保存
- 用户后续重启服务后仍优先复用原槽位
- 当无空闲槽位时，新增用户接口直接返回 `no_available_browser_slot`

### 不做热扩容

第一期不支持运行中自动新增槽位。若浏览器池容量不足，需要修改启动配置并重启浏览器容器。

这是刻意限制范围的设计：先确保多用户稳定，再考虑后续扩容体验。

## 用户注册与状态模型

### 配置模型

现有 `src/settings.py` 的 `AppSettings` 继续保留给单用户实例使用。

新增两类全局能力：

1. 多用户注册表
2. 浏览器池全局配置

浏览器池全局配置负责描述：

- 数据根目录
- 浏览器池大小
- 起始 CDP 端口
- 默认保活间隔
- 默认 CDP Host

用户注册表负责描述所有已创建用户。

### 用户注册表字段

每个用户至少需要以下持久化字段：

- `user_id`
- `display_name`
- `enabled`
- `status`
- `created_at`
- `slot_id`
- `cdp_host`
- `cdp_port`
- `chrome_user_data_dir`
- `token_file`

其中：

- `user_id` 由系统自动生成，格式采用 `user-001`、`user-002`
- `display_name` 可选，若未传可与 `user_id` 一致
- `status` 用于表示 `pending_login`、`ready`、`disabled` 等状态
- `chrome_user_data_dir` 直接记录该用户绑定槽位的 `profile_dir`，两者始终是同一个目录，不额外再为用户创建第二套浏览器 Profile 目录

### 运行时状态字段

`MultiUserManager` 在内存中维护每个用户的运行时状态，至少包括：

- `browser_connected`
- `keepalive_running`
- `cookie_present`
- `cookie_valid`
- `last_cookie_updated_at`
- `last_keepalive_at`
- `last_keepalive_status`
- `last_error`
- `busy`

### Cookie 状态输出规则

系统必须让调用方知道每个用户的 Cookie 情况，但默认不直接返回完整 `full_cookie`。状态接口默认返回：

- Cookie 是否存在
- 最近更新时间
- 当前是否有效
- 是否需要重新登录
- Token 或 Cookie 摘要预览

完整 Cookie 只保存在用户自己的 `token_file` 中，不作为常规状态接口的默认响应字段。

## 用户生命周期

### 创建用户

新增用户时：

1. `MultiUserManager` 申请一个空闲槽位
2. 生成新的 `user_id`
3. 生成用户元数据并写入注册表
4. 创建对应单用户 `AppSettings`
5. 预备该用户运行时实例，但状态标记为 `pending_login`

创建成功后返回：

- `user_id`
- `slot_id`
- `cdp_port`
- `status=pending_login`

### 登录用户

登录只针对指定 `user_id` 执行。

流程：

1. 根据 `user_id` 获取该用户实例
2. 连接该用户绑定槽位的 CDP 端点
3. 调用当前单用户 `login` 或 `show_qr_code`
4. 用户扫码成功后更新状态为 `ready`
5. 自动启动该用户 keepalive

### 服务重启恢复

服务重启后：

- 从注册表恢复所有用户元数据
- 不要求立刻连接所有浏览器实例
- 在首次请求或恢复保活时按需建立运行时实例
- 已登录用户在条件满足时自动恢复保活

## 执行与并发模型

### 单用户内部并发

继续沿用当前单用户内部锁和页面协调逻辑：

- `session_lock`
- 搜索与发布相关锁
- `PageCoordinator`

这些锁仍只约束单个用户实例内部行为。

### 全局业务锁

在 `MultiUserManager` 新增一个全局业务锁，统一约束以下接口：

- `search`
- `publish`

规则：

- 任意时刻只允许一个业务操作执行
- 不区分用户，只要是业务操作就全局串行
- 会话管理和保活不占用该全局业务锁

这样可以满足“多用户同时保活，但每次只执行一个用户的相关操作”。

### 保活并发

每个已登录用户都拥有自己的 keepalive 任务：

- 只访问自己的浏览器实例
- 只读取和写入自己的 Cookie 文件
- 只更新自己的运行时状态

保活任务彼此可以并行。

## 接口设计

### 新增接口

建议新增以下多用户接口：

- `xianyu_create_user(display_name=None)`
- `xianyu_list_users()`
- `xianyu_get_user_status(user_id)`
- `xianyu_check_all_sessions()`
- 可选：`xianyu_enable_user(user_id)`
- 可选：`xianyu_disable_user(user_id)`

### 调整现有接口

- `xianyu_login(user_id)`
- `xianyu_show_qr(user_id)`
- `xianyu_check_session(user_id)`
- `xianyu_refresh_token(user_id)`
- `xianyu_publish(user_id, item_url, ...)`
- `xianyu_search(keyword, ..., user_id=None)`

### 用户选择规则

#### `publish`

- `user_id` 必填
- 若用户不存在、被禁用或未登录，直接返回明确错误

#### `search`

- `user_id` 可选
- 若指定 `user_id`，则在该用户实例上执行
- 若未指定，则从可用用户集合中随机选择一个
- 响应中必须带回实际使用的 `user_id` 与 `slot_id`

### 可用用户判定

随机选用户时，候选用户至少满足：

- `enabled=true`
- 已绑定槽位
- 处于 `ready` 状态
- Cookie 存在，且会话检查未明确失败

若没有可用用户，返回 `no_available_user`。

### 错误语义

统一错误码建议包括：

- `user_not_found`
- `user_disabled`
- `user_not_logged_in`
- `no_available_user`
- `no_available_browser_slot`
- `global_operation_in_progress`
- `user_busy`

## 模块改动设计

### `docker-compose.yml`

浏览器容器需要从“单 Chrome 实例”改为“多 Chrome 进程池”启动模式。

新增或调整：

- 浏览器池大小配置
- CDP 起始端口配置
- 浏览器池 Profile 目录挂载
- 健康检查策略，至少能验证主进程和部分槽位存活

### 浏览器容器启动脚本

新增浏览器池启动脚本，职责：

- 读取 `BROWSER_POOL_SIZE`
- 读取 `BROWSER_CDP_START_PORT`
- 循环拉起多个 Chrome 进程
- 为每个槽位分配固定 Profile 目录
- 在容器生命周期内管理这些子进程

### `src/browser.py`

`AsyncChromeManager` 继续只连接一个 CDP 端点，不承担多用户职责。每个用户运行时创建自己的 `AsyncChromeManager(host, port)`。

### `src/settings.py`

保留现有 `AppSettings`，新增多用户和浏览器池相关全局配置解析能力。

### `src/core.py`

`XianyuApp` 保持单用户职责，不直接感知多用户注册表和槽位分配。

### `src/session.py`

继续承担单用户会话管理逻辑，无需改成多用户类。

### `mcp_server/http_server.py`

入口从单例 `_app` 改为单例 `MultiUserManager`，所有接口调用都转发到 manager，再由 manager 转发到目标用户实例。

### 新增模块

建议新增：

- `src/browser_pool.py`：浏览器池配置与槽位模型
- `src/multi_user_registry.py`：用户注册表持久化
- `src/multi_user_manager.py`：多用户调度与运行时管理

## 数据持久化

### 浏览器数据

浏览器池的槽位 Profile 目录由浏览器容器维护，例如：

- `/data/browser-pool/slot-1/profile`
- `/data/browser-pool/slot-2/profile`
- `/data/browser-pool/slot-3/profile`

用户绑定槽位后，注册表中的 `chrome_user_data_dir` 直接指向对应槽位目录。例如：

- `user-001 -> /data/browser-pool/slot-1/profile`
- `user-002 -> /data/browser-pool/slot-2/profile`

这样浏览器池层和用户注册表层只维护一套浏览器 Profile 路径，不引入第二套用户级浏览器目录。

### 用户数据

用户级 Cookie 快照仍按用户保存，例如：

- `/data/users/user-001/tokens/token.json`
- `/data/users/user-002/tokens/token.json`

### 注册表数据

新增用户注册表文件，例如：

- `/data/registry/users.json`

该文件保存：

- 用户基本信息
- 用户与槽位绑定关系
- 各用户的静态配置映射

## 风险与缓解

### 风险 1：槽位绑定关系丢失

缓解：

- 将 `user_id -> slot_id -> cdp_port` 固定落盘
- 服务启动时优先从注册表恢复绑定关系

### 风险 2：单个 Chrome 子进程异常退出

缓解：

- 浏览器池启动脚本要能感知子进程退出
- 对异常槽位标记 `unhealthy`
- 用户状态中暴露该异常信息

### 风险 3：浏览器池容量不足

缓解：

- `create_user` 明确返回 `no_available_browser_slot`
- 不做隐式复用或挤占其他用户槽位

### 风险 4：保活与业务操作互相干扰

缓解：

- 保持“每用户独立浏览器实例”
- 保活只访问该用户自己的首页和 Cookie
- 业务串行只限制 `search` 和 `publish`

### 风险 5：旧接口仍按单用户语义使用

缓解：

- 对必须指定用户的接口做显式参数校验
- `publish` 缺失 `user_id` 时直接报错，不做默认回退

## 测试设计

### 单元测试

新增或调整以下测试：

1. 用户注册表
- 创建用户后写入注册表
- 重复加载时能恢复用户与槽位绑定

2. 槽位分配
- 有空闲槽位时正常分配
- 槽位不足时返回 `no_available_browser_slot`

3. 用户选择
- `search` 不传 `user_id` 时从可用用户中随机选择
- `publish` 不传 `user_id` 时返回错误

4. 多用户状态聚合
- 能返回所有用户的 Cookie / 保活 / 错误状态摘要

5. 全局业务串行
- 两个不同用户的 `search` / `publish` 不能并发执行

### 集成测试

至少覆盖以下场景：

1. 创建 2 到 3 个用户并分配不同槽位
2. 为多个用户分别登录成功
3. 多个用户的 keepalive 同时运行
4. 指定用户发布成功，且不会使用错误账号
5. 不指定用户搜索时能返回实际使用的 `user_id`
6. 某个用户会话失效时，不影响其他用户保活和状态查询

### 部署验证

部署后至少验证：

1. 浏览器容器启动后多个 CDP 端口可连接
2. `mcp-server` 能按用户连接到不同端口
3. 服务重启后用户注册表、槽位绑定和 Cookie 文件仍然存在

## 兼容性与迁移

### 单用户兼容

对于现有单用户部署，可通过以下方式平滑迁移：

- 浏览器池大小设置为 `1`
- 只创建一个用户 `user-001`
- 现有搜索、登录、会话行为仍保持单用户体验

### 接口兼容策略

旧接口名称尽量保留，但参数会扩展为多用户模式。调用方必须逐步适配：

- `publish` 新增必填 `user_id`
- `search` 响应新增 `user_id` 与 `slot_id`

## 结论

本次设计采用“单浏览器容器 + 多 Chrome 进程池 + 动态用户注册表 + 多用户调度器”的方案。

该方案在不增加浏览器容器数量的前提下，实现：

- 多用户同时保活
- 每用户独立浏览器实例和登录态
- 通过接口动态新增用户并扫码登录
- 指定用户发布、随机可用用户搜索
- 全局串行业务执行

这个方案的核心取舍是：通过预分配固定数量的浏览器槽位，换取多用户隔离和部署简单性。容量不足时通过调整浏览器池大小并重启容器扩容，而不是在第一期引入热扩容复杂度。
