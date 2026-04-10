# Search Stability And Sign-Aware Page API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a sign-aware page-context search path that fixes keyword accuracy and pagination stability while keeping the existing DOM search implementation as automatic fallback.

**Architecture:** Add a focused page-API search client that runs inside the Playwright page context, a stable search runner that owns dedupe/pagination/stop conditions, and a coordinator in `XianyuApp.search_with_meta` that prefers the new path and falls back to `_BrowserSearchImpl` on failure. Keep MCP interfaces backward-compatible while adding engine metadata.

**Tech Stack:** Python 3.11, asyncio, Playwright, pytest, FastMCP

---

> Note: This workspace snapshot is not a git repository. The commit steps below assume execution in the source repository. If you are implementing in this exact snapshot, skip only the `git commit` command.

## File Map

- Create: `src/search_api.py`
  Page-context sign-aware search client, stable runner, fallback exception types.
- Modify: `src/core.py`
  Search metadata types, coordinator wiring, fallback handling.
- Modify: `src/__init__.py`
  Export new search metadata types if they are public.
- Modify: `mcp_server/http_server.py`
  Return `engine_used`, `fallback_reason`, and `pages_fetched` without breaking existing fields.
- Modify: `mcp_server/server.py`
  Return the same search metadata through MCP stdio/SSE.
- Modify: `tests/test_search_pagination.py`
  Add page-API success/fallback/pagination regression coverage.
- Create: `tests/test_search_api.py`
  Focused tests for page-API client and stable runner behavior.
- Modify: `README.md`
  Document new search behavior and search metadata.

### Task 1: Add Search Metadata Type Support

**Files:**
- Modify: `src/core.py`
- Modify: `src/__init__.py`
- Test: `tests/test_search_pagination.py`

- [ ] **Step 1: Write the failing metadata test**

Add this test near the end of `tests/test_search_pagination.py`:

```python
@pytest.mark.asyncio
async def test_search_outcome_exposes_engine_metadata():
    searcher = FakeSearchImpl(
        pages=[[make_item("a-1")]],
        response_flags=[True],
        max_stale_pages=1,
    )

    outcome = await searcher.search(SearchParams(keyword="泡泡玛特", rows=1))

    assert outcome.engine_used == "browser_fallback"
    assert outcome.fallback_reason is None
    assert outcome.pages_fetched == 1
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_search_pagination.py::test_search_outcome_exposes_engine_metadata -v`

Expected: FAIL with `AttributeError` or dataclass init error because the new fields do not exist.

- [ ] **Step 3: Extend `SearchOutcome` with metadata fields**

Update the dataclass in `src/core.py` to:

```python
@dataclass
class SearchOutcome:
    items: List[SearchItem]
    requested_rows: int
    returned_rows: int
    stop_reason: str
    stale_pages: int
    engine_used: str = "browser_fallback"
    fallback_reason: Optional[str] = None
    pages_fetched: int = 0
```

If `src/__init__.py` exports `SearchOutcome`, keep that export intact.

- [ ] **Step 4: Set metadata in existing browser-search return paths**

Update each `SearchOutcome(...)` return in `_BrowserSearchImpl.search()` so it passes:

```python
engine_used="browser_fallback",
fallback_reason=None,
pages_fetched=page,
```

Use the same `page` counter already maintained by the loop.

- [ ] **Step 5: Run the focused test to verify it passes**

Run: `pytest tests/test_search_pagination.py::test_search_outcome_exposes_engine_metadata -v`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/core.py src/__init__.py tests/test_search_pagination.py
git commit -m "feat: add search outcome metadata"
```

### Task 2: Build The Page-Context Search Client

**Files:**
- Create: `src/search_api.py`
- Test: `tests/test_search_api.py`

- [ ] **Step 1: Write the failing page-client tests**

Create `tests/test_search_api.py` with:

```python
import pytest

from src.core import SearchItem, SearchParams
from src.search_api import PageApiSearchClient, PageApiSearchError


def make_item(item_id: str) -> dict:
    return {
        "item_id": item_id,
        "title": f"title-{item_id}",
        "price": "100",
        "original_price": "120",
        "want_cnt": 1,
        "seller_nick": "seller",
        "seller_city": "Hangzhou",
        "image_urls": [],
        "detail_url": f"https://www.goofish.com/item?id={item_id}",
        "is_free_ship": False,
        "publish_time": None,
        "exposure_score": 1.0,
    }


