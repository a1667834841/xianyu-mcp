# 商品数据解析修复与格式化模块实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复搜索 API 解析逻辑确保数据准确，并新增格式化模块提供数据分析格式和发布筛选格式两种输出。

**Architecture:**
1. 修复 `http_search.py` 中的 `_parse_response` 方法，修正字段提取路径
2. 在 `search_api.py` 添加曝光度计算函数
3. 新增独立 `formatter.py` 模块

**Tech Stack:** Python dataclass, datetime, re, pytest

---

## 文件结构

| 文件 | 操作 | 职责 |
|------|------|------|
| `src/http_search.py` | Modify | 修复字段提取路径，新增 `_extract_want_cnt`、`_format_publish_time` 辅助函数 |
| `src/search_api.py` | Modify | 新增 `calculate_exposure_score` 函数，在搜索后计算曝光度 |
| `src/formatter.py` | Create | 新增格式化模块，包含 `format_for_analysis` 和 `format_for_publish` |
| `tests/test_http_search_unit.py` | Modify | 更新测试数据中的字段名以匹配 API 变更 |
| `tests/test_formatter.py` | Create | 格式化模块单元测试 |
| `tests/test_search_api.py` | Modify | 曝光度计算函数测试 |

---

## Task 1: 修复 http_search.py 字段提取逻辑

**Files:**
- Modify: `src/http_search.py:127-222`
- Modify: `tests/test_http_search_unit.py:153-191`
- Test: `pytest tests/test_http_search_unit.py -v`

- [ ] **Step 1: 添加辅助函数 `_extract_want_cnt`**

在 `src/http_search.py` 文件末尾（`HttpApiSearchClient` 类之后）添加：

```python
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
```

- [ ] **Step 2: 添加辅助函数 `_format_publish_time`**

在 `_extract_want_cnt` 函数之后添加：

```python
def _format_publish_time(publish_time_ms: Any) -> Optional[str]:
    """格式化发布时间（毫秒转字符串）"""
    try:
        from datetime import datetime
        publish_dt = datetime.fromtimestamp(int(publish_time_ms) / 1000)
        return publish_dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return None
```

- [ ] **Step 3: 修改 `_parse_response` 方法中的 seller_nick 提取**

找到 `_parse_response` 方法中 `seller_nick = ex_content.get("userNick", "")` 这一行（约第 209 行），修改为：

```python
seller_nick = ex_content.get("userNickName", "")
```

- [ ] **Step 4: 修改 `_parse_response` 方法中的 seller_city 提取**

找到 `seller_city = ex_content.get("city", "")` 这一行，修改为：

```python
seller_city = ex_content.get("area", "")
```

- [ ] **Step 5: 修改 `_parse_response` 方法中的 want_cnt 提取**

找到以下代码块：
```python
want_cnt = 0
try:
    want_cnt = int(ex_content.get("wantNum", 0))
except Exception:
    pass
```

替换为：
```python
want_cnt = _extract_want_cnt(ex_content)
```

- [ ] **Step 6: 修改 `_parse_response` 方法中的 price 提取**

找到以下代码块：
```python
price_str = extract_text(ex_content.get("price", []))
original_price_str = extract_text(ex_content.get("originalPrice", []))
```

替换为：
```python
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
```

- [ ] **Step 7: 修改 `_parse_response` 方法中的 is_free_ship**

找到 `is_free_ship = bool(ex_content.get("freeDelivery"))` 这一行，修改为：

```python
is_free_ship = False  # API 无此字段
```

- [ ] **Step 8: 修改 publish_time 格式化逻辑**

找到以下代码块：
```python
publish_time_str = None
publish_time_ms = click_args.get("publishTime")
if publish_time_ms:
    try:
        from datetime import datetime
        publish_dt = datetime.fromtimestamp(int(publish_time_ms) / 1000)
        publish_time_str = publish_dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        pass
```

替换为：
```python
publish_time_str = _format_publish_time(click_args.get("publishTime"))
```

- [ ] **Step 9: 更新测试文件中的测试数据**

修改 `tests/test_http_search_unit.py` 第 153-191 行的 `test_parse_response_success` 测试：

将测试数据从：
```python
"userNick": "seller",
"city": "北京",
"freeDelivery": True,
```

