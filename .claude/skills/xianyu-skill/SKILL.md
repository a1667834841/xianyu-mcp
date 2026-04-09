---
name: xianyu-skill
description: Use when managing Xianyu store via MCP tools - login, search products, publish listings, refresh tokens, or check session validity
---

# 闲鱼技能 (xianyu-skill)

## 概述

通过 MCP 协议操作闲鱼店铺的自动化技能。支持扫码登录、商品搜索、根据对标商品链接复制发布、Token 刷新和会话检查。

## 何时使用

**应当使用：**
- 需要通过 MCP 工具管理闲鱼店铺
- 需要搜索特定商品并获取详细数据
- 需要复制热门商品的文案和图片并发布
- Token 过期需要刷新
- 验证登录状态是否有效

**不适用：**
- 非闲鱼平台的电商操作
- 需要绕过平台限制的操作

## 登录约束

**重要：在调用任何操作工具前，必须先确保已登录！**

### 登录检查流程

1. **首次使用或不确定登录状态时：**
   - 先调用 `xianyu_check_session` 检查登录状态
   - 如果返回 `valid: false` 或提示 Cookie 过期，需要重新登录

2. **搜索异常时，优先检查登录状态：**
   - 如果出现以下现象，必须第一时间调用 `xianyu_check_session`，不要先猜测搜索逻辑、性能或页面结构问题
   - 典型信号包括：搜索长时间无响应、明显变慢、返回空结果、页面被弹窗拦住、接口响应异常、浏览器看起来正常但搜索流程卡住
   - 这类症状经常不是搜索本身坏了，而是登录态失效后页面交互和接口请求都变得不稳定
   - 只有在 `xianyu_check_session` 确认 `valid: true` 后，才继续排查搜索逻辑本身

3. **未登录时的处理：**
   - 当用户提示需要登录或检测到未登录状态时，必须调用 `xianyu_login`
   - **终端环境**：`xianyu_login` 会自动在终端显示 ASCII 二维码，用户直接扫码即可
   - **GUI 环境**：二维码会在浏览器中显示

4. **扫码后确认：**
   - 用户扫码后，调用 `xianyu_check_session` 确认登录成功
   - 登录成功后方可继续执行其他操作

### 二维码扫码方式

登录返回的二维码支持扫码：

| 字段 | 说明 | 适用场景 |
|------|------|----------|
| `public_url` | 公网可访问的二维码图片 URL | **推荐** - 手机扫码 |
| `text` | 原始 URL | 复制链接到浏览器打开 |

**推荐扫码流程：**
1. 访问 `public_url` 打开二维码图片
2. 用闲鱼 APP 扫码

### 终端环境登录示例

```
用户：我要搜索机械键盘
你：请先登录。调用 xianyu_login...

[调用 xianyu_login]

█▀▀▀▀▀▀▀█ █▀▀▀▀▀▀▀█
█ ▀▀▀ █ █ ▀▀▀ █
█▄▄▄▄▄▄▄█ █▄▄▄▄▄▄▄█
(二维码 ASCII 艺术)

请打开闲鱼 APP 扫码登录...

[用户扫码后]

[调用 xianyu_check_session]

登录成功！现在可以搜索商品了。
```

**注意：** 在终端环境下，严禁调用浏览器相关操作，所有交互必须通过终端完成。

## 前置条件

**推荐环境：Docker Compose 部署**

- [ ] 已在项目根目录执行 `docker compose up -d`
- [ ] `mcp-server` 服务可通过 `http://127.0.0.1:8080/sse` 访问
- [ ] 已按项目 README 完成 MCP 接入配置

**兼容模式：本地 stdio / 手工 Chrome**

如果没有使用 Docker Compose，也可以手动启动本地 Chrome 调试端口并运行 stdio 版 MCP Server；该模式仅用于本地调试，不再作为默认部署方式。

## 可用工具

### 1. xianyu_check_session

**功能：** 检查闲鱼 Cookie 是否有效

**参数：** 无

**返回（Cookie 有效）：**
```json
{
  "success": true,
  "valid": true,
  "message": "Cookie 有效"
}
```

**返回（Cookie 无效）：**
```json
{
  "success": true,
  "valid": false,
  "message": "Cookie 已过期，需要重新登录"
}
```

