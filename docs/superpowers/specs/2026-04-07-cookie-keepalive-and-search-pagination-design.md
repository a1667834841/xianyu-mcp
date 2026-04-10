# 闲鱼 Cookie 持久化、后台保活与搜索分页修复设计

日期: 2026-04-07
状态: 待审阅

## 1. 背景

当前项目有三个直接相关的问题：

1. Cookie/Token 持久化路径与 Docker 挂载目录没有打通。代码默认写入 `~/.claude/...`，而不是显式写入宿主机持久化目录。
2. Cookie 刷新只有一次性手动流程，没有进程内常驻后台保活任务。
3. 搜索请求传入大于 30 的 `rows` 时，结果经常只返回约 30 条，说明翻页后的新结果没有被稳定采集。

本设计将这三个问题放在同一个会话生命周期方案中处理。

## 2. 目标

### 2.1 功能目标

- Cookie 和 Chrome profile 都必须可持久化到宿主机目录。
- 支持进程内常驻后台任务，按可配置间隔刷新页面并获取最新 Cookie。
- 后台保活必须通过刷新页面完成，不允许改成直接刷新接口。
- 搜索中的 `rows` 语义统一为“目标唯一商品总数”。
- 搜索未达到目标数量时，继续翻页，直到凑够目标数量或触发停止条件。
- 搜索停止条件采用“连续 N 页没有新增唯一商品”，且 `N` 可配置。

### 2.2 约束

- 后台保活页与业务页必须隔离，互不影响。
- 保活失败只记录日志，不中断服务，也不强制让用户重新登录。
- 配置支持环境变量；环境变量优先于 `config.json`。
- MCP Server 配置中也必须能传入相关环境变量。
- 目录结构要兼容未来多用户扩展。

### 2.3 非目标

- 本轮不实现真正的多用户调度和租户隔离，只预留目录结构和配置入口。
- 本轮不改变闲鱼登录方式，不新增自动扫码或自动重新登录能力。
- 本轮不引入新的外部调度系统，后台保活仍由 `mcp-server` 进程内异步任务承担。

## 3. 方案概览

推荐方案为：单浏览器上下文、双页面分工、宿主机持久化目录重构、搜索请求串行化。

核心思路如下：

- 共享一个浏览器 `context`，保证登录态天然共享。
- 固定维护两个页面：
  - `work_page`：登录、搜索、发布等业务操作专用
  - `keepalive_page`：仅用于定时访问/刷新闲鱼首页并提取最新 Cookie
- `mcp-server` 启动后创建一个后台保活任务，只操作 `keepalive_page`
- 宿主机持久化采用多用户兼容目录结构：`/data/users/<user_id>/...`
- 搜索请求在 `work_page` 上串行执行，保证每次搜索拥有独立的翻页窗口和响应采集状态

## 4. 持久化与目录设计

### 4.1 目录结构

容器内统一采用以下固定结构：

```text
/data/users/<user_id>/
  chrome-profile/
  tokens/
    token.json
```

默认 `user_id=default`。

### 4.2 数据归属

- `browser` 容器负责真实浏览器 profile：
  - `/data/users/<user_id>/chrome-profile`
- `mcp-server` 容器负责程序侧 Cookie 快照：
  - `/data/users/<user_id>/tokens/token.json`

这样可以明确区分：

- 浏览器真实登录态：由 Chrome profile 维护
- 程序缓存快照：由 `SessionManager` 写入 JSON 文件

### 4.3 Docker 挂载要求

Docker Compose 中宿主机挂载目录允许重新指定，但容器内路径固定。

建议宿主机根目录通过单独变量配置，例如：

```text
${XIANYU_HOST_DATA_DIR}/users/<user_id>/chrome-profile -> browser:/data/users/<user_id>/chrome-profile
${XIANYU_HOST_DATA_DIR}/users/<user_id>/tokens         -> mcp-server:/data/users/<user_id>/tokens
```

关键修正点：

- `chrome-profile` 必须挂到 `browser` 服务，而不是 `mcp-server`
- `browser` 服务必须显式使用该 profile 目录作为 Chrome 的 `--user-data-dir`
- `mcp-server` 不再假定自身本地的 `user_data_dir` 能控制远端 CDP 浏览器

