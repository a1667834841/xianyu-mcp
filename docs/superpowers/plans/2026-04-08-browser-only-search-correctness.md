# Browser-Only 搜索正确性 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让闲鱼搜索只走“页面交互 + 监听真实接口”主链路，优先保证 `泡泡玛特 rows=100` 结果正确、无重复，并在强校验失败时明确报错。

**Architecture:** 保留 `XianyuApp.search_with_meta()` 作为入口，但移除 PageApi 主链路依赖，把搜索收敛到 `_BrowserSearchImpl` 及其会话状态。新增轻量的响应过滤与结果校验单元，第一页必须通过强校验，后续页只保证会话隔离、响应新鲜度和去重累计。

**Tech Stack:** Python 3, asyncio, Playwright, pytest

---

## File Structure

- Modify: `src/core.py`
  - 将 `search_with_meta()` 改为直接调用 browser-only 搜索。
  - 为 `_BrowserSearchImpl` 增加会话边界、响应过滤、第一页强校验和明确错误停止原因。
- Create: `src/search_validation.py`
  - 放置轻量校验与响应过滤辅助函数，避免 `src/core.py` 继续膨胀。
- Modify: `tests/test_search_pagination.py`
  - 删除 PageApi 优先 / fallback 旧假设，补 browser-only 行为测试。
- Create: `tests/test_search_validation.py`
  - 覆盖响应过滤、关键词一致性、明显跑偏拦截等纯逻辑测试。

### Task 1: 锁定 browser-only 入口行为

**Files:**
- Modify: `tests/test_search_pagination.py`
- Modify: `src/core.py`
- Test: `tests/test_search_pagination.py`

- [ ] **Step 1: 写失败测试，声明应用层不再优先走 PageApi**

```python
@pytest.mark.asyncio
async def test_app_uses_browser_only_search(monkeypatch):
    app = XianyuApp(browser=DummyBrowser())
    browser_outcome = SearchOutcome(
        items=[make_item("browser-1")],
        requested_rows=1,
        returned_rows=1,
        stop_reason="target_reached",
        stale_pages=0,
        engine_used="browser_interaction",
        fallback_reason=None,
        pages_fetched=1,
    )

    class StubSearchImpl:
        async def search(self, params):
            assert params.keyword == "泡泡玛特"
            return browser_outcome

    monkeypatch.setattr(
        "src.core._BrowserSearchImpl", lambda browser, max_stale_pages=3: StubSearchImpl()
    )

    outcome = await app.search_with_meta("泡泡玛特", rows=1)

    assert outcome.engine_used == "browser_interaction"
    assert outcome.items[0].item_id == "browser-1"
```

- [ ] **Step 2: 运行测试确认现状失败**

Run: `pytest tests/test_search_pagination.py::test_app_uses_browser_only_search -v`
Expected: FAIL，原因是当前 `search_with_meta()` 仍尝试走 `_build_page_api_runner` 或断言的 `engine_used` 不匹配。

- [ ] **Step 3: 用最小实现改成 browser-only 入口**

```python
async def search_with_meta(self, keyword: str, **options) -> SearchOutcome:
    params = SearchParams(
        keyword=keyword,
        rows=options.get("rows", 30),
        min_price=options.get("min_price"),
        max_price=options.get("max_price"),
        free_ship=options.get("free_ship", False),
        sort_field=options.get("sort_field", ""),
        sort_order=options.get("sort_order", ""),
    )

    async with self._work_lock:
        page = await self.browser.get_work_page()
        self.browser.page = page
        searcher = _BrowserSearchImpl(
            self.browser,
            max_stale_pages=self.settings.search.max_stale_pages,
        )
        return await searcher.search(params)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_search_pagination.py::test_app_uses_browser_only_search -v`
Expected: PASS

- [ ] **Step 5: 提交本任务改动**

```bash
git add tests/test_search_pagination.py src/core.py
git commit -m "refactor: route search through browser interaction"
```

### Task 2: 提取纯逻辑校验模块

**Files:**
- Create: `src/search_validation.py`
- Create: `tests/test_search_validation.py`
- Test: `tests/test_search_validation.py`

- [ ] **Step 1: 写失败测试，覆盖关键词一致性和明显跑偏拦截**

