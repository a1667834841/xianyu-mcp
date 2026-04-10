# 商品数据解析修复与格式化模块设计

**日期:** 2026-04-10
**状态:** 待审阅

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复搜索 API 解析逻辑确保数据准确，并新增格式化模块提供数据分析格式和发布筛选格式两种输出。

**Architecture:**
1. 修复 `http_search.py` 中的 `_parse_response` 方法，修正字段提取路径
2. 新增独立 `formatter.py` 模块，职责分离，两个函数分别输出分析格式和发布筛选格式

**Tech Stack:** Python dataclass, datetime, re, pytest

---

## 一、背景

当前搜索功能返回的数据存在多个字段为空或不准确的问题：
- `want_cnt`（想要人数）始终为 0
- `seller_nick`（卖家昵称）为空
- `seller_city`（卖家城市）为空
- `is_free_ship` 字段在 API 中不存在

这些问题的根本原因是解析代码中的字段路径与实际 API 响应结构不匹配。通过直接调用 API 获取原始响应分析，确认了正确的字段路径。

此外，用户需要将搜索结果格式化为两种用途：
1. **数据分析格式**：完整字段，用于导入分析工具
2. **发布筛选格式**：按曝光度排序，精简字段，用于筛选对标商品

---

## 二、问题分析

### 2.1 数据验证方法

通过直接调用闲鱼搜索 API（`mtop.taobao.idlemtopsearch.pc.search`）获取原始 JSON 响应，分析 `resultList[0].data.item.main` 结构确认字段路径。

### 2.2 字段路径对比

| 字段 | 当前路径 | 实际 API 路径 | 状态 |
|------|---------|--------------|------|
| item_id | `exContent.itemId` | 同 + `clickParam.args.item_id` | 可用 |
| title | `exContent.title` | 同 | 可用 |
| price | `exContent.price` 数组 | `clickParam.args.price` 或解析数组 | 需修复 |
| seller_nick | `exContent.userNick` ❌ | `exContent.userNickName` | 需修复 |
| seller_city | `exContent.city` ❌ | `exContent.area` | 需修复 |
| want_cnt | `exContent.wantNum` ❌ | `fishTags.r3.tagList[].data.content` 解析 | 需修复 |
| publish_time | `clickParam.args.publishTime` | 同 | 可用 |
| picUrl | `exContent.picUrl` | 同 | 可用 |
| is_free_ship | `exContent.freeDelivery` ❌ | API 无此字段 | 移除 |
| original_price | - | API 无可靠来源 | 保持空 |

---

## 三、修复方案

### 3.1 修改文件

**文件:** `src/http_search.py`
**修改范围:** `_parse_response` 方法（约第 127-222 行）

### 3.2 字段提取逻辑

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
                if isinstance(price_parts, list):
                    price_str = "".join(
                        p.get("text", "") for p in price_parts
                        if isinstance(p, dict)
                    )

            # 4. original_price - API 无可靠来源，保持空
            original_price_str = ""

            # 5. seller_nick - 从 userNickName
            seller_nick = ex_content.get("userNickName", "")

            # 6. seller_city - 从 area
            seller_city = ex_content.get("area", "")

            # 7. want_cnt - 从 fishTags.r3 解析
            want_cnt = _extract_want_cnt(ex_content)

            # 8. publish_time - 毫秒转日期
            publish_time_str = None
            publish_time_ms = click_args.get("publishTime")
            if publish_time_ms:
                publish_time_str = _format_publish_time(publish_time_ms)

            # 9. image_urls
            pic_url = ex_content.get("picUrl", "")
            image_urls = [pic_url] if pic_url else []

            # 10. is_free_ship - API 无此字段，设为 False
            is_free_ship = False

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

        except (KeyError, TypeError, ValueError) as e:
            logger.debug(f"解析商品条目失败: {e}")
            continue

    return items


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
    """格式化发布时间"""
    try:
        from datetime import datetime
        publish_dt = datetime.fromtimestamp(int(publish_time_ms) / 1000)
        return publish_dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return None
```

### 3.3 曝光度计算

**调用位置:** `src/search_api.py` 的 `StableSearchRunner.search` 方法，在解析完每页数据后批量计算。

**函数实现:**
```python
from datetime import datetime