修改为：
```python
"userNickName": "seller",
"area": "北京",
# 移除 freeDelivery，API 无此字段
```

将断言从：
```python
assert items[0].seller_nick == "seller"
assert items[0].is_free_ship == True
```

修改为：
```python
assert items[0].seller_nick == "seller"
assert items[0].is_free_ship == False  # API 无此字段，始终为 False
```

- [ ] **Step 10: 运行测试验证修改**

```bash
pytest tests/test_http_search_unit.py -v
```

Expected: 所有测试通过

- [ ] **Step 11: 提交 http_search.py 和测试修改**

```bash
git add src/http_search.py tests/test_http_search_unit.py
git commit -m "fix: 修复搜索 API 字段提取路径

- seller_nick: userNick -> userNickName
- seller_city: city -> area
- want_cnt: 从 fishTags.r3 解析
- price: 优先 clickParam.args
- is_free_ship: 移除，API 无此字段
- 更新测试数据以匹配 API 变更

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 2: 添加曝光度计算函数到 search_api.py

**Files:**
- Modify: `src/search_api.py`
- Modify: `tests/test_search_api.py`

- [ ] **Step 1: 在 test_search_api.py 追加曝光度计算测试**

在 `tests/test_search_api.py` 文件末尾追加：

```python
# ==================== 曝光度计算测试 ====================

from datetime import datetime
from unittest.mock import patch


