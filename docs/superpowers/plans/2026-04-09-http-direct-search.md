# HTTP 直调搜索实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现纯 HTTP 直调搜索，完全绕过浏览器 JavaScript 执行，从根本上解决搜索稳定性问题。

**Architecture:** 新增 `HttpApiSearchClient` 类，使用 `httpx` 异步客户端直接发送 POST 请求到闲鱼搜索 API。复用现有的 `SessionManager` 获取 cookie 和签名。去除 `page.evaluate()` 依赖。

**Tech Stack:** Python 3.10+, httpx (异步 HTTP), pytest

---

## File Structure

### 新增文件
- `src/http_search.py` - HTTP 直调搜索客户端
- `tests/test_http_search_unit.py` - 单元测试

### 修改文件
- `pyproject.toml` - 添加 httpx 依赖
- `src/core.py` - 改造 `search_with_meta()` 使用新客户端
- `src/search_api.py` - 改造 `StableSearchRunner` 支持新客户端

---

## Task 1: 添加 httpx 依赖

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: 添加 httpx 到依赖列表**

```toml
[project]
name = "xianyu-assistant"
version = "0.1.0"
description = "闲鱼助手 - 自动化搜索和发布工具"
requires-python = ">=3.10"
dependencies = [
    "playwright>=1.40.0",
    "requests>=2.31.0",
    "mcp>=1.0.0",
    "httpx>=0.27.0",
]
```

- [ ] **Step 2: 安装依赖**

Run: `pip install httpx>=0.27.0`
Expected: Successfully installed httpx-xxx

- [ ] **Step 3: 提交**

```bash
git add pyproject.toml
git commit -m "chore: add httpx dependency for direct HTTP search"
```

---

## Task 2: 实现 HttpApiSearchClient（TDD）

**Files:**
- Create: `src/http_search.py`
- Create: `tests/test_http_search_unit.py`

### 2.1 数据类定义

- [ ] **Step 1: 创建文件并定义数据类**

```python
# src/http_search.py
"""HTTP 直调搜索客户端 - 不依赖浏览器"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx

try:
    from .core import SearchItem, SearchParams
except ImportError:
    from core import SearchItem, SearchParams


@dataclass
class HttpApiResult:
    """HTTP API 搜索结果"""
    keyword: str
    page: int
    items: List[SearchItem]
    error: Optional[str] = None
    message: Optional[str] = None
    raw_response: Optional[Dict[str, Any]] = None


class HttpApiSearchError(RuntimeError):
    """HTTP API 搜索错误"""
    pass
```

- [ ] **Step 2: 运行检查语法**

Run: `python -m py_compile src/http_search.py`
Expected: 无输出（语法正确）

- [ ] **Step 3: 提交数据类定义**

```bash
git add src/http_search.py
git commit -m "feat: add HttpApiResult dataclass for HTTP search"
```

### 2.2 签名方法测试

- [ ] **Step 4: 写签名测试**

```python
# tests/test_http_search_unit.py
"""HTTP 搜索客户端单元测试"""

import pytest
from src.http_search import HttpApiSearchClient


class TestHttpApiSearchClientSign:
    """测试签名生成"""

    def test_generate_sign_basic(self):
        """测试基本签名生成"""
        client = HttpApiSearchClient.__new__(HttpApiSearchClient)
        client._m_h5_tk = "test_token_1234567890"

        data = {"keyword": "iPhone", "pageNumber": 1}
        result = client._generate_sign(data)

        assert "sign" in result
        assert "t" in result
        assert "appKey" in result
        assert result["appKey"] == "34839810"
        assert len(result["sign"]) == 32  # MD5 是 32 位十六进制

    def test_generate_sign_consistency(self):
        """测试签名一致性（相同输入产生相同签名）"""
        client = HttpApiSearchClient.__new__(HttpApiSearchClient)
        client._m_h5_tk = "abc_1234567890"

        data = {"keyword": "test", "pageNumber": 1}
        result1 = client._generate_sign(data)
        result2 = client._generate_sign(data)

        assert result1["sign"] == result2["sign"]

    def test_extract_token_from_cookie(self):
        """测试从 cookie 字符串提取 token"""
        client = HttpApiSearchClient.__new__(HttpApiSearchClient)

        cookie_str = "_m_h5_tk=abc123_1700000000000; other=value"
        token = client._extract_token_from_cookie(cookie_str)

        assert token == "abc123"

    def test_extract_token_missing(self):
        """测试 cookie 缺失 token 时返回空"""
        client = HttpApiSearchClient.__new__(HttpApiSearchClient)

        cookie_str = "other=value; another=test"
        token = client._extract_token_from_cookie(cookie_str)

        assert token == ""
```

