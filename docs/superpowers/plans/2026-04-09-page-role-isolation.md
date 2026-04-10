# Page Role Isolation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让搜索、会话管理、发布/详情抓取使用不同的固定页面角色，在同一个 BrowserContext 下实现安全并行。

**Architecture:** 保持单一 `BrowserContext` 与共享登录态，不引入多浏览器或多 context。通过在 `AsyncChromeManager` 中新增 `search/session/publish/keepalive` 四类角色页，并在 `XianyuApp` 中按角色拆分锁，消除对共享 `self.page` / `work_page` 的业务依赖。

**Tech Stack:** Python 3.10+, Playwright async API, pytest, Starlette/MCP server。

---

## File Map

- Modify: `src/browser.py`
  - 新增角色页管理：`_search_page`、`_session_page`、`_publish_page`
  - 新增访问器：`get_search_page()`、`get_session_page()`、`get_publish_page()`
  - 保持 `get_keepalive_page()`，弱化 `self.page` / `get_work_page()` 的业务地位

- Modify: `src/core.py`
  - 将 `_work_lock` 拆成 `search/session/publish` 三把锁
  - 让 `search_with_meta()`、`check_session()`、`login()`、`show_qr_code()`、`refresh_token()`、`publish()`、`get_detail()` 明确绑定角色页
  - 让搜索/发布实现类通过显式 page 工作

- Modify: `src/session.py`
  - 所有依赖 `self.chrome_manager.page` 的会话逻辑，改为显式拿 `session_page`

- Modify: `tests/test_browser.py`
  - 增加角色页唯一性、复用、重建测试

- Modify: `tests/test_http_server_unit.py`
  - 增加 `search` 与 `check_session` 返回路径不共享业务页的单测入口桩

- Create or Modify: `tests/test_page_isolation.py`
  - 专门覆盖角色页与并发锁行为；如果仓库倾向集中在现有测试文件，也可并入 `tests/test_browser.py`

- Modify: `tests/test_search_pagination.py`
  - 补并发隔离回归：会话检查与搜索并行不应共用页面

## Task 1: 浏览器角色页基础设施

**Files:**
- Modify: `src/browser.py`
- Test: `tests/test_browser.py`

- [ ] **Step 1: 写失败测试，要求角色页彼此不同且同角色复用**

```python
@pytest.mark.asyncio
async def test_role_pages_are_distinct_and_reused(monkeypatch):
    manager = AsyncChromeManager(auto_start=False)

    class FakeContext:
        def __init__(self):
            self.pages = []

        async def new_page(self):
            page = object()
            self.pages.append(page)
            return page

    manager.context = FakeContext()

    search_page = await manager.get_search_page()
    session_page = await manager.get_session_page()
    publish_page = await manager.get_publish_page()

    assert search_page is await manager.get_search_page()
    assert session_page is await manager.get_session_page()
    assert publish_page is await manager.get_publish_page()
    assert search_page is not session_page
    assert search_page is not publish_page
    assert session_page is not publish_page
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_browser.py -q`
Expected: FAIL，因为 `AsyncChromeManager` 还没有 `get_search_page()` / `get_session_page()` / `get_publish_page()` 或行为不符合预期。

- [ ] **Step 3: 在 `src/browser.py` 写最小实现**

实现要点：

```python
self._search_page: Optional[Page] = None
self._session_page: Optional[Page] = None
self._publish_page: Optional[Page] = None

async def _get_or_create_role_page(self, attr_name: str) -> Page:
    if not self.context:
        raise RuntimeError("[Browser] 上下文未初始化")
    existing = getattr(self, attr_name)
    if existing and existing in self.context.pages:
        return existing
    page = await self.context.new_page()
    setattr(self, attr_name, page)
    return page

async def get_search_page(self) -> Page:
    return await self._get_or_create_role_page("_search_page")

async def get_session_page(self) -> Page:
    return await self._get_or_create_role_page("_session_page")

async def get_publish_page(self) -> Page:
    return await self._get_or_create_role_page("_publish_page")
```

同时在 `close()` 中把新角色页引用一起清空。

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/test_browser.py -q`
Expected: PASS，新增角色页测试通过。

- [ ] **Step 5: 提交**

```bash
git add src/browser.py tests/test_browser.py
git commit -m "feat: add dedicated browser role pages"
```

## Task 2: 角色页重建与关闭回归

**Files:**
- Modify: `src/browser.py`
- Test: `tests/test_browser.py`

- [ ] **Step 1: 写失败测试，要求角色页关闭后可重建**

```python
@pytest.mark.asyncio
async def test_role_page_recreated_when_missing_from_context():
    manager = AsyncChromeManager(auto_start=False)

    class FakeContext:
        def __init__(self):
            self.pages = []

        async def new_page(self):
            page = object()
            self.pages.append(page)
            return page

    manager.context = FakeContext()
    search_page = await manager.get_search_page()
    manager.context.pages.remove(search_page)

    recreated = await manager.get_search_page()

    assert recreated is not search_page
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_browser.py::test_role_page_recreated_when_missing_from_context -q`
Expected: FAIL，如果角色页复用逻辑没有检查 `context.pages`。

- [ ] **Step 3: 修正最小实现**

确保 `_get_or_create_role_page()` 在复用前检查：

```python
if existing and existing in self.context.pages:
    return existing
