# 项目清理设计文档

**日期**: 2026-04-10
**状态**: 待审核

## 一、背景

项目经过多轮开发迭代，积累了以下需要清理的内容：
- 4个已完成的开发分支 worktrees
- 为重构准备的空目录结构
- 打包错误生成的遗留目录
- 重构过程中废弃的未使用代码

清理这些内容可以：
- 简化项目结构，提高可维护性
- 减少代码理解成本
- 避免混淆和误用

## 二、清理范围

### 2.1 Git Worktrees 和分支

| Worktree 目录 | 对应分支 | 操作 |
|---------------|----------|------|
| `.worktrees/browser-only-search-correctness` | `browser-only-search-correctness` | 删除目录 + 删除分支 |
| `.worktrees/feature-claude-fix1` | `feature/claude-fix1` | 删除目录 + 删除分支 |
| `.worktrees/feature-opencode-fix-2` | `feature/opencode-fix-2` | 删除目录 + 删除分支 |
| `.worktrees/refactor-structure` | `refactor-structure` | 删除目录 + 删除分支 |

**说明**: 这些分支的开发工作已完成或废弃，用户确认直接删除。

### 2.2 空目录结构

| 目录 | 说明 |
|------|------|
| `src/services/` | 只有 `__init__.py`，`__all__ = []` |
| `src/services/publish/` | 只有 `__init__.py`，`__all__ = []` |
| `src/services/search/` | 只有 `__init__.py`，`__all__ = []` |
| `src/services/session/` | 只有 `__init__.py`，`__all__ = []` |
| `src/api/` | 只有 `__init__.py`，`__all__ = []` |
| `src/api/mcp/` | 只有 `__init__.py`，`__all__ = []` |

**说明**: 这些目录是为重构准备的骨架结构，但重构未完成，目前没有任何实际代码。

### 2.3 打包遗留目录

| 目录 | 说明 |
|------|------|
| `UNKNOWN.egg-info/` | 打包时因项目名未正确配置而生成的目录 |

### 2.4 未使用代码（高优先级）

#### 2.4.1 src/browser.py - 同步方法

删除以下方法（向后兼容设计但实际未被使用）：

| 方法 | 行号 | 说明 |
|------|------|------|
| `connect_sync()` | 约666 | 同步版本的 connect |
| `navigate_sync()` | 约669 | 同步版本的 navigate |
| `get_cookie_sync()` | 约672 | 同步版本的 get_cookie |
| `get_xianyu_token_sync()` | 约675 | 同步版本的 get_xianyu_token |
| `get_browser()` | 约709 | 便捷函数 |

**注意**: 保留 `close_sync()` 方法，因为它被 `__exit__` 方法使用。

**原因**: 项目已全面转向异步模式，无调用者使用同步 API。

#### 2.4.2 src/search_api.py - PageApiSearchClient 相关代码

删除以下内容（第9-325行）：
- `PageApiSearchError` 类（第9-10行）
- `PageApiResult` 数据类（第13-18行）
- `PageApiSearchClient` 类（第20-325行）

**注意**: `StableSearchRunner` 类（第328-402行）应**保留**，它仍被 `HttpApiSearchClient` 使用。

**原因**: 搜索架构已切换为 HTTP API 方式，`HttpApiSearchClient` 已替代基于浏览器页面执行 JavaScript 的 `PageApiSearchClient`。`PageApiSearchError` 和 `PageApiResult` 仅被 `PageApiSearchClient` 使用，删除后成为死代码。

#### 2.4.3 tests/test_search_api.py - 测试文件更新

需要更新测试文件：
- 第4行：修改 import 语句，删除 `PageApiSearchClient, PageApiSearchError`，保留 `StableSearchRunner`
- 第40-81行：删除 `test_page_api_client_returns_structured_page` 和 `test_page_api_client_rejects_keyword_mismatch` 测试
- 第156-227行：删除 `test_page_api_client_installs_bridge_once`、`test_page_api_client_runs_ready_hook_before_bridge`、`test_page_api_client_wraps_page_errors_as_search_errors` 测试

**注意**: `StableSearchRunner` 相关测试（第94-153行）应保留。

#### 2.4.4 tests/test_page_isolation.py - 更新测试

该测试文件包含两类测试：

**需要删除的测试**（依赖 `_BrowserSearchImpl` 和 `_build_page_api_runner`）：
- 第372-440行区域的测试
- 第480-574行区域的测试
- 第581-703行区域的测试
- 第706-776行区域的测试

