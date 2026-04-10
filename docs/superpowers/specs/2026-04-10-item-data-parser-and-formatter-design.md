# 商品数据解析修复与格式化模块设计

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复搜索 API 解析逻辑确保数据准确，并新增格式化模块提供数据分析格式和发布筛选格式两种输出。

**Architecture:**
1. 修复 `http_search.py` 中的 `_parse_response` 方法，修正字段提取路径
2. 新增独立 `formatter.py` 模块，职责分离，两个函数分别输出分析格式和发布筛选格式

**Tech Stack:** Python dataclass, datetime, re

---

## 一、问题分析

当前 `http_search.py` 的 `_parse_response` 方法存在字段路径错误：

| 字段 | 当前路径 | 实际 API 路径 | 状态 |
|------|---------|--------------|------|
| item_id | `exContent.itemId` | 同 + `clickParam.args.item_id` | 可用 |
| title | `exContent.title` | 同 | 可用 |
| price | `exContent.price` 数组 | `clickParam.args.price` 或解析数组 | 需修复 |
| seller_nick | `exContent.userNick` | `exContent.userNickName` | 需修复 |
| seller_city | `exContent.city` | `exContent.area` | 需修复 |
| want_cnt | `exContent.wantNum` | `fishTags.r3.tagList[].data.content` 解析 | 需修复 |
| publish_time | `clickParam.args.publishTime` | 同 | 可用 |
| picUrl | `exContent.picUrl` | 同 | 可用 |
| is_free_ship | `exContent.freeDelivery` | API 无此字段 | 移除 |

---

## 二、修复方案

### 2.1 修改文件

**文件:** `src/http_search.py`

**修改范围:** `_parse_response` 方法（约第 127-222 行）

### 2.2 字段提取逻辑

```python
def _parse_response(self, response: Dict[str, Any], keyword: str, page: int) -> List["SearchItem"]:
    """解析 API 响应"""
    SearchItem, _ = _get_search_classes()

    # ... 错误检查逻辑保持不变 ...

    items = []
    for entry in result_list:
        try:
            main = entry.get("data", {}).get("item", {}).get("main", {})
            if not main:
                continue

            ex_content = main.get("exContent", {})
            click_args = main.get("clickParam", {}).get("args", {})

            # 1. item_id
            item_id = click_args.get("item_id") or ex_content.get("itemId", "")
            if not item_id:
                continue

            # 2. title
            title = ex_content.get("title", "")

            # 3. price - 从 clickParam 或解析数组
            price_str = click_args.get("price") or click_args.get("displayPrice", "")
            if not price_str:
                price_parts = ex_content.get("price", [])
                price_str = "".join(p.get("text", "") for p in price_parts if isinstance(p, dict))

            # 4. original_price - 暂无可靠来源，保持空
            original_price_str = ""

            # 5. seller_nick - 从 userNickName
            seller_nick = ex_content.get("userNickName", "")

            # 6. seller_city - 从 area
            seller_city = ex_content.get("area", "")

            # 7. want_cnt - 从 fishTags.r3 解析
            want_cnt = 0
            fish_tags = ex_content.get("fishTags", {})
            r3_tags = fish_tags.get("r3", {}).get("tagList", [])
            for tag in r3_tags:
                content = tag.get("data", {}).get("content", "")
                if "人想要" in content:
                    match = re.search(r"(\d+)人想要", content)
                    if match:
                        want_cnt = int(match.group(1))
                        break

            # 8. publish_time - 毫秒转日期
            publish_time_str = None
            publish_time_ms = click_args.get("publishTime")
            if publish_time_ms:
                try:
                    from datetime import datetime
                    publish_dt = datetime.fromtimestamp(int(publish_time_ms) / 1000)
                    publish_time_str = publish_dt.strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    pass

            # 9. image_urls
            pic_url = ex_content.get("picUrl", "")
            image_urls = [pic_url] if pic_url else []

            # 10. is_free_ship - API 无此字段，设为 False
            is_free_ship = False

            # 11. exposure_score - 稍后计算

            item = SearchItem(
                item_id=str(item_id),
                title=title,
                price=price_str,
                original_price=original_price_str,
                want_cnt=want_cnt,
                seller_nick=seller_nick,
                seller_city=seller_city,
                image_urls=image_urls,
                detail_url=f"https://www.goofish.com/item?id={item_id}",
                is_free_ship=is_free_ship,
                publish_time=publish_time_str,
                exposure_score=0.0,  # 稍后计算
            )
            items.append(item)

        except Exception:
            continue

    return items
```

