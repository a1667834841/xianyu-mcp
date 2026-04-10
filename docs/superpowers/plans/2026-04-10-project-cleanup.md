# 项目清理实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 清理项目中未使用的文件、空目录、废弃分支和死代码，简化项目结构。

**Architecture:** 按阶段清理：先物理目录（worktrees/空目录/egg-info），后代码清理（browser同步方法/search_api废弃类/core废弃函数/session重复方法），每步验证。

**Tech Stack:** Python 3.11, pytest, asyncio, MCP SSE protocol

---

## File Structure

| 文件 | 操作 | 说明 |
|------|------|------|
| `.worktrees/*` | 删除 | 4个废弃的 git worktree 目录 |
| `src/services/*` | 删除 | 空目录结构 |
| `src/api/*` | 删除 | 空目录结构 |
| `UNKNOWN.egg-info/*` | 删除 | 打包遗留 |
| `src/browser.py` | 修改 | 删除同步方法 |
| `src/search_api.py` | 修改 | 删除 PageApiSearchClient 相关代码 |
| `tests/test_search_api.py` | 修改 | 删除相关测试 |
| `src/core.py` | 修改 | 删除 _build_page_api_runner |
| `src/session.py` | 修改 | 删除重复 get_token |

---

## Task 1: 清理 Git Worktrees 和分支

**Files:**
- 删除: `.worktrees/browser-only-search-correctness`
- 删除: `.worktrees/feature-claude-fix1`
- 删除: `.worktrees/feature-opencode-fix-2`
- 删除: `.worktrees/refactor-structure`

- [ ] **Step 1: 删除 worktree 目录**

```bash
rm -rf .worktrees/browser-only-search-correctness
rm -rf .worktrees/feature-claude-fix1
rm -rf .worktrees/feature-opencode-fix-2
rm -rf .worktrees/refactor-structure
```

- [ ] **Step 2: 删除对应的 git 分支**

```bash
git branch -D browser-only-search-correctness
git branch -D feature/claude-fix1
git branch -D feature/opencode-fix-2
git branch -D refactor-structure
```

- [ ] **Step 3: 验证目录已删除**

```bash
ls -la .worktrees/
# Expected: 目录不存在或为空
git branch -a
# Expected: 分支列表中不再包含以上4个分支
```

- [ ] **Step 4: 提交**

```bash
git add -A
git commit -m "chore: 删除废弃的 git worktrees 和分支"
```

---

## Task 2: 清理空目录结构

**Files:**
- 删除: `src/services/` 及所有子目录
- 删除: `src/api/` 及所有子目录

- [ ] **Step 1: 删除 src/services 目录**

```bash
rm -rf src/services/
```

- [ ] **Step 2: 删除 src/api 目录**

```bash
rm -rf src/api/
```

- [ ] **Step 3: 验证导入正常**

```bash
python -c "from src import XianyuApp, AsyncChromeManager, SessionManager, CookieKeepaliveService, SearchItem, SearchParams, SearchOutcome"
# Expected: 无报错，正常导入
```

- [ ] **Step 4: 提交**

```bash
git add -A
git commit -m "chore: 删除空的 services 和 api 目录结构"
```

---

## Task 3: 清理打包遗留目录

**Files:**
- 删除: `UNKNOWN.egg-info/`

- [ ] **Step 1: 删除 UNKNOWN.egg-info 目录**

```bash
rm -rf UNKNOWN.egg-info/
```

- [ ] **Step 2: 验证目录已删除**

```bash
ls -la UNKNOWN.egg-info/
# Expected: 目录不存在
```

- [ ] **Step 3: 提交**

```bash
git add -A
git commit -m "chore: 删除打包遗留的 UNKNOWN.egg-info 目录"
```

---

## Task 4: 清理 browser.py 同步方法

**Files:**
- 修改: `src/browser.py` (删除同步方法，约666-718行)

- [ ] **Step 1: 确认要删除的代码位置**

先读取文件确认行号：

```bash
grep -n "def connect_sync\|def navigate_sync\|def get_cookie_sync\|def get_xianyu_token_sync\|def get_browser" src/browser.py
```

- [ ] **Step 2: 删除同步方法**

编辑 `src/browser.py`，删除以下方法：
- `connect_sync()` - 同步版本的 connect
- `navigate_sync()` - 同步版本的 navigate
- `get_cookie_sync()` - 同步版本的 get_cookie
- `get_xianyu_token_sync()` - 同步版本的 get_xianyu_token
- `get_browser()` - 便捷函数

同时删除 `close_sync()` 方法（如果仅在 `__exit__` 中使用，检查是否可删除）

- [ ] **Step 3: 验证单元测试**

```bash
pytest tests/test_browser.py -v
# Expected: 所有测试通过
```

- [ ] **Step 4: 提交**

```bash
git add src/browser.py
git commit -m "refactor(browser): 删除未使用的同步方法"
```

---

## Task 5: 清理 search_api.py PageApiSearchClient

