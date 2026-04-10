# HTTP 直调搜索方案设计

## 背景

当前搜索实现依赖 Playwright 的 `page.evaluate()` 执行 JavaScript 发送 HTTP 请求。这种方式存在稳定性问题：

1. `page.evaluate()` 连续调用时会卡住（CDP 连接稳定性问题）
2. 搜索结果偶发返回 0 条
3. 调试困难（JavaScript 执行环境不易观察）

## 目标

- 从根本上解决搜索稳定性问题，每次搜索都能返回结果或明确的错误信息
- 完全绕过 `page.evaluate()`，使用纯 HTTP 请求
- 复用现有的 cookie 同步机制（CookieKeepaliveService）
- 参考 FishOps 项目实现：https://github.com/a1667834841/FishOps/blob/main/xianyu-api.js

## 架构

```
┌─────────────────┐
│   XianyuApp     │
│  (统一入口)      │
└─────────────────┘
        │
        ▼
┌─────────────────────────────────────┐
│        HttpApiSearchClient          │
│  (新增：纯 HTTP 请求，不依赖浏览器)    │
│                                     │
│  - httpx.AsyncClient 发送 POST      │
│  - 从 SessionManager 获取 cookie    │
│  - 签名逻辑复用现有 _generate_sign() │
└─────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────┐
│       SessionManager                │
│  (现有：cookie 缓存 + 签名)          │
│                                     │
│  - load_cached_cookie() 读取缓存    │
│  - _generate_sign() 生成 MD5 签名   │
│  - CookieKeepaliveService 定期刷新  │
└─────────────────────────────────────┘
```

## 组件设计

### HttpApiSearchClient（新增）

**职责**：发送 HTTP POST 请求到闲鱼搜索 API，返回商品列表。

**关键方法**：

```python
class HttpApiSearchClient:
    def __init__(self, session_manager: SessionManager):
        self.session_manager = session_manager
        self._client: Optional[httpx.AsyncClient] = None
    
    async def fetch_page(
        self, 
        params: SearchParams, 
        page_number: int
    ) -> HttpApiResult:
        """发送单页搜索请求"""
        
    async def close(self):
        """关闭 HTTP 客户端"""
```

**依赖**：
- `SessionManager`：获取 cookie 和签名
- `httpx.AsyncClient`：发送 HTTP 请求（异步）

**请求格式**：

```
POST https://h5api.m.goofish.com/h5/mtop.taobao.idlemtopsearch.pc.search/1.0/

URL 参数：
- jsv=2.7.2
- appKey=34839810
- t={timestamp}
- sign={md5签名}
- api=mtop.taobao.idlemtopsearch.pc.search
- v=1.0
- type=originaljson
- dataType=json
- timeout=20000

请求体（form-urlencoded）：
- data={JSON请求参数}

请求参数（JSON）：
{
    "pageNumber": page_number,
    "rowsPerPage": 30,
    "keyword": keyword,
    "sortValue": "",
    "sortField": "",
    "propValueStr": JSON.stringify({
        "searchFilter": "publishDays:14;",
        "minPrice": min_price ?? "",
        "maxPrice": max_price ?? "",
        "freeShipping": free_ship ? "1" : ""
    }),
    "searchReqFromPage": "pcSearch"
}

请求头：
- cookie: {完整cookie字符串}
- content-type: application/x-www-form-urlencoded
- origin: https://www.goofish.com
- referer: https://www.goofish.com/
```

**签名算法**（复用现有）：

```
sign = MD5(token + "&" + timestamp + "&" + appKey + "&" + dataStr)
```

其中：
- `token`：从 `_m_h5_tk` cookie 提取，格式为 `token_timestamp`，取下划线前的部分
- `timestamp`：从 `_m_h5_tk` cookie 提取时间戳部分，或使用当前时间
- `appKey`：固定值 `34839810`
- `dataStr`：JSON.stringify(data)

### StableSearchRunner（现有，改造）

**改造点**：
- 将 `PageApiSearchClient` 替换为 `HttpApiSearchClient`
- 去除 `ensure_page_ready` 依赖（不再需要浏览器页面）
- 保持现有的分页、去重、stale page 控制逻辑

### XianyuApp（改造）

**改造点**：
- `search_with_meta()` 方法使用 `HttpApiSearchClient` 作为主引擎
- 去除 PageApi 和 Browser Fallback 降级链路（纯 HTTP 方案）

## 数据流

### 搜索流程

```
用户调用 search(keyword)
    │
    ▼
XianyuApp.search_with_meta()
    │
    ▼
HttpApiSearchClient.fetch_page()
    │
    ├─► SessionManager.load_cached_cookie() → 获取完整 cookie
    │
    ├─► 从 cookie 提取 _m_h5_tk → token + timestamp
    │
    ├─► SessionManager._generate_sign() → 生成签名
    │
    ├─► httpx.AsyncClient.post() → 发送 HTTP 请求
    │
    └─► 解析响应 → 提取商品列表
    │
    ▼
StableSearchRunner.search()
    │
    ├─► 循环获取多页直到满足 rows 数量
    │
    └─► 去重 + stale page 控制
    │
    ▼
返回 SearchOutcome
```