```python
from src.search_validation import is_keyword_match, has_obvious_topic_drift
from src.core import SearchItem


def make_item(item_id: str, title: str) -> SearchItem:
    return SearchItem(
        item_id=item_id,
        title=title,
        price="100",
        original_price="120",
        want_cnt=1,
        seller_nick="seller",
        seller_city="Hangzhou",
        image_urls=[],
        detail_url=f"https://www.goofish.com/item?id={item_id}",
        is_free_ship=False,
    )


def test_is_keyword_match_requires_exact_query_text():
    assert is_keyword_match("泡泡玛特", "泡泡玛特") is True
    assert is_keyword_match("泡泡玛特", "Mac mini") is False


def test_has_obvious_topic_drift_rejects_mac_mini_results_for_pop_mart():
    items = [
        make_item("1", "2022 款 Mac mini M2 8+256 国行"),
        make_item("2", "苹果 Mac mini 主机 准系统"),
        make_item("3", "Mac mini 办公电脑 小主机"),
    ]
    assert has_obvious_topic_drift("泡泡玛特", items) is True
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_search_validation.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.search_validation'`

- [ ] **Step 3: 写最小实现**

```python
from __future__ import annotations

from typing import Iterable


def is_keyword_match(expected: str, actual: str) -> bool:
    return expected.strip() == actual.strip()


def has_obvious_topic_drift(keyword: str, items: Iterable[object]) -> bool:
    if keyword.strip() != "泡泡玛特":
        return False
    sample_titles = [getattr(item, "title", "") for item in list(items)[:5]]
    drift_hits = 0
    for title in sample_titles:
        lowered = title.lower()
        if "mac mini" in lowered or "苹果" in title or "电脑" in title or "主机" in title:
            drift_hits += 1
    return drift_hits >= 2
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_search_validation.py -v`
Expected: PASS

- [ ] **Step 5: 提交本任务改动**

```bash
git add src/search_validation.py tests/test_search_validation.py
git commit -m "test: add browser search validation helpers"
```

### Task 3: 让第一页强校验可测试化

**Files:**
- Modify: `tests/test_search_pagination.py`
- Modify: `src/core.py`
- Test: `tests/test_search_pagination.py`

- [ ] **Step 1: 写失败测试，要求第一页跑偏时直接失败**

```python
@pytest.mark.asyncio
async def test_search_fails_when_first_page_has_obvious_topic_drift():
    class DriftSearchImpl(FakeSearchImpl):
        def _parse_results(self):
            return [
                make_item("1"),
                SearchItem(**{**make_item("2").__dict__, "title": "Mac mini 8+256 准系统"}),
                SearchItem(**{**make_item("3").__dict__, "title": "苹果 Mac mini 办公主机"}),
            ]

    searcher = DriftSearchImpl(pages=[[make_item("a-1")]], response_flags=[True])
    outcome = await searcher.search(SearchParams(keyword="泡泡玛特", rows=10))

    assert outcome.returned_rows == 0
    assert outcome.stop_reason == "validation_failed"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_search_pagination.py::test_search_fails_when_first_page_has_obvious_topic_drift -v`
Expected: FAIL，原因是当前实现仍把第一页数据当成功返回。

- [ ] **Step 3: 在 `_BrowserSearchImpl` 增加第一页校验钩子**

```python
def _validate_first_page(self, params: SearchParams, items: List[SearchItem]) -> None:
    from .search_validation import has_obvious_topic_drift

    if has_obvious_topic_drift(params.keyword, items):
        raise ValueError("validation_failed")


if page == 1:
    self._validate_first_page(params, items)
```

并在 `search()` 的异常分支中将这类错误映射为：

```python
return SearchOutcome(
    items=[],
    requested_rows=params.rows,
    returned_rows=0,
    stop_reason="validation_failed",
    stale_pages=stale_pages,
    engine_used="browser_interaction",
    fallback_reason=None,
    pages_fetched=page,
)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_search_pagination.py::test_search_fails_when_first_page_has_obvious_topic_drift -v`
Expected: PASS

- [ ] **Step 5: 提交本任务改动**

```bash
git add src/core.py tests/test_search_pagination.py
git commit -m "fix: fail browser search on first-page topic drift"
```

### Task 4: 收紧响应过滤边界

**Files:**
- Create: `tests/test_search_validation.py`
- Modify: `src/search_validation.py`
- Modify: `src/core.py`
- Test: `tests/test_search_validation.py`

- [ ] **Step 1: 写失败测试，确保只接收真实搜索接口**