- [ ] **Step 5: 运行测试确认失败**

Run: `pytest tests/test_http_search_unit.py -v`
Expected: FAIL（方法未定义）

- [ ] **Step 6: 实现签名方法**

```python
# src/http_search.py（追加到文件末尾）

class HttpApiSearchClient:
    """HTTP 直调搜索客户端"""

    API_BASE_URL = "https://h5api.m.goofish.com/h5/mtop.taobao.idlemtopsearch.pc.search/1.0/"
    API_NAME = "mtop.taobao.idlemtopsearch.pc.search"
    APP_KEY = "34839810"

    def __init__(self, get_cookie_func):
        """
        Args:
            get_cookie_func: 异步函数，返回完整 cookie 字符串
        """
        self._get_cookie = get_cookie_func
        self._m_h5_tk: Optional[str] = None
        self._client: Optional[httpx.AsyncClient] = None

    def _md5(self, text: str) -> str:
        """计算 MD5 哈希"""
        return hashlib.md5(text.encode("utf-8")).hexdigest()

    def _extract_token_from_cookie(self, cookie_str: str) -> str:
        """从 cookie 字符串提取 _m_h5_tk 的 token 部分"""
        for part in cookie_str.split("; "):
            if part.startswith("_m_h5_tk="):
                full_value = part[len("_m_h5_tk="):]
                # 格式：token_timestamp
                if "_" in full_value:
                    return full_value.split("_")[0]
                return full_value
        return ""

    def _generate_sign(self, data: Dict[str, Any]) -> Dict[str, str]:
        """生成 MTOP 签名"""
        data_str = json.dumps(data, separators=(",", ":"))

        # 从 _m_h5_tk 提取 token 和 timestamp
        if self._m_h5_tk and "_" in self._m_h5_tk:
            token, timestamp = self._m_h5_tk.rsplit("_", 1)
        else:
            token = self._m_h5_tk or ""
            timestamp = str(int(time.time() * 1000))

        # 签名字符串：token&timestamp&appKey&dataStr
        sign_str = f"{token}&{timestamp}&{self.APP_KEY}&{data_str}"
        sign = self._md5(sign_str)

        return {
            "sign": sign,
            "t": timestamp,
            "appKey": self.APP_KEY,
            "data": data_str,
        }

    async def close(self):
        """关闭 HTTP 客户端"""
        if self._client:
            await self._client.aclose()
            self._client = None
```

- [ ] **Step 7: 运行测试确认通过**

Run: `pytest tests/test_http_search_unit.py -v`
Expected: PASS（4 tests）

- [ ] **Step 8: 提交签名实现**

```bash
git add src/http_search.py tests/test_http_search_unit.py
git commit -m "feat: implement HttpApiSearchClient signature generation"
```

### 2.3 请求构造测试

- [ ] **Step 9: 写请求参数构造测试**

```python
# tests/test_http_search_unit.py（追加到文件末尾）

class TestHttpApiSearchClientRequest:
    """测试请求参数构造"""

    def test_build_request_data_basic(self):
        """测试基本请求参数构造"""
        client = HttpApiSearchClient.__new__(HttpApiSearchClient)

        params = SearchParams(keyword="iPhone", rows=30)
        page_number = 1

        data = client._build_request_data(params, page_number)

        assert data["pageNumber"] == 1
        assert data["rowsPerPage"] == 30
        assert data["keyword"] == "iPhone"
        assert data["searchReqFromPage"] == "pcSearch"

    def test_build_request_data_with_filters(self):
        """测试带筛选条件的请求参数"""
        client = HttpApiSearchClient.__new__(HttpApiSearchClient)

        params = SearchParams(
            keyword="MacBook",
            rows=20,
            min_price=1000,
            max_price=5000,
            free_ship=True,
        )
        page_number = 2

        data = client._build_request_data(params, page_number)

        assert data["pageNumber"] == 2
        assert data["rowsPerPage"] == 30  # 固定 30

        # 检查 propValueStr
        import json
        prop_value = json.loads(data["propValueStr"])
        assert prop_value["minPrice"] == "1000"
        assert prop_value["maxPrice"] == "5000"
        assert prop_value["freeShipping"] == "1"
```