## 5. 配置设计

### 5.1 配置优先级

统一采用以下优先级：

1. 环境变量
2. `config.json`
3. 默认值

### 5.2 新增配置项

```json
{
  "storage": {
    "data_root": "/data/users",
    "user_id": "default",
    "token_file": "",
    "chrome_user_data_dir": ""
  },
  "keepalive": {
    "enabled": true,
    "interval_minutes": 10
  },
  "search": {
    "max_stale_pages": 3
  }
}
```

说明：

- `token_file` 和 `chrome_user_data_dir` 允许显式覆盖
- 如果未显式设置，则由 `data_root + user_id` 推导
- `rows` 不是全局配置项，而是单次搜索请求参数

### 5.3 对应环境变量

- `XIANYU_DATA_ROOT`
- `XIANYU_USER_ID`
- `XIANYU_TOKEN_FILE`
- `XIANYU_CHROME_USER_DATA_DIR`
- `XIANYU_KEEPALIVE_ENABLED`
- `XIANYU_KEEPALIVE_INTERVAL_MINUTES`
- `XIANYU_SEARCH_MAX_STALE_PAGES`

这些变量既可由 Docker Compose 注入，也可由 MCP Server 运行环境注入。

## 6. 会话与页面架构

### 6.1 浏览器结构

共享单个浏览器 `context`，其下维护两个长期页面：

```text
Browser
└── Context(shared cookies/session)
    ├── work_page
    └── keepalive_page
```

原因：

- 两个页面共享 Cookie 和登录态
- `keepalive_page` 刷新后产生的最新 Cookie 会自然作用于整个会话
- 不会因为保活而刷新掉业务操作中的页面内容

### 6.2 页面职责

`work_page`

- 登录二维码展示
- 搜索与翻页
- 发布流程
- 其他前台业务交互

`keepalive_page`

- 首次打开闲鱼首页
- 周期性执行 `page.reload()`
- reload 后读取最新完整 Cookie
- 将 Cookie 快照写回持久化文件

### 6.3 生命周期

- `mcp-server` 初始化应用实例时，确保 `context` 就绪
- 首次需要会话操作时，创建或复用 `work_page`
- 服务启动后尽早创建 `keepalive_page`
- 服务退出时，显式取消后台保活任务并关闭浏览器连接

## 7. 后台保活设计

### 7.1 保活触发方式

后台保活任务由 `mcp-server` 进程内异步任务实现，服务启动后常驻运行。

仅允许通过页面刷新实现 Cookie 更新：

1. 若 `keepalive_page` 尚未初始化，先访问 `https://www.goofish.com`
2. 之后按配置间隔执行 `keepalive_page.reload()`
3. reload 完成后，从共享 `context` 重新提取完整 Cookie 字符串
4. 将 Cookie 快照写入持久化文件

### 7.2 失败策略

- 未拿到有效 Cookie：只记录日志
- 页面刷新失败：只记录日志
- 文件写入失败：只记录日志
- 不终止服务
- 不自动触发重新登录
- 不改变相关 MCP 工具当前的返回语义

### 7.3 写盘策略

建议 `token.json` 至少包含以下字段：

```json
{
  "full_cookie": "...",
  "created_at": "2026-04-07T10:00:00+08:00",
  "updated_at": "2026-04-07T12:00:00+08:00",
  "last_refresh_at": "2026-04-07T12:00:00+08:00",
  "expires_at": "2026-04-08T12:00:00+08:00"
}
```

写盘规则：

- 第一次写入时创建文件
- Cookie 内容变化时更新 `full_cookie`、`updated_at`、`last_refresh_at`
- Cookie 内容未变化时至少更新 `last_refresh_at`

## 8. 搜索语义与分页设计

### 8.1 语义修正

`rows` 的定义统一为：

- 本次请求希望最终返回的“唯一商品总数”

不再使用“每页数量”的描述。

### 8.2 搜索主流程

搜索流程调整为：

