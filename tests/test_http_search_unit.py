"""
test_http_search_unit.py - HttpApiSearchClient 单元测试
测试 HTTP 直接调用 API 的搜索客户端
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import hashlib
import json

from src.http_search import (
    HttpApiSearchClient,
    HttpApiSearchError,
    HttpApiResult,
)
from src.core import SearchParams, SearchItem


class TestHttpApiSearchClientSign:
    """测试签名生成"""

    def test_generate_sign_basic(self):
        """测试基本签名生成"""
        client = HttpApiSearchClient()
        token = "test_token"
        timestamp = "1234567890"
        data_str = '{"keyword":"test"}'

        sign = client._generate_sign(token, timestamp, data_str)

        expected = hashlib.md5(
            f"{token}&{timestamp}&{client.APP_KEY}&{data_str}".encode()
        ).hexdigest()
        assert sign == expected

    def test_generate_sign_consistency(self):
        """测试相同输入产生相同签名"""
        client = HttpApiSearchClient()
        token = "abc123"
        timestamp = "1700000000"
        data_str = '{"pageNumber":1}'

        sign1 = client._generate_sign(token, timestamp, data_str)
        sign2 = client._generate_sign(token, timestamp, data_str)

        assert sign1 == sign2

    def test_extract_token_from_cookie(self):
        """测试从 cookie 提取 token"""
        client = HttpApiSearchClient()
        cookie_str = "_m_h5_tk=test_token_1234567890; other_cookie=value"

        token = client._extract_token_from_cookie(cookie_str)

        assert token == "test_token"

    def test_extract_token_missing(self):
        """测试缺失 token 返回空字符串"""
        client = HttpApiSearchClient()
        cookie_str = "other_cookie=value; session=abc"

        token = client._extract_token_from_cookie(cookie_str)

        assert token == ""

    def test_extract_token_empty_cookie(self):
        """测试空 cookie 返回空字符串"""
        client = HttpApiSearchClient()

        token = client._extract_token_from_cookie("")

        assert token == ""

    def test_md5_function(self):
        """测试 MD5 计算"""
        client = HttpApiSearchClient()
        text = "hello world"

        result = client._md5(text)

        expected = hashlib.md5(text.encode()).hexdigest()
        assert result == expected


class TestHttpApiSearchClientRequest:
    """测试请求构建"""

    def test_build_request_data_basic(self):
        """测试基本请求数据构建"""
        client = HttpApiSearchClient()
        params = SearchParams(keyword="iPhone")
        page_number = 1

        data = client._build_request_data(params, page_number)

        assert data["pageNumber"] == 1
        assert data["rowsPerPage"] == 30
        assert data["keyword"] == "iPhone"
        assert data["searchReqFromPage"] == "pcSearch"

    def test_build_request_data_with_filters(self):
        """测试带筛选条件的请求构建"""
        client = HttpApiSearchClient()
        params = SearchParams(
            keyword="手机",
            min_price=100,
            max_price=500,
            free_ship=True,
            sort_field="price",
            sort_order="ASC",
        )
        page_number = 2

        data = client._build_request_data(params, page_number)

        assert data["pageNumber"] == 2
        assert data["keyword"] == "手机"
        assert data["sortField"] == "price"
        assert data["sortValue"] == "ASC"
        assert data["fromFilter"] == False
        assert data["searchReqFromPage"] == "pcSearch"

    def test_build_request_data_no_price_filter(self):
        """测试无价格筛选"""
        client = HttpApiSearchClient()
        params = SearchParams(keyword="test")
        page_number = 1

        data = client._build_request_data(params, page_number)

        assert data["propValueStr"] == {}
        assert data["extraFilterValue"] == "{}"

    def test_build_request_data_with_sort(self):
        """测试带排序"""
        client = HttpApiSearchClient()
        params = SearchParams(
            keyword="test",
            sort_field="pub_time",
            sort_order="DESC",
        )
        page_number = 1

        data = client._build_request_data(params, page_number)

        assert data["sortField"] == "pub_time"
        assert data["sortValue"] == "DESC"


class TestHttpApiSearchClientResponse:
    """测试响应解析"""

    def test_parse_response_success(self):
        """测试成功响应解析"""
        client = HttpApiSearchClient()
        response = {
            "ret": ["SUCCESS::调用成功"],
            "data": {
                "resultList": [
                    {
                        "data": {
                            "item": {
                                "main": {
                                    "exContent": {
                                        "itemId": "123456",
                                        "title": "测试商品",
                                        "price": [{"text": "¥100"}],
                                        "originalPrice": [{"text": "¥200"}],
                                        "wantNum": "10",
                                        "userNick": "seller",
                                        "city": "北京",
                                        "picUrl": "http://example.com/img.jpg",
                                        "freeDelivery": True,
                                    },
                                    "clickParam": {"args": {"item_id": "123456"}},
                                }
                            }
                        }
                    }
                ]
            },
        }

        items = client._parse_response(response, "iPhone", 1)

        assert len(items) == 1
        assert items[0].item_id == "123456"
        assert items[0].title == "测试商品"
        assert items[0].price == "¥100"
        assert items[0].seller_nick == "seller"
        assert items[0].is_free_ship == True

    def test_parse_response_empty(self):
        """测试空响应"""
        client = HttpApiSearchClient()
        response = {
            "ret": ["SUCCESS::调用成功"],
            "data": {"resultList": []},
        }

        items = client._parse_response(response, "test", 1)

        assert items == []

    def test_parse_response_error_session_expired(self):
        """测试 session 过期错误"""
        client = HttpApiSearchClient()
        response = {
            "ret": ["FAIL_SYS_SESSION_EXPIRED::Session过期"],
            "data": None,
        }

        with pytest.raises(HttpApiSearchError) as exc_info:
            client._parse_response(response, "test", 1)

        assert "SESSION_EXPIRED" in str(exc_info.value)

    def test_parse_response_error_illegal_sign(self):
        """测试签名错误"""
        client = HttpApiSearchClient()
        response = {
            "ret": ["FAIL_SYS_ILLEGAL_SIGN::签名错误"],
            "data": None,
        }

        with pytest.raises(HttpApiSearchError) as exc_info:
            client._parse_response(response, "test", 1)

        assert "ILLEGAL_SIGN" in str(exc_info.value)

    def test_parse_response_missing_item_id(self):
        """测试缺少 item_id 的商品被过滤"""
        client = HttpApiSearchClient()
        response = {
            "ret": ["SUCCESS::调用成功"],
            "data": {
                "resultList": [
                    {
                        "data": {
                            "item": {
                                "main": {
                                    "exContent": {
                                        "title": "无ID商品",
                                    }
                                }
                            }
                        }
                    },
                    {
                        "data": {
                            "item": {
                                "main": {
                                    "exContent": {"itemId": "789"},
                                    "clickParam": {"args": {"item_id": "789"}},
                                }
                            }
                        }
                    },
                ]
            },
        }

        items = client._parse_response(response, "test", 1)

        assert len(items) == 1
        assert items[0].item_id == "789"

    def test_parse_response_with_publish_time(self):
        """测试带发布时间的响应解析"""
        client = HttpApiSearchClient()
        response = {
            "ret": ["SUCCESS::调用成功"],
            "data": {
                "resultList": [
                    {
                        "data": {
                            "item": {
                                "main": {
                                    "exContent": {
                                        "itemId": "123",
                                        "title": "测试",
                                        "price": [{"text": "¥50"}],
                                    },
                                    "clickParam": {
                                        "args": {
                                            "item_id": "123",
                                            "publishTime": "1700000000000",
                                        }
                                    },
                                }
                            }
                        }
                    }
                ]
            },
        }

        items = client._parse_response(response, "test", 1)

        assert len(items) == 1
        assert items[0].publish_time is not None


class TestHttpApiSearchClientFetchPage:
    """测试 fetch_page 方法"""

    @pytest.mark.asyncio
    async def test_fetch_page_success(self):
        """测试成功获取页面"""
        client = HttpApiSearchClient()
        params = SearchParams(keyword="iPhone")

        mock_response = {
            "ret": ["SUCCESS::调用成功"],
            "data": {
                "resultList": [
                    {
                        "data": {
                            "item": {
                                "main": {
                                    "exContent": {
                                        "itemId": "111",
                                        "title": "iPhone",
                                        "price": [{"text": "¥999"}],
                                    },
                                    "clickParam": {"args": {"item_id": "111"}},
                                }
                            }
                        }
                    }
                ]
            },
        }

        mock_cookie = "_m_h5_tk=testtoken_1234567890; session=abc"

        async def mock_get_cookie():
            return mock_cookie

        with patch.object(client, "_send_request", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = mock_response

            result = await client.fetch_page(params, 1, _get_cookie=mock_get_cookie)

        assert result.error is None
        assert len(result.items) == 1
        assert result.keyword == "iPhone"
        assert result.page == 1

    @pytest.mark.asyncio
    async def test_fetch_page_cookie_expired(self):
        """测试 cookie 过期错误"""
        client = HttpApiSearchClient()
        params = SearchParams(keyword="test")

        mock_response = {
            "ret": ["FAIL_SYS_SESSION_EXPIRED::Session过期"],
            "data": None,
        }

        async def mock_get_cookie():
            return "_m_h5_tk=test_123"

        with patch.object(client, "_send_request", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = mock_response

            result = await client.fetch_page(params, 1, _get_cookie=mock_get_cookie)

        assert result.error == "SESSION_EXPIRED"
        assert result.items == []

    @pytest.mark.asyncio
    async def test_fetch_page_empty_cookie(self):
        """测试空 cookie 处理"""
        client = HttpApiSearchClient()
        params = SearchParams(keyword="test")

        async def mock_get_cookie():
            return ""

        with patch.object(client, "_send_request", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = {"ret": ["SUCCESS::"], "data": {"resultList": []}}

            result = await client.fetch_page(params, 1, _get_cookie=mock_get_cookie)

        assert result.error is None

    @pytest.mark.asyncio
    async def test_fetch_page_network_error(self):
        """测试网络错误处理"""
        client = HttpApiSearchClient()
        params = SearchParams(keyword="test")

        async def mock_get_cookie():
            return "_m_h5_tk=test_123"

        with patch.object(client, "_send_request", new_callable=AsyncMock) as mock_send:
            mock_send.side_effect = Exception("Network error")

            result = await client.fetch_page(params, 1, _get_cookie=mock_get_cookie)

        assert result.error == "NETWORK_ERROR"
        assert "Network error" in result.message


class TestHttpApiResult:
    """测试 HttpApiResult 数据类"""

    def test_result_creation_success(self):
        """测试成功结果创建"""
        items = [
            SearchItem(
                item_id="123",
                title="Test",
                price="¥100",
                original_price="¥200",
                want_cnt=5,
                seller_nick="seller",
                seller_city="北京",
                image_urls=["url"],
                detail_url="url",
                is_free_ship=True,
            )
        ]
        result = HttpApiResult(
            keyword="test",
            page=1,
            items=items,
            error=None,
            message="",
            raw_response={"data": {}},
        )

        assert result.keyword == "test"
        assert result.page == 1
        assert len(result.items) == 1
        assert result.error is None

    def test_result_creation_error(self):
        """测试错误结果创建"""
        result = HttpApiResult(
            keyword="test",
            page=1,
            items=[],
            error="SESSION_EXPIRED",
            message="Session expired",
            raw_response=None,
        )

        assert result.error == "SESSION_EXPIRED"
        assert result.items == []