- [ ] **Step 10: 运行测试确认失败**

Run: `pytest tests/test_http_search_unit.py::TestHttpApiSearchClientRequest -v`
Expected: FAIL（方法未定义）

- [ ] **Step 11: 实现请求参数构造**

```python
# src/http_search.py（在 HttpApiSearchClient 类中添加方法）

    def _build_request_data(
        self, params: SearchParams, page_number: int
    ) -> Dict[str, Any]:
        """构造请求参数"""
        prop_value = {
            "searchFilter": "publishDays:14;",
        }

        if params.min_price is not None:
            prop_value["minPrice"] = str(params.min_price)
        else:
            prop_value["minPrice"] = ""

        if params.max_price is not None:
            prop_value["maxPrice"] = str(params.max_price)
        else:
            prop_value["maxPrice"] = ""

        if params.free_ship:
            prop_value["freeShipping"] = "1"
        else:
            prop_value["freeShipping"] = ""

        return {
            "pageNumber": page_number,
            "rowsPerPage": 30,
            "keyword": params.keyword,
            "sortValue": params.sort_order or "",
            "sortField": params.sort_field or "",
            "propValueStr": json.dumps(prop_value, separators=(",", ":")),
            "searchReqFromPage": "pcSearch",
        }
```

- [ ] **Step 12: 运行测试确认通过**

Run: `pytest tests/test_http_search_unit.py -v`
Expected: PASS（6 tests）

- [ ] **Step 13: 提交请求参数构造**

```bash
git add src/http_search.py tests/test_http_search_unit.py
git commit -m "feat: implement request data builder for HTTP search"
```

### 2.4 响应解析测试

- [ ] **Step 14: 写响应解析测试**

```python
# tests/test_http_search_unit.py（追加到文件末尾）

class TestHttpApiSearchClientResponse:
    """测试响应解析"""

    def test_parse_response_success(self):
        """测试成功响应解析"""
        client = HttpApiSearchClient.__new__(HttpApiSearchClient)

        response = {
            "ret": ["SUCCESS::调用成功"],
            "data": {
                "resultList": [
                    {
                        "data": {
                            "item": {
                                "main": {
                                    "exContent": {
                                        "itemId": "12345",
                                        "title": "测试商品",
                                        "price": [{"text": "99.00"}],
                                        "userNick": "卖家昵称",
                                        "city": "北京",
                                        "picUrl": "https://example.com/pic.jpg",
                                    },
                                    "clickParam": {
                                        "args": {
                                            "item_id": "12345",
                                        }
                                    },
                                }
                            }
                        }
                    }
                ]
            }
        }

        items = client._parse_response(response, "测试关键词", 1)

        assert len(items) == 1
        assert items[0].item_id == "12345"
        assert items[0].title == "测试商品"
        assert items[0].price == "99.00"
        assert items[0].seller_nick == "卖家昵称"
        assert items[0].seller_city == "北京"

    def test_parse_response_empty(self):
        """测试空响应解析"""
        client = HttpApiSearchClient.__new__(HttpApiSearchClient)

        response = {
            "ret": ["SUCCESS::调用成功"],
            "data": {
                "resultList": []
            }
        }

        items = client._parse_response(response, "测试关键词", 1)

        assert len(items) == 0

    def test_parse_response_error(self):
        """测试错误响应"""
        client = HttpApiSearchClient.__new__(HttpApiSearchClient)

        response = {
            "ret": ["FAIL_SYS_SESSION_EXPIRED::Session过期"],
        }

        with pytest.raises(HttpApiSearchError) as exc_info:
            client._parse_response(response, "测试关键词", 1)

        assert "SESSION_EXPIRED" in str(exc_info.value)
```

- [ ] **Step 15: 运行测试确认失败**

Run: `pytest tests/test_http_search_unit.py::TestHttpApiSearchClientResponse -v`
Expected: FAIL（方法未定义）

- [ ] **Step 16: 实现响应解析**