1. 在 `work_page` 上发起搜索
2. 为本次搜索建立独立的响应采集状态
3. 解析第一页搜索结果
4. 若唯一商品数未达到 `rows`，执行翻页
5. 每翻一页，只接受翻页后产生的新响应
6. 对结果按 `item_id` 去重
7. 若累计唯一商品数达到 `rows`，立即返回前 `rows` 条
8. 若连续 `N` 页没有新增唯一商品，则停止并返回当前结果，同时标记停止原因

### 8.3 停止条件

停止条件采用：

- 连续 `N` 页没有新增唯一商品

默认建议值：

- `N = 3`

配置来源：

- `XIANYU_SEARCH_MAX_STALE_PAGES`
- `config.json.search.max_stale_pages`

### 8.4 响应采集原则

为避免当前“请求 100 但常停在 30”的问题，必须满足以下约束：

- 每次翻页后的响应必须与本轮翻页动作关联
- 不能把旧响应重新当作新页数据解析
- 不能依赖页面上残留的历史监听器
- 每次搜索结束后，必须清理本次搜索的页面监听器或将监听器封装为一次性作用域

### 8.5 翻页与校验

翻页逻辑需要显式校验以下事实：

- 翻页按钮确实存在且可用
- 点击或滚动后，页面状态确实变化
- 监听到的新响应确实出现在本次翻页之后

如果翻页动作未带来新的搜索响应，则本页计入一次“无新增页”，而不是直接重复解析旧数据。

### 8.6 并发约束

搜索必须串行化到 `work_page`。

原因：

- 当前 HTTP 模式使用全局 `XianyuApp`
- 多个搜索若共用同一业务页和同一响应监听器，会相互污染
- 搜索、登录、发布也都依赖同一个前台页面

因此设计要求：

- `work_page` 上的业务操作必须经过显式锁或串行执行器
- `keepalive_page` 不参与该锁争用，因为它不操作 `work_page`

## 9. 错误处理

### 9.1 后台保活

| 场景 | 处理 |
|------|------|
| 页面刷新失败 | 记录日志，等待下轮 |
| 未登录或拿不到 Cookie | 记录日志，等待下轮 |
| Cookie 写盘失败 | 记录日志，等待下轮 |

### 9.2 搜索

| 场景 | 处理 |
|------|------|
| 第 1 页超时且无数据 | 返回空结果，并带失败原因 |
| 后续翻页无新响应 | 计入一次 stale page |
| 连续 stale page 达到阈值 | 停止搜索，返回当前累计结果 |
| 页面结构变化导致翻页失败 | 计入一次 stale page，并记录日志 |

## 10. 测试设计

### 10.1 单元测试

- 路径解析优先级：环境变量 > `config.json` > 默认值
- `user_id=default` 时的默认目录推导
- Cookie 快照写盘字段更新逻辑
- 后台保活只使用 `keepalive_page`
- 搜索 stale page 计数逻辑
- 搜索达到 `rows` 后立即停止

### 10.2 集成测试

- Docker 环境下 token 文件路径确实落在 `/data/users/default/tokens/token.json`
- `browser` 容器 profile 路径确实落在 `/data/users/default/chrome-profile`
- 连续多页响应时，可凑满大于 30 的目标数量
- 连续多页无新增时，可按阈值停止
- 重复多次搜索后，不会出现监听器残留污染

### 10.3 回归测试

- 登录二维码流程不受影响
- `refresh_token` 和 `check_session` 仍然可用
- 发布流程仍通过 `work_page` 正常工作

## 11. 分阶段实施建议

建议实施顺序如下：

1. 先统一路径解析与配置优先级
2. 修正 Docker Compose 挂载与 browser profile 目录
3. 引入双页面模型和后台保活任务
4. 重构搜索响应监听与翻页逻辑
5. 补齐测试与日志

这样可以先解决持久化错误，再处理后台保活，最后修复搜索分页，降低联动风险。

## 12. 风险与取舍

- 双页面模型增加了浏览器管理复杂度，但可以避免保活打断业务页，这是必要复杂度。
- 搜索改成串行化后，并发吞吐会下降，但当前架构本来就是单浏览器单会话模型，串行化更符合事实。
- 未来如果扩展真正多用户，应在此基础上演进为“每个用户独立浏览器上下文或独立浏览器实例”，本设计已为目录层做了兼容准备。

