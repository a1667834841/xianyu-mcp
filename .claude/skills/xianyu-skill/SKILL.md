---
name: xianyu-skill
description: Use when managing one or more Xianyu accounts via MCP, especially when you need to create or inspect users, verify login state, search products, copy-publish listings, or troubleshoot session issues.
---

# 闲鱼技能

## Overview

通过闲鱼 MCP 进行多用户店铺操作。核心原则：先确认要操作的 `user_id`，再执行登录、搜索、发布；不要把当前 MCP 当成单用户工具集使用。

## When to Use

- 需要查看当前有哪些闲鱼用户、哪个用户可用
- 需要创建新用户并扫码登录
- 需要检查某个用户的登录状态、Cookie、Token
- 需要按关键词搜索商品，并在结果上做二次排序
- 需要根据对标商品链接复制发布商品
- 需要排查浏览器上下文、页面空白、搜索卡住等问题

**不要用于：**
- 非闲鱼平台操作
- 需要绕过平台限制或风控的行为
- 高风险的批量频繁发布

## Core Rules

1. **先选用户，再做操作。**
   除 `xianyu_list_users` 和 `xianyu_browser_overview` 外，大多数账号相关操作都应明确知道目标 `user_id`。

2. **多用户场景下不要省略 `user_id`。**
   `xianyu_search` 虽然允许省略 `user_id`，但这只适合“任意可用账号都行”的场景。当前 MCP 会在所有 `ready` 用户里挑一个可用用户；如果没有就绪用户，会报 `no_available_user`。只要用户指定了账号，或你需要稳定复现结果，就显式传 `user_id`。

3. **搜索接口不能按曝光度排序。**
   `sort_field` 只支持 `pub_time` 和 `price`。`exposure_score` 是返回字段，不是可直接传给 MCP 的排序参数。用户要“按曝光度排行”时，先搜索，再按 `exposure_score` 在结果里二次排序。

4. **发布成功不等于一定已正式上架。**
   `xianyu_publish` 的本质是复制并填充发布表单。特殊类目（如潮玩盲盒）可能保存为草稿；`success: true` 更应理解为“采集和填充流程成功”。

## Quick Reference

| 工具 | 用途 | 关键参数 | 何时优先用 |
| --- | --- | --- | --- |
| `xianyu_list_users` | 查看全部用户和状态 | 无 | 用户问“当前有哪些账号” |
| `xianyu_create_user` | 创建新用户 | `display_name?` | 需要新增账号 |
| `xianyu_get_user_status` | 查看单个用户详情 | `user_id` | 需要确认某个账号是否就绪 |
| `xianyu_login` | 对指定用户发起登录 | `user_id` | 登录入口首选 |
| `xianyu_check_session` | 检查某用户登录态 | `user_id` | 搜索/发布前核验状态 |
| `xianyu_refresh_token` | 刷新某用户 token | `user_id` | token 过期或用户明确要求刷新 |
| `xianyu_search` | 搜索商品 | `keyword`, `user_id?` | 查商品、做选品 |
| `xianyu_publish` | 复制发布商品 | `user_id`, `item_url` | 根据对标链接填充发布表单 |
| `xianyu_browser_overview` | 浏览器排障 | 无 | 页面卡住、空白、上下文异常 |

## Tool Guide

### `xianyu_list_users`

查看当前全部用户。返回值不是简单 ID 列表，而是带状态的对象数组，常见字段包括：

- `user_id`
- `display_name`
- `status`: 常见值为 `ready`、`pending_login`
- `enabled`
- `cookie_valid`
- `busy`
- `slot_id`
- `cdp_host` / `cdp_port`

**适用场景：**
- 用户问“当前有哪些闲鱼用户”
- 需要从多个账号里选一个可用账号
- 需要判断是否已经存在可复用账号

### `xianyu_create_user`

创建一个新用户，并分配浏览器 slot 和 CDP 端口。

**参数：**
- `display_name`：可选。不给时通常会自动使用类似 `user-001` 的默认名。

**常见返回：**
- `user_id`
- `slot_id`
- `cdp_port`
- `status`，新建后通常是 `pending_login`

**要点：**
- 创建成功后不要直接搜索或发布，下一步通常是 `xianyu_login(user_id)`。