def test_calculate_exposure_score_normal():
    """正常计算曝光度"""
    from src.search_api import calculate_exposure_score

    # 使用固定时间避免时间差问题
    with patch("src.search_api.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 4, 10, 12, 0, 0)
        mock_dt.strptime = datetime.strptime

        # 1天前发布，100人想要
        result = calculate_exposure_score(100, "2026-04-09 12:00:00")
        # 曝光度 = (100 * 100) / (1 + 1) = 5000
        assert result == 5000.0


def test_calculate_exposure_score_zero_want():
    """想要人数为 0"""
    from src.search_api import calculate_exposure_score

    result = calculate_exposure_score(0, "2026-04-09 00:00:00")
    assert result == 0.0


def test_calculate_exposure_score_no_publish_time():
    """无发布时间"""
    from src.search_api import calculate_exposure_score

    result = calculate_exposure_score(100, None)
    assert result == 0.0


def test_calculate_exposure_score_future_time():
    """发布时间在未来"""
    from src.search_api import calculate_exposure_score

    with patch("src.search_api.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 4, 10, 12, 0, 0)
        mock_dt.strptime = datetime.strptime

        result = calculate_exposure_score(100, "2026-04-11 12:00:00")
        assert result == 0.0


def test_calculate_exposure_score_just_published():
    """刚发布（0天）"""
    from src.search_api import calculate_exposure_score

    with patch("src.search_api.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 4, 10, 12, 0, 0)
        mock_dt.strptime = datetime.strptime

        result = calculate_exposure_score(100, "2026-04-10 12:00:00")
        # 曝光度 = (100 * 100) / (0 + 1) = 10000
        assert result == 10000.0
```

- [ ] **Step 2: 运行测试验证失败**

```bash
pytest tests/test_search_api.py::test_calculate_exposure_score_normal -v
```

Expected: FAIL - `cannot import name 'calculate_exposure_score'`

- [ ] **Step 3: 在 search_api.py 添加曝光度计算函数**

在 `src/search_api.py` 文件开头导入之后、`StableSearchRunner` 类之前添加：

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
            return 0.0
        hours_diff = (now - publish_dt).total_seconds() / 3600
        days_diff = max(0, hours_diff / 24)
        exposure_score = (want_cnt * 100) / (days_diff + 1)
        return round(exposure_score, 2)
    except (ValueError, TypeError):
        return 0.0
```

- [ ] **Step 4: 运行测试验证通过**

```bash
pytest tests/test_search_api.py -v -k "calculate_exposure"
```

Expected: PASS

- [ ] **Step 5: 在 StableSearchRunner.search 中调用曝光度计算**

在 `StableSearchRunner.search` 方法中，找到以下循环（约第 35-40 行）：

```python
new_count = 0
for item in items:
    if item.item_id not in seen_item_ids:
        seen_item_ids.add(item.item_id)
        all_items.append(item)
        new_count += 1
```

修改为：

```python
new_count = 0
for item in items:
    if item.item_id not in seen_item_ids:
        seen_item_ids.add(item.item_id)
        # 计算曝光度
        item.exposure_score = calculate_exposure_score(item.want_cnt, item.publish_time)
        all_items.append(item)
        new_count += 1
```

- [ ] **Step 6: 运行所有测试**

```bash
pytest tests/ -v
```

Expected: 所有测试通过

- [ ] **Step 7: 提交 search_api.py 修改**

```bash
git add src/search_api.py tests/test_search_api.py
git commit -m "feat: 添加曝光度计算函数

- 新增 calculate_exposure_score 函数
- 在搜索结果中自动计算曝光度
- 使用 mock 避免测试时间差问题

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 3: 创建 formatter.py 格式化模块

**Files:**
- Create: `src/formatter.py`
- Create: `tests/test_formatter.py`

- [ ] **Step 1: 创建 test_formatter.py 测试文件**

创建 `tests/test_formatter.py`：

```python
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
```

- [ ] **Step 2: 运行测试验证失败**

```bash
pytest tests/test_formatter.py -v
```

Expected: FAIL - `ModuleNotFoundError: No module named 'src.formatter'`

- [ ] **Step 3: 创建 formatter.py 模块**

创建 `src/formatter.py`：

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
```

- [ ] **Step 4: 运行测试验证通过**

```bash
pytest tests/test_formatter.py -v
```

Expected: PASS

- [ ] **Step 5: 运行所有测试**

```bash
pytest tests/ -v
```

Expected: 所有测试通过

- [ ] **Step 6: 提交 formatter 模块**

```bash
git add src/formatter.py tests/test_formatter.py
git commit -m "feat: 新增商品数据格式化模块

- format_for_analysis: 数据分析格式
- format_for_publish: 发布筛选格式（按曝光度排序）
- 添加完整单元测试

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 4: 集成测试与验收

**Files:**
- 无新增文件

- [ ] **Step 1: 运行完整测试套件**

```bash
pytest tests/ -v
```

Expected: 所有测试通过

- [ ] **Step 2: 手动验证搜索数据**

调用搜索接口验证字段是否正确填充：

```bash
curl -s -X POST http://localhost:8080/rest/search \
  -H "Content-Type: application/json" \
  -d '{"keyword": "popmart", "rows": 5}' | python3 -c "
import sys, json
data = json.load(sys.stdin)
if data.get('items'):
    item = data['items'][0]
    print(f'seller_nick: {item.get(\"seller_nick\")}')
    print(f'seller_city: {item.get(\"seller_city\")}')
    print(f'want_cnt: {item.get(\"want_cnt\")}')
    print(f'exposure_score: {item.get(\"exposure_score\")}')
"
```

Expected: 输出真实数据（非空）

- [ ] **Step 3: 验证格式化函数**

在项目目录运行 Python：

```bash
python3 << 'EOF'
import asyncio
from src.core import XianyuApp
from src.formatter import format_for_analysis, format_for_publish

async def test():
    async with XianyuApp() as app:
        outcome = await app.search_with_meta("popmart", rows=5)

        print("=== 分析格式 ===")
        analysis = format_for_analysis(outcome.items)
        print(analysis[0] if analysis else "无数据")

        print("\n=== 发布筛选格式 ===")
        publish = format_for_publish(outcome.items, top_n=3)
        print(publish[0] if publish else "无数据")

asyncio.run(test())
EOF
```

Expected: 正确输出两种格式

- [ ] **Step 4: 最终提交（如有遗漏）**

```bash
git status
# 如有未提交的文件
git add -A
git commit -m "chore: 完成商品数据解析修复与格式化模块"
```

---

## 验收标准

- [ ] 搜索返回数据中 `want_cnt` 字段有真实数据（非零值）
- [ ] 搜索返回数据中 `seller_nick`、`seller_city` 字段有真实数据
- [ ] 曝光度计算公式正确，数值合理
- [ ] `format_for_analysis` 返回完整字段字典列表
- [ ] `format_for_publish` 按曝光度排序并返回精简字段
- [ ] `tests/test_formatter.py` 所有测试通过
- [ ] `pytest tests/` 全部通过