def calculate_exposure_score(want_cnt: int, publish_time_str: Optional[str]) -> float:
    """
    计算曝光度分数

    公式: 曝光度 = (想要人数 × 100) / (天数差 + 1)
    天数差 = (当前时间 - 发布时间) / 24小时

    Args:
        want_cnt: 想要人数
        publish_time_str: 发布时间字符串（格式：%Y-%m-%d %H:%M:%S）

    Returns:
        曝光度分数，保留两位小数
    """
    if want_cnt <= 0 or not publish_time_str:
        return 0.0

    try:
        publish_dt = datetime.strptime(publish_time_str, "%Y-%m-%d %H:%M:%S")
        now = datetime.now()
        if publish_dt > now:
            # 发布时间在未来，返回 0
            return 0.0
        hours_diff = (now - publish_dt).total_seconds() / 3600
        days_diff = max(0, hours_diff / 24)  # 确保非负
        exposure_score = (want_cnt * 100) / (days_diff + 1)
        return round(exposure_score, 2)
    except (ValueError, TypeError):
        return 0.0
```

---

## 四、格式化模块

### 4.1 新增文件

**文件:** `src/formatter.py`

### 4.2 模块结构

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
    if not items:
        return []

    result = []
    for item in items:
        # 标题截断处理
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

### 4.3 使用示例

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

## 五、文件变更清单

| 操作 | 文件 | 说明 |
|------|------|------|
| Modify | `src/http_search.py` | 修复 `_parse_response` 字段提取逻辑，新增辅助函数 |
| Modify | `src/search_api.py` | 添加 `calculate_exposure_score` 函数并在搜索后调用 |
| Create | `src/formatter.py` | 新增格式化模块 |
| No Change | `src/__init__.py` | 不修改，formatter 为独立模块，按需导入 |

**破坏性变更:** 无。现有 API 保持向后兼容。

---

## 六、测试计划

### 6.1 测试文件

**新增:** `tests/test_formatter.py`
**修改:** `tests/test_http_search.py`（如存在）

### 6.2 解析逻辑测试用例

| 测试项 | 输入 | 预期结果 |
|--------|------|---------|
| want_cnt 正常解析 | `fishTags.r3.tagList = [{"data": {"content": "21人想要"}}]` | want_cnt = 21 |
| want_cnt 无匹配 | `fishTags.r3.tagList = []` | want_cnt = 0 |
| seller_nick 提取 | `exContent.userNickName = "星星潮玩"` | seller_nick = "星星潮玩" |
| seller_city 提取 | `exContent.area = "浙江"` | seller_city = "浙江" |
| price 从 clickParam | `clickParam.args.price = "18.90"` | price = "18.90" |
| price 从数组解析 | `exContent.price = [{"text": "¥"}, {"text": "18"}, {"text": ".90"}]` | price = "¥18.90" |

### 6.3 曝光度计算测试用例

| 测试项 | 输入 | 预期结果 |
|--------|------|---------|
| 正常计算 | want_cnt=100, publish_time=1天前 | 约 5000 |
| 零想要人数 | want_cnt=0 | 0.0 |
| 无发布时间 | publish_time=None | 0.0 |
| 未来时间 | publish_time=明天 | 0.0 |

### 6.4 格式化函数测试用例

| 测试项 | 输入 | 预期结果 |
|--------|------|---------|
| format_for_analysis 空列表 | [] | [] |
| format_for_analysis 正常 | [SearchItem(...)] | [{"item_id": ...}] |
| format_for_publish 空列表 | [] | [] |
| format_for_publish top_n=0 | items, top_n=0 | [] |
| format_for_publish top_n=-1 | items, top_n=-1 | [] |
| format_for_publish 排序 | 曝光度 [100, 300, 200] | 按 300, 200, 100 排序 |

---

## 七、风险与限制

### 7.1 风险

1. **API 结构变更**：闲鱼 API 可能更新字段结构，导致解析失败。缓解措施：添加日志记录解析失败情况。
2. **fishTags 缺失**：部分商品可能没有 fishTags 字段。缓解措施：已在代码中处理缺失情况，返回 0。

### 7.2 限制

1. `original_price` 字段无可靠数据源，保持为空。
2. `is_free_ship` 字段 API 不提供，始终为 False。
3. 曝光度计算依赖发布时间，部分商品可能无发布时间。

---

## 八、验收标准

- [ ] 搜索返回数据中 `want_cnt` 字段有真实数据（非零值）
- [ ] 搜索返回数据中 `seller_nick`、`seller_city` 字段有真实数据
- [ ] 曝光度计算公式正确，数值合理
- [ ] `format_for_analysis` 返回完整字段字典列表
- [ ] `format_for_publish` 按曝光度排序并返回精简字段
- [ ] `tests/test_formatter.py` 所有测试通过
- [ ] `pytest tests/` 全部通过