```python
from src.search_validation import is_search_api_url


def test_is_search_api_url_rejects_suggest_and_shade():
    assert is_search_api_url(
        "https://h5api.m.goofish.com/h5/mtop.taobao.idlemtopsearch.pc.search/1.0/"
    ) is True
    assert is_search_api_url(
        "https://h5api.m.goofish.com/h5/mtop.taobao.idlemtopsearch.pc.search.suggest/1.0/"
    ) is False
    assert is_search_api_url(
        "https://h5api.m.goofish.com/h5/mtop.taobao.idlemtopsearch.pc.search.shade/1.0/"
    ) is False
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_search_validation.py::test_is_search_api_url_rejects_suggest_and_shade -v`
Expected: FAIL with `ImportError` or missing function error.

- [ ] **Step 3: 实现 URL 过滤并接入 `_setup_response_listener()`**

```python
def is_search_api_url(url: str) -> bool:
    return (
        "mtop.taobao.idlemtopsearch.pc.search/1.0" in url
        and "suggest" not in url
        and "shade" not in url
    )
```

在监听器内替换判断：

```python
from .search_validation import is_search_api_url


def on_response(response):
    url = response.url
    if not is_search_api_url(url):
        return
    ...
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_search_validation.py::test_is_search_api_url_rejects_suggest_and_shade -v`
Expected: PASS

- [ ] **Step 5: 提交本任务改动**

```bash
git add src/search_validation.py src/core.py tests/test_search_validation.py
git commit -m "fix: filter browser search responses by exact api url"
```

### Task 5: 阻止旧响应冒充新页结果

**Files:**
- Modify: `tests/test_search_pagination.py`
- Modify: `src/core.py`
- Test: `tests/test_search_pagination.py`

- [ ] **Step 1: 写失败测试，要求翻页只接受新增响应**

```python
@pytest.mark.asyncio
async def test_search_waits_for_new_response_before_parsing_next_page():
    searcher = FakeSearchImpl(
        pages=[
            [make_item("a-1")],
            [make_item("b-1")],
        ],
        response_flags=[True, False],
        max_stale_pages=1,
    )

    outcome = await searcher.search(SearchParams(keyword="泡泡玛特", rows=2))

    assert [item.item_id for item in outcome.items] == ["a-1"]
    assert outcome.stop_reason == "stale_limit"
```

- [ ] **Step 2: 运行测试确认当前行为不稳或失败**

Run: `pytest tests/test_search_pagination.py::test_search_waits_for_new_response_before_parsing_next_page -v`
Expected: FAIL 或出现旧页面结果被复用。

- [ ] **Step 3: 用最小改动把“是否有新响应”与“要解析哪一份响应”绑定起来**

```python
async def _wait_for_new_api_response(self, timeout: int = 30, prev_count: int = 0):
    ...
    if len(self._captured_responses) > prev_count:
        self.search_results = [self._captured_responses[-1]]
        return True
    return False


async def _wait_for_api_response(self, timeout: int = 30, clear: bool = False):
    ...
    if len(self._captured_responses) > prev_count:
        self.search_results = [self._captured_responses[-1]]
        return True
    return False
```

这样 `_parse_results()` 永远只消费刚刚判定为“当前页有效”的最后一份响应。

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_search_pagination.py::test_search_waits_for_new_response_before_parsing_next_page -v`
Expected: PASS

- [ ] **Step 5: 提交本任务改动**

```bash
git add src/core.py tests/test_search_pagination.py
git commit -m "fix: bind parsed results to newest browser response"
```

### Task 6: 明确 engine 和停止原因语义

**Files:**
- Modify: `tests/test_search_pagination.py`
- Modify: `src/core.py`
- Test: `tests/test_search_pagination.py`

- [ ] **Step 1: 写失败测试，更新 metadata 语义**

```python
@pytest.mark.asyncio
async def test_search_outcome_exposes_browser_interaction_metadata():
    searcher = FakeSearchImpl(
        pages=[[make_item("a-1")]],
        response_flags=[True],
        max_stale_pages=1,
    )

    outcome = await searcher.search(SearchParams(keyword="泡泡玛特", rows=1))

    assert outcome.engine_used == "browser_interaction"
    assert outcome.fallback_reason is None
    assert outcome.pages_fetched == 1
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_search_pagination.py::test_search_outcome_exposes_browser_interaction_metadata -v`
Expected: FAIL，因为当前值还是 `browser_fallback`。

- [ ] **Step 3: 更新 `SearchOutcome` 填充值**

```python
return SearchOutcome(
    items=result,
    requested_rows=params.rows,
    returned_rows=len(result),
    stop_reason="target_reached",
    stale_pages=stale_pages,
    engine_used="browser_interaction",
    fallback_reason=None,
    pages_fetched=page,
)
```

对 `stale_limit`、`validation_failed`、`response_timeout`、`error` 分支同步更新 `engine_used`。

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_search_pagination.py::test_search_outcome_exposes_browser_interaction_metadata -v`
Expected: PASS