class FakePage:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    async def evaluate(self, script, payload):
        self.calls.append(payload)
        response = self.responses[len(self.calls) - 1]
        if isinstance(response, Exception):
            raise response
        return response


@pytest.mark.asyncio
async def test_page_api_client_returns_structured_page():
    page = FakePage(
        [
            {
                "keyword": "泡泡玛特",
                "page": 1,
                "items": [make_item("a-1"), make_item("a-2")],
            }
        ]
    )
    client = PageApiSearchClient(page)

    result = await client.fetch_page(SearchParams(keyword="泡泡玛特", rows=10), page_number=1)

    assert result.keyword == "泡泡玛特"
    assert [item.item_id for item in result.items] == ["a-1", "a-2"]


@pytest.mark.asyncio
async def test_page_api_client_rejects_keyword_mismatch():
    page = FakePage(
        [{"keyword": "Mac mini", "page": 1, "items": [make_item("wrong-1")] }]
    )
    client = PageApiSearchClient(page)

    with pytest.raises(PageApiSearchError, match="keyword mismatch"):
        await client.fetch_page(SearchParams(keyword="泡泡玛特", rows=10), page_number=1)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_search_api.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'src.search_api'`

- [ ] **Step 3: Implement the minimal page client**

Create `src/search_api.py` with:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from .core import SearchItem, SearchParams


class PageApiSearchError(RuntimeError):
    pass


@dataclass
class PageApiResult:
    keyword: str
    page: int
    items: List[SearchItem]


class PageApiSearchClient:
    def __init__(self, page):
        self.page = page

    async def fetch_page(self, params: SearchParams, page_number: int) -> PageApiResult:
        payload = {
            "keyword": params.keyword,
            "page": page_number,
            "min_price": params.min_price,
            "max_price": params.max_price,
            "free_ship": params.free_ship,
            "sort_field": params.sort_field,
            "sort_order": params.sort_order,
        }
        raw = await self.page.evaluate(
            """
            async ({ keyword, page, min_price, max_price, free_ship, sort_field, sort_order }) => {
              if (!window.__XY_SEARCH_FETCH__) {
                throw new Error('page search bridge missing');
              }
              return await window.__XY_SEARCH_FETCH__({
                keyword,
                page,
                min_price,
                max_price,
                free_ship,
                sort_field,
                sort_order,
              });
            }
            """,
            payload,
        )
        if not isinstance(raw, dict):
            raise PageApiSearchError("invalid page api response")
        actual_keyword = raw.get("keyword")
        if actual_keyword != params.keyword:
            raise PageApiSearchError(
                f"keyword mismatch: expected {params.keyword}, got {actual_keyword}"
            )
        items = [SearchItem(**item) for item in raw.get("items", [])]
        return PageApiResult(keyword=actual_keyword, page=int(raw.get("page", page_number)), items=items)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_search_api.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/search_api.py tests/test_search_api.py
git commit -m "feat: add page context search client"
```

### Task 3: Add The Stable Search Runner

**Files:**
- Modify: `src/search_api.py`
- Test: `tests/test_search_api.py`

- [ ] **Step 1: Write the failing runner tests**

Append to `tests/test_search_api.py`:

```python
from src.search_api import StableSearchRunner


class StubClient:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    async def fetch_page(self, params, page_number):
        self.calls.append(page_number)
        return self.pages[page_number - 1]


@pytest.mark.asyncio
async def test_stable_runner_collects_multiple_pages_until_target():
    params = SearchParams(keyword="泡泡玛特", rows=4)
    runner = StableSearchRunner(
        client=StubClient(
            [
                type("Result", (), {"page": 1, "items": [SearchItem(**make_item("a-1")), SearchItem(**make_item("a-2"))]})(),
                type("Result", (), {"page": 2, "items": [SearchItem(**make_item("b-1")), SearchItem(**make_item("b-2"))]})(),
            ]
        ),
        max_stale_pages=2,
    )

    outcome = await runner.search(params)

    assert [item.item_id for item in outcome.items] == ["a-1", "a-2", "b-1", "b-2"]
    assert outcome.engine_used == "page_api"
    assert outcome.stop_reason == "target_reached"
    assert outcome.pages_fetched == 2


@pytest.mark.asyncio
async def test_stable_runner_stops_after_stale_pages():
    repeated = [SearchItem(**make_item("a-1")), SearchItem(**make_item("a-2"))]
    runner = StableSearchRunner(
        client=StubClient(
            [
                type("Result", (), {"page": 1, "items": repeated})(),
                type("Result", (), {"page": 2, "items": repeated})(),
                type("Result", (), {"page": 3, "items": repeated})(),
            ]
        ),
        max_stale_pages=2,
    )

    outcome = await runner.search(SearchParams(keyword="泡泡玛特", rows=10))

    assert len(outcome.items) == 2
    assert outcome.stop_reason == "stale_limit"
    assert outcome.stale_pages == 2
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_search_api.py -v`

Expected: FAIL with `ImportError` because `StableSearchRunner` does not exist.

- [ ] **Step 3: Implement the minimal runner**

Append to `src/search_api.py`:

```python
class StableSearchRunner:
    def __init__(self, client: PageApiSearchClient, max_stale_pages: int = 3):
        self.client = client
        self.max_stale_pages = max_stale_pages

    async def search(self, params: SearchParams):
        all_items = []
        seen_item_ids = set()
        stale_pages = 0
        page_number = 1

        while len(all_items) < params.rows:
            result = await self.client.fetch_page(params, page_number=page_number)
            new_count = 0
            for item in result.items:
                if item.item_id not in seen_item_ids:
                    seen_item_ids.add(item.item_id)
                    all_items.append(item)
                    new_count += 1

            if len(all_items) >= params.rows:
                return SearchOutcome(
                    items=all_items[: params.rows],
                    requested_rows=params.rows,
                    returned_rows=min(len(all_items), params.rows),
                    stop_reason="target_reached",
                    stale_pages=stale_pages,
                    engine_used="page_api",
                    fallback_reason=None,
                    pages_fetched=page_number,
                )

            stale_pages = stale_pages + 1 if new_count == 0 else 0
            if stale_pages >= self.max_stale_pages:
                return SearchOutcome(
                    items=all_items[: params.rows],
                    requested_rows=params.rows,
                    returned_rows=min(len(all_items), params.rows),
                    stop_reason="stale_limit",
                    stale_pages=stale_pages,
                    engine_used="page_api",
                    fallback_reason=None,
                    pages_fetched=page_number,
                )

            page_number += 1
```

Also update imports at the top of `src/search_api.py`:

```python
from .core import SearchItem, SearchOutcome, SearchParams
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_search_api.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/search_api.py tests/test_search_api.py
git commit -m "feat: add stable page api search runner"
```

### Task 4: Wire Coordinator Fallback Into `XianyuApp.search_with_meta`

**Files:**
- Modify: `src/core.py`
- Modify: `tests/test_search_pagination.py`

- [ ] **Step 1: Write the failing coordinator tests**

Append to `tests/test_search_pagination.py`:

```python
from src.search_api import PageApiSearchError


class FakePageApiRunner:
    def __init__(self, outcome=None, error=None):
        self.outcome = outcome
        self.error = error

    async def search(self, params):
        if self.error:
            raise self.error
        return self.outcome


@pytest.mark.asyncio
async def test_app_prefers_page_api_runner(monkeypatch):
    app = XianyuApp(browser=DummyBrowser())
    expected = SearchOutcome(
        items=[make_item("api-1")],
        requested_rows=1,
        returned_rows=1,
        stop_reason="target_reached",
        stale_pages=0,
        engine_used="page_api",
        fallback_reason=None,
        pages_fetched=1,
    )

    monkeypatch.setattr("src.core._build_page_api_runner", lambda browser, params, max_stale_pages: FakePageApiRunner(outcome=expected))
    monkeypatch.setattr("src.core._BrowserSearchImpl", lambda browser, max_stale_pages=3: pytest.fail("fallback should not run"))

    outcome = await app.search_with_meta("泡泡玛特", rows=1)

    assert outcome.engine_used == "page_api"
    assert outcome.items[0].item_id == "api-1"


@pytest.mark.asyncio
async def test_app_falls_back_when_page_api_runner_fails(monkeypatch):
    app = XianyuApp(browser=DummyBrowser())
    fallback = FakeSearchImpl(pages=[[make_item("fallback-1")]], response_flags=[True])

    monkeypatch.setattr(
        "src.core._build_page_api_runner",
        lambda browser, params, max_stale_pages: FakePageApiRunner(error=PageApiSearchError("bridge missing")),
    )
    monkeypatch.setattr("src.core._BrowserSearchImpl", lambda browser, max_stale_pages=3: fallback)

    outcome = await app.search_with_meta("泡泡玛特", rows=1)

    assert outcome.engine_used == "browser_fallback"
    assert outcome.fallback_reason == "bridge missing"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_search_pagination.py -v`