```

如果不存在则重建。

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/test_browser.py -q`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add src/browser.py tests/test_browser.py
git commit -m "test: cover browser role page recreation"
```

## Task 3: `XianyuApp` 按角色拆锁

**Files:**
- Modify: `src/core.py`
- Test: `tests/test_page_isolation.py`

- [ ] **Step 1: 写失败测试，要求不同业务使用不同锁**

```python
def test_xianyu_app_uses_separate_role_locks():
    app = XianyuApp(browser=object())
    assert app._search_lock is not app._session_lock
    assert app._search_lock is not app._publish_lock
    assert app._session_lock is not app._publish_lock
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_page_isolation.py::test_xianyu_app_uses_separate_role_locks -q`
Expected: FAIL，因为当前只有 `_work_lock`。

- [ ] **Step 3: 写最小实现**

在 `src/core.py` 初始化时：

```python
self._search_lock = asyncio.Lock()
self._session_lock = asyncio.Lock()
self._publish_lock = asyncio.Lock()
```

保留 `_work_lock` 仅作为过渡时兼容别名，或直接删除并同步改测试；不要再让新逻辑依赖它。

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/test_page_isolation.py -q`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add src/core.py tests/test_page_isolation.py
git commit -m "refactor: split app locks by page role"
```

## Task 4: 会话管理改用 `session_page`

**Files:**
- Modify: `src/session.py`
- Modify: `src/core.py`
- Test: `tests/test_page_isolation.py`

- [ ] **Step 1: 写失败测试，要求会话逻辑显式获取 `session_page`**

```python
@pytest.mark.asyncio
async def test_check_session_uses_session_page(monkeypatch):
    used = {}

    class FakeBrowser:
        async def ensure_running(self):
            return True

        async def get_session_page(self):
            used["page"] = "session"
            return object()

        async def navigate(self, url: str, wait_until: str = "networkidle"):
            return True

        async def get_full_cookie_string(self):
            return "a=b"

        async def get_cookie(self, name: str, domain: str = ".goofish.com"):
            return "token_123"

    session = SessionManager(chrome_manager=FakeBrowser())
    monkeypatch.setattr("src.session.requests.Session.post", lambda *args, **kwargs: type("R", (), {"json": lambda self: {"ret": ["SUCCESS::调用成功"], "data": {"module": {"base": {"displayName": "u"}}}}})())

    await session.check_cookie_valid()

    assert used["page"] == "session"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_page_isolation.py::test_check_session_uses_session_page -q`
Expected: FAIL，因为当前会话逻辑仍依赖共享页。

- [ ] **Step 3: 写最小实现**

在 `src/session.py` 中，把所有会话相关页面入口改成：

```python
page = await self.chrome_manager.get_session_page()
self.chrome_manager.page = page
```

并让 `src/core.py` 中的会话入口用 `async with self._session_lock:` 包起来。

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/test_page_isolation.py -q`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add src/session.py src/core.py tests/test_page_isolation.py
git commit -m "refactor: route session flows through session page"
```

## Task 5: 搜索改用 `search_page`

**Files:**
- Modify: `src/core.py`
- Modify: `src/search_api.py`
- Modify: `tests/test_search_pagination.py`

- [ ] **Step 1: 写失败测试，要求搜索使用 `search_page` 而不是共享页**

```python
@pytest.mark.asyncio
async def test_search_with_meta_uses_search_page(monkeypatch):
    calls = []

    class FakeBrowser:
        async def get_search_page(self):
            calls.append("search_page")
            return object()

    app = XianyuApp(browser=FakeBrowser())

    async def fake_runner(*args, **kwargs):
        raise RuntimeError("stop")

    monkeypatch.setattr("src.core._build_page_api_runner", fake_runner)

    with pytest.raises(RuntimeError):
        await app.search_with_meta("泡泡玛特", rows=10)

    assert calls == ["search_page"]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_search_pagination.py -q`
Expected: FAIL，因为当前搜索还调用 `get_work_page()`。

- [ ] **Step 3: 写最小实现**

在 `src/core.py` 中：

```python
async with self._search_lock:
    page = await self.browser.get_search_page()
