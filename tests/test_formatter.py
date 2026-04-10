"""
test_formatter.py - 格式化模块单元测试
"""

import pytest


def make_search_item(**kwargs):
    """创建测试用 SearchItem"""
    from src.core import SearchItem
    defaults = {
        "item_id": "123",
        "title": "测试商品",
        "price": "¥99.00",
        "original_price": "",
        "want_cnt": 10,
        "seller_nick": "测试卖家",
        "seller_city": "杭州",
        "image_urls": ["http://example.com/img.jpg"],
        "detail_url": "https://www.goofish.com/item?id=123",
        "is_free_ship": False,
        "publish_time": "2026-04-10 00:00:00",
        "exposure_score": 500.0,
    }
    defaults.update(kwargs)
    return SearchItem(**defaults)


# ==================== format_for_analysis 测试 ====================

def test_format_for_analysis_empty_list():
    """空列表返回空列表"""
    from src.formatter import format_for_analysis
    assert format_for_analysis([]) == []


def test_format_for_analysis_normal():
    """正常格式化"""
    from src.formatter import format_for_analysis
    item = make_search_item()
    result = format_for_analysis([item])

    assert len(result) == 1
    assert result[0]["item_id"] == "123"
    assert result[0]["title"] == "测试商品"
    assert result[0]["price"] == "¥99.00"
    assert result[0]["want_cnt"] == 10
    assert result[0]["exposure_score"] == 500.0
    assert result[0]["seller_nick"] == "测试卖家"
    assert result[0]["seller_city"] == "杭州"


def test_format_for_analysis_title_truncation():
    """标题超过 50 字符时截断"""
    from src.formatter import format_for_analysis
    long_title = "这是一个非常长的标题" * 10  # 100+ 字符
    item = make_search_item(title=long_title)
    result = format_for_analysis([item])

    assert len(result[0]["title"]) == 53  # 50 + "..."
    assert result[0]["title"].endswith("...")


def test_format_for_analysis_short_title():
    """短标题不截断"""
    from src.formatter import format_for_analysis
    item = make_search_item(title="短标题")
    result = format_for_analysis([item])

    assert result[0]["title"] == "短标题"


# ==================== format_for_publish 测试 ====================

def test_format_for_publish_empty_list():
    """空列表返回空列表"""
    from src.formatter import format_for_publish
    assert format_for_publish([]) == []


def test_format_for_publish_top_n_zero():
    """top_n=0 返回空列表"""
    from src.formatter import format_for_publish
    items = [make_search_item()]
    assert format_for_publish(items, top_n=0) == []


def test_format_for_publish_top_n_negative():
    """top_n 为负数返回空列表"""
    from src.formatter import format_for_publish
    items = [make_search_item()]
    assert format_for_publish(items, top_n=-1) == []


def test_format_for_publish_sorting():
    """按曝光度排序"""
    from src.formatter import format_for_publish
    items = [
        make_search_item(item_id="1", exposure_score=100.0),
        make_search_item(item_id="2", exposure_score=300.0),
        make_search_item(item_id="3", exposure_score=200.0),
    ]
    result = format_for_publish(items, top_n=10)

    assert len(result) == 3
    assert result[0]["item_id"] == "2"  # 最高曝光度
    assert result[1]["item_id"] == "3"
    assert result[2]["item_id"] == "1"


def test_format_for_publish_top_n_limit():
    """top_n 限制返回数量"""
    from src.formatter import format_for_publish
    items = [
        make_search_item(item_id=str(i), exposure_score=float(i))
        for i in range(20)
    ]
    result = format_for_publish(items, top_n=5)

    assert len(result) == 5


def test_format_for_publish_fields():
    """返回正确字段"""
    from src.formatter import format_for_publish
    item = make_search_item()
    result = format_for_publish([item])

    assert "item_id" in result[0]
    assert "title" in result[0]
    assert "price" in result[0]
    assert "exposure_score" in result[0]
    assert "image_urls" in result[0]
    assert "detail_url" in result[0]
    # 不应包含的字段
    assert "want_cnt" not in result[0]
    assert "seller_nick" not in result[0]