### `xianyu_get_user_status`

查询单个用户的详细状态，是多用户场景下最重要的“定点检查”工具。

**必须参数：**
- `user_id`

**重点字段解释：**
- `status`: `ready` 表示通常可直接操作；`pending_login` 表示还需登录
- `cookie_valid`: 当前 Cookie 是否有效
- `browser_connected`: 浏览器实例是否已连接
- `keepalive_running`: 后台保活是否运行中
- `busy`: 该用户当前是否正在执行任务
- `last_error`: 最近一次错误

**适用场景：**
- 用户指定某个账号，如 `user-001`
- 需要确认某个用户能否立刻执行搜索或发布

**注意：**
- `xianyu_get_user_status` 更适合看运行状态和错误信息。
- 只看到 `status: ready` 不代表一定可以直接执行关键操作；真正要判断登录态是否有效，仍以 `xianyu_check_session(user_id)` 为准。

### `xianyu_login`

对指定用户发起登录。它是默认登录入口，不要先假设系统存在“当前默认用户”。

**必须参数：**
- `user_id`

**常见分支：**
- 已登录：返回 `logged_in: true`
- 未登录：返回 `logged_in: false` 和 `qr_code`

**二维码字段：**
- `public_url`: 最适合直接发给用户扫码
- `text`: 原始登录链接

**标准流程：**
1. `xianyu_list_users`
2. 不存在目标用户就 `xianyu_create_user`
3. `xianyu_login(user_id)`
4. 把 `qr_code.public_url` 发给用户扫码
5. 用户扫码后调用 `xianyu_check_session(user_id)` 确认成功

### `xianyu_check_session`

检查某个用户的登录态是否仍然有效。

**必须参数：**
- `user_id`

**常见返回：**
- `valid: true`：可以继续搜索、发布等操作
- `valid: false`：需要重新登录
- `last_updated_at`：最近一次更新时间

**适用场景：**
- 首次接手某个用户时
- 搜索变慢、返回空、卡住时
- 发布前确认登录态

**不要犯的错：**
- 不要把它当成“无参数全局检查”；多用户场景必须指定 `user_id`

### `xianyu_refresh_token`

为指定用户刷新 token。

**必须参数：**
- `user_id`

**适用场景：**
- 用户明确要求刷新 token
- 你已确认问题与 token 过期有关

**建议：**
- 刷新后可再执行一次 `xianyu_check_session(user_id)` 做确认
- 若刷新失败，下一步通常是重新登录，而不是继续盲目搜索或发布

### `xianyu_search`

按关键词搜索商品，返回唯一商品列表。

**参数：**
- `keyword`：必填
- `user_id`：可选，但多用户场景推荐显式传入
- `rows`：目标数量，默认 30
- `min_price` / `max_price`
- `free_ship`
- `sort_field`: 仅支持 `pub_time` 或 `price`
- `sort_order`: `ASC` 或 `DESC`

**常见返回字段：**
- `user_id` / `slot_id`：实际执行搜索的账号
- `requested` / `total`
- `stop_reason`
- `stale_pages`
- `items`

`items` 中常见字段：
- `item_id`
- `title`
- `price`
- `want_cnt`
- `detail_url`
- `publish_time`
- `exposure_score`

**要点：**
- `rows > 30` 时会自动翻页
- 结果会自动去重
- 如果用户要求“按曝光度排序”，先拉取结果，再按 `exposure_score` 二次排序
- 如果用户只说“第 2 个”“排名第二”但没说排序依据，默认按你当前展示给用户的列表顺序理解；如果此前上下文已经明确是“按曝光度排行”，就按曝光度重排后的顺序理解。仍有歧义时，要先说明你采用的排序依据。
- 如果没有可用账号且未传 `user_id`，可能收到 `no_available_user`

### `xianyu_publish`

根据对标商品链接复制发布商品。

**必须参数：**
- `user_id`
- `item_url`

**可选参数：**
- `new_price`
- `new_description`
- `condition`，默认 `全新`

**输入来源：**
- 通常可直接把搜索结果中的 `detail_url` 作为这里的 `item_url`

**返回理解：**
- `success: true`：复制和填充流程成功
- `item_data`：抓取到的标题、描述、分类、图片等
- `item_id` 可能为 `null`