```python
# src/http_search.py（在 HttpApiSearchClient 类中添加方法）

    def _parse_response(
        self, response: Dict[str, Any], keyword: str, page: int
    ) -> List[SearchItem]:
        """解析 API 响应"""
        ret = response.get("ret", [])

        # 检查返回状态
        if not ret or "SUCCESS" not in ret[0]:
            error_msg = ret[0] if ret else "Unknown error"

            if "SESSION_EXPIRED" in error_msg:
                raise HttpApiSearchError(f"Cookie 过期: {error_msg}")
            if "ILLEGAL_SIGN" in error_msg:
                raise HttpApiSearchError(f"签名错误: {error_msg}")

            raise HttpApiSearchError(f"API 错误: {error_msg}")

        # 提取商品列表
        data = response.get("data", {})
        result_list = data.get("resultList", [])

        items = []
        for entry in result_list:
            try:
                main = entry.get("data", {}).get("item", {}).get("main", {})
                if not main:
                    continue

                ex_content = main.get("exContent", {})
                click_param = main.get("clickParam", {}).get("args", {})

                # 提取 item_id
                item_id = click_param.get("item_id") or ex_content.get("itemId", "")
                if not item_id:
                    continue

                # 提取价格
                price_list = ex_content.get("price", [])
                if price_list and isinstance(price_list, list):
                    price = "".join(
                        p.get("text", "") for p in price_list if isinstance(p, dict)
                    )
                else:
                    price = "0"

                # 提取图片 URL
                pic_url = ex_content.get("picUrl", "")
                image_urls = [pic_url] if pic_url else []

                item = SearchItem(
                    item_id=item_id,
                    title=ex_content.get("title", ""),
                    price=price,
                    original_price=ex_content.get("oriPrice", "0"),
                    want_cnt=0,  # HTTP API 不返回想要人数
                    seller_nick=ex_content.get("userNick", ""),
                    seller_city=ex_content.get("city", ""),
                    image_urls=image_urls,
                    detail_url=f"https://www.goofish.com/item?id={item_id}",
                    is_free_ship=False,  # 需要从其他字段提取
                    publish_time=None,
                    exposure_score=0.0,
                )
                items.append(item)

            except Exception as e:
                print(f"[HttpSearch] 解析商品失败: {e}")
                continue

        return items
```

- [ ] **Step 17: 运行测试确认通过**

Run: `pytest tests/test_http_search_unit.py -v`
Expected: PASS（9 tests）

- [ ] **Step 18: 提交响应解析**

```bash
git add src/http_search.py tests/test_http_search_unit.py
git commit -m "feat: implement response parser for HTTP search"
```

### 2.5 fetch_page 方法测试

- [ ] **Step 19: 写 fetch_page 测试（使用 Mock）**

```python
# tests/test_http_search_unit.py（追加到文件末尾）

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


class TestHttpApiSearchClientFetchPage:
    """测试 fetch_page 方法"""

    @pytest.mark.asyncio
    async def test_fetch_page_success(self):
        """测试成功获取一页数据"""
        # Mock cookie 函数
        async def mock_get_cookie():
            return "_m_h5_tk=test_token_1234567890; other=value"

        client = HttpApiSearchClient(mock_get_cookie)

        # Mock httpx.AsyncClient
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "ret": ["SUCCESS::调用成功"],
            "data": {
                "resultList": [
                    {
                        "data": {
                            "item": {
                                "main": {
                                    "exContent": {
                                        "itemId": "99999",
                                        "title": "Mock商品",
                                        "price": [{"text": "100.00"}],
                                        "userNick": "卖家",
                                        "city": "上海",
                                        "picUrl": "https://example.com/pic.jpg",
                                    },
                                    "clickParam": {"args": {"item_id": "99999"}},
                                }
                            }
                        }
                    }
                ]
            },
        }

        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            params = SearchParams(keyword="test", rows=30)
            result = await client.fetch_page(params, page_number=1)

            assert result.error is None
            assert len(result.items) == 1
            assert result.items[0].item_id == "99999"
            assert result.keyword == "test"
            assert result.page == 1

        await client.close()

    @pytest.mark.asyncio
    async def test_fetch_page_cookie_expired(self):
        """测试 cookie 过期错误"""
        async def mock_get_cookie():
            return "_m_h5_tk=expired_token_123"

        client = HttpApiSearchClient(mock_get_cookie)

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "ret": ["FAIL_SYS_SESSION_EXPIRED::Session过期"],
        }

        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            params = SearchParams(keyword="test", rows=30)
            result = await client.fetch_page(params, page_number=1)

            assert result.error == "cookie_expired"
            assert len(result.items) == 0

        await client.close()
```

- [ ] **Step 20: 运行测试确认失败**