- [ ] **Step 5: 提交本任务改动**

```bash
git add src/core.py tests/test_search_pagination.py
git commit -m "refactor: rename browser search engine metadata"
```

### Task 7: 清理旧 PageApi 测试假设

**Files:**
- Modify: `tests/test_search_pagination.py`
- Modify: `tests/test_search_api.py`
- Test: `tests/test_search_pagination.py`

- [ ] **Step 1: 删除或改写与本轮设计冲突的测试**

从 `tests/test_search_pagination.py` 中移除以下旧测试：

```python
async def test_app_prefers_page_api_runner(monkeypatch):
    ...


async def test_app_falls_back_when_page_api_runner_fails(monkeypatch):
    ...


async def test_app_falls_back_when_page_api_returns_zero_items(monkeypatch):
    ...
```

并在 `tests/test_search_api.py` 顶部加注释，表明该文件仅保留历史 PageApi 单元测试，当前搜索主链路不再依赖它：

```python
"""历史 PageApi 单元测试；当前搜索主链路已切换到 browser-only。"""
```

- [ ] **Step 2: 运行分页测试确认没有残留旧断言**

Run: `pytest tests/test_search_pagination.py -v`
Expected: FAIL 仅来自尚未完成的 browser-only 新断言，不应再出现 PageApi fallback 相关失败。

- [ ] **Step 3: 整理 `FakeSearchImpl` 以适配新模型**

将 `FakeSearchImpl` 的默认 metadata 对齐 browser-only 语义：

```python
return SearchOutcome(
    items=result,
    requested_rows=params.rows,
    returned_rows=len(result),
    stop_reason="target_reached",
    stale_pages=stale_pages,
    engine_used="browser_interaction",
    fallback_reason=None,
    pages_fetched=page,
)
```

- [ ] **Step 4: 运行分页测试确认通过**

Run: `pytest tests/test_search_pagination.py -v`
Expected: PASS

- [ ] **Step 5: 提交本任务改动**

```bash
git add tests/test_search_pagination.py tests/test_search_api.py
git commit -m "test: remove page api assumptions from search flow"
```

### Task 8: 跑回归测试并记录手动验收步骤

**Files:**
- Modify: `docs/superpowers/specs/2026-04-08-browser-only-search-correctness-design.md`
- Test: `tests/test_search_pagination.py`
- Test: `tests/test_search_validation.py`

- [ ] **Step 1: 运行单元测试组合**

Run: `pytest tests/test_search_pagination.py tests/test_search_validation.py -v`
Expected: PASS

- [ ] **Step 2: 运行现有核心回归，确保没有明显破坏**

Run: `pytest tests/test_core.py tests/test_http_server_unit.py -v`
Expected: PASS，若失败，修复与 `SearchOutcome` 或 `search_with_meta()` 行为变化直接相关的断言。

- [ ] **Step 3: 记录手动端到端验收步骤到 spec 末尾**

```markdown
## 13. 手动验收

1. 启动服务并确保浏览器登录态有效。
2. 以 `keyword=泡泡玛特`、`rows=100` 触发搜索。
3. 核对返回总数、唯一 `item_id` 数量、前 10 条标题。
4. 确认前 10 条不出现 `Mac mini`、电脑主机等明显错误品类。
5. 若第一页强校验失败，确认接口返回 `validation_failed`。
```

- [ ] **Step 4: 再次运行目标测试确认文档改动未影响代码**

Run: `pytest tests/test_search_pagination.py tests/test_search_validation.py -v`
Expected: PASS

- [ ] **Step 5: 提交本任务改动**

```bash
git add docs/superpowers/specs/2026-04-08-browser-only-search-correctness-design.md tests/test_search_pagination.py tests/test_search_validation.py src/core.py src/search_validation.py
git commit -m "docs: add browser-only search validation acceptance steps"
```

## Self-Review

- Spec coverage: 已覆盖 browser-only 主链路、第一页强校验、100 条分页、去重、停止原因、测试与手动验收。未纳入价格/包邮/排序，符合 spec 非目标。
- Placeholder scan: 计划中没有 `TBD`、`TODO`、`implement later` 一类占位符。
- Type consistency: 统一使用 `engine_used="browser_interaction"`、`stop_reason="validation_failed"`、`SearchOutcome`、`SearchParams`。
