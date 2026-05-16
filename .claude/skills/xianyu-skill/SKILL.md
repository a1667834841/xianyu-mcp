---
name: xianyu-skill
description: Use when operating the Xianyu MCP service from OpenCode-style platforms with built-in MCP tools, or when locally debugging the same tools through the repository script for login, session checks, search, detail lookup, publish, sourcing publish, messaging, and WebSocket troubleshooting.
---

# 闲鱼技能

## Overview

本 skill 面向已接入闲鱼 MCP 的平台环境，例如 OpenCode。优先直接使用平台内置 `xianyu_*` 工具；只有本地联调或脱离平台排查时，才使用仓库里的调试脚本。

## 调用方式

### 方式一：平台内置工具（推荐）

适用于 OpenCode 这类已集成 MCP client 的平台。直接调用 `xianyu_*` 工具即可，平台会自动维护连接、认证和 session。

```bash
xianyu_check_session()
xianyu_search(keyword="机械键盘", rows=5)
xianyu_get_detail(item_url="https://www.goofish.com/item?id=1047155930582")
```

### 方式二：本地调试脚本

适用于仓库内本地联调。

```bash
./scripts/mcp-dev call xianyu_check_session
./scripts/mcp-dev call xianyu_search --keyword "机械键盘" --rows 5
./scripts/mcp-dev call xianyu_get_detail --item-url "https://www.goofish.com/item?id=1047155930582"
```

## 核心规则

1. 先确认登录态，再做搜索、发布、消息相关操作。
2. `xianyu_publish` 是手动给图片/标题/价格发布。
3. `xianyu_publish_from_item_url` 是按商品链接直接铺货。
4. 结果里如果有 `logs`、`failed_step`，排错优先看它们。

## 常用流程

### 登录流程

1. `xianyu_login`
2. 如果返回二维码，扫码
3. `xianyu_check_session`
4. 需要时 `xianyu_refresh_token`

### 搜索选品流程

1. `xianyu_check_session`
2. `xianyu_search`
3. `xianyu_get_detail`

### 铺货流程

1. `xianyu_check_session`
2. `xianyu_publish_from_item_url`
3. 看 `logs`

### 消息流程

1. `xianyu_create_conversation`
2. `xianyu_ws_send`
3. `xianyu_list_conversations`
4. `xianyu_get_messages`

### WebSocket 排障流程

1. `xianyu_ws_status`
2. 再看 `xianyu_list_conversations` / `xianyu_get_messages`

## MCP 方法

每个方法只保留两类示例：平台内置工具、仓库本地调试脚本。

### `xianyu_login`

用途：登录闲鱼。

参数：
- `user_id`：可选，占位参数，当前单用户实现里可不传。

示例：
```bash
# 平台内置工具
xianyu_login()

# 本地调试脚本
./scripts/mcp-dev call xianyu_login
```

### `xianyu_check_session`

用途：检查登录态。

参数：
- `user_id`：可选，占位参数。

示例：
```bash
# 平台内置工具
xianyu_check_session()

# 本地调试脚本
./scripts/mcp-dev call xianyu_check_session
```

### `xianyu_refresh_token`

用途：刷新 token。

参数：
- `user_id`：可选，占位参数。

示例：
```bash
# 平台内置工具
xianyu_refresh_token()

# 本地调试脚本
./scripts/mcp-dev call xianyu_refresh_token
```

### `xianyu_search`

用途：搜索商品。

参数：
- `keyword`：必填，搜索词
- `user_id`：可选，占位参数
- `rows`：可选，返回数量，默认 `30`
- `min_price`：可选，最低价
- `max_price`：可选，最高价
- `free_ship`：可选，是否包邮，默认 `false`
- `sort_field`：可选，支持 `pub_time` / `price`
- `sort_order`：可选，支持 `ASC` / `DESC`

示例：
```bash
# 平台内置工具
xianyu_search(keyword="机械键盘", rows=5)
xianyu_search(keyword="iPad", min_price=500, max_price=3000, sort_field="price", sort_order="ASC")

# 本地调试脚本
./scripts/mcp-dev call xianyu_search --keyword "机械键盘" --rows 5
./scripts/mcp-dev call xianyu_search --keyword "iPad" --min-price 500 --max-price 3000 --sort-field price --sort-order ASC
```

### `xianyu_suggest_keywords`

用途：搜索联想词。

参数：
- `input_words`：可选，输入词，默认 `x`

示例：
```bash
# 平台内置工具
xianyu_suggest_keywords(input_words="手机")

# 本地调试脚本
./scripts/mcp-dev call xianyu_suggest_keywords --input-words 手机
```

