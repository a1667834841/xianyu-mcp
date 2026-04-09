# 闲鱼搜索 API 协议文档

> **版本**: v1.0  
> **创建日期**: 2026-04-09  
> **最后更新**: 2026-04-09  
> **实现文件**: `src/http_search.py`

## 变更记录

| 版本 | 日期 | 变更内容 |
|-----|------|---------|
| v1.0 | 2026-04-09 | 初始版本，基于逆向分析和抓包整理 |

## 概述

本文档记录闲鱼搜索 API 的请求/响应格式，用于 HTTP 直调搜索实现。

> **来源**: 通过逆向分析 FishOps 项目 (https://github.com/a1667834841/FishOps) 和浏览器抓包获得。

---

## API 基本信息

| 字段 | 值 |
|-----|-----|
| API URL | `https://h5api.m.goofish.com/h5/mtop.taobao.idlemtopsearch.pc.search/1.0/` |
| API 名称 | `mtop.taobao.idlemtopsearch.pc.search` |
| API 版本 | `1.0` |
| App Key | `34839810` |
| 请求方式 | `POST` |
| Content-Type | `application/x-www-form-urlencoded` |

---

## 请求格式

### URL Query 参数

| 参数名 | 类型 | 必填 | 说明 | 示例值 |
|-------|------|------|------|--------|
| `jsv` | string | 是 | JS SDK 版本 | `2.7.2` |
| `appKey` | string | 是 | 应用标识 | `34839810` |
| `t` | string | 是 | 时间戳（毫秒） | `1744198800000` |
| `sign` | string | 是 | 签名（见签名算法） | `abc123def456...` |
| `api` | string | 是 | API 名称 | `mtop.taobao.idlemtopsearch.pc.search` |
| `v` | string | 是 | API 版本 | `1.0` |
| `type` | string | 是 | 返回类型 | `originaljson` |
| `accountSite` | string | 是 | 站点标识 | `xianyu` |
| `dataType` | string | 是 | 数据格式 | `json` |
| `timeout` | string | 是 | 超时时间（毫秒） | `20000` |
| `sessionOption` | string | 是 | 会话选项 | `AutoLoginOnly` |
| `spm_cnt` | string | 是 | 埋点追踪参数 | `a21ybx.search.0.0` |

### Request Body 参数

请求体格式：`data={URL编码的JSON字符串}`

JSON 结构：

```json
{
  "pageNumber": 1,
  "keyword": "搜索关键词",
  "fromFilter": false,
  "rowsPerPage": 30,
  "sortValue": "",
  "sortField": "",
  "customDistance": "",
  "gps": "",
  "propValueStr": {},
  "customGps": "",
  "searchReqFromPage": "pcSearch",
  "extraFilterValue": "{}",
  "userPositionJson": "{}"
}
```

#### 字段说明

| 字段名 | 类型 | 说明 | 可选值 |
|-------|------|------|--------|
| `pageNumber` | int | 页码，从 1 开始 | `1`, `2`, `3`, ... |
| `keyword` | string | 搜索关键词 | 任意字符串 |
| `fromFilter` | bool | 是否从筛选入口 | `false` |
| `rowsPerPage` | int | 每页条数 | `30`（固定） |
| `sortValue` | string | 排序方向 | `""`, `"ASC"`, `"DESC"` |
| `sortField` | string | 排序字段 | `""`, `"pub_time"`, `"price"` |
| `customDistance` | string | 自定义距离 | 空字符串 |
| `gps` | string | GPS 信息 | 空字符串 |
| `propValueStr` | object | 属性筛选（价格、包邮等） | `{}` 或筛选条件 |
| `customGps` | string | 自定义 GPS | 空字符串 |
| `searchReqFromPage` | string | 搜索来源页面 | `"pcSearch"` |
| `extraFilterValue` | string | 额外筛选值 | `"{}"` |
| `userPositionJson` | string | 用户位置信息 | `"{}"` |

#### propValueStr 扩展字段（暂未实现）

用于价格筛选和包邮筛选：

```json
{
  "propValueStr": {
    "minPrice": "100",
    "maxPrice": "500",
    "freeShipping": "true"
  }
}
```

---

## 请求头

| Header | 值 | 说明 |
|--------|-----|------|
| `Accept` | `application/json` | 接收 JSON 响应 |
| `Accept-Language` | `zh-CN,zh;q=0.9` | 语言偏好 |
| `Content-Type` | `application/x-www-form-urlencoded` | 表单格式 |
| `Origin` | `https://www.goofish.com` | 来源站点 |
| `Referer` | `https://www.goofish.com/` | 引用页 |
| `Cookie` | 完整 Cookie 字符串 | 必须包含 `_m_h5_tk` |
| `User-Agent` | Chrome UA | 浏览器标识 |
| `Sec-Ch-Ua` | `"Chromium";v="146"...` | UA 客户端提示 |
| `Sec-Ch-Ua-Mobile` | `?0` | 非移动端 |
| `Sec-Ch-Ua-Platform` | `"macOS"` | 平台 |
| `Sec-Fetch-Dest` | `empty` | Fetch 目标 |
| `Sec-Fetch-Mode` | `cors` | 跨域模式 |
| `Sec-Fetch-Site` | `same-site` | 同站点 |

---

## 签名算法

### 签名公式

```
sign = MD5(token + "&" + timestamp + "&" + appKey + "&" + dataStr)
```

### Token 提取

从 Cookie `_m_h5_tk` 字段提取：

```
_m_h5_tk = token_timestamp
```

例如：`_m_h5_tk=abc123def456_1744198800`

- `token` = `abc123def456`（最后一个 `_` 之前的部分）
- `timestamp` = `1744198800`（最后一个 `_` 之后的部分，是秒级时间戳）

### 签名步骤

1. 从 Cookie 中提取 `token`
2. 获取当前时间戳 `t`（毫秒级）
3. 将请求参数 `data` 序列化为 JSON 字符串 `dataStr`
4. 按公式拼接并计算 MD5

### Python 实现

```python
import hashlib
import json
import re
import time

def extract_token(cookie_str):
    match = re.search(r"_m_h5_tk=([^;]+)", cookie_str)
    if not match:
        return ""
    token_value = match.group(1)
    last_underscore = token_value.rfind("_")
    if last_underscore > 0:
        return token_value[:last_underscore]
    return token_value

def generate_sign(token, timestamp_ms, data):
    data_str = json.dumps(data, separators=(',', ':'))
    sign_str = f"{token}&{timestamp_ms}&34839810&{data_str}"
    return hashlib.md5(sign_str.encode()).hexdigest()

# 使用示例
cookie = "_m_h5_tk=abc123_1744198800; other=..."
token = extract_token(cookie)
timestamp = str(int(time.time() * 1000))
data = {"pageNumber": 1, "keyword": "手机", ...}
sign = generate_sign(token, timestamp, data)
```

---

## 响应格式

### 成功响应

```json
{
  "ret": ["SUCCESS::调用成功"],
  "data": {
    "resultList": [
      {
        "data": {
          "item": {
            "main": {
              "exContent": {
                "itemId": "123456789",
                "title": "商品标题",
                "price": [{"text": "¥100"}],
                "originalPrice": [{"text": "¥200"}],
                "picUrl": "http://img.alicdn.com/...",
                "userNick": "卖家昵称",
                "city": "城市",
                "wantNum": "10",
                "freeDelivery": "true"
              },
              "clickParam": {
                "args": {
                  "item_id": "123456789",
                  "publishTime": "1744198800000"
                }
              }
            }
          }
        }
      }
    ]
  }
}
```

### 字段映射

| 响应字段 | SearchItem 字段 | 转换规则 |
|---------|----------------|---------|
| `exContent.itemId` | `item_id` | 直接使用 |
| `clickParam.args.item_id` | `item_id` | 备用来源 |
| `exContent.title` | `title` | 直接使用 |
| `exContent.price` | `price` | 提取 `text`，拼接多个 |
| `exContent.originalPrice` | `original_price` | 提取 `text` |
| `exContent.picUrl` | `image_urls` | 单元素数组 |
| `exContent.userNick` | `seller_nick` | 直接使用 |
| `exContent.city` | `seller_city` | 直接使用 |
| `exContent.wantNum` | `want_cnt` | 转 int |
| `exContent.freeDelivery` | `is_free_ship` | 转 bool |
| `clickParam.args.publishTime` | `publish_time` | 毫秒转 datetime |
| N/A | `detail_url` | `https://www.goofish.com/item?id={item_id}` |
| N/A | `exposure_score` | 默认 `0.0` |

---

## 错误类型

| 错误类型 | ret 内容 | 说明 | 处理建议 |
|---------|---------|------|---------|
| `SUCCESS` | `SUCCESS::调用成功` | 成功 | 正常处理 |
| `SESSION_EXPIRED` | `SESSION_EXPIRED::SESSION_EXPIRED` | Cookie 过期 | 重新登录 |
| `ILLEGAL_SIGN` | `ILLEGAL_SIGN::签名错误` | 签名无效 | 检查 token 和签名算法 |
| `RGV587_ERROR` | `RGV587_ERROR::SM::哎哟喂,被挤爆啦` | 缺少必要参数/请求头 | 补齐所有字段 |
| `RATE_LIMIT` | 可能的限流 | 请求频率过高 | 降低并发，增加延迟 |
| `NETWORK_ERROR` | - | 网络错误 | 重试或检查连接 |

---

## 常见问题

### 1. `RGV587_ERROR::SM::哎哟喂,被挤爆啦`

**原因**: 请求缺少必要参数或请求头。

**解决方案**:
- 确保所有 Query 参数都已包含
- 确保所有请求头都已包含
- 确保 `spm_cnt` 参数存在
- 确保 `data` 字段包含完整结构

### 2. `ILLEGAL_SIGN::签名错误`

**原因**: 签名计算错误。

**检查项**:
- token 是否正确提取（最后一个 `_` 之前）
- 时间戳是否为毫秒级
- dataStr 是否为紧凑 JSON（无空格）
- appKey 是否正确（`34839810`）

### 3. `SESSION_EXPIRED`

**原因**: Cookie 过期或无效。

**解决方案**:
- 调用 `xianyu_login` 或 `xianyu_show_qr` 重新登录
- 或调用 `xianyu_refresh_token` 刷新

---

## 代码实现

详见：
- `src/http_search.py` - HTTP 搜索客户端实现
- `tests/test_http_search_unit.py` - 单元测试

---

---

## 配置建议

当前硬编码值建议迁移到配置：

| 配置项 | 当前位置 | 建议 |
|-------|---------|------|
| `API_BASE_URL` | `http_search.py:60` | 环境变量 `XIANYU_API_URL` |
| `APP_KEY` | `http_search.py:63` | 环境变量 `XIANYU_APP_KEY` |
| `timeout` | 构造函数参数 | 环境变量 `XIANYU_API_TIMEOUT` |
| `User-Agent` | `_send_request()` | 配置文件，支持自定义 |

---

## Schema 验证建议

建议添加响应格式验证：

```python
# 响应 Schema
RESPONSE_SCHEMA = {
    "type": "object",
    "required": ["ret"],
    "properties": {
        "ret": {"type": "array"},
        "data": {
            "type": "object",
            "properties": {
                "resultList": {"type": "array"}
            }
        }
    }
}

# Item Schema
ITEM_SCHEMA = {
    "type": "object",
    "required": ["item_id", "title", "price"],
    "properties": {
        "item_id": {"type": "string"},
        "title": {"type": "string"},
        "price": {"type": "string"},
        "image_urls": {"type": "array"},
        "publish_time": {"type": "string", "format": "datetime"}
    }
}
```

---

## 参考资料

- FishOps 项目: https://github.com/a1667834841/FishOps/blob/main/xianyu-api.js
- MTOP 协议分析: 阿里系 API 标准格式
- 闲鱼 H5 端抓包: Chrome DevTools Network 分析