**Files:**
- 修改: `src/search_api.py` (删除第9-325行)
- 修改: `tests/test_search_api.py` (删除相关测试)

- [ ] **Step 1: 删除 PageApiSearchError 和 PageApiResult**

编辑 `src/search_api.py`，删除：
- 第9-10行: `class PageApiSearchError(RuntimeError): pass`
- 第13-18行: `@dataclass class PageApiResult`

- [ ] **Step 2: 删除 PageApiSearchClient 类**

删除第20-325行的 `PageApiSearchClient` 类。

**注意**: 保留 `StableSearchRunner` 类（第328行开始）！

- [ ] **Step 3: 更新测试文件 import**

编辑 `tests/test_search_api.py`，修改第4行：

```python
# 修改前:
from src.search_api import PageApiSearchClient, PageApiSearchError, StableSearchRunner

# 修改后:
from src.search_api import StableSearchRunner
```

- [ ] **Step 4: 删除 PageApiSearchClient 相关测试**

删除以下测试函数：
- `test_page_api_client_returns_structured_page` (第40-81行区域)
- `test_page_api_client_rejects_keyword_mismatch` (第40-81行区域)
- `test_page_api_client_installs_bridge_once` (第156-227行区域)
- `test_page_api_client_runs_ready_hook_before_bridge` (第156-227行区域)
- `test_page_api_client_wraps_page_errors_as_search_errors` (第156-227行区域)

**保留**: `StableSearchRunner` 相关测试（第94-153行区域）

- [ ] **Step 5: 验证单元测试**

```bash
pytest tests/test_search_api.py -v
# Expected: 所有保留的测试通过
```

- [ ] **Step 6: 提交**

```bash
git add src/search_api.py tests/test_search_api.py
git commit -m "refactor(search_api): 删除废弃的 PageApiSearchClient 及相关测试"
```

---

## Task 6: 清理 core.py _build_page_api_runner

**Files:**
- 修改: `src/core.py` (删除约第367行的函数)

- [ ] **Step 1: 确认函数位置**

```bash
grep -n "_build_page_api_runner" src/core.py
```

- [ ] **Step 2: 删除 _build_page_api_runner 函数**

删除整个 `_build_page_api_runner()` 函数定义。

- [ ] **Step 3: 验证单元测试**

```bash
pytest tests/test_core.py -v
# Expected: 所有测试通过
```

- [ ] **Step 4: 提交**

```bash
git add src/core.py
git commit -m "refactor(core): 删除废弃的 _build_page_api_runner 函数"
```

---

## Task 7: 清理 session.py 重复 get_token

**Files:**
- 修改: `src/session.py` (删除第982-992行)

- [ ] **Step 1: 确认代码位置**

```bash
grep -n "async def get_token" src/session.py
```

预期输出：
- 第415行: 第一个 `get_token()` (正常版本，保留)
- 第982行: 第二个 `get_token()` (死代码，删除)

- [ ] **Step 2: 删除重复的 get_token 方法**

删除第982-992行的 `get_token()` 方法（包含调用不存在 `load_cached_token()` 的代码）。

**注意**: 不要删除第415行的正常版本！

- [ ] **Step 3: 验证单元测试**

```bash
pytest tests/test_session.py -v
# Expected: 所有测试通过
```

- [ ] **Step 4: 提交**

```bash
git add src/session.py
git commit -m "fix(session): 删除重复的 get_token 死代码"
```

---

## Task 8: 全量单元测试验证

- [ ] **Step 1: 运行全量单元测试**

```bash
pytest tests/ -v
# Expected: 所有测试通过，无失败
```

- [ ] **Step 2: 检查测试覆盖率（可选）**

```bash
pytest tests/ --tb=short
# Expected: 无错误输出
```

---

## Task 9: Python 层端到端测试

- [ ] **Step 1: 验证核心模块导入**

```bash
python -c "
from src import (
    XianyuApp,
    AsyncChromeManager,
    SessionManager,
    CookieKeepaliveService,
    SearchItem,
    SearchParams,
    SearchOutcome,
    login,
    refresh_token,
    check_cookie_valid,
    search,
    publish,
    get_detail,
)
from src.settings import AppSettings, load_settings
print('所有核心模块导入成功')
"
```

- [ ] **Step 2: 验证 XianyuApp 初始化（需要浏览器环境）**

```bash
python -c "
import asyncio
from src import XianyuApp, AsyncChromeManager

async def test_init():
    browser = AsyncChromeManager(host='localhost', port=9222, auto_start=False)
    app = XianyuApp(browser)
    print(f'XianyuApp 初始化成功: {app}')
    return app

asyncio.run(test_init())
"
```

- [ ] **Step 3: 验证会话检查功能（需要浏览器已登录）**

```bash
python -c "
import asyncio
from src import XianyuApp, AsyncChromeManager

async def test_session():
    browser = AsyncChromeManager(host='localhost', port=9222)
    app = XianyuApp(browser)
    await app.browser.ensure_running()
    result = await app.check_session()
    print(f'Session check result: {result}')
    await app.browser.close()

asyncio.run(test_session())
"
```