### Cookie 同步流程（现有，不变）

```
CookieKeepaliveService 定时任务
    │
    ▼
定期刷新 keepalive 页面（默认每 5 分钟）
    │
    ▼
browser.get_full_cookie_string()
    │
    ▼
SessionManager.save_cookie()
    │
    ▼
写入 ~/.claude/xianyu-tokens/token.json
```

**关键点**：
- HTTP 搜索只读取缓存 cookie，不主动刷新
- Cookie 有效性由 keepalive 定时任务保证
- 如果 cookie 过期，HTTP 搜索会失败并返回错误

## 错误处理

### HTTP 请求错误

| 错误类型 | 处理方式 |
|---------|---------|
| Cookie 过期（SESSION_EXPIRED） | 返回错误信息，提示用户重新登录 |
| 网络超时 | 重试 2 次，间隔 1 秒 |
| API 返回空数据 | 记录日志，返回空列表（stale page 处理） |
| 签名错误（ILLEGAL_SIGN） | 检查 cookie 格式，重试一次 |
| 其他 HTTP 错误 | 记录日志，抛出 SearchError |

### Cookie 缺失处理

```python
cached_cookie = session_manager.load_cached_cookie()
if not cached_cookie:
    # 尝试从浏览器获取
    full_cookie = await browser.get_full_cookie_string()
    if full_cookie:
        session_manager.save_cookie(full_cookie)
        cached_cookie = full_cookie
    else:
        raise SearchError("Cookie 缺失，请先调用 login() 或 refresh_token()")
```

### 响应解析错误

```python
ret = response.get("ret", [])
if not ret or "SUCCESS" not in ret[0]:
    if "SESSION_EXPIRED" in ret[0]:
        return HttpApiResult(items=[], error="cookie_expired", message=ret[0])
    if "ILLEGAL_SIGN" in ret[0]:
        return HttpApiResult(items=[], error="sign_error", message=ret[0])
    return HttpApiResult(items=[], error="api_error", message=ret[0])
```

## 测试策略

### 单元测试

| 测试文件 | 测试内容 |
|---------|---------|
| `tests/test_http_api_search_unit.py` | HttpApiSearchClient 的签名、请求构造、响应解析 |

**关键测试点**：
- 签名生成正确性（对比 FishOps 的 JavaScript 实现）
- Cookie 格式解析（从 `name=value; name2=value2` 提取 `_m_h5_tk`）
- 响应解析正确性（从 `resultList` 提取商品信息）
- 错误响应处理（SESSION_EXPIRED、ILLEGAL_SIGN 等）

### 集成测试

| 测试文件 | 测试内容 |
|---------|---------|
| `tests/test_http_api_search_integration.py` | 真实 HTTP 请求（需要有效 cookie） |

**前置条件**：
- 需要先登录获取有效 cookie
- 使用 `SessionManager.login()` 或手动设置 cookie

## 实现计划

| 步骤 | 内容 | 预估时间 |
|-----|------|---------|
| 1 | 新增依赖：httpx（在 pyproject.toml 或 requirements.txt） | 5 分钟 |
| 2 | 新增 `HttpApiSearchClient` 类（在 `src/http_search.py`） | 30 分钟 |
| 3 | 改造 `StableSearchRunner` 使用新客户端 | 15 分钟 |
| 4 | 改造 `XianyuApp.search_with_meta()` | 10 分钟 |
| 5 | 编写单元测试 `test_http_api_search_unit.py` | 20 分钟 |
| 6 | 编写集成测试 `test_http_api_search_integration.py` | 15 分钟 |
| 7 | 容器验证（docker compose build && up -d） | 10 分钟 |

**总计**：约 1.5 小时

## 参考资料

- FishOps xianyu-api.js：https://github.com/a1667834841/FishOps/blob/main/xianyu-api.js
- 现有 SessionManager 签名逻辑：`src/session.py` `_generate_sign()` 方法
- 现有 CookieKeepaliveService：`src/keepalive.py`

## 风险与限制

### 风险

1. **Cookie 过期频率**：如果 cookie 过期太快（如 30 分钟），keepalive 定时任务可能来不及刷新
   - 解决：调整 keepalive 间隔（当前默认 5 分钟，可根据实际情况调整）

2. **API 变更**：闲鱼搜索 API 可能变更参数或签名算法
   - 解决：参考 FishOps 项目持续更新

3. **并发限制**：HTTP 直调可能被闲鱼限流
   - 解决：控制并发数，添加请求间隔

### 限制

1. **不支持复杂交互**：无法处理需要浏览器渲染的场景（如动态筛选、复杂 UI 交互）
   - 当前场景：纯搜索请求，不涉及复杂交互

2. **依赖 cookie 有效**：如果 cookie 无效，所有搜索都会失败
   - 解决：提供 `check_session()` 接口让用户验证 cookie

## 后续优化方向

1. **添加请求缓存**：相同关键词缓存结果，减少 API 调用
2. **并发请求优化**：多页并发获取，提升速度
3. **错误降级**：HTTP 失败时降级到 Browser Fallback（可选，取决于稳定性需求）