**说明：**
- 调用用户信息接口验证当前登录状态
- 建议在调用其他工具前先检查登录状态

### 2. xianyu_login

**功能：** 访问闲鱼首页，自动检测登录状态。已登录则返回 token，未登录则显示二维码。

**参数：** 无

**返回（已登录）：**
```json
{
  "success": true,
  "logged_in": true,
  "token": "8d5ad923e6ae3191423a...",
  "message": "已登录"
}
```

**返回（未登录，需要扫码）：**
```json
{
  "success": true,
  "logged_in": false,
  "qr_code": {
    "url": "https://passport.goofish.com/qrcodeCheck.htm?lgToken=xxx",
    "public_url": "https://img.ggball.top/xianyu/qr-xxx.png",
    "text": "https://passport.goofish.com/qrcodeCheck.htm?lgToken=xxx"
  },
  "message": "请扫码登录。扫码后浏览器会自动跳转，然后请调用 check_session 确认登录状态"
}
```

**说明：**
- 访问闲鱼首页，自动检测是否已登录
- 已登录：直接返回 token
- 未登录：获取页面触发的二维码接口，显示二维码
- **用户扫码后，浏览器页面会自动跳转完成登录**
- 扫码完成后，调用 `xianyu_check_session` 确认登录状态

**终端环境登录流程：**

```
1. 调用 xianyu_login
2. 如果已登录，返回 token
3. 如果未登录，终端显示 ASCII 二维码
4. 用户扫码（浏览器自动跳转）
5. 调用 xianyu_check_session 确认登录成功
```

### 3. xianyu_show_qr

**功能：** 显示登录二维码（仅用于未登录场景）

**参数：** 无

**返回（已登录）：**
```json
{
  "success": true,
  "logged_in": true,
  "message": "已登录，无需扫码"
}
```

**返回（未登录，显示二维码）：**
```json
{
  "success": true,
  "logged_in": false,
  "qr_code": {
    "url": "https://passport.goofish.com/qrcodeCheck.htm?lgToken=xxx",
    "public_url": "https://img.ggball.top/xianyu/qr-xxx.png",
    "text": "https://..."
  },
  "message": "请扫码登录。扫码后浏览器会自动跳转，然后请调用 check_session 确认登录状态"
}
```

**说明：**
- 此方法仅在未登录场景下使用
- 推荐直接使用 `xianyu_login`，它会自动检测登录状态

### 4. xianyu_search

**功能：** 搜索商品并获取详细数据（自动去重，支持多页获取）

**参数：**
| 参数 | 类型 | 必填 | 说明 |
|-----|------|-----|------|
| keyword | string | 是 | 搜索关键词 |
| rows | integer | 否 | 获取数量（默认 30，自动翻页） |
| min_price | number | 否 | 最低价格 |
| max_price | number | 否 | 最高价格 |
| free_ship | boolean | 否 | 是否只看包邮（默认 false） |
| sort_field | string | 否 | 排序字段（pub_time/price） |
| sort_order | string | 否 | 排序方向（ASC/DESC） |

**返回：**
```json
{
  "success": true,
  "total": 10,
  "items": [
    {
      "item_id": "123456789",
      "title": "商品标题",
      "price": "99.00",
      "want_cnt": 207,
      "seller_nick": "卖家昵称",
      "seller_city": "杭州",
      "image_urls": ["..."],
      "detail_url": "https://...",
      "is_free_ship": true,
      "publish_time": "2024-11-08"
    }
  ]
}
```

**说明：**
- 当 `rows > 30` 时自动翻页获取多页数据
- 返回结果自动去重，不会有重复商品
- 每页等待新 API 响应确保数据不同

**默认输出格式（Markdown 表格）：**

调用 `xianyu_search` 后，默认以 Markdown 表格格式展示结果（按曝光度倒序排列）：

