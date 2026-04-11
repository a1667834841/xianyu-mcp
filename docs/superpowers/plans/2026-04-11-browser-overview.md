# Browser Overview MCP Tool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a new `xianyu_browser_overview` MCP tool that returns the current Playwright browser context count and, for each context, the page titles and URLs.

**Architecture:** Keep browser inspection in `AsyncChromeManager`, expose it through `XianyuApp`, and wire the same application-level method into both MCP entrypoints. Treat browser-not-ready as a structured failure, but degrade a single page title failure to `""` so the overall overview still succeeds.

**Tech Stack:** Python 3, Playwright async API, MCP Server/FastMCP, pytest

---

## File Map

- Modify: `src/browser.py`
  Adds `get_browser_overview()` to inspect `browser.contexts` and `context.pages`.
- Modify: `src/core.py`
  Adds `XianyuApp.browser_overview()` as a thin pass-through.
- Modify: `mcp_server/http_server.py`
  Registers `xianyu_browser_overview()` for the HTTP/SSE MCP server and returns JSON text.
- Modify: `mcp_server/server.py`
  Registers `xianyu_browser_overview` in stdio tool metadata, dispatch, and handler.
- Modify: `tests/test_browser.py`
  Adds browser-layer tests for multi-context aggregation, title fallback, and browser-not-ready failure.
- Modify: `tests/test_http_server_unit.py`
  Adds HTTP and stdio MCP unit tests for tool registration and payload formatting.

### Task 1: Add browser overview tests and minimal browser implementation

**Files:**
- Modify: `tests/test_browser.py`
- Modify: `src/browser.py`

- [ ] **Step 1: Write the failing browser-layer tests**

Add these test helpers and test cases near the bottom of `tests/test_browser.py`:

```python
class OverviewFakePage:
    def __init__(self, title_text: str, url: str, *, fail_title: bool = False):
        self._title_text = title_text
        self.url = url
        self._fail_title = fail_title

    async def title(self):
        if self._fail_title:
            raise RuntimeError("title failed")
        return self._title_text


class OverviewFakeContext:
    def __init__(self, pages):
        self.pages = pages


class OverviewFakeBrowserRoot:
    def __init__(self, contexts):
        self.contexts = contexts


@pytest.mark.asyncio
async def test_get_browser_overview_returns_all_contexts_and_pages(tmp_path):
    manager = AsyncChromeManager(user_data_dir=tmp_path, auto_start=False)

    async def fake_ensure_running():
        return True

    manager.ensure_running = fake_ensure_running
    manager.browser = OverviewFakeBrowserRoot(
        [
            OverviewFakeContext(
                [
                    OverviewFakePage("闲鱼", "https://www.goofish.com/"),
                    OverviewFakePage("发布", "https://www.goofish.com/publish"),
                ]
            ),
            OverviewFakeContext(
                [
                    OverviewFakePage("消息", "https://www.goofish.com/im"),
                ]
            ),
        ]
    )

    overview = await manager.get_browser_overview()

    assert overview == {
        "browser_context_count": 2,
        "contexts": [
            {
                "page_count": 2,
                "pages": [
                    {"title": "闲鱼", "url": "https://www.goofish.com/"},
                    {"title": "发布", "url": "https://www.goofish.com/publish"},
                ],
            },
            {
                "page_count": 1,
                "pages": [
                    {"title": "消息", "url": "https://www.goofish.com/im"},
                ],
            },
        ],
    }


@pytest.mark.asyncio
async def test_get_browser_overview_falls_back_when_page_title_fails(tmp_path):
    manager = AsyncChromeManager(user_data_dir=tmp_path, auto_start=False)

    async def fake_ensure_running():
        return True

    manager.ensure_running = fake_ensure_running
    manager.browser = OverviewFakeBrowserRoot(
        [
            OverviewFakeContext(
                [
                    OverviewFakePage(
                        "ignored",
                        "https://www.goofish.com/failing-title",
                        fail_title=True,
                    )
                ]
            )
        ]
    )

    overview = await manager.get_browser_overview()

    assert overview["contexts"][0]["pages"] == [
        {"title": "", "url": "https://www.goofish.com/failing-title"}
    ]


@pytest.mark.asyncio
async def test_get_browser_overview_raises_when_browser_not_ready(tmp_path):
    manager = AsyncChromeManager(user_data_dir=tmp_path, auto_start=False)

    async def fake_ensure_running():
        return False

    manager.ensure_running = fake_ensure_running

    with pytest.raises(RuntimeError, match="浏览器未连接，无法获取概览"):
        await manager.get_browser_overview()
```

- [ ] **Step 2: Run the browser tests to verify they fail**

Run: `pytest tests/test_browser.py -k browser_overview -v`

Expected: FAIL with `AttributeError: 'AsyncChromeManager' object has no attribute 'get_browser_overview'`

- [ ] **Step 3: Add the minimal browser implementation**