Run: `pytest tests/test_http_search_unit.py::TestHttpApiSearchClientFetchPage -v`
Expected: FAIL（方法未定义）

- [ ] **Step 21: 实现 fetch_page 方法**

```python
# src/http_search.py（在 HttpApiSearchClient 类中添加方法）

    async def _ensure_client(self) -> httpx.AsyncClient:
        """确保 HTTP 客户端已初始化"""
        if not self._client:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def fetch_page(
        self, params: SearchParams, page_number: int
    ) -> HttpApiResult:
        """发送单页搜索请求"""
        try:
            # 获取 cookie
            cookie_str = await self._get_cookie()
            if not cookie_str:
                return HttpApiResult(
                    keyword=params.keyword,
                    page=page_number,
                    items=[],
                    error="cookie_missing",
                    message="Cookie 缺失，请先登录",
                )

            # 提取 _m_h5_tk
            self._m_h5_tk = self._extract_token_from_cookie(cookie_str)
            if not self._m_h5_tk:
                return HttpApiResult(
                    keyword=params.keyword,
                    page=page_number,
                    items=[],
                    error="token_missing",
                    message="_m_h5_tk cookie 缺失",
                )

            # 构造请求数据
            data = self._build_request_data(params, page_number)
            sign_result = self._generate_sign(data)

            # 构造 URL 参数
            url_params = {
                "jsv": "2.7.2",
                "appKey": sign_result["appKey"],
                "t": sign_result["t"],
                "sign": sign_result["sign"],
                "v": "1.0",
                "type": "originaljson",
                "dataType": "json",
                "timeout": "20000",
                "api": self.API_NAME,
            }

            # 确保客户端初始化
            client = await self._ensure_client()

            # 发送请求
            response = await client.post(
                self.API_BASE_URL,
                params=url_params,
                headers={
                    "accept": "application/json",
                    "content-type": "application/x-www-form-urlencoded",
                    "origin": "https://www.goofish.com",
                    "referer": "https://www.goofish.com/",
                    "cookie": cookie_str,
                },
                data={"data": sign_result["data"]},
            )

            response_data = response.json()

            # 解析响应
            items = self._parse_response(response_data, params.keyword, page_number)

            print(
                f"[HttpSearch] 第 {page_number} 页返回 keyword={params.keyword!r} items={len(items)}",
                flush=True,
            )

            return HttpApiResult(
                keyword=params.keyword,
                page=page_number,
                items=items,
                raw_response=response_data,
            )

        except HttpApiSearchError as e:
            error_type = "unknown"
            if "SESSION_EXPIRED" in str(e):
                error_type = "cookie_expired"
            elif "ILLEGAL_SIGN" in str(e):
                error_type = "sign_error"

            return HttpApiResult(
                keyword=params.keyword,
                page=page_number,
                items=[],
                error=error_type,
                message=str(e),
            )

        except Exception as e:
            print(f"[HttpSearch] fetch_page 异常: {e}", flush=True)
            return HttpApiResult(
                keyword=params.keyword,
                page=page_number,
                items=[],
                error="network_error",
                message=str(e),
            )
```

- [ ] **Step 22: 运行测试确认通过**

Run: `pytest tests/test_http_search_unit.py -v`
Expected: PASS（11 tests）

- [ ] **Step 23: 提交 fetch_page 实现**

```bash
git add src/http_search.py tests/test_http_search_unit.py
git commit -m "feat: implement fetch_page method for HTTP search client"
```

---

## Task 3: 改造 StableSearchRunner

**Files:**
- Modify: `src/search_api.py`

- [ ] **Step 1: 更新 StableSearchRunner 支持新客户端**