| 序号 | 商品名称 | 价格 | 曝光度 | 发布时间 | 商品链接 |
|:----:|---------|:----:|:--------:|---------|---------|
| 1 | 超值盲盒机械键盘... | ¥26 | 15800 | 2024-11-08 | [链接](https://...) |
| 2 | 全新 狼蛛 F2088pro... | ¥55 | 20700 | 2024-11-07 | [链接](https://...) |

**字段说明：**
- **序号**: 从 1 开始的序号
- **商品名称**: 标题前 30 字，超出显示省略号
- **价格**: 显示为 ¥XX 格式
- **曝光度**: 根据公式计算 `曝光度 = (想要人数 × 100) / (天数差 + 1)`
- **发布时间**: 商品发布日期（YYYY-MM-DD）
- **商品链接**: 可点击的闲鱼商品链接

**曝光度计算公式：**

```
曝光度 = (想要人数 × 100) / (DAYS(采集时间，发布时间)/24 + 1)
```

- **想要人数**: 商品页面上的"XX 人想要"数值
- **采集时间**: 当前搜索时间
- **发布时间**: 商品上架时间
- **天数差**: 发布至今的小时数除以 24 转换为天数

**示例：**
- 商品发布 1 天，想要 100 人 → 曝光度 = (100×100)/(1+1) = 5000
- 商品发布 7 天，想要 100 人 → 曝光度 = (100×100)/(7+1) = 1250
- 商品刚发布（0 天），想要 100 人 → 曝光度 = (100×100)/(0+1) = 10000

**排序说明：** 搜索结果默认按曝光度倒序排列，曝光度高的商品排在前面，优先展示近期热门商品。

### 5. xianyu_publish

**功能：** 根据商品链接复制发布新商品

**参数：**
| 参数 | 类型 | 必填 | 说明 |
|-----|------|-----|------|
| item_url | string | 是 | 对标商品链接 |
| new_price | number | 否 | 新商品价格（默认原价） |
| new_description | string | 否 | 新商品描述（默认原描述） |
| condition | string | 否 | 成色（默认"全新"） |

**返回：**
```json
{
  "success": true,
  "item_id": null,
  "error": null,
  "message": "表单填充完成，请检查浏览器窗口",
  "captured_item": {
    "title": "商品标题前 50 字",
    "price": 99.0,
    "images": 5,
    "category": "分类名称"
  }
}
```

### 6. xianyu_refresh_token

**功能：** 刷新 Token（当 Token 过期时）

**参数：** 无

**返回：**
```json
{
  "success": true,
  "token": "8d5ad923e6ae3191423a...",
  "full_cookie": "8d5ad923e6ae3191423af7cc4412a019_1775398734523",
  "message": "Token 刷新成功"
}
```

### 7. xianyu_check_session

**功能：** 检查 Cookie 是否有效

**参数：** 无

**返回：**
```json
{
  "success": true,
  "valid": true,
  "message": "Cookie 有效"
}
```

## 使用示例

### 登录并搜索商品

```
1. 调用 xianyu_login 登录
2. 调用 xianyu_search 搜索"机械键盘"，rows=10
3. 查看返回的商品列表
```

### 复制发布商品

```
1. 调用 xianyu_check_session 检查登录状态
2. 如果 Cookie 有效，调用 xianyu_publish:
   - item_url: "https://www.goofish.com/item?id=123456789"
   - new_price: 150.0
   - condition: "全新"
3. 检查返回结果
```

### 刷新 Token

```
当收到 Token 过期错误时:
1. 调用 xianyu_refresh_token
2. 使用返回的新 Token 继续操作
```

## 常见问题

| 问题 | 解决方案 |
|-----|---------|
| 登录超时 | 检查 Chrome 是否启动（端口 9222） |
| 搜索返回空/很慢/卡住 | **先调用 `xianyu_check_session` 检查是否已掉登录**，确认 `valid: true` 后再排查关键词或搜索逻辑 |
| 发布失败 | 检查商品链接格式是否正确 |
| Token 过期 | 调用 xianyu_refresh_token 或重新登录 |
| Cookie 无效 | 调用 xianyu_login 重新登录 |

## 注意事项

1. **浏览器要求** - 需要安装 Google Chrome 并启动调试端口
2. **Token 有效期** - Token 约 24 小时过期
3. **发布频率** - 避免短时间大量发布，可能触发风控
4. **特殊类目** - 潮玩盲盒等需要资质，会自动保存草稿
5. **技能名称** - 本技能名称为 **xianyu-skill**
6. **排查顺序** - 搜索问题先查登录态，再查关键词、页面结构、响应监听和性能；不要跳过 session 检查直接猜搜索逻辑故障