**重要：**
- 不要把 `success: true` 直接理解成“商品已正式上架”
- 潮玩盲盒等类目可能自动保存为草稿

### `xianyu_browser_overview`

查看浏览器 context 和页面信息，用于排障。

**无参数。**

**常见返回：**
- `browser_context_count`
- `contexts[].page_count`
- `contexts[].pages[].title`
- `contexts[].pages[].url`

**适用场景：**
- 页面一直卡在 `about:blank`
- 登录后页面没有跳转
- 搜索或发布时怀疑浏览器页面异常

## Recommended Workflows

### 查看当前用户并选择账号

1. 调用 `xianyu_list_users`
2. 如果用户指定了账号，再调用 `xianyu_get_user_status(user_id)`
3. 如果接下来要执行搜索、发布、刷新 token 等关键操作，再补一次 `xianyu_check_session(user_id)`
4. 只有在 `xianyu_check_session(user_id)` 返回 `valid: true` 时，再继续业务操作

### 新用户登录

1. `xianyu_create_user(display_name?)`
2. `xianyu_login(user_id)`
3. 把 `qr_code.public_url` 发给用户
4. 用户扫码后执行 `xianyu_check_session(user_id)`

### 指定用户搜索并按曝光度重排

1. `xianyu_check_session(user_id)`
2. `xianyu_search(keyword, user_id, rows, sort_field, sort_order)`
3. 如果用户要“按曝光度”，在返回的 `items` 上按 `exposure_score` 重新排序

### 搜索结果里选商品并复制发布

1. `xianyu_check_session(user_id)`
2. `xianyu_search(...)`
3. 取目标商品的 `detail_url`
4. `xianyu_publish(user_id, item_url=detail_url, ...)`
5. 向用户说明发布结果更接近“表单填充完成”，必要时提醒可能是草稿

### 排障顺序

1. `xianyu_get_user_status(user_id)`
2. `xianyu_check_session(user_id)`
3. `xianyu_browser_overview()`
4. 再排查搜索关键词、排序参数或页面状态

## Common Mistakes

| 错误 | 正确做法 |
| --- | --- |
| 把 `xianyu_check_session` 当成无参数工具 | 多用户场景必须传 `user_id` |
| 忽略 `xianyu_refresh_token(user_id)` 的 `user_id` | 指定用户刷新 token，必要时再复查 session |
| 以为搜索可以直接按曝光度排序 | 先搜索，再按 `exposure_score` 二次排序 |
| 省略 `user_id` 还以为一定会用当前账号 | 省略时可能随机使用某个 `ready` 用户，或直接报 `no_available_user` |
| `xianyu_publish` 成功就当成已正式上架 | 正确理解为复制/填充成功，特殊类目可能是草稿 |
| 只看到 `status: ready` 就认为一定已登录 | 真正执行关键操作前，再跑一次 `xianyu_check_session(user_id)` |
| 用户指定了 `user-001`，却只看 `xianyu_list_users` 不看单用户详情 | 再补一次 `xianyu_get_user_status(user_id)` |
| 用户只说“排名第二”，却没说按什么排 | 默认按当前展示顺序理解；若上下文已明确“按曝光度排行”，按曝光度顺序处理，并说明你的依据 |
| 扫码后不复查登录态 | 扫码后必须调用 `xianyu_check_session(user_id)` |

## Example

用户说：`创建一个新用户，登录后搜索 50 个泡泡玛特商品，并发布曝光度第二的商品。`

推荐步骤：

1. `xianyu_create_user`
2. `xianyu_login(user_id)`
3. 把 `qr_code.public_url` 发给用户扫码
4. `xianyu_check_session(user_id)`
5. `xianyu_search(keyword="泡泡玛特", user_id=user_id, rows=50)`
6. 按 `items[].exposure_score` 在本地重排
7. 取第 2 个商品的 `detail_url`
8. `xianyu_publish(user_id=user_id, item_url=detail_url)`

这里最容易犯的错有三个：
- 忘记给 `login`、`check_session`、`publish` 传 `user_id`
- 误以为 MCP 能直接按曝光度排序
- 把发布结果误判为“已经正式上架”
