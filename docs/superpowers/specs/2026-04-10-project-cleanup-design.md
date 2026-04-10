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

**原因**: 项目已全面转向异步模式，无调用者使用同步 API。

#### 2.4.2 src/search_api.py - PageApiSearchClient 类

删除 `PageApiSearchClient` 类（约第20-166行）。

**原因**: 搜索架构已切换为 HTTP API 方式，`HttpApiSearchClient` 已替代基于浏览器页面执行 JavaScript 的 `PageApiSearchClient`。

#### 2.4.3 src/core.py - _build_page_api_runner() 函数

删除 `_build_page_api_runner()` 函数（约第367行）。

**原因**: 仅用于构建 `PageApiSearchClient` runner，该类已废弃。

#### 2.4.4 src/session.py - 重复的 get_token() 方法

删除以下内容：
- 第415行的 `get_token()` 方法（第一个定义）
- `load_cached_token()` 方法（约第455行）
- 第982行的 `get_token()` 方法（第二个定义，调用 load_cached_token）

**原因**: `get_token()` 有两个重复定义，代码逻辑混乱。当前使用的是其他方式获取 token。

## 三、执行计划

### Phase 1: 清理 Git Worktrees
1. 删除 `.worktrees/` 下所有目录
2. 删除对应的 git 分支

### Phase 2: 清理空目录
1. 删除 `src/services/` 及所有子目录
2. 删除 `src/api/` 及所有子目录

### Phase 3: 清理打包遗留
1. 删除 `UNKNOWN.egg-info/` 目录

### Phase 4: 清理未使用代码
1. 编辑 `src/browser.py`，删除同步方法
2. 编辑 `src/search_api.py`，删除 `PageApiSearchClient` 类
3. 编辑 `src/core.py`，删除 `_build_page_api_runner()` 函数
4. 编辑 `src/session.py`，删除重复的 `get_token()` 相关方法

### Phase 5: 验证
1. 运行测试确保功能正常
2. 检查导入是否正确

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