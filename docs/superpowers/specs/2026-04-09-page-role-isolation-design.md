# 页面角色隔离设计

日期：2026-04-09

## 背景

当前项目中的搜索、会话管理、发布/详情抓取大多共享同一个业务页面引用（`self.page` / `work_page`）。这会导致不同类型任务在并行执行时互相污染：

- `check_session()` 导航首页，可能打断正在执行的搜索
- `publish()` 或 `get_detail()` 打开商品页，可能污染搜索页上下文
- 搜索过程中的监听器、翻页、页面清理逻辑，可能被其他任务打断

实际现象已经出现：并行执行 `check_session` 与 `search` 时，搜索页被会话检查改写，导致超时、空结果或跑偏结果。

## 目标

第一阶段目标是让以下三类任务可并行执行，并且使用不同页面隔离：

- 搜索
- 会话管理（登录、会话检查、刷新 token、显示二维码）
- 发布/详情抓取

同时保留已有保活页面，不与业务页面混用。

## 非目标

本次不做以下事情：

- 不切换到多 BrowserContext 架构
- 不引入多浏览器实例
- 不重写搜索算法或发布流程本身
- 不以“全局串行队列”代替真正并行

## 方案选型

### 方案 A：单 Context，多固定角色页（推荐）

在同一个 `BrowserContext` 下维护多个长期复用的角色页面：

- `search_page`
- `session_page`
- `publish_page`
- `keepalive_page`

优点：

- 改动最小，贴合现有 `keepalive_page` 设计
- 登录态与 Cookie 天然共享
- 最容易在当前架构上稳定落地

缺点：

- 仍共享同一个 `BrowserContext`，个别全局副作用仍需注意

### 方案 B：多 Context 隔离

优点：

- 隔离更彻底

缺点：

- 登录态同步复杂
- 资源更重
- 超出当前最小改动范围

### 方案 C：全局串行队列

优点：

- 实现简单

缺点：

- 不满足并行目标

结论：采用方案 A。

## 页面角色模型

### 页面定义

浏览器管理器新增并维护以下固定角色页：

- `search_page`：专门用于商品搜索及搜索结果分页
- `session_page`：专门用于登录、会话检查、刷新 token、二维码展示
- `publish_page`：专门用于商品详情抓取与复制发布
- `keepalive_page`：专门用于后台保活

这些页面在 `BrowserContext` 生命周期内长期复用，不在每次调用时创建临时页。

### 生命周期规则

页面按需懒创建：

- 第一次请求某个角色页时创建
- 后续同角色任务复用该页
- 如果该页已被关闭或不在 `context.pages` 中，则重新创建

### 复用前清理规则

每个角色页在任务开始前执行自己的轻量清理，而不是由其他角色统一清理：

- `search_page`：允许回到首页或空白页后再进入搜索页，确保旧搜索监听器和旧页面状态不复用
- `session_page`：回到首页，确保二维码/登录检查在干净页面进行
- `publish_page`：必要时关闭弹窗，必要时回到空白页或商品/发布入口页
- `keepalive_page`：维持现有保活行为

## 并发与锁模型

### 现状问题

当前 `XianyuApp` 使用单个 `_work_lock`，本质上是假设所有业务操作共享一个工作页。

### 新锁模型

拆分为按角色的锁：

- `search_lock`
- `session_lock`
- `publish_lock`

规则：

- 同类任务串行
- 异类任务并行

具体表现：

- 两个搜索请求不能同时操作 `search_page`
- 两个会话管理请求不能同时操作 `session_page`
- 两个发布/详情请求不能同时操作 `publish_page`
- 搜索 与 会话管理 可并行
- 搜索 与 发布/详情 可并行
- 会话管理 与 发布/详情 可并行

`keepalive_page` 保持后台任务独立运行，不占用业务锁。

## 模块改动设计

### `src/browser.py`

新增明确的页面访问器：

- `get_search_page()`
- `get_session_page()`
- `get_publish_page()`
- 保留 `get_keepalive_page()`

兼容策略：

- `get_work_page()` 可以暂时保留，但内部不再作为核心业务入口
- `self.page` 不再作为业务共享状态的真实来源

目标是让业务模块显式拿到自己的角色页，而不是隐式依赖“当前页”。

### `src/core.py`

调整业务入口：

- `search_with_meta()`：拿 `search_page`，使用 `search_lock`
- `login()` / `show_qr_code()` / `refresh_token()` / `check_session()`：拿 `session_page`，使用 `session_lock`
- `publish()` / `get_detail()`：拿 `publish_page`，使用 `publish_lock`

### `src/session.py`

所有当前通过 `self.chrome_manager.page` 访问页面的逻辑，改为显式拿 `session_page`。

这样可保证：

- 会话检查不会打断搜索
- 二维码监听不会污染发布页或搜索页

### 搜索与发布实现类

搜索与发布内部实现不应继续偷读全局页面引用，而应在构造时或调用时拿到目标页。

建议改成：

- 搜索实现类显式绑定 `search_page`
- 发布/详情实现类显式绑定 `publish_page`

## 数据与状态边界

共享的只有：

- 同一个 `BrowserContext`
- Cookie
- 登录态

不共享的包括：

- 页面实例
- 页面监听器
- 页面导航历史
- 页面上的临时 DOM 状态

这意味着“共享登录态，但不共享任务现场”。

## 兼容性要求

对外工具接口不变：

- `xianyu_check_session`
- `xianyu_login`
- `xianyu_show_qr`
- `xianyu_search`
- `xianyu_publish`
- `xianyu_refresh_token`

本次改动只调整内部页面调度与并发隔离，不改变外部 API 形态。

## 测试设计

### 单元测试

新增或调整以下验证：

1. 页面角色隔离
- `search_page`、`session_page`、`publish_page`、`keepalive_page` 均为不同页面实例

2. 页面复用
- 同一角色重复获取时应复用同一页面
- 页面被关闭后应重新创建

3. 锁粒度
- 同类任务共享同一锁
- 异类任务使用不同锁

4. 会话与搜索并发隔离
- 会话检查和搜索同时执行时，应分别使用不同 page

5. 搜索与发布并发隔离
- 发布/详情抓取不会改写搜索 page

### 集成验证

至少验证以下场景：

1. 搜索中同时执行 `check_session`
- 搜索不应超时或被主页导航打断

2. 搜索中同时执行 `publish` 或 `get_detail`
- 搜索结果页不应被商品详情/发布页污染

3. 保活运行时执行搜索和会话检查
- 保活不应影响业务页行为

## 风险与缓解

### 风险 1：旧代码仍通过 `self.page` 间接共享页面

缓解：

- 逐步消除业务逻辑对 `self.page` 的隐式依赖
- 在关键模块中改为显式传 page

### 风险 2：同类任务并发仍会互相覆盖监听器

缓解：

- 同角色维持串行锁
- 不允许同一角色页同时跑多个任务

### 风险 3：页面长期复用导致脏状态累积

缓解：

- 每个角色页在任务前做轻量清理
- 页面异常时允许重建该角色页

## 预期结果

完成后应达到：

- `check_session` 与 `search` 可以并行执行，不互相打断
- `search` 与 `publish/get_detail` 可以并行执行，不互相污染
- 保活页继续独立运行
- 外部 API 保持不变
- 页面角色边界清晰，可继续扩展更多并发任务类型