Add this method to `src/browser.py` near the other page/query helpers:

```python
    async def get_browser_overview(self) -> Dict:
        """返回当前浏览器 context 和页面概览。"""
        if not await self.ensure_running():
            raise RuntimeError("浏览器未连接，无法获取概览")

        if not self.browser:
            raise RuntimeError("浏览器未连接，无法获取概览")

        contexts = getattr(self.browser, "contexts", None)
        if contexts is None:
            raise RuntimeError("浏览器上下文不可用，无法获取概览")

        overview = {"browser_context_count": len(contexts), "contexts": []}

        for context in contexts:
            pages_payload = []
            for page in getattr(context, "pages", []):
                title = ""
                try:
                    title = await page.title()
                except Exception:
                    title = ""

                pages_payload.append(
                    {
                        "title": title,
                        "url": getattr(page, "url", "") or "",
                    }
                )

            overview["contexts"].append(
                {
                    "page_count": len(pages_payload),
                    "pages": pages_payload,
                }
            )

        return overview
```

- [ ] **Step 4: Run the browser tests to verify they pass**

Run: `pytest tests/test_browser.py -k browser_overview -v`

Expected: PASS with 3 selected tests

- [ ] **Step 5: Commit**

```bash
git add tests/test_browser.py src/browser.py
git commit -m "feat: add browser overview query"
```

### Task 2: Expose browser overview through `XianyuApp` and the HTTP MCP entrypoint

**Files:**
- Modify: `src/core.py`
- Modify: `mcp_server/http_server.py`
- Modify: `tests/test_http_server_unit.py`

- [ ] **Step 1: Write the failing app and HTTP tests**

Append these tests to `tests/test_http_server_unit.py`:

```python
@pytest.mark.asyncio
async def test_xianyu_browser_overview_returns_http_payload(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.http_server as http_server

    class FakeApp:
        async def browser_overview(self):
            return {
                "browser_context_count": 2,
                "contexts": [
                    {
                        "page_count": 1,
                        "pages": [
                            {
                                "title": "闲鱼",
                                "url": "https://www.goofish.com/",
                            }
                        ],
                    }
                ],
            }

    monkeypatch.setattr(http_server, "get_app", lambda: FakeApp())

    payload = json.loads(await http_server.xianyu_browser_overview())

    assert payload == {
        "success": True,
        "browser_context_count": 2,
        "contexts": [
            {
                "page_count": 1,
                "pages": [
                    {
                        "title": "闲鱼",
                        "url": "https://www.goofish.com/",
                    }
                ],
            }
        ],
    }


@pytest.mark.asyncio
async def test_xianyu_browser_overview_returns_http_failure_payload(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.http_server as http_server

    class FakeApp:
        async def browser_overview(self):
            raise RuntimeError("浏览器未连接，无法获取概览")

    monkeypatch.setattr(http_server, "get_app", lambda: FakeApp())

    payload = json.loads(await http_server.xianyu_browser_overview())

    assert payload == {
        "success": False,
        "message": "浏览器未连接，无法获取概览",
    }
```

- [ ] **Step 2: Run the HTTP tests to verify they fail**

Run: `pytest tests/test_http_server_unit.py -k browser_overview_returns_http -v`

Expected: FAIL with `AttributeError` because `xianyu_browser_overview` does not exist yet

- [ ] **Step 3: Add the app pass-through and HTTP MCP tool**

Add this method to `src/core.py` near the other top-level `XianyuApp` methods:

```python
    async def browser_overview(self) -> Dict[str, Any]:
        """返回当前浏览器 context 和页面概览。"""
        return await self.browser.get_browser_overview()
```

Add this tool to `mcp_server/http_server.py` after `xianyu_check_session()`:

```python
@mcp.tool()
async def xianyu_browser_overview() -> str:
    """
    获取当前浏览器 context 数量，以及各 context 下页面标题和 URL。
    """
    app = get_app()

    try:
        overview = await app.browser_overview()
        response = {"success": True, **overview}
    except RuntimeError as exc:
        response = {"success": False, "message": str(exc)}

    return json.dumps(response, ensure_ascii=False)
```

- [ ] **Step 4: Run the HTTP tests to verify they pass**

Run: `pytest tests/test_http_server_unit.py -k browser_overview_returns_http -v`

Expected: PASS with 2 selected tests

- [ ] **Step 5: Commit**

```bash
git add src/core.py mcp_server/http_server.py tests/test_http_server_unit.py
git commit -m "feat: expose browser overview over http mcp"
```

### Task 3: Register the stdio MCP tool and test tool metadata and dispatch

**Files:**
- Modify: `mcp_server/server.py`
- Modify: `tests/test_http_server_unit.py`

- [ ] **Step 1: Write the failing stdio MCP tests**

Append these tests to `tests/test_http_server_unit.py` after the HTTP browser overview tests:

```python
@pytest.mark.asyncio
async def test_stdio_list_tools_includes_browser_overview(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.server as stdio_server

    tools = await stdio_server.list_tools()
    tool_names = [tool.kwargs["name"] for tool in tools]

    assert "xianyu_browser_overview" in tool_names


@pytest.mark.asyncio
async def test_stdio_call_tool_returns_browser_overview_payload(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.server as stdio_server

    class FakeApp:
        async def browser_overview(self):
            return {
                "browser_context_count": 1,
                "contexts": [
                    {
                        "page_count": 1,
                        "pages": [
                            {
                                "title": "闲鱼",
                                "url": "https://www.goofish.com/",
                            }
                        ],
                    }
                ],
            }

    monkeypatch.setattr(stdio_server, "get_app", lambda: FakeApp())

    result = await stdio_server.call_tool("xianyu_browser_overview", {})
    payload = json.loads(result.content[0].text)

    assert payload == {
        "success": True,
        "browser_context_count": 1,
        "contexts": [
            {
                "page_count": 1,
                "pages": [
                    {
                        "title": "闲鱼",
                        "url": "https://www.goofish.com/",
                    }
                ],
            }
        ],
    }


@pytest.mark.asyncio
async def test_stdio_call_tool_returns_browser_overview_failure_payload(monkeypatch):
    _install_fake_mcp(monkeypatch)
    import mcp_server.server as stdio_server

    class FakeApp:
        async def browser_overview(self):
            raise RuntimeError("浏览器未连接，无法获取概览")

    monkeypatch.setattr(stdio_server, "get_app", lambda: FakeApp())

    result = await stdio_server.call_tool("xianyu_browser_overview", {})
    payload = json.loads(result.content[0].text)

    assert payload == {
        "success": False,
        "message": "浏览器未连接，无法获取概览",
    }
```

- [ ] **Step 2: Run the stdio tests to verify they fail**

Run: `pytest tests/test_http_server_unit.py -k "browser_overview and stdio" -v`

Expected: FAIL because `xianyu_browser_overview` is missing from `list_tools()` and `call_tool()`

- [ ] **Step 3: Register the stdio tool and add the handler**

Update the tool list in `mcp_server/server.py` by inserting this block near the other tool definitions:

```python
        types.Tool(
            name="xianyu_browser_overview",
            description="获取当前浏览器 context 数量，以及各 context 下页面标题和 URL。",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
```

Update the dispatcher in `call_tool()` with this branch:

```python
        elif name == "xianyu_browser_overview":
            return await handle_browser_overview(arguments)
```

Add this handler near the other `handle_*` functions:

```python
async def handle_browser_overview(arguments: dict) -> types.CallToolResult:
    """处理浏览器概览查询。"""
    app = get_app()

    try:
        overview = await app.browser_overview()
        response = {"success": True, **overview}
    except RuntimeError as exc:
        response = {"success": False, "message": str(exc)}

    return types.CallToolResult(
        content=[
            types.TextContent(type="text", text=json.dumps(response, ensure_ascii=False))
        ]
    )
```

- [ ] **Step 4: Run the stdio tests to verify they pass**

Run: `pytest tests/test_http_server_unit.py -k "browser_overview and stdio" -v`

Expected: PASS with 3 selected tests

- [ ] **Step 5: Commit**

```bash
git add mcp_server/server.py tests/test_http_server_unit.py
git commit -m "feat: add stdio browser overview tool"
```

### Task 4: Run the focused verification suite and smoke-check the final payload shape

**Files:**
- Modify: none
- Test: `tests/test_browser.py`
- Test: `tests/test_http_server_unit.py`

- [ ] **Step 1: Run the combined focused unit tests**

Run: `pytest tests/test_browser.py tests/test_http_server_unit.py -k browser_overview -v`

Expected: PASS for all browser overview tests in both files

- [ ] **Step 2: Run the full touched test files once**

Run: `pytest tests/test_browser.py tests/test_http_server_unit.py -v`

Expected: PASS with no regressions in existing browser or MCP unit tests

- [ ] **Step 3: Manually inspect the final JSON contract**

Use the expected success payload as the manual checklist:

```json
{
  "success": true,
  "browser_context_count": 1,
  "contexts": [
    {
      "page_count": 1,
      "pages": [
        {
          "title": "闲鱼",
          "url": "https://www.goofish.com/"
        }
      ]
    }
  ]
}
```

Confirm all of the following:

- `success` exists on both success and failure payloads
- `browser_context_count` is the number of `browser.contexts`
- each context item has `page_count`
- each page item has only `title` and `url`
- browser-not-ready returns `{"success": false, "message": "浏览器未连接，无法获取概览"}`

- [ ] **Step 4: Commit**

```bash
git add src/browser.py src/core.py mcp_server/http_server.py mcp_server/server.py tests/test_browser.py tests/test_http_server_unit.py
git commit -m "feat: add browser overview mcp tool"
```