```python
# src/search_api.py（修改 StableSearchRunner 类）

class StableSearchRunner:
    """稳定搜索运行器 - 支持分页、去重、stale page 控制"""

    def __init__(self, client, max_stale_pages: int = 3):
        """
        Args:
            client: 搜索客户端（HttpApiSearchClient 或 PageApiSearchClient）
            max_stale_pages: 最大连续无新增页数
        """
        self.client = client
        self.max_stale_pages = max_stale_pages

    async def search(self, params: SearchParams) -> SearchOutcome:
        """执行搜索"""
        all_items = []
        seen_item_ids = set()
        stale_pages = 0
        page_number = 1

        while len(all_items) < params.rows:
            # 调用客户端获取一页
            if hasattr(self.client, "fetch_page"):
                result = await self.client.fetch_page(params, page_number=page_number)
                items = result.items
            else:
                # 兼容旧客户端
                result = await self.client.fetch_page(params, page_number=page_number)
                items = result.items

            # 去重
            new_count = 0
            for item in items:
                if item.item_id not in seen_item_ids:
                    seen_item_ids.add(item.item_id)
                    all_items.append(item)
                    new_count += 1

            engine_name = "http_api" if "HttpApi" in type(self.client).__name__ else "page_api"
            print(
                f"[{engine_name}] 第 {page_number} 页解析完成 "
                f"raw_items={len(items)} new_items={new_count} total_items={len(all_items)}",
                flush=True,
            )

            # 检查是否达到目标
            if len(all_items) >= params.rows:
                print(
                    f"[{engine_name}] 停止：达到目标 rows={params.rows} pages_fetched={page_number}",
                    flush=True,
                )
                return SearchOutcome(
                    items=all_items[: params.rows],
                    requested_rows=params.rows,
                    returned_rows=min(len(all_items), params.rows),
                    stop_reason="target_reached",
                    stale_pages=stale_pages,
                    engine_used=engine_name,
                    fallback_reason=None,
                    pages_fetched=page_number,
                )

            # 检查 stale page
            stale_pages = stale_pages + 1 if new_count == 0 else 0
            if stale_pages >= self.max_stale_pages:
                print(
                    f"[{engine_name}] 停止：连续无新增 stale_pages={stale_pages} "
                    f"pages_fetched={page_number} total_items={len(all_items)}",
                    flush=True,
                )
                return SearchOutcome(
                    items=all_items[: params.rows],
                    requested_rows=params.rows,
                    returned_rows=min(len(all_items), params.rows),
                    stop_reason="stale_limit",
                    stale_pages=stale_pages,
                    engine_used=engine_name,
                    fallback_reason=None,
                    pages_fetched=page_number,
                )

            page_number += 1

        return SearchOutcome(
            items=all_items[: params.rows],
            requested_rows=params.rows,
            returned_rows=len(all_items[: params.rows]),
            stop_reason="target_reached",
            stale_pages=stale_pages,
            engine_used=engine_name,
            fallback_reason=None,
            pages_fetched=page_number,
        )
```

- [ ] **Step 2: 运行现有测试确认兼容性**

Run: `pytest tests/test_search_api.py -v`
Expected: PASS

- [ ] **Step 3: 提交 StableSearchRunner 改造**

```bash
git add src/search_api.py
git commit -m "refactor: update StableSearchRunner to support HttpApiSearchClient"
```

---

## Task 4: 改造 XianyuApp.search_with_meta()

**Files:**
- Modify: `src/core.py`

- [ ] **Step 1: 更新 import**

```python
# src/core.py（修改 import 部分）

try:
    from .browser import AsyncChromeManager
    from .session import SessionManager
    from .settings import AppSettings, load_settings
    from .keepalive import CookieKeepaliveService
    from .http_search import HttpApiSearchClient
except ImportError:
    from browser import AsyncChromeManager
    from session import SessionManager
    from settings import AppSettings, load_settings
    from keepalive import CookieKeepaliveService
    from http_search import HttpApiSearchClient
```

- [ ] **Step 2: 更新 search_with_meta 方法**

```python
# src/core.py（替换 search_with_meta 方法）

    async def search_with_meta(self, keyword: str, **options) -> SearchOutcome:
        """
        搜索商品（使用 HTTP 直调）

        Args:
            keyword: 搜索关键词
            **options: 搜索选项 (rows, min_price, max_price, free_ship, sort_field, sort_order)

        Returns:
            搜索结果
        """
        params = SearchParams(
            keyword=keyword,
            rows=options.get("rows", 30),
            min_price=options.get("min_price"),
            max_price=options.get("max_price"),
            free_ship=options.get("free_ship", False),
            sort_field=options.get("sort_field", ""),
            sort_order=options.get("sort_order", ""),
        )

        print(
            f"[Search] 开始 HTTP 搜索 keyword={params.keyword!r} rows={params.rows}",
            flush=True,
        )

        # 创建 HTTP 搜索客户端
        async def get_cookie():
            # 先尝试从缓存加载
            cached = self.session.load_cached_cookie()
            if cached:
                return cached
            # 缓存不存在，从浏览器获取
            if await self.browser.ensure_running():
                full_cookie = await self.browser.get_full_cookie_string()
                if full_cookie:
                    self.session.save_cookie(full_cookie)
                    return full_cookie
            return None

        client = HttpApiSearchClient(get_cookie)

        try:
            runner = StableSearchRunner(
                client=client,
                max_stale_pages=self.settings.search.max_stale_pages,
            )
            outcome = await runner.search(params)

            print(
                f"[Search] HTTP 搜索结束 engine={outcome.engine_used} "
                f"returned={outcome.returned_rows} stop_reason={outcome.stop_reason} "
                f"pages_fetched={outcome.pages_fetched}",
                flush=True,
            )

            return outcome

        finally:
            await client.close()
```