### `xianyu_publish`

用途：直接发布商品。

参数：
- `user_id`：可选，占位参数
- `images_paths`：必填，图片路径，多个用逗号分隔
- `title`：必填，商品标题
- `current_price`：可选，现价
- `original_price`：可选，原价
- `shipping`：可选，默认 `包邮`
- `self_pickup`：可选，是否自提，默认 `false`
- `post_price`：可选，运费，默认 `0`

示例：
```bash
# 平台内置工具
xianyu_publish(images_paths="/tmp/a.jpg,/tmp/b.jpg", title="测试商品", current_price=88)

# 本地调试脚本
./scripts/mcp-dev call xianyu_publish --images-paths "/tmp/a.jpg,/tmp/b.jpg" --title "测试商品" --current-price 88
```

注意：这是实发商品，不是按链接铺货。

### `xianyu_get_detail`

用途：获取商品详情。

参数：
- `user_id`：可选，占位参数
- `item_url`：必填，商品链接

示例：
```bash
# 平台内置工具
xianyu_get_detail(item_url="https://www.goofish.com/item?id=1047155930582")

# 本地调试脚本
./scripts/mcp-dev call xianyu_get_detail --item-url "https://www.goofish.com/item?id=1047155930582"
```

### `xianyu_publish_from_item_url`

用途：按商品链接直接铺货。

参数：
- `user_id`：可选，占位参数
- `item_url`：必填，商品链接

示例：
```bash
# 平台内置工具
xianyu_publish_from_item_url(item_url="https://www.goofish.com/item?id=1047155930582")

# 本地调试脚本
./scripts/mcp-dev call xianyu_publish_from_item_url --item-url "https://www.goofish.com/item?id=1047155930582"
```

返回重点：
- 成功看 `published_item_id`、`published_item_url`
- 失败看 `failed_step`、`message`
- 全程看 `logs`

### `xianyu_create_conversation`

用途：创建对话。

参数：
- `user_id`：可选，占位参数
- `item_url`：必填，商品链接

示例：
```bash
# 平台内置工具
xianyu_create_conversation(item_url="https://www.goofish.com/item?id=1047155930582")

# 本地调试脚本
./scripts/mcp-dev call xianyu_create_conversation --item-url "https://www.goofish.com/item?id=1047155930582"
```

### `xianyu_ws_send`

用途：发送消息。

参数：
- `user_id`：可选，占位参数
- `target_id`：必填，对方用户 ID
- `content`：可选，文本内容
- `image_url`：可选，图片 URL
- `conversation_id`：可选，对话 ID

示例：
```bash
# 平台内置工具
xianyu_ws_send(target_id="660749856", content="你好", conversation_id="61066151753")

# 本地调试脚本
./scripts/mcp-dev call xianyu_ws_send --target-id "660749856" --content "你好" --conversation-id "61066151753"
```

### `xianyu_ws_status`

用途：查看 WebSocket 状态。

参数：
- `user_id`：可选，占位参数

示例：
```bash
# 平台内置工具
xianyu_ws_status()

# 本地调试脚本
./scripts/mcp-dev call xianyu_ws_status
```

### `xianyu_list_conversations`

用途：获取对话列表。

参数：
- `user_id`：可选，占位参数
- `limit`：可选，返回数量，默认 `20`

示例：
```bash
# 平台内置工具
xianyu_list_conversations(limit=10)

# 本地调试脚本
./scripts/mcp-dev call xianyu_list_conversations --limit 10
```

### `xianyu_get_messages`

用途：获取消息历史。

参数：
- `user_id`：可选，占位参数
- `conversation_id`：必填，对话 ID
- `limit`：可选，返回数量，默认 `50`

示例：
```bash
# 平台内置工具
xianyu_get_messages(conversation_id="61066151753", limit=5)

# 本地调试脚本
./scripts/mcp-dev call xianyu_get_messages --conversation-id "61066151753" --limit 5
```

## 常见错误

| 错误 | 正确做法 |
| --- | --- |
| 没登录就搜索/发布 | 先跑 `xianyu_check_session` |
| 想按链接铺货却用 `xianyu_publish` | 用 `xianyu_publish_from_item_url` |
| `xianyu_publish_from_item_url` 失败只看 `message` | 同时看 `failed_step` 和 `logs` |
| 在 OpenCode 里还想手动处理 SSE / session | 直接用平台内置 `xianyu_*` 工具 |
| 以为脚本调用和平台调用是两套能力 | 两者调用的是同一批 MCP 工具，只是入口不同 |
| `xianyu_publish` 成功就当成一定上架 | 特殊类目可能是草稿 |