### 2.3 曝光度计算

在解析完成后计算曝光度，可在 `fetch_page` 或 `search_api.py` 中处理：

```python
from datetime import datetime

def calculate_exposure_score(want_cnt: int, publish_time_str: str) -> float:
    """
    计算曝光度分数

    公式: 曝光度 = (想要人数 × 100) / (天数差 + 1)
    天数差 = (当前时间 - 发布时间) / 24小时
    """
    if want_cnt == 0 or not publish_time_str:
        return 0.0

    try:
        publish_dt = datetime.strptime(publish_time_str, "%Y-%m-%d %H:%M:%S")
        now = datetime.now()
        hours_diff = (now - publish_dt).total_seconds() / 3600
        days_diff = hours_diff / 24
        exposure_score = (want_cnt * 100) / (days_diff + 1)
        return round(exposure_score, 2)
    except:
        return 0.0
```

**调用时机:** 在 `search_api.py` 的 `StableSearchRunner.search` 方法中，解析完每页数据后批量计算曝光度。

---

## 三、格式化模块

### 3.1 新增文件

**文件:** `src/formatter.py`

### 3.2 模块结构

```python
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
    result = []
    for item in items:
        result.append({
            "item_id": item.item_id,
            "title": item.title[:50] + "..." if len(item.title) > 50 else item.title,
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
        top_n: 取前 N 条，默认 10

    Returns:
        按曝光度排序的精简字典列表
    """
    # 按曝光度倒序排序
    sorted_items = sorted(items, key=lambda x: x.exposure_score, reverse=True)

    # 取前 top_n 条
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
```

### 3.3 使用示例

```python
from src.core import XianyuApp
from src.formatter import format_for_analysis, format_for_publish

async with XianyuApp() as app:
    outcome = await app.search_with_meta("popmart", rows=30)

    # 数据分析格式
    analysis_data = format_for_analysis(outcome.items)

    # 发布筛选格式（取曝光度前 10）
    publish_data = format_for_publish(outcome.items, top_n=10)
```

---

## 四、文件变更清单

| 操作 | 文件 | 说明 |
|------|------|------|
| Modify | `src/http_search.py` | 修复 `_parse_response` 字段提取逻辑 |
| Modify | `src/search_api.py` | 添加曝光度计算逻辑 |
| Create | `src/formatter.py` | 新增格式化模块 |
| Modify | `src/__init__.py` | 导出 formatter 函数（可选） |

---

## 五、测试计划

### 5.1 解析逻辑测试

- 测试 `want_cnt` 从 fishTags.r3 正确解析
- 测试 `seller_nick` 从 userNickName 提取
- 测试 `seller_city` 从 area 提取
- 测试 price 从 clickParam 或数组解析

### 5.2 曝光度计算测试

- 测试公式正确性（边界值、负数时间差等）
- 测试无发布时间或无想要人数的情况

### 5.3 格式化函数测试

- 测试 `format_for_analysis` 输出字段完整性
- 测试 `format_for_publish` 排序和截取逻辑
- 测试空列表输入

---

## 六、验收标准

1. 搜索返回数据中 `want_cnt`、`seller_nick`、`seller_city` 字段有真实数据
2. 曝光度计算公式正确，数值合理
3. `format_for_analysis` 返回完整字段字典列表
4. `format_for_publish` 按曝光度排序并返回精简字段
5. 相关单元测试全部通过