---

## Task 10: MCP SSE 协议层面验证

**MCP 提供的方法列表：**
1. `xianyu_login` - 扫码登录
2. `xianyu_search` - 搜索商品
3. `xianyu_publish` - 发布商品
4. `xianyu_refresh_token` - 刷新 Token
5. `xianyu_check_session` - 检查会话
6. `xianyu_show_qr` - 显示二维码

- [ ] **Step 1: 启动 MCP HTTP Server**

在后台启动服务：

```bash
cd /opt/dockercompose/xianyu
python mcp_server/http_server.py &
```

等待服务启动（约5秒），确认端口监听：

```bash
sleep 5
curl -s http://localhost:8080/sse -H "Accept: text/event-stream" --max-time 2 || echo "SSE endpoint responding"
```

- [ ] **Step 2: 测试 xianyu_check_session 方法**

```bash
curl -s http://localhost:8080/rest/check_session
# Expected: JSON 响应 {"success": true, "valid": true/false, ...}
```

- [ ] **Step 3: 测试 xianyu_show_qr 方法**

```bash
curl -s http://localhost:8080/rest/show_qr
# Expected: JSON 响应包含二维码信息或已登录状态
```

- [ ] **Step 4: 测试 xianyu_search 方法**

```bash
curl -s -X POST http://localhost:8080/rest/search \
  -H "Content-Type: application/json" \
  -d '{"keyword":"测试关键词","rows":5}'
# Expected: JSON 响应 {"success": true, "items": [...], "total": N}
```

- [ ] **Step 5: 测试 xianyu_refresh_token 方法（需要已登录）**

通过 Python 脚本调用 MCP 工具：

```python
# 保存为 test_mcp_tools.py
import asyncio
import sys
sys.path.insert(0, '/opt/dockercompose/xianyu')

from mcp_server.http_server import get_app

async def test_refresh_token():
    app = get_app()
    result = await app.refresh_token()
    print(f"refresh_token result: {result}")
    return result

asyncio.run(test_refresh_token())
```

运行：
```bash
python test_mcp_tools.py
# Expected: Token 刷新成功或返回错误信息
```

- [ ] **Step 6: 测试 xianyu_login 方法（可选，需要扫码）**

```python
# 添加到 test_mcp_tools.py
async def test_login():
    app = get_app()
    result = await app.login(timeout=10)
    print(f"login result: {result}")
    return result
```

- [ ] **Step 7: 测试 xianyu_publish 方法（可选，需要商品链接）**

```python
# 添加到 test_mcp_tools.py
async def test_publish():
    app = get_app()
    await app.browser.ensure_running()
    result = await app.publish(
        item_url="https://www.goofish.com/item?id=TEST_ID",
        new_price=99.0
    )
    print(f"publish result: {result}")
    return result
```

- [ ] **Step 8: 通过 SSE 协议测试 MCP 工具列表**

```bash
# 获取 MCP 工具列表
curl -s http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
# Expected: 返回所有 MCP 工具列表
```

- [ ] **Step 9: 清理测试文件并停止 MCP Server**

```bash
rm -f test_mcp_tools.py
pkill -f "python mcp_server/http_server.py"
```

---

## Task 11: 最终提交和验收

- [ ] **Step 1: 检查项目状态**

```bash
git status
# Expected: 无未提交的更改
```

- [ ] **Step 2: 检查目录结构**

```bash
ls -la .worktrees/ 2>/dev/null || echo ".worktrees 已删除"
ls -la src/services/ 2>/dev/null || echo "src/services 已删除"
ls -la src/api/ 2>/dev/null || echo "src/api 已删除"
ls -la UNKNOWN.egg-info/ 2>/dev/null || echo "UNKNOWN.egg-info 已删除"
```

- [ ] **Step 3: 检查分支状态**

```bash
git branch -a
# Expected: 只有 master 和 main 分支
```

- [ ] **Step 4: 最终提交（如有遗漏）**

```bash
git add -A
git status --porcelain | wc -l
# Expected: 0 (无未提交文件)
```

---

## 验收标准

完成以下所有项即为成功：

1. ✅ `.worktrees/` 目录不存在
2. ✅ 相关 git 分支已删除
3. ✅ `src/services/` 和 `src/api/` 目录不存在
4. ✅ `UNKNOWN.egg-info/` 目录不存在
5. ✅ `src/browser.py` 同步方法已删除
6. ✅ `src/search_api.py` PageApiSearchClient 已删除
7. ✅ `src/core.py` _build_page_api_runner 已删除
8. ✅ `src/session.py` 重复 get_token 已删除
9. ✅ 所有单元测试通过 (`pytest tests/ -v`)
10. ✅ Python 层端到端测试通过
11. ✅ MCP 所有方法验证通过：
    - `xianyu_check_session` ✅
    - `xianyu_show_qr` ✅
    - `xianyu_search` ✅
    - `xianyu_refresh_token` ✅
    - `xianyu_login` ✅ (可选)
    - `xianyu_publish` ✅ (可选)