Expected: FAIL because `_build_page_api_runner` does not exist and `search_with_meta` always uses `_BrowserSearchImpl`.

- [ ] **Step 3: Add the coordinator hook and fallback path**

Update `src/core.py` imports:

```python
from .search_api import PageApiSearchError, PageApiSearchClient, StableSearchRunner
```

Add this helper near the search section:

```python
def _build_page_api_runner(browser: AsyncChromeManager, params: SearchParams, max_stale_pages: int):
    page = browser.page
    client = PageApiSearchClient(page)
    return StableSearchRunner(client=client, max_stale_pages=max_stale_pages)
```

Then update `XianyuApp.search_with_meta()` to:

```python
        async with self._work_lock:
            page = await self.browser.get_work_page()
            self.browser.page = page

            try:
                runner = _build_page_api_runner(
                    self.browser,
                    params,
                    self.settings.search.max_stale_pages,
                )
                return await runner.search(params)
            except PageApiSearchError as exc:
                fallback_reason = str(exc)

            searcher = _BrowserSearchImpl(
                self.browser,
                max_stale_pages=self.settings.search.max_stale_pages,
            )
            outcome = await searcher.search(params)
            outcome.fallback_reason = fallback_reason
            return outcome
```

Initialize `fallback_reason = None` just before the `try` block.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_search_pagination.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/core.py tests/test_search_pagination.py
git commit -m "feat: add page api search fallback coordinator"
```

### Task 5: Add MCP Metadata Output

**Files:**
- Modify: `mcp_server/http_server.py`
- Modify: `mcp_server/server.py`
- Modify: `tests/test_http_server_unit.py`

- [ ] **Step 1: Write the failing HTTP-server metadata test**

Add to `tests/test_http_server_unit.py`:

```python
@pytest.mark.asyncio
async def test_xianyu_search_returns_engine_metadata(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.http_server as http_server

    class FakeBrowser:
        async def ensure_running(self):
            return True

    class FakeAppWithMetadata:
        def __init__(self):
            self.browser = FakeBrowser()

        async def search_with_meta(self, keyword: str, **options):
            return SearchOutcome(
                items=[_make_search_item("item-1")],
                requested_rows=10,
                returned_rows=1,
                stop_reason="target_reached",
                stale_pages=0,
                engine_used="page_api",
                fallback_reason=None,
                pages_fetched=1,
            )

    monkeypatch.setattr(http_server, "get_app", lambda: FakeAppWithMetadata())

    payload = json.loads(await http_server.xianyu_search(keyword="泡泡玛特", rows=10))

    assert payload["engine_used"] == "page_api"
    assert payload["fallback_reason"] is None
    assert payload["pages_fetched"] == 1
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_http_server_unit.py::test_xianyu_search_returns_engine_metadata -v`

Expected: FAIL with missing keys in the JSON payload.

- [ ] **Step 3: Add the metadata fields to both server outputs**

Update the search result dict in both `mcp_server/http_server.py` and `mcp_server/server.py` to include:

```python
        "engine_used": outcome.engine_used,
        "fallback_reason": outcome.fallback_reason,
        "pages_fetched": outcome.pages_fetched,
```

Keep all existing keys unchanged.

- [ ] **Step 4: Run the focused test to verify it passes**

Run: `pytest tests/test_http_server_unit.py::test_xianyu_search_returns_engine_metadata -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add mcp_server/http_server.py mcp_server/server.py tests/test_http_server_unit.py
git commit -m "feat: expose search engine metadata"
```

### Task 6: Install The Real Page Bridge And Document It

**Files:**
- Modify: `src/search_api.py`
- Modify: `README.md`
- Test: `tests/test_search_api.py`

- [ ] **Step 1: Write the failing bridge-install test**

Append to `tests/test_search_api.py`:

```python
@pytest.mark.asyncio
async def test_page_api_client_installs_bridge_once():
    class BridgePage(FakePage):
        def __init__(self):
            super().__init__([{ "keyword": "泡泡玛特", "page": 1, "items": [] }])
            self.init_calls = 0

        async def evaluate(self, script, payload=None):
            if payload is None:
                self.init_calls += 1
                return None
            return await super().evaluate(script, payload)

    page = BridgePage()
    client = PageApiSearchClient(page)

    await client.fetch_page(SearchParams(keyword="泡泡玛特", rows=1), page_number=1)
    await client.fetch_page(SearchParams(keyword="泡泡玛特", rows=1), page_number=1)

    assert page.init_calls == 1
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_search_api.py::test_page_api_client_installs_bridge_once -v`

Expected: FAIL because bridge installation is not implemented.

- [ ] **Step 3: Install the page bridge once inside `PageApiSearchClient`**

Update `src/search_api.py`:

```python
class PageApiSearchClient:
    def __init__(self, page):
        self.page = page
        self._bridge_ready = False

    async def _ensure_bridge(self):
        if self._bridge_ready:
            return
        await self.page.evaluate(
            """
            () => {
              if (window.__XY_SEARCH_FETCH__) {
                return;
              }
              const getToken = () => {
                const match = document.cookie.match(/(?:^|; )_m_h5_tk=([^;]+)/);
                if (!match) {
                  throw new Error('missing _m_h5_tk');
                }
                return decodeURIComponent(match[1]).split('_')[0];
              };

              const md5 = (input) => {
                if (typeof window.md5 === 'function') {
                  return window.md5(input);
                }
                if (window.CryptoJS && typeof window.CryptoJS.MD5 === 'function') {
                  return window.CryptoJS.MD5(input).toString();
                }
                throw new Error('missing md5 implementation in page context');
              };

              window.__XY_SEARCH_FETCH__ = async ({ keyword, page, min_price, max_price, free_ship, sort_field, sort_order }) => {
                const timestamp = String(Date.now());
                const appKey = '34839810';
                const data = {
                  pageNumber: page,
                  rowsPerPage: 30,
                  keyword,
                  sortValue: sort_order || '',
                  sortField: sort_field || '',
                  propValueStr: JSON.stringify({
                    searchFilter: 'publishDays:14;',
                    minPrice: min_price ?? '',
                    maxPrice: max_price ?? '',
                    freeShipping: free_ship ? '1' : '',
                  }),
                  searchReqFromPage: 'pcSearch',
                };
                const dataStr = JSON.stringify(data);
                const token = getToken();
                const sign = md5(`${token}&${timestamp}&${appKey}&${dataStr}`);
                const query = new URLSearchParams({
                  jsv: '2.7.2',
                  appKey,
                  t: timestamp,
                  sign,
                  api: 'mtop.taobao.idlemtopsearch.pc.search',
                  v: '1.0',
                  type: 'originaljson',
                  dataType: 'json',
                  timeout: '20000',
                  data: dataStr,
                });
                const response = await fetch(`https://h5api.m.goofish.com/h5/mtop.taobao.idlemtopsearch.pc.search/1.0/?${query.toString()}`, {
                  method: 'POST',
                  credentials: 'include',
                  headers: {
                    'content-type': 'application/x-www-form-urlencoded',
                  },
                });
                const payload = await response.json();
                const resultList = payload?.data?.resultList || [];
                return {
                  keyword,
                  page,
                  items: resultList.map((entry) => {
                    const main = entry?.data?.item?.main || {};
                    const exContent = main.exContent || {};
                    const clickArgs = main.clickParam?.args || {};
                    const itemId = clickArgs.item_id || exContent.itemId || '';
                    return {
                      item_id: itemId,
                      title: main.title || '',
                      price: exContent.price || '',
                      original_price: exContent.originalPrice || '',
                      want_cnt: Number(exContent.wantNum || 0),
                      seller_nick: exContent.userNick || '',
                      seller_city: exContent.city || '',
                      image_urls: exContent.picUrl ? [exContent.picUrl] : [],
                      detail_url: itemId ? `https://www.goofish.com/item?id=${itemId}` : '',
                      is_free_ship: Boolean(exContent.freeDelivery),
                      publish_time: null,
                      exposure_score: 0.0,
                    };
                  }).filter((item) => item.item_id),
                };
              };
            }
            """
        )
        self._bridge_ready = True

    async def fetch_page(self, params: SearchParams, page_number: int) -> PageApiResult:
        await self._ensure_bridge()
        payload = {
            "keyword": params.keyword,
            "page": page_number,
            "min_price": params.min_price,
            "max_price": params.max_price,
            "free_ship": params.free_ship,
            "sort_field": params.sort_field,
            "sort_order": params.sort_order,
        }
        raw = await self.page.evaluate(
            """
            async ({ keyword, page, min_price, max_price, free_ship, sort_field, sort_order }) => {
              return await window.__XY_SEARCH_FETCH__({
                keyword,
                page,
                min_price,
                max_price,
                free_ship,
                sort_field,
                sort_order,
              });
            }
            """,
            payload,
        )
        if not isinstance(raw, dict):
            raise PageApiSearchError("invalid page api response")
        actual_keyword = raw.get("keyword")
        if actual_keyword != params.keyword:
            raise PageApiSearchError(
                f"keyword mismatch: expected {params.keyword}, got {actual_keyword}"
            )
        items = [SearchItem(**item) for item in raw.get("items", [])]
        return PageApiResult(
            keyword=actual_keyword,
            page=int(raw.get("page", page_number)),
            items=items,
        )
```

- [ ] **Step 4: Document the behavior in `README.md`**

Add a short bullet under the search feature section:

```md
- **搜索能力** (`xianyu-search`) - 优先使用页面上下文内的 sign 感知 API 搜索，失败时自动回退到页面交互搜索；返回结果包含 `stop_reason`、`engine_used`、`fallback_reason`、`pages_fetched`
```

- [ ] **Step 5: Run the search-api tests to verify they pass**

Run: `pytest tests/test_search_api.py -v`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/search_api.py README.md tests/test_search_api.py
git commit -m "docs: describe sign aware page api search"
```

### Task 7: Full Verification

**Files:**
- Modify: none
- Test: `tests/test_search_api.py`
- Test: `tests/test_search_pagination.py`
- Test: `tests/test_http_server_unit.py`

- [ ] **Step 1: Run the focused test suite**

Run: `pytest tests/test_search_api.py tests/test_search_pagination.py tests/test_http_server_unit.py -v`

Expected: PASS

- [ ] **Step 2: Run the targeted runtime smoke check**

Run: `pytest tests/test_search_api.py::test_stable_runner_collects_multiple_pages_until_target tests/test_search_pagination.py::test_app_falls_back_when_page_api_runner_fails -v`

Expected: PASS

- [ ] **Step 3: Commit the final verified state**

```bash
git add src/search_api.py src/core.py src/__init__.py mcp_server/http_server.py mcp_server/server.py tests/test_search_api.py tests/test_search_pagination.py tests/test_http_server_unit.py README.md
git commit -m "feat: stabilize xianyu search with page api fallback"
```

## Self-Review

- Spec coverage check:
  - 页面内 API 主链路: Task 2, Task 6
  - 稳定分页与去重: Task 3
  - 自动 fallback: Task 4
  - MCP 元信息输出: Task 5
  - 文档更新: Task 6
  - 自动化验证: Task 1, Task 2, Task 3, Task 4, Task 5, Task 7
- Placeholder scan:
  - No unresolved placeholders or shorthand references remain.
- Type consistency check:
  - `SearchOutcome.engine_used`, `fallback_reason`, and `pages_fetched` are defined in Task 1 and used consistently in later tasks.
  - `PageApiSearchClient`, `PageApiSearchError`, and `StableSearchRunner` are introduced before coordinator wiring uses them.
