# 浏览器概览 MCP 工具设计

日期：2026-04-11
状态：已确认，待审阅

## 背景

当前闲鱼 MCP 已经具备登录、搜索、发布、会话检查等能力，但缺少一个面向诊断和观察的只读工具，无法直接看到当前 Playwright 浏览器里有多少个 `BrowserContext`，以及每个 `context` 下有哪些页面。

最近仓库已经在推进页面生命周期治理，例如引入 `PageCoordinator` 和更清晰的页面租约模型。新增的浏览器概览工具应当复用现有分层，不把 Playwright 细节散落到多个 MCP 入口中。

## 目标

本次设计的目标如下：

- 新增一个 MCP 工具，用于查询当前浏览器概览
- 返回当前 `browser.contexts` 的数量
- 返回所有 `BrowserContext` 下的页面列表
- 每个页面返回 `title` 和 `url`
- 同时支持 `mcp_server/server.py` 和 `mcp_server/http_server.py`
- 在现有架构下做最小必要改动

## 非目标

本次不做以下内容：

- 不新增多浏览器实例管理
- 不返回页面角色名，如 `work`、`keepalive`、`session`
- 不区分活动页面或前台标签页
- 不返回额外调试字段，如 `context_index`、连接耗时、页面 ID
- 不重构现有页面协调逻辑

## 方案选型

### 方案 A：查询逻辑放在 `AsyncChromeManager`，应用层透传（推荐）

由 `src/browser.py` 直接读取 Playwright 的 `browser.contexts` 和 `context.pages`，组装精简结构；`XianyuApp` 仅做透传；两个 MCP 入口共同复用该方法。

优点：

- 浏览器状态读取职责留在浏览器层
- `XianyuApp` 继续保持统一业务入口
- `stdio` 和 `http` 两个 MCP 入口不会复制浏览器遍历逻辑
- 后续如果要补充页面级观测字段，可以继续在同一层扩展

缺点：

- 需要补一层从浏览器到应用层的透传方法

### 方案 B：查询逻辑放在 `XianyuApp`

由 `src/core.py` 直接访问 `app.browser.browser.contexts` 并组装返回值。

优点：

- 改动量也不大

缺点：

- `XianyuApp` 会知道过多 Playwright 底层细节
- 边界比方案 A 更弱

### 方案 C：查询逻辑直接写在 MCP 入口

由 `mcp_server/server.py` 和 `mcp_server/http_server.py` 分别读取浏览器对象并各自组装 JSON。

优点：

- 上手最快

缺点：

- 两个入口会复制逻辑
- 后续维护成本最高
- 不符合当前仓库统一经由 `XianyuApp` 的趋势

结论：采用方案 A。

## 工具命名与接口

建议新增工具名：`xianyu_browser_overview`

工具描述：获取当前浏览器 context 数量，以及各 context 下页面标题和 URL。

该工具不需要输入参数。

成功返回结构：

```json
{
  "success": true,
  "browser_context_count": 2,
  "contexts": [
    {
      "page_count": 2,
      "pages": [
        {
          "title": "闲鱼",
          "url": "https://www.goofish.com/"
        },
        {
          "title": "发布",
          "url": "https://www.goofish.com/publish"
        }
      ]
    }
  ]
}
```

失败返回结构：

```json
{
  "success": false,
  "message": "浏览器未连接，无法获取概览"
}
```

## 分层设计

### `src/browser.py`

新增一个只读异步方法，例如 `get_browser_overview()`。

职责：

- 确认浏览器连接可用
- 读取 `browser.contexts`
- 遍历每个 `context.pages`
- 为每个页面提取 `title` 和 `url`
- 组装并返回精简结构

这里不负责 MCP 文本包装，也不负责额外业务语义解释。

### `src/core.py`

在 `XianyuApp` 中新增对应方法，例如 `browser_overview()`，只负责调用 `self.browser.get_browser_overview()` 并返回结果。

这样可以保持：

- 对外业务入口仍然统一收口在 `XianyuApp`
- MCP 入口不直接访问 Playwright 内部对象

### `mcp_server/server.py`

- 在 `list_tools()` 中注册 `xianyu_browser_overview`
- 在 `call_tool()` 中接入对应分支
- 新增 `handle_browser_overview()`
- 返回 JSON 字符串结果

### `mcp_server/http_server.py`

- 新增 `@mcp.tool()` 装饰的 `xianyu_browser_overview()`
- 调用 `app.browser_overview()`
- 返回 JSON 字符串结果

## 数据采集规则

### `BrowserContext` 数量

只统计当前 Playwright `browser.contexts` 的数量，即当前浏览器实例中已存在的 context 数量。

不统计：

- 未来可能存在但尚未创建的 context
- 外部概念上的“浏览器窗口数”

### 页面范围

返回所有 `browser.contexts` 下的全部页面，并按 `context` 分组。

每个分组包含：

- `page_count`
- `pages`

每个页面包含：

- `title`
- `url`

不额外返回 `context_index` 或页面内部标识。

## 错误处理

### 浏览器未连接

调用时先确保底层连接可用。如果浏览器无法连接成功，则整次请求返回失败：

- `success: false`
- `message: 浏览器未连接，无法获取概览`

这符合本次需求中“未连接视为错误，而不是空数据”的约定。

### 浏览器对象存在但 `contexts` 不可读

这也视为失败，而不是回退为空列表。因为该工具的目的之一是诊断当前浏览器状态，空结构会掩盖真实问题。

### 单个页面标题读取失败

`page.title()` 可能因页面关闭、导航中断或瞬时异常失败。此时不让整个工具失败，而是仅对当前页面降级：

- `title` 回退为空字符串 `""`
- `url` 仍尽量返回 `page.url`

原因是页面标题属于附加展示信息，失败不应影响整个浏览器概览可用性。

## 并发与副作用

该工具为纯只读查询：

- 不创建新页面
- 不关闭页面
- 不修改现有页面状态
- 不改变现有页面协调策略

它只读取当前浏览器已存在的 `context` 和 `page` 信息，因此不会影响搜索、发布、登录、保活等已有流程。

## 测试设计

本次只补最小必要测试。

### 浏览器层单元测试

验证 `get_browser_overview()` 在多个 `context`、多个页面时能够正确返回：

- `browser_context_count`
- 每个 context 的 `page_count`
- 每个页面的 `title`
- 每个页面的 `url`

### 页面标题异常回退测试

构造一个 fake page，让 `title()` 抛异常，确认：

- 整体结果仍成功返回
- 该页面 `title` 为空字符串
- `url` 被保留

### MCP 入口测试

参考现有 `tests/test_http_server_unit.py` 的风格，补充：

- 新工具已注册
- MCP 入口调用后能返回 JSON 文本
- 当应用层抛异常时，入口返回错误结果而不是崩溃

## 验收标准

满足以下条件即可认为本次实现完成：

1. `xianyu_browser_overview` 在 `stdio` 和 `http` 两个 MCP 入口都可见
2. 已连接浏览器时，能正确返回 `browser_context_count`
3. 能返回所有 `browser.contexts` 下的页面，并按 `context` 分组
4. 每个页面包含 `title` 和 `url`
5. 浏览器未连接时返回失败信息，而不是空结构
6. 页面标题读取失败时仅该字段降级，不影响整体结果
7. 新增测试通过，且不影响现有工具行为
