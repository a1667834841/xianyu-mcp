"""
formatter.py - 商品数据格式化模块
提供数据分析格式和发布筛选格式两种输出
"""

from typing import List, Dict

try:
    from .core import SearchItem
except ImportError:
    from core import SearchItem


def format_for_analysis(items: List[SearchItem]) -> List[Dict]:
    """
    数据分析格式

    包含完整字段，适合导入分析工具（Excel、pandas 等）。

    返回字段: item_id, title, price, want_cnt, exposure_score,
              publish_time, seller_nick, seller_city, detail_url

    Args:
        items: SearchItem 列表

    Returns:
        格式化后的字典列表
    """
    if not items:
        return []

    result = []
    for item in items:
        title_display = item.title
        if len(title_display) > 50:
            title_display = title_display[:50] + "..."

        result.append({
            "item_id": item.item_id,
            "title": title_display,
            "price": item.price,
            "want_cnt": item.want_cnt,
            "exposure_score": item.exposure_score,
            "publish_time": item.publish_time,
            "seller_nick": item.seller_nick,
            "seller_city": item.seller_city,
            "detail_url": item.detail_url,
        })
    return result


def format_for_publish(items: List[SearchItem], top_n: int = 10) -> List[Dict]:
    """
    发布筛选格式

    按曝光度排序，取前 N 条高曝光商品，返回精简字段。

    返回字段: item_id, title, price, exposure_score, image_urls, detail_url

    Args:
        items: SearchItem 列表
        top_n: 取前 N 条，默认 10。如果为负数或零，返回空列表。

    Returns:
        按曝光度排序的精简字典列表
    """
    if not items or top_n <= 0:
        return []

    sorted_items = sorted(items, key=lambda x: x.exposure_score, reverse=True)
    top_items = sorted_items[:top_n]

    result = []
    for item in top_items:
        result.append({
            "item_id": item.item_id,
            "title": item.title,
            "price": item.price,
            "exposure_score": item.exposure_score,
            "image_urls": item.image_urls,
            "detail_url": item.detail_url,
        })
    return result
