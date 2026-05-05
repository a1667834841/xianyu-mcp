---
name: xianyu-skill
description: Use when managing one or more Xianyu accounts via MCP, especially when you need to create or inspect users, verify login state, search products, copy-publish listings, or troubleshoot session issues.
---

# 闲鱼 MCP 工具参考

## 架构

单用户模式，所有业务走 HTTP MTOP API 或 WebSocket RPC，浏览器仅用于滑块/风控。接口失败直接返回错误，不做隐式浏览器降级。

## 调用方式

**在项目根目录下**使用 `scripts/mcp-dev call` 脚本调用所有工具。

```bash
scripts/mcp-dev call <tool-name> [--key value ...]
```

**参数格式：** `--参数名 值`，字符串参数（`item_url`、`keyword`、`title`、`images_paths`、`content`、`conversation_id`、`target_id`）直接传递，其他类型（数字、布尔）按原值传递。

**环境变量：**
- `MCP_DEV_URL` - 完整 MCP URL（默认 `http://127.0.0.1:8080/mcp`）
- `MCP_HOST_PORT` - 端口（默认 `8080`）

---

### `xianyu_login`

扫码登录。返回 `logged_in: true` 或 `logged_in: false` + `qr_code.public_url`。**只把 `public_url` 发给用户扫码**，不传 `qr_code.url`。

```bash
scripts/mcp-dev call xianyu_login
```

---

### `xianyu_check_session`

检查登录态。返回 `valid: true/false`。无参数。

```bash
scripts/mcp-dev call xianyu_check_session
```

---

### `xianyu_refresh_token`

刷新 Token，纯 HTTP。返回 `method: "http"`。无参数。

```bash
scripts/mcp-dev call xianyu_refresh_token
```

---

### `xianyu_search`

关键词搜索商品。

| 参数 | 必填 | 默认 | 说明 |
|---|---|---|---|
| `--keyword` | 是 | - | 搜索关键词 |
| `--rows` | 否 | 30 | 返回条数 |
| `--min_price` | 否 | - | 最低价格（元） |
| `--max_price` | 否 | - | 最高价格（元） |
| `--free_ship` | 否 | false | 是否包邮 |
| `--sort_field` | 否 | - | 排序字段（`pub_time`/`price`） |
| `--sort_order` | 否 | - | 排序方向（`asc`/`desc`） |

> 注意：不支持按曝光度排序，需收到结果后按 `exposure_score` 本地排序。`rows>30` 自动翻页合并去重。

```bash
scripts/mcp-dev call xianyu_search --keyword 手机壳 --rows 10
```

```bash
scripts/mcp-dev call xianyu_search --keyword iPad --min_price 500 --max_price 3000 --free_ship true
```

---

### `xianyu_suggest_keywords`

搜索联想词。

| 参数 | 必填 | 默认 | 说明 |
|---|---|---|---|
| `--input_words` | 否 | `"x"` | 输入词 |

```bash
scripts/mcp-dev call xianyu_suggest_keywords --input_words 手机
```

---

### `xianyu_get_detail`

商品详情。

| 参数 | 必填 | 默认 | 说明 |
|---|---|---|---|
| `--item_url` | 是 | - | 商品链接（支持 `goofish.com` 和 `xianyu.com`） |

```bash
scripts/mcp-dev call xianyu_get_detail --item_url "https://www.goofish.com/item?id=1047155930582"
```

---

### `xianyu_publish`

HTTP 发布商品，**无浏览器降级，无 `item_url` 参数**。接口失败直接抛异常。

| 参数 | 必填 | 默认 | 说明 |
|---|---|---|---|
| `--images_paths` | 是 | - | 图片路径，逗号分隔（至少1张） |
| `--title` | 是 | - | 商品标题（最多20个中英文单词） |
| `--current_price` | 否 | - | 现价（元） |
| `--original_price` | 否 | - | 原价（元） |
| `--shipping` | 否 | `"包邮"` | 物流选项（`包邮`/`按距离计费`/`一口价`/`无需邮寄`） |
| `--self_pickup` | 否 | false | 是否支持自提 |
| `--post_price` | 否 | 0 | 物流费用（一口价时使用） |
| `--is_original` | 否 | false | 是否声明原创 |
| `--visibility` | 否 | `公开可见` | 可见范围 |

```bash
scripts/mcp-dev call xianyu_publish --images_paths "/path/to/img1.jpg,/path/to/img2.jpg" --title "商品标题" --current_price 100
```

> 注意：`publish` 成功不等于已上架，特殊类目可能为草稿状态。

---

### `xianyu_create_conversation`

创建对话，WebSocket RPC。自动检测是否自己商品（返回 `CANNOT_CREATE_CONVERSATION_WITH_SELF`），创建后自动发送问候语。

| 参数 | 必填 | 默认 | 说明 |
|---|---|---|---|
| `--item_url` | 是 | - | 商品链接 |

```bash
scripts/mcp-dev call xianyu_create_conversation --item_url "https://www.goofish.com/item?id=1047155930582"
```

---

### `xianyu_ws_send`

发送消息。

| 参数 | 必填 | 默认 | 说明 |
|---|---|---|---|
| `--target_id` | 是 | - | 对方用户 ID |
| `--content` | 否 | - | 消息文本 |
| `--image_url` | 否 | - | 图片 URL |
| `--conversation_id` | 否 | - | 对话 ID（可从 `xianyu_list_conversations` 获取） |

```bash
scripts/mcp-dev call xianyu_ws_send --target_id "660749856" --content "你好" --conversation_id "61066151753"
```

---

### `xianyu_ws_status`

WebSocket 连接状态。返回 `connected`/`status`/`last_error`/`started_at`。无参数。

```bash
scripts/mcp-dev call xianyu_ws_status
```

---

### `xianyu_get_access_token`

获取 WebSocket token，纯 HTTP。返回 `access_token_masked`。无参数。

```bash
scripts/mcp-dev call xianyu_get_access_token
```

---

### `xianyu_list_conversations`

对话列表，优先 WS RPC，失败回退缓存。

| 参数 | 必填 | 默认 | 说明 |
|---|---|---|---|
| `--limit` | 否 | 20 | 返回条数 |

```bash
scripts/mcp-dev call xianyu_list_conversations --limit 10
```

---

### `xianyu_get_messages`

消息历史，优先 WS RPC，失败回退缓存。

| 参数 | 必填 | 默认 | 说明 |
|---|---|---|---|
| `--conversation_id` | 是 | - | 对话 ID（从 `xianyu_list_conversations` 获取） |
| `--limit` | 否 | 50 | 返回条数 |

```bash
scripts/mcp-dev call xianyu_get_messages --conversation_id "61066151753" --limit 5
```

---

## 常见错误

| 错误 | 正确做法 |
|---|---|
| `publish` 传 `item_url` | 用 `images_paths` + `title` |
| 以为搜索可排序曝光度 | 搜索后按 `exposure_score` 本地排序 |
| `create_conversation` 对自己商品 | 系统自动返回 `CANNOT_CREATE_CONVERSATION_WITH_SELF` |
| `qr_code.public_url` 为空仍发码 | 告知用户不可展示，引导重试 |
| `publish` 成功=已上架 | 特殊类目可能为草稿 |

## 典型流程

**搜索并联系卖家：** `search` → `get_detail` → `create_conversation` → `ws_send`

**登录：** `login`(发`public_url`给用户扫码) → `check_session`

**发布：** `check_session` → `publish(images_paths, title, current_price)`