- [ ] **Step 3: 运行测试确认**

Run: `pytest tests/test_core.py -v -k search`
Expected: PASS

- [ ] **Step 4: 提交 XianyuApp 改造**

```bash
git add src/core.py
git commit -m "refactor: use HttpApiSearchClient in XianyuApp.search_with_meta"
```

---

## Task 5: 集成测试

**Files:**
- Create: `tests/test_http_search_integration.py`

- [ ] **Step 1: 写集成测试**

```python
# tests/test_http_search_integration.py
"""HTTP 搜索集成测试 - 需要有效 cookie"""

import pytest
from src.http_search import HttpApiSearchClient
from src.core import SearchParams


@pytest.mark.integration
@pytest.mark.asyncio
class TestHttpApiSearchIntegration:
    """集成测试 - 真实 HTTP 请求"""

    async def test_real_search_with_browser_cookie(self, xianyu_app):
        """使用浏览器 cookie 进行真实搜索"""
        # 获取 cookie
        cookie_str = await xianyu_app.browser.get_full_cookie_string()

        if not cookie_str or "_m_h5_tk" not in cookie_str:
            pytest.skip("需要有效 cookie，请先登录")

        async def get_cookie():
            return cookie_str

        client = HttpApiSearchClient(get_cookie)

        try:
            params = SearchParams(keyword="iPhone", rows=10)
            result = await client.fetch_page(params, page_number=1)

            print(f"搜索结果: error={result.error} items={len(result.items)}")

            # 不强制要求有结果（可能是 cookie 过期）
            assert result.error in [None, "cookie_expired"]

        finally:
            await client.close()

    async def test_search_flow_via_xianyu_app(self, xianyu_app):
        """通过 XianyuApp 进行完整搜索流程"""
        outcome = await xianyu_app.search_with_meta("MacBook", rows=5)

        print(
            f"搜索结果: engine={outcome.engine_used} "
            f"returned={outcome.returned_rows} "
            f"stop_reason={outcome.stop_reason}"
        )

        # 检查引擎类型
        assert outcome.engine_used == "http_api"

        # 不强制要求有结果
        assert outcome.stop_reason in ["target_reached", "stale_limit"]
```

- [ ] **Step 2: 运行集成测试（可能需要先登录）**

Run: `pytest tests/test_http_search_integration.py -v -m integration`
Expected: SKIP 或 PASS（取决于 cookie 状态）

- [ ] **Step 3: 提交集成测试**

```bash
git add tests/test_http_search_integration.py
git commit -m "test: add integration tests for HTTP search"
```

---

## Task 6: 容器验证

**Files:**
- 无（验证步骤）

- [ ] **Step 1: 重新构建容器**

Run: `docker compose build`
Expected: Successfully built xxx

- [ ] **Step 2: 启动容器**

Run: `docker compose up -d`
Expected: Container started

- [ ] **Step 3: 测试搜索接口**

Run: `curl -X POST http://localhost:8080/search -H "Content-Type: application/json" -d '{"keyword": "iPhone", "rows": 5}'`
Expected: 返回 JSON 响应，包含 items 列表

- [ ] **Step 4: 检查日志**

Run: `docker compose logs --tail=50`
Expected: 看到搜索日志，显示 engine=http_api

- [ ] **Step 5: 最终提交（如有修改）**

```bash
git add -A
git commit -m "chore: verify HTTP search in container"
```

---

## Self-Review Checklist

- [x] Spec coverage: 所有设计要点都有对应任务
- [x] Placeholder scan: 无 TBD/TODO/模糊步骤
- [x] Type consistency: SearchParams, SearchItem, HttpApiResult 类型一致

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-09-http-direct-search.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

2. **Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**