**应保留的测试**（测试锁机制和页面隔离，不依赖废弃代码）：
- `test_xianyu_app_uses_distinct_role_locks`
- `test_publish_entries_use_publish_page_and_publish_lock`
- `test_check_cookie_valid_uses_session_page`
- 其他不依赖 `_BrowserSearchImpl` 的测试

#### 2.4.5 tests/test_search_pagination.py - 更新测试

需要更新测试文件：
- 删除 `from src.search_api import PageApiSearchError` 导入
- 删除或更新使用 `PageApiSearchError` 和 `_build_page_api_runner` 的测试用例

#### 2.4.6 src/core.py - _build_page_api_runner() 和 _BrowserSearchImpl

删除以下内容：
- `_build_page_api_runner()` 函数（约第367行）
- `get_search_detail()` 方法（约第308行）- 未被外部调用
- `_BrowserSearchImpl` 类（约第388行）- 仅被 `get_search_detail()` 使用

**原因**: 这些代码相互依赖形成死代码链：`_build_page_api_runner` 构建 `PageApiSearchClient` runner（已废弃），`get_search_detail()` 使用 `_BrowserSearchImpl`，而 `_BrowserSearchImpl` 又依赖已删除的代码。

#### 2.4.7 src/session.py - 重复的 get_token() 方法

删除以下内容：
- 第982-992行的 `get_token()` 方法（重复定义，调用了不存在的方法 `load_cached_token()`，是死代码）

**注意**: 第415行的 `get_token()` 方法是正常工作的版本，不应删除。

**原因**: 第982行的 `get_token()` 调用了不存在的 `load_cached_token()` 方法，这是一个 bug，整个方法是死代码无法正常执行。

## 三、执行计划

### Phase 1: 清理 Git Worktrees
1. 删除 `.worktrees/` 下所有目录
2. 删除对应的 git 分支
3. **验证**: 无需测试验证（物理目录清理）

### Phase 2: 清理空目录
1. 删除 `src/services/` 及所有子目录
2. 删除 `src/api/` 及所有子目录
3. **验证**: 运行 `python -c "from src import XianyuApp"` 验证导入正常

### Phase 3: 清理打包遗留
1. 删除 `UNKNOWN.egg-info/` 目录
2. **验证**: 无需测试验证（打包遗留清理）

### Phase 4: 清理未使用代码
每步执行后立即验证：

#### 4.1 清理 browser.py 同步方法
1. 删除同步方法
2. **验证**: 运行 `pytest tests/test_browser.py -v`

#### 4.2 清理 search_api.py PageApiSearchClient
1. 删除 PageApiSearchClient 相关代码
2. 更新 tests/test_search_api.py
3. **验证**: 运行 `pytest tests/test_search_api.py -v`

#### 4.3 清理 core.py _build_page_api_runner
1. 删除 _build_page_api_runner 函数
2. **验证**: 运行 `pytest tests/test_core.py -v`

#### 4.4 清理 session.py 重复 get_token
1. 删除重复的 get_token 方法
2. **验证**: 运行 `pytest tests/test_session.py -v`

### Phase 5: 全量验证

#### 5.1 单元测试全量运行
```bash
pytest tests/ -v
```

#### 5.2 Python 层端到端测试
验证核心功能流程：
```bash
# 测试搜索功能
python -c "
import asyncio
from src import XianyuApp, AsyncChromeManager

async def test():
    browser = AsyncChromeManager(host='localhost', port=9222)
    app = XianyuApp(browser)
    await app.browser.ensure_running()
    result = await app.check_session()
    print(f'Session valid: {result}')
    # 其他核心功能验证...

asyncio.run(test())
"
```

#### 5.3 MCP 接口层面验证
启动 MCP Server 并验证所有接口可用：
```bash
# 启动 HTTP MCP Server
python mcp_server/http_server.py

# 验证接口调用（通过 REST endpoints）
curl http://localhost:8080/rest/check_session
curl -X POST http://localhost:8080/rest/search -d '{"keyword":"test","rows":5}'
```

## 四、风险评估

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 删除分支可能丢失工作 | 中 | 用户已确认直接删除，分支历史可通过 git reflog 恢复 |
| 删除代码可能影响测试 | 低 | 先运行测试确认，如有测试依赖则调整测试 |
| 删除空目录可能影响未来重构 | 无 | 目录可在需要时重新创建 |

## 五、验收标准

1. `.worktrees/` 目录不存在
2. 相关 git 分支已删除
3. `src/services/` 和 `src/api/` 目录不存在
4. `UNKNOWN.egg-info/` 目录不存在
5. 指定的未使用代码已删除
6. 所有测试通过