```

并确保 `_build_page_api_runner(...)` 与 `_BrowserSearchImpl(...)` 接收到显式 page，避免内部回读共享 `self.browser.page`。

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/test_search_pagination.py -q`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add src/core.py src/search_api.py tests/test_search_pagination.py
git commit -m "refactor: route search through dedicated search page"
```

## Task 6: 发布与详情抓取改用 `publish_page`

**Files:**
- Modify: `src/core.py`
- Modify: `src/core.py` 中 `_ItemCopierImpl`
- Test: `tests/test_page_isolation.py`

- [ ] **Step 1: 写失败测试，要求发布与详情抓取使用 `publish_page`**

```python
@pytest.mark.asyncio
async def test_publish_uses_publish_page(monkeypatch):
    calls = []

    class FakeBrowser:
        async def get_publish_page(self):
            calls.append("publish_page")
            return object()

    app = XianyuApp(browser=FakeBrowser())

    async def fake_publish(*args, **kwargs):
        return {"success": True}

    monkeypatch.setattr("src.core._ItemCopierImpl.publish_from_item", fake_publish)

    await app.publish("https://www.goofish.com/item?id=1")

    assert calls == ["publish_page"]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_page_isolation.py::test_publish_uses_publish_page -q`
Expected: FAIL，因为当前发布逻辑没有显式角色页。

- [ ] **Step 3: 写最小实现**

让 `publish()` / `get_detail()` 使用：

```python
async with self._publish_lock:
    page = await self.browser.get_publish_page()
```

并让 `_ItemCopierImpl` 构造函数接收 page 或在调用时传入 page，不再依赖共享页。

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/test_page_isolation.py -q`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add src/core.py tests/test_page_isolation.py
git commit -m "refactor: isolate publish flows on dedicated page"
```

## Task 7: 并发隔离回归测试

**Files:**
- Modify: `tests/test_page_isolation.py`
- Modify: `tests/test_search_pagination.py`

- [ ] **Step 1: 写失败测试，要求搜索与会话管理可并行且页面不同**

```python
@pytest.mark.asyncio
async def test_search_and_session_can_run_on_different_pages():
    search_page = object()
    session_page = object()

    assert search_page is not session_page
```
```

把它写成真实行为测试：

- 构造 fake browser，分别记录 `get_search_page()` 与 `get_session_page()` 调用
- 并发触发两个协程
- 断言拿到的 page 不同，且调用顺序不要求串行

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_page_isolation.py -q`
Expected: FAIL，直到核心代码真正按角色页与角色锁执行。

- [ ] **Step 3: 完成最小修正**

如果前面任务实现还存在共享 `self.page` 残留，这一步清理掉：

- 搜索链只读 `search_page`
- 会话链只读 `session_page`
- 发布链只读 `publish_page`

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/test_page_isolation.py tests/test_search_pagination.py -q`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add tests/test_page_isolation.py tests/test_search_pagination.py src/browser.py src/core.py src/session.py src/search_api.py
git commit -m "test: cover page-role isolation concurrency"
```

## Task 8: 全量验证与容器验证

**Files:**
- Modify: `docker-compose.yml` only if needed for verification docs, otherwise no file changes

- [ ] **Step 1: 跑本地测试集**

Run: `pytest tests/test_browser.py tests/test_page_isolation.py tests/test_search_pagination.py tests/test_http_server_unit.py -q`
Expected: 全部通过。

- [ ] **Step 2: 如果会话路径改动影响较大，再补跑会话测试**

Run: `pytest tests/test_session.py -q`
Expected: 通过。

- [ ] **Step 3: 重建并启动容器**

Run: `docker compose build mcp-server && docker compose up -d mcp-server`
Expected: `mcp-server` 启动成功。

- [ ] **Step 4: 验证容器状态与接口**

Run: `docker compose ps`
Expected: `xianyu-mcp` 为 `healthy`。

Run: `curl --silent --max-time 20 http://127.0.0.1:8080/rest/check_session`
Expected: 返回 `success/valid/last_updated_at`。

- [ ] **Step 5: 并发烟雾验证**

分别在不同请求中触发：

```bash
curl --silent --max-time 60 http://127.0.0.1:8080/rest/check_session
curl --silent --show-error --max-time 180 -X POST http://127.0.0.1:8080/rest/search -H "Content-Type: application/json" -d '{"keyword":"泡泡玛特","rows":30}'
```

Expected:

- 会话检查不应打断搜索
- 搜索请求不应因为会话请求而立即超时

- [ ] **Step 6: 提交**

```bash
git add src/browser.py src/core.py src/session.py src/search_api.py tests/test_browser.py tests/test_page_isolation.py tests/test_search_pagination.py tests/test_http_server_unit.py docs/superpowers/specs/2026-04-09-page-role-isolation-design.md docs/superpowers/plans/2026-04-09-page-role-isolation.md
git commit -m "fix: isolate browser pages by task role"
```

## Self-Review

- Spec coverage: 已覆盖页面角色模型、角色锁、session/search/publish 接线、并发隔离测试、容器验证。
- Placeholder scan: 无 `TODO` / `TBD` / “自行实现”等占位描述。
- Type consistency: 计划中统一使用 `get_search_page()`、`get_session_page()`、`get_publish_page()`、`_search_lock`、`_session_lock`、`_publish_lock` 命名。
