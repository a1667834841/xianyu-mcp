"""
http_search.py - HTTP 直接调用闲鱼搜索 API
绕过浏览器 JavaScript 执行，直接调用 MTOP API
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.parse
from dataclasses import dataclass, field
import asyncio
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Dict, List, Optional, Union

try:
    import httpx
except ImportError:
    httpx = None

if TYPE_CHECKING:
    from .core import SearchItem, SearchParams


def _get_search_classes():
    """Lazy import to avoid circular dependency"""
    try:
        from .core import SearchItem, SearchParams
    except ImportError:
        from core import SearchItem, SearchParams
    return SearchItem, SearchParams


class HttpApiSearchError(RuntimeError):
    """HTTP API 搜索错误"""

    def __init__(self, error_type: str, message: str):
        self.error_type = error_type
        super().__init__(f"{error_type}: {message}")


@dataclass
class HttpApiResult:
    """HTTP API 搜索结果"""

    keyword: str
    page: int
    items: List[SearchItem]
    error: Optional[str] = None
    message: str = ""
    raw_response: Optional[Dict[str, Any]] = None


class HttpApiSearchClient:
    """HTTP 直接调用搜索 API 客户端"""

    engine_name = "http_api"
    API_BASE_URL = (
        "https://h5api.m.goofish.com/h5/mtop.taobao.idlemtopsearch.pc.search/1.0/"
    )
    API_NAME = "mtop.taobao.idlemtopsearch.pc.search"
    APP_KEY = "34839810"
    API_VERSION = "1.0"

    def __init__(
        self,
        get_cookie: Optional[
            Union[Callable[[], str], Callable[[], Awaitable[str]]]
        ] = None,
        timeout: float = 20.0,
    ):
        self._get_cookie = get_cookie
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    def _md5(self, text: str) -> str:
        """计算 MD5 哈希"""
        return hashlib.md5(text.encode()).hexdigest()

    def _extract_token_from_cookie(self, cookie_str: str) -> str:
        """从 cookie 字符串提取 token

        _m_h5_tk 格式为 token_timestamp，提取 token 部分
        """
        if not cookie_str:
            return ""

        match = re.search(r"_m_h5_tk=([^;]+)", cookie_str)
        if not match:
            return ""

        token_value = match.group(1)
        last_underscore_idx = token_value.rfind("_")
        if last_underscore_idx > 0:
            return token_value[:last_underscore_idx]
        return token_value

    def _generate_sign(self, token: str, timestamp: str, data_str: str) -> str:
        """生成 MTOP 签名

        签名算法: MD5(token + "&" + timestamp + "&" + appKey + "&" + dataStr)
        """
        sign_str = f"{token}&{timestamp}&{self.APP_KEY}&{data_str}"
        return self._md5(sign_str)

    def _build_request_data(
        self, params: SearchParams, page_number: int
    ) -> Dict[str, Any]:
        """构建请求参数"""
        return {
            "pageNumber": page_number,
            "keyword": params.keyword,
            "fromFilter": False,
            "rowsPerPage": 30,
            "sortValue": params.sort_order or "",
            "sortField": params.sort_field or "",
            "customDistance": "",
            "gps": "",
            "propValueStr": {},
            "customGps": "",
            "searchReqFromPage": "pcSearch",
            "extraFilterValue": "{}",
            "userPositionJson": "{}",
        }

    def _parse_response(
        self, response: Dict[str, Any], keyword: str, page: int
    ) -> List["SearchItem"]:
        """解析 API 响应"""
        SearchItem, _ = _get_search_classes()

        ret = response.get("ret", [])
        if not ret:
            return []

        ret_str = ret[0] if isinstance(ret, list) else str(ret)

        if "SESSION_EXPIRED" in ret_str:
            raise HttpApiSearchError("SESSION_EXPIRED", ret_str)

        if "ILLEGAL_SIGN" in ret_str:
            raise HttpApiSearchError("ILLEGAL_SIGN", ret_str)

        if not ret_str.startswith("SUCCESS"):
            raise HttpApiSearchError("API_ERROR", ret_str)

        data = response.get("data")
        if not data:
            return []

        result_list = data.get("resultList", [])
        if not result_list:
            return []

        items = []
        for entry in result_list:
            try:
                main = entry.get("data", {}).get("item", {}).get("main", {})
                if not main:
                    continue

                ex_content = main.get("exContent", {})
                click_args = main.get("clickParam", {}).get("args", {})

                item_id = click_args.get("item_id") or ex_content.get("itemId", "")
                if not item_id:
                    continue

                def extract_text(val: Any) -> str:
                    if isinstance(val, str):
                        return val
                    if isinstance(val, list):
                        return "".join(
                            v.get("text", "") if isinstance(v, dict) else str(v)
                            for v in val
                        )
                    return str(val or "")

                # price: 优先从 clickParam 获取，否则从 price 数组解析
                price_str = click_args.get("price") or click_args.get("displayPrice", "")
                if not price_str:
                    price_parts = ex_content.get("price", [])
                    if isinstance(price_parts, list):
                        price_str = "".join(
                            p.get("text", "") for p in price_parts
                            if isinstance(p, dict)
                        )
                # original_price: API 无可靠来源，保持空
                original_price_str = ""

                publish_time_str = _format_publish_time(click_args.get("publishTime"))

                pic_url = ex_content.get("picUrl", "")
                image_urls = [pic_url] if pic_url else []

                want_cnt = _extract_want_cnt(ex_content)

                item = SearchItem(
                    item_id=str(item_id),
                    title=ex_content.get("title", ""),
                    price=price_str,
                    original_price=original_price_str,
                    want_cnt=want_cnt,
                    seller_nick=ex_content.get("userNickName", ""),
                    seller_city=ex_content.get("area", ""),
                    image_urls=image_urls,
                    detail_url=f"https://www.goofish.com/item?id={item_id}",
                    is_free_ship=False,  # API 无此字段
                    publish_time=publish_time_str,
                    exposure_score=0.0,
                )
                items.append(item)

            except Exception:
                continue

        return items


    async def _send_request(
        self,
        cookie: str,
        data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """发送 HTTP 请求"""
        if httpx is None:
            raise ImportError("httpx is required for HttpApiSearchClient")

        timestamp = str(int(time.time() * 1000))
        data_str = json.dumps(data)
        token = self._extract_token_from_cookie(cookie)
        sign = self._generate_sign(token, timestamp, data_str)

        query_params = {
            "jsv": "2.7.2",
            "appKey": self.APP_KEY,
            "t": timestamp,
            "sign": sign,
            "api": self.API_NAME,
            "v": self.API_VERSION,
            "type": "originaljson",
            "accountSite": "xianyu",
            "dataType": "json",
            "timeout": str(int(self.timeout * 1000)),
            "sessionOption": "AutoLoginOnly",
            "spm_cnt": "a21ybx.search.0.0",
        }

        headers = {
            "Accept": "application/json",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": "https://www.goofish.com",
            "Referer": "https://www.goofish.com/",
            "Cookie": cookie,
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
            "Sec-Ch-Ua": '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"macOS"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
        }

        request_body = f"data={urllib.parse.quote(json.dumps(data))}"

        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)

        response = await self._client.post(
            self.API_BASE_URL,
            params=query_params,
            headers=headers,
            content=request_body,
        )
        response.raise_for_status()
        return response.json()

    async def aclose(self):
        """Close HTTP client"""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def fetch_page(
        self,
        params: SearchParams,
        page_number: int,
        _get_cookie: Optional[
            Union[Callable[[], str], Callable[[], Awaitable[str]]]
        ] = None,
    ) -> HttpApiResult:
        """获取搜索结果页

        Args:
            params: 搜索参数
            page_number: 页码
            _get_cookie: 获取 cookie 的回调函数（可选，优先使用构造函数传入的）

        Returns:
            HttpApiResult: 搜索结果
        """
        cookie_getter = _get_cookie or self._get_cookie
        if cookie_getter is None:
            return HttpApiResult(
                keyword=params.keyword,
                page=page_number,
                items=[],
                error="NO_COOKIE_PROVIDER",
                message="No cookie provider configured",
                raw_response=None,
            )

        try:
            if callable(cookie_getter):
                result = cookie_getter()
                if asyncio.iscoroutine(result):
                    cookie = await result
                else:
                    cookie = result
            else:
                cookie = cookie_getter or ""

            data = self._build_request_data(params, page_number)
            response = await self._send_request(cookie, data)

            items = self._parse_response(response, params.keyword, page_number)

            return HttpApiResult(
                keyword=params.keyword,
                page=page_number,
                items=items,
                error=None,
                message="",
                raw_response=response,
            )

        except HttpApiSearchError as e:
            return HttpApiResult(
                keyword=params.keyword,
                page=page_number,
                items=[],
                error=e.error_type,
                message=str(e),
                raw_response=None,
            )

        except Exception as e:
            return HttpApiResult(
                keyword=params.keyword,
                page=page_number,
                items=[],
                error="NETWORK_ERROR",
                message=str(e),
                raw_response=None,
            )


def _extract_want_cnt(ex_content: Dict[str, Any]) -> int:
    """从 fishTags.r3 提取想要人数"""
    try:
        fish_tags = ex_content.get("fishTags", {})
        r3_tags = fish_tags.get("r3", {}).get("tagList", [])
        if not isinstance(r3_tags, list):
            return 0
        for tag in r3_tags:
            if not isinstance(tag, dict):
                continue
            content = tag.get("data", {}).get("content", "")
            if "人想要" in content:
                match = re.search(r"(\d+)人想要", content)
                if match:
                    return int(match.group(1))
    except (KeyError, TypeError):
        pass
    return 0


def _format_publish_time(publish_time_ms: Any) -> Optional[str]:
    """格式化发布时间（毫秒转字符串）"""
    try:
        from datetime import datetime
        publish_dt = datetime.fromtimestamp(int(publish_time_ms) / 1000)
        return publish_dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return None
