# 项目目录结构优化实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use @superpowers:subagent-driven-development (recommended) or @superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重构项目目录结构为按层级聚集(models/services/api)的三层架构,拆分大文件,清理冗余代码,统一命名规范。

**Architecture:** 采用分层架构,数据层(models)负责数据类定义,服务层(services)实现核心业务逻辑,接口层(api)提供统一入口和MCP服务。每个服务模块独立目录,文件控制在200-400行。

**Tech Stack:** Python 3.10+, pytest测试框架, playwright浏览器自动化, MCP协议

---

## 文件结构规划

### 创建的新文件

```
src/models/
├── __init__.py          # 导出所有数据类
├── search.py            # SearchItem, SearchParams, SearchOutcome
├── publish.py           # CopiedItem

src/services/
├── __init__.py          # 导出所有Service类
├── search/
│   ├── __init__.py      # 导出SearchService
│   ├── service.py       # SearchService主类
│   ├── http_client.py   # HTTP API搜索(合并http_search.py)
│   ├── browser_impl.py  # 浏览器搜索实现
│   └── pagination.py    # 分页逻辑(如有)
├── session/
│   ├── __init__.py      # 导出SessionManager
│   ├── session_manager.py   # SessionManager核心
│   ├── login_handler.py     # login函数
│   ├── token_manager.py     # refresh_token, check_cookie_valid
│   └── keepalive_service.py # 保活服务(迁移keepalive.py)
├── publish/
│   ├── __init__.py      # 导出PublishService
│   ├── service.py       # PublishService主类
│   ├── detail_fetcher.py    # get_detail功能
│   └── copier.py        # 商品复制逻辑
├── browser.py           # AsyncChromeManager(迁移)

src/api/
├── __init__.py          # 导出XianyuApp
├── app.py               # XianyuApp统一入口
├── mcp/
│   ├── __init__.py      # 导出MCP Server
│   ├── server.py        # MCP Server(迁移mcp_server/server.py)
│   └── http.py          # HTTP接口(迁移mcp_server/http_server.py)

tests/models/
├── test_search.py       # 测试SearchItem等
├── test_publish.py      # 测试CopiedItem

tests/services/
├── search/
│   ├── test_service.py
│   ├── test_http_client.py  # 对应test_http_search_unit.py
│   └── test_pagination.py   # 对应test_search_pagination.py
├── session/
│   ├── test_manager.py
│   ├── test_login_handler.py
│   ├── test_token_manager.py
│   ├── test_keepalive_service.py  # 对应test_keepalive.py
├── publish/
│   ├── test_service.py
│   ├── test_detail_fetcher.py
│   └── test_copier.py
├── test_browser.py      # 对应test_browser.py

tests/api/
├── test_app.py          # 对应test_http_mcp.py
├── test_http.py         # 对应test_http_server_unit.py
```

### 修改的现有文件

```
src/__init__.py          # 更新导入路径
tests/conftest.py        # 可能需要调整fixtures
README.md                # 更新目录结构说明
```

### 删除的文件

```
src/core.py              # 拆分后删除原文件
src/session.py           # 拆分后删除原文件
src/http_search.py       # 合并到search/http_client.py后删除
src/keepalive.py         # 迁移到session/keepalive_service.py后删除
mcp_server/server.py     # 迁移到api/mcp/server.py后删除
mcp_server/http_server.py # 迁移到api/mcp/http.py后删除
run-mcp-native.sh        # 废弃的旧入口

tests/test_core.py       # 迁移到tests/api/test_app.py等
tests/test_session.py    # 迁移到tests/services/session/
tests/test_http_search_unit.py # 迁移到tests/services/search/test_http_client.py
tests/test_search_pagination.py # 迁移到tests/services/search/test_pagination.py
tests/test_keepalive.py  # 迁移到tests/services/session/test_keepalive_service.py
tests/test_page_isolation.py # 迁移到tests/services/test_browser.py
tests/test_http_mcp.py   # 迁移到tests/api/test_app.py
tests/test_http_server_unit.py # 迁移到tests/api/test_http.py
```

---

## Phase 1: 建立新目录结构骨架

**目标:** 创建新目录结构和__init__.py文件,不移动代码,确保现有测试不受影响。

### Task 1.1: 创建models目录结构

**Files:**
- Create: `src/models/__init__.py`
- Create: `src/models/search.py`
- Create: `src/models/publish.py`

- [ ] **Step 1: 创建models目录和__init__.py**

```bash
mkdir -p src/models
touch src/models/__init__.py
```

- [ ] **Step 2: 创建空的search.py占位文件**

```python
# src/models/search.py - 占位文件
"""
Search models - 数据类定义
"""

# TODO: 从core.py迁移SearchItem, SearchParams, SearchOutcome
```

Write to: `src/models/search.py`

- [ ] **Step 3: 创建空的publish.py占位文件**

```python
# src/models/publish.py - 占位文件
"""
Publish models - 数据类定义
"""

# TODO: 从core.py迁移CopiedItem
```

Write to: `src/models/publish.py`

- [ ] **Step 4: 编写__init__.py导出占位**

```python
"""
Models - 数据模型层
"""

# TODO: 导出数据类
# from .search import SearchItem, SearchParams, SearchOutcome
# from .publish import CopiedItem

__all__ = []
```

Write to: `src/models/__init__.py`

- [ ] **Step 5: 运行测试验证骨架创建不影响现有代码**

```bash
pytest tests/ -v
```

Expected: 所有测试通过(100% pass rate)

- [ ] **Step 6: 提交骨架创建**

```bash
git add src/models/
git commit -m "feat(phase1): create models directory skeleton"
```

---

### Task 1.2: 创建services目录结构

**Files:**
- Create: `src/services/__init__.py`
- Create: `src/services/search/__init__.py`
- Create: `src/services/session/__init__.py`
- Create: `src/services/publish/__init__.py`

- [ ] **Step 1: 创建services目录和__init__.py**

```bash
mkdir -p src/services
touch src/services/__init__.py
```

- [ ] **Step 2: 创建search子目录和__init__.py**

```bash
mkdir -p src/services/search
touch src/services/search/__init__.py
```

- [ ] **Step 3: 创建session子目录和__init__.py**

```bash
mkdir -p src/services/session
touch src/services/session/__init__.py
```

- [ ] **Step 4: 创建publish子目录和__init__.py**

```bash
mkdir -p src/services/publish
touch src/services/publish/__init__.py
```

- [ ] **Step 5: 运行测试验证**

```bash
pytest tests/ -v
```

Expected: 所有测试通过

- [ ] **Step 6: 提交services骨架**

```bash
git add src/services/
git commit -m "feat(phase1): create services directory skeleton"
```

---

### Task 1.3: 创建api目录结构

**Files:**
- Create: `src/api/__init__.py`
- Create: `src/api/mcp/__init__.py`

- [ ] **Step 1: 创建api目录和__init__.py**

```bash
mkdir -p src/api
touch src/api/__init__.py
```

- [ ] **Step 2: 创建mcp子目录和__init__.py**

```bash
mkdir -p src/api/mcp
touch src/api/mcp/__init__.py
```

- [ ] **Step 3: 运行测试验证**

```bash
pytest tests/ -v
```

Expected: 所有测试通过

- [ ] **Step 4: 提交api骨架**

```bash
git add src/api/
git commit -m "feat(phase1): create api directory skeleton"
```

---

### Task 1.4: 创建tests新目录结构

**Files:**
- Create: `tests/models/__init__.py`
- Create: `tests/services/__init__.py`
- Create: `tests/services/search/__init__.py`
- Create: `tests/services/session/__init__.py`
- Create: `tests/services/publish/__init__.py`
- Create: `tests/api/__init__.py`

- [ ] **Step 1: 创建tests/models目录**

```bash
mkdir -p tests/models
touch tests/models/__init__.py
```

- [ ] **Step 2: 创建tests/services目录结构**

```bash
mkdir -p tests/services/search tests/services/session tests/services/publish
touch tests/services/__init__.py
touch tests/services/search/__init__.py
touch tests/services/session/__init__.py
touch tests/services/publish/__init__.py
```

- [ ] **Step 3: 创建tests/api目录**

```bash
mkdir -p tests/api
touch tests/api/__init__.py
```

- [ ] **Step 4: 运行测试验证**

```bash
pytest tests/ -v
```

Expected: 所有测试通过

- [ ] **Step 5: 提交tests骨架**

```bash
git add tests/models tests/services tests/api
git commit -m "feat(phase1): create tests directory skeleton"
```

---

### Task 1.5: Phase 1 完成验证

- [ ] **Step 1: 验证目录结构完整性**

```bash
tree src/ tests/ -L 3
```

Expected: 所有新目录和__init__.py文件都已创建

- [ ] **Step 2: 运行完整测试套件**

```bash
pytest tests/ -v --tb=short
```

Expected: 测试通过率100%,无import错误

- [ ] **Step 3: 验证代码覆盖率基线**

```bash
pytest tests/ --cov=src --cov-report=term-missing
```

Expected: 记录当前覆盖率作为基线

- [ ] **Step 4: 提交Phase 1完成标记**

```bash
git tag phase1-skeleton-complete
git commit --allow-empty -m "feat(phase1): directory skeleton creation complete"
```

---

## Phase 2: 代码迁移与拆分

**目标:** 将代码从core.py和session.py迁移到新目录结构,拆分大文件,调整导入关系,补充单测。

### Task 2.0: 预验证当前代码结构

**Files:**
- None (只读验证)

- [ ] **Step 1: 验证core.py和session.py的实际内容**

```bash
echo "=== core.py 统计 ==="
wc -l src/core.py
grep -c "^class\|^def\|^async def" src/core.py

echo "=== session.py 统计 ==="
wc -l src/session.py
grep -c "^class\|^def\|^async def" src/session.py
```

Expected: 确认文件行数和函数/类数量,为拆分做准备

- [ ] **Step 2: 验证现有测试运行状态**

```bash
pytest tests/ -v --tb=short 2>&1 | head -50
```

Expected: 记录当前测试状态作为迁移基准

- [ ] **Step 3: 提交预验证结果(可选)**

```bash
git add -A
git commit --allow-empty -m "chore(phase2): pre-verification complete"
```

---

### Task 2.1: 提取数据类到models

**Files:**
- Modify: `src/models/search.py`
- Modify: `src/models/publish.py`
- Modify: `src/models/__init__.py`
- Test: `tests/models/test_search.py`
- Test: `tests/models/test_publish.py`

- [ ] **Step 1: 写SearchItem数据类测试**

```python
# tests/models/test_search.py
"""
测试models/search.py数据类
"""
import pytest
from src.models.search import SearchItem, SearchParams, SearchOutcome


def test_search_item_creation():
    """测试SearchItem创建"""
    item = SearchItem(
        item_id="123",
        title="测试商品",
        price="100",
        original_price="150",
        want_cnt=5,
        seller_nick="卖家",
        seller_city="北京",
        image_urls=["http://img.jpg"],
        detail_url="http://detail.url",
        is_free_ship=True
    )
    assert item.item_id == "123"
    assert item.title == "测试商品"
    assert item.is_free_ship is True


def test_search_params_defaults():
    """测试SearchParams默认值"""
    params = SearchParams(keyword="机械键盘")
    assert params.rows == 30
    assert params.min_price is None
    assert params.free_ship is False


def test_search_outcome_creation():
    """测试SearchOutcome创建"""
    outcome = SearchOutcome(
        items=[],
        requested_rows=10,
        returned_rows=0,
        stop_reason="complete",
        stale_pages=0
    )
    assert outcome.stop_reason == "complete"
```

Write to: `tests/models/test_search.py`

- [ ] **Step 2: 运行测试验证失败**

```bash
pytest tests/models/test_search.py -v
```

Expected: FAIL - "cannot import SearchItem from src.models.search"

- [ ] **Step 3: 从core.py提取SearchItem等类到search.py**

以下是完整的SearchItem等数据类实现,可直接使用:

```python
# src/models/search.py
"""
Search models - 数据类定义
"""
from typing import Optional, List
from dataclasses import dataclass


@dataclass
class SearchItem:
    """搜索商品"""
    item_id: str
    title: str
    price: str
    original_price: str
    want_cnt: int
    seller_nick: str
    seller_city: str
    image_urls: List[str]
    detail_url: str
    is_free_ship: bool
    publish_time: Optional[str] = None
    exposure_score: float = 0.0


@dataclass
class SearchParams:
    """搜索参数"""
    keyword: str
    rows: int = 30
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    free_ship: bool = False
    sort_field: str = ""
    sort_order: str = ""


@dataclass
class SearchOutcome:
    """搜索结果"""
    items: List[SearchItem]
    requested_rows: int
    returned_rows: int
    stop_reason: str
    stale_pages: int
    engine_used: str = "browser_fallback"
    fallback_reason: Optional[str] = None
    pages_fetched: int = 0
```

Write to: `src/models/search.py`

- [ ] **Step 4: 运行测试验证通过**

```bash
pytest tests/models/test_search.py -v
```

Expected: PASS - 所有测试通过

- [ ] **Step 5: 写CopiedItem数据类测试**

```python
# tests/models/test_publish.py
"""
测试models/publish.py数据类
"""
import pytest
from src.models.publish import CopiedItem


def test_copied_item_creation():
    """测试CopiedItem创建"""
    item = CopiedItem(
        item_id="456",
        title="测试发布",
        description="描述",
        category="数码",
        category_id=100,
        brand="品牌",
        model="型号",
        min_price=100.0,
        max_price=200.0,
        image_urls=["http://img.jpg"],
        seller_city="上海",
        is_free_ship=True,
        raw_data={}
    )
    assert item.item_id == "456"
    assert item.category_id == 100
```

Write to: `tests/models/test_publish.py`

- [ ] **Step 6: 运行测试验证失败**

```bash
pytest tests/models/test_publish.py -v
```

Expected: FAIL - "cannot import CopiedItem"

- [ ] **Step 7: 从core.py提取CopiedItem到publish.py**

以下是完整的CopiedItem数据类实现,可直接使用:

```python
# src/models/publish.py
"""
Publish models - 数据类定义
"""
from typing import Optional, List, Dict, Any
from dataclasses import dataclass


@dataclass
class CopiedItem:
    """复制的商品数据"""
    item_id: str
    title: str
    description: str
    category: str
    category_id: int
    brand: Optional[str]
    model: Optional[str]
    min_price: float
    max_price: float
    image_urls: List[str]
    seller_city: str
    is_free_ship: bool
    raw_data: Dict[str, Any]
```

Write to: `src/models/publish.py`

- [ ] **Step 8: 运行测试验证通过**

```bash
pytest tests/models/test_publish.py -v
```

Expected: PASS

- [ ] **Step 9: 更新models/__init__.py导出**

```python
"""
Models - 数据模型层
"""

from .search import SearchItem, SearchParams, SearchOutcome
from .publish import CopiedItem

__all__ = [
    "SearchItem",
    "SearchParams",
    "SearchOutcome",
    "CopiedItem",
]
```

Write to: `src/models/__init__.py`

- [ ] **Step 10: 运行所有测试验证models迁移不影响现有代码**

```bash
pytest tests/ -v
```

Expected: 所有测试通过(包括原有tests/下的测试)

- [ ] **Step 11: 提交models迁移**

```bash
git add src/models tests/models
git commit -m "feat(phase2): migrate data classes to models layer"
```

---

### Task 2.2: 拆分session.py到services/session

**Files:**
- Create: `src/services/session/session_manager.py`
- Create: `src/services/session/login_handler.py`
- Create: `src/services/session/token_manager.py`
- Create: `src/services/session/keepalive_service.py`
- Modify: `src/services/session/__init__.py`
- Test: `tests/services/session/test_keepalive_service.py`

**注意:** session.py拆分需要保留原有导入路径兼容性,逐步迁移。

- [ ] **Step 1: 分析session.py的函数和类分布**

```bash
grep -n "^class\|^def\|^async def" src/session.py
```

Expected: 输出所有类和函数定义位置,用于拆分决策

- [ ] **Step 2: 迁移keepalive.py到keepalive_service.py**

由于keepalive.py已是独立文件(95行),直接复制迁移。

```bash
cp src/keepalive.py src/services/session/keepalive_service.py
```

- [ ] **Step 3: 调整keepalive_service.py导入路径**

修改导入从相对导入改为services内部导入。

```python
# src/services/session/keepalive_service.py
"""
Cookie保活服务
"""
# 修改导入
try:
    from ..browser import AsyncChromeManager
    from ...settings import AppSettings, load_settings
except ImportError:
    from src.services.browser import AsyncChromeManager
    from src.settings import AppSettings, load_settings
```

Edit: `src/services/session/keepalive_service.py` imports section

- [ ] **Step 4: 更新session/__init__.py导出keepalive**

```python
"""
Session services - 会话管理
"""

from .keepalive_service import CookieKeepaliveService

__all__ = [
    "CookieKeepaliveService",
]
```

Write to: `src/services/session/__init__.py`

- [ ] **Step 5: 复制测试文件到新位置**

```bash
cp tests/test_keepalive.py tests/services/session/test_keepalive_service.py
```

- [ ] **Step 6: 调整测试导入路径**

使用Edit工具修改tests/services/session/test_keepalive_service.py的导入:

```python
# 将 from src.keepalive import 改为
from src.services.session.keepalive_service import CookieKeepaliveService
```

- [ ] **Step 7: 运行测试验证keepalive迁移**

```bash
pytest tests/services/session/test_keepalive_service.py -v
```

Expected: 测试通过

- [ ] **Step 8: 提交keepalive迁移**

```bash
git add src/services/session/keepalive_service.py
git add tests/services/session/test_keepalive_service.py
git add src/services/session/__init__.py
git commit -m "feat(phase2): migrate keepalive to services/session"
```

---

### Task 2.3: 拆分core.py搜索功能到services/search

**Files:**
- Create: `src/services/search/http_client.py` (合并http_search.py)
- Create: `src/services/search/browser_impl.py`
- Create: `src/services/search/service.py`
- Modify: `src/services/search/__init__.py`
- Test: `tests/services/search/test_http_client.py`

**注意:** 搜索功能拆分较复杂,需要仔细处理依赖关系。

- [ ] **Step 1: 迁移http_search.py到http_client.py**

```bash
cp src/http_search.py src/services/search/http_client.py
```

- [ ] **Step 2: 调整http_client.py导入路径**

修改HttpApiSearchClient类的导入。

```python
# src/services/search/http_client.py
"""
HTTP API搜索客户端
"""
# 修改导入
try:
    from ...session import SessionManager  # Phase 2拆分session.py后调整
    from ...browser import AsyncChromeManager
    from ...models import SearchItem
except ImportError:
    # 临时兼容导入(Phase 3清理时移除)
    from src.session import SessionManager
    from src.browser import AsyncChromeManager
    from src.models import SearchItem
```

Edit imports section in `src/services/search/http_client.py`

- [ ] **Step 3: 迁移test_http_search_unit.py**

```bash
cp tests/test_http_search_unit.py tests/services/search/test_http_client.py
```

- [ ] **Step 4: 调整测试导入路径**

```python
# tests/services/search/test_http_client.py
"""
测试HTTP API搜索客户端
"""
# 修改导入
from src.services.search.http_client import HttpApiSearchClient
```

Edit imports in `tests/services/search/test_http_client.py`

- [ ] **Step 5: 运行测试验证http_client迁移**

```bash
pytest tests/services/search/test_http_client.py -v
```

Expected: 测试通过(可能需要调整部分mock)

- [ ] **Step 6: 提交http_client迁移**

```bash
git add src/services/search/http_client.py
git add tests/services/search/test_http_client.py
git commit -m "feat(phase2): migrate http_search to services/search/http_client"
```

---

### Task 2.4: 创建SearchService主类

**Files:**
- Create: `src/services/search/service.py`
- Modify: `src/services/search/__init__.py`
- Test: `tests/services/search/test_service.py`

- [ ] **Step 1: 写SearchService初始化测试**

```python
# tests/services/search/test_service.py
"""
测试SearchService主类
"""
import pytest
from unittest.mock import Mock, AsyncMock
from src.services.search.service import SearchService


@pytest.mark.asyncio
async def test_search_service_init():
    """测试SearchService初始化"""
    mock_session = Mock()
    service = SearchService(session_manager=mock_session)
    assert service.session_manager == mock_session
    assert service.http_client is not None
```

Write to: `tests/services/search/test_service.py`

- [ ] **Step 2: 运行测试验证失败**

```bash
pytest tests/services/search/test_service.py -v
```

Expected: FAIL - "SearchService not defined"

- [ ] **Step 3: 创建SearchService骨架类**

以下是SearchService的初始骨架实现,可直接使用:

```python
# src/services/search/service.py
"""
SearchService - 搜索服务主类
"""
import logging
from typing import Optional
from .http_client import HttpApiSearchClient
from ...models import SearchParams, SearchOutcome, SearchItem

logger = logging.getLogger(__name__)


class SearchService:
    """搜索服务"""

    def __init__(self, session_manager=None, browser_manager=None):
        self.session_manager = session_manager
        self.browser_manager = browser_manager
        self.http_client = HttpApiSearchClient()

    async def search(self, params: SearchParams) -> SearchOutcome:
        """
        执行搜索

        Args:
            params: 搜索参数

        Returns:
            SearchOutcome: 搜索结果
        """
        raise NotImplementedError("search方法将在后续步骤实现")
```

Write to: `src/services/search/service.py`

- [ ] **Step 4: 运行测试验证通过**

```bash
pytest tests/services/search/test_service.py::test_search_service_init -v
```

Expected: PASS

- [ ] **Step 5: 写search方法测试**

在tests/services/search/test_service.py添加search方法测试:

```python
@pytest.mark.asyncio
async def test_search_service_search_basic():
    """测试SearchService search方法基本功能"""
    mock_session = Mock()
    mock_browser = AsyncMock()
    service = SearchService(session_manager=mock_session, browser_manager=mock_browser)

    params = SearchParams(keyword="测试关键词", rows=10)
    result = await service.search(params)
    assert isinstance(result, SearchOutcome)
    assert result.requested_rows == 10
```

- [ ] **Step 6: 实现search方法**

从core.py迁移search方法的核心逻辑。由于core.py的search方法较复杂(约200-300行),拆分为多个子步骤:

- [ ] **Step 6a: 实现HTTP API搜索优先逻辑**

```python
# 在SearchService.search方法中添加
async def search(self, params: SearchParams) -> SearchOutcome:
    # 优先使用HTTP API
    try:
        result = await self.http_client.search(params)
        if result.items:
            return result
    except Exception as e:
        logger.warning(f"HTTP API搜索失败: {e}, 回退到浏览器搜索")

    # 浏览器搜索实现将在Step 6c添加
    raise NotImplementedError("浏览器搜索待实现")
```

- [ ] **Step 6b: 运行测试验证HTTP搜索**

```bash
pytest tests/services/search/test_service.py -v
```

Expected: 部分测试通过(HTTP API相关)

- [ ] **Step 6c: 实现浏览器回退搜索**

添加浏览器搜索逻辑到search方法中(需要导入browser_impl模块)。

- [ ] **Step 7: 运行完整测试验证**

Expected: PASS

- [ ] **Step 6: 完善SearchService实现**

从core.py完整迁移search方法逻辑,包括:
- HTTP API优先搜索
- 浏览器回退搜索
- 分页处理
- 结果去重

Read `src/core.py` lines 200-600 and extract full search logic.

- [ ] **Step 7: 运行测试验证完整功能**

```bash
pytest tests/services/search/test_service.py -v
```

Expected: 所有测试通过

- [ ] **Step 8: 提交SearchService**

```bash
git add src/services/search/service.py tests/services/search/test_service.py
git commit -m "feat(phase2): create SearchService with search logic"
```

---

### Task 2.5: 迁移browser.py到services

**Files:**
- Create: `src/services/browser.py`
- Modify: 保持src/browser.py暂时不变(兼容性)
- Test: 迁移test_browser.py

- [ ] **Step 1: 复制browser.py到services**

```bash
cp src/browser.py src/services/browser.py
```

- [ ] **Step 2: 调整services/browser.py导入**

保持相对导入兼容性。

- [ ] **Step 3: 迁移test_browser.py**

```bash
cp tests/test_browser.py tests/services/test_browser.py
```

- [ ] **Step 4: 调整测试导入路径**

```python
# tests/services/test_browser.py
from src.services.browser import AsyncChromeManager
```

- [ ] **Step 5: 运行测试验证**

```bash
pytest tests/services/test_browser.py -v
```

Expected: 测试通过

- [ ] **Step 6: 提交browser迁移**

```bash
git add src/services/browser.py tests/services/test_browser.py
git commit -m "feat(phase2): migrate browser to services layer"
```

---

### Task 2.6: 创建XianyuApp统一入口

**Files:**
- Create: `src/api/app.py`
- Modify: `src/api/__init__.py`
- Test: `tests/api/test_app.py`

- [ ] **Step 1: 写XianyuApp测试**

从test_http_mcp.py和test_core.py迁移相关测试。

```python
# tests/api/test_app.py
"""
测试XianyuApp统一入口
"""
import pytest
from src.api.app import XianyuApp


@pytest.mark.asyncio
async def test_xianyu_app_init():
    """测试XianyuApp初始化"""
    app = XianyuApp()
    assert app is not None
    assert app.browser_manager is not None
    assert app.session_manager is not None
```

Write to: `tests/api/test_app.py`

- [ ] **Step 2: 运行测试验证失败**

```bash
pytest tests/api/test_app.py -v
```

Expected: FAIL - "XianyuApp not defined"

- [ ] **Step 3: 创建XianyuApp骨架类**

以下是XianyuApp的初始骨架实现,可直接使用:

```python
# src/api/app.py
"""
XianyuApp - 统一入口
"""
from ..models import SearchItem, SearchParams, SearchOutcome, CopiedItem
from ..services.search import SearchService
from ..services.session import SessionManager, CookieKeepaliveService
from ..services.browser import AsyncChromeManager


class XianyuApp:
    """闲鱼操作统一入口"""

    def __init__(self):
        self.browser_manager = AsyncChromeManager()
        self.session_manager = SessionManager(self.browser_manager)
        self.search_service = SearchService(self.session_manager, self.browser_manager)

    async def login(self):
        """登录"""
        return await self.session_manager.login()

    async def search(self, keyword: str, rows: int = 30, **kwargs):
        """搜索"""
        params = SearchParams(keyword=keyword, rows=rows, **kwargs)
        return await self.search_service.search(params)
```

Write to: `src/api/app.py`

- [ ] **Step 4: 运行测试验证通过**

```bash
pytest tests/api/test_app.py -v
```

Expected: PASS

- [ ] **Step 5: 完善XianyuApp实现**

从core.py完整迁移所有方法。

- [ ] **Step 6: 运行完整测试套件**

```bash
pytest tests/ -v
```

Expected: 所有测试通过(包括原有test_core.py暂时保留)

- [ ] **Step 7: 提交XianyuApp**

```bash
git add src/api/app.py tests/api/test_app.py
git commit -m "feat(phase2): create XianyuApp unified entry point"
```

---

### Task 2.7: 更新src/__init__.py导入路径

**Files:**
- Modify: `src/__init__.py`

- [ ] **Step 1: 读取当前src/__init__.py内容**

```bash
cat src/__init__.py
```

- [ ] **Step 2: 更新导入路径指向新结构**

```python
"""
闲鱼助手 - 三鱼店铺自动化工作流
"""

# 从新结构导入
from .models import SearchItem, SearchParams, SearchOutcome, CopiedItem
from .services.browser import AsyncChromeManager, ChromeManager
from .services.session import SessionManager, CookieKeepaliveService
from .api.app import XianyuApp

# 便捷函数(临时保持兼容,Phase 3清理时移除)
from .session import login, refresh_token, check_cookie_valid
from .core import search, publish, get_detail

__version__ = "2.1.0"
__all__ = [
    # 核心类
    "AsyncChromeManager",
    "ChromeManager",
    "SessionManager",
    "CookieKeepaliveService",
    "XianyuApp",
    # 数据类
    "SearchItem",
    "SearchParams",
    "SearchOutcome",
    "CopiedItem",
    # 便捷函数
    "login",
    "refresh_token",
    "check_cookie_valid",
    "search",
    "publish",
    "get_detail",
]
```

Write to: `src/__init__.py`

- [ ] **Step 3: 运行测试验证导入兼容性**

```bash
pytest tests/ -v
```

Expected: 所有测试通过,导入无错误

- [ ] **Step 4: 提交导入路径更新**

```bash
git add src/__init__.py
git commit -m "feat(phase2): update src/__init__.py imports to new structure"
```

---

### Task 2.8: Phase 2 完成验证

- [ ] **Step 1: 运行完整测试套件并检查覆盖率**

```bash
pytest tests/ -v --cov=src --cov-report=term-missing
```

Expected: 测试通过率100%,覆盖率不低于Phase 1基线

- [ ] **Step 2: 验证循环依赖(使用pydeps或Python导入)**

方案A - 使用pydeps工具:
```bash
pip install pydeps 2>/dev/null || true
pydeps src --no-output --show-cycles 2>/dev/null || echo "跳过pydeps检查"
```

方案B - 使用Python导入检查:
```bash
python -c "
import sys
sys.path.insert(0, 'src')
from api.app import XianyuApp
from models.search import SearchItem
from services.search.service import SearchService
print('导入检查通过,无循环依赖')
"
```

Expected: 无循环依赖错误

- [ ] **Step 3: 验证核心功能可调用**

```bash
python -c "
from src import XianyuApp, SearchItem, SessionManager
app = XianyuApp()
print('XianyuApp创建成功')
print('核心功能验证通过')
"
```

Expected: 输出"XianyuApp创建成功"和"核心功能验证通过"

- [ ] **Step 4: 提交Phase 2完成标记**

```bash
git tag phase2-migration-complete
git commit --allow-empty -m "feat(phase2): code migration and splitting complete"
```

---

## Phase 3: 清理未使用代码

**目标:** 通过子代理排查未使用代码,删除确认无用的文件和函数,验证测试覆盖率不下降。

### Task 3.1: 子代理排查src目录

**Files:**
- Output: `cleanup-src-report.json`

- [ ] **Step 1: 派发src排查子代理** @superpowers:subagent-driven-development

使用Agent工具派发Explore子代理,任务:
- 扫描src目录所有函数和类
- 检查每个定义是否被其他文件import或调用
- 输出JSON格式的未使用函数/类清单

Prompt: "排查src目录未使用的函数和类,输出JSON格式报告,包含:文件路径、函数名、未使用原因、建议操作(删除/保留)"

- [ ] **Step 2: 收集src排查报告**

子代理完成后,获取JSON报告。

Expected: JSON格式清单,格式如:
```json
{
  "file": "src/xxx.py",
  "unused": [
    {"name": "old_func", "reason": "无导入引用", "action": "delete"}
  ]
}
```

- [ ] **Step 3: 验证JSON格式正确**

```bash
python -c "import json; data=json.load(open('cleanup-src-report.json')); print('JSON格式验证通过')"
```

Expected: 输出"JSON格式验证通过"

- [ ] **Step 4: 分析src排查结果**

主代理分析JSON报告,识别:
- 确认可删除的函数
- 需保留的工具函数
- 待确认的边界情况

- [ ] **Step 5: 提交排查报告**

```bash
git add cleanup-src-report.json
git commit -m "docs(phase3): src unused code investigation report"
```

---

### Task 3.2: 子代理排查tests目录

**Files:**
- Output: `cleanup-tests-report.json`

- [ ] **Step 1: 派发tests排查子代理** @superpowers:subagent-driven-development

使用Agent工具派发Explore子代理,任务:
- 扫描tests目录所有测试文件
- 检查是否有测试已废弃功能的测试
- 检查是否有重复测试
- 检查是否有临时调试测试
- 输出JSON格式报告

Prompt: "排查tests目录未使用的测试文件,输出JSON格式报告,识别:测试废弃功能的、重复测试、临时调试测试"

- [ ] **Step 2: 收集tests排查报告**

Expected: JSON格式清单

- [ ] **Step 3: 验证JSON格式正确**

```bash
python -c "import json; data=json.load(open('cleanup-tests-report.json')); print('JSON格式验证通过')"
```

Expected: 输出"JSON格式验证通过"

- [ ] **Step 4: 分析tests排查结果**

识别可删除的测试文件。

- [ ] **Step 5: 提交排查报告**

```bash
git add cleanup-tests-report.json
git commit -m "docs(phase3): tests unused investigation report"
```

---

### Task 3.3: 子代理排查docs目录

**Files:**
- Output: `cleanup-docs-report.json`

- [ ] **Step 1: 派发docs排查子代理**

使用Agent工具派发Explore子代理,任务:
- 扫描docs/superpowers/specs目录所有设计文档
- 对照已实现功能,识别过时文档
- 输出JSON格式报告,标记(保留/归档)

Prompt: "排查docs目录过时的设计文档,对照README功能清单,输出JSON格式报告,标记每篇spec的action(保留/归档)"

- [ ] **Step 2: 收集docs排查报告**

Expected: JSON格式清单

- [ ] **Step 3: 分析docs排查结果**

识别需要归档的spec文档。

- [ ] **Step 4: 提交排查报告**

```bash
git add cleanup-docs-report.json
git commit -m "docs(phase3): docs cleanup investigation report"
```

---

### Task 3.4: 执行代码清理

**Files:**
- Delete: 根据排查报告确认删除的文件
- Modify: 清理文件内未使用的函数

**注意:** 清理前确保git状态干净,可随时回滚。

- [ ] **Step 1: 创建清理分支(保险措施)**

```bash
git checkout -b cleanup-phase
```

- [ ] **Step 2: 删除确认无用的源代码文件**

根据cleanup-src-report.json,删除确认无用的函数。

示例(假设):
```bash
# 如果排查发现run-mcp-native.sh无用
rm run-mcp-native.sh
```

- [ ] **Step 3: 删除确认无用的测试文件**

根据cleanup-tests-report.json,删除无用测试。

- [ ] **Step 4: 归档过时的设计文档**

根据cleanup-docs-report.json,归档文档。

```bash
mkdir -p docs/superpowers/archive
# 移动过时spec到archive
mv docs/superpowers/specs/过时spec.md docs/superpowers/archive/
```

- [ ] **Step 5: 运行测试验证清理不影响核心功能**

```bash
pytest tests/ -v --cov=src
```

Expected: 测试通过率100%,覆盖率不低于Phase 2

- [ ] **Step 6: 合并清理分支**

```bash
git checkout master
git merge cleanup-phase
git branch -d cleanup-phase
```

- [ ] **Step 7: 提交清理完成**

```bash
git add -A
git commit -m "feat(phase3): cleanup unused code based on investigation reports"
```

---

### Task 3.5: 删除已拆分的原始大文件

**Files:**
- Delete: `src/core.py` (已拆分到services和api)
- Delete: `src/session.py` (已拆分到services/session)
- Delete: `src/http_search.py` (已合并到services/search/http_client.py)
- Delete: `src/keepalive.py` (已迁移到services/session/keepalive_service.py)
- Delete: `mcp_server/server.py` (已迁移到api/mcp/server.py)
- Delete: `mcp_server/http_server.py` (已迁移到api/mcp/http.py)

**前提:** Phase 2验证通过,所有功能已迁移到新结构。

- [ ] **Step 1: 验证导入路径已完全切换**

```bash
grep -r "from.*core import\|from.*session import\|from.*http_search import" src/ tests/
```

Expected: 无结果(所有导入已切换到新结构)

- [ ] **Step 2: 删除src/core.py**

```bash
rm src/core.py
```

- [ ] **Step 3: 删除src/session.py(如果拆分完成)**

```bash
rm src/session.py
```

- [ ] **Step 4: 删除其他已迁移的原始文件**

```bash
rm src/http_search.py
rm src/keepalive.py
rm -rf mcp_server/
```

- [ ] **Step 5: 运行测试验证删除后功能正常**

```bash
pytest tests/ -v
```

Expected: 所有测试通过

- [ ] **Step 6: 提交原始文件删除**

```bash
git add -A
git commit -m "feat(phase3): remove original files after migration complete"
```

---

### Task 3.6: Phase 3 完成验证

- [ ] **Step 1: 验证清理比例**

统计删除代码量占比。

```bash
git diff phase2-migration-complete phase3-cleanup-complete --stat | grep "files changed"
```

Expected: 删除代码量不超过总代码量的15%

- [ ] **Step 2: 运行完整测试套件**

```bash
pytest tests/ -v --cov=src --cov-report=html
```

Expected: 测试通过率100%,覆盖率不低于Phase 2

- [ ] **Step 3: 验证导入关系无断裂**

```python
# 验证脚本
import src
assert hasattr(src, 'XianyuApp')
assert hasattr(src, 'SearchItem')
print("所有导入正常")
```

- [ ] **Step 4: 提交Phase 3完成标记**

```bash
git tag phase3-cleanup-complete
git commit --allow-empty -m "feat(phase3): unused code cleanup complete"
```

---

## Phase 4: 统一命名与文档更新

**目标:** 统一文件命名符合PEP8规范,重命名测试文件,更新README文档。

### Task 4.1: 统一源代码文件命名

**Files:**
- Rename: 所有不符合PEP8规范的文件名

- [ ] **Step 1: 检查需要重命名的源代码文件**

对照设计文档2.4节的命名规范表。

- [ ] **Step 2: 使用git mv重命名文件**

保留git历史。

```bash
# 如果需要重命名(假设示例)
git mv src/old_name.py src/new_name.py
```

- [ ] **Step 3: 更新相关导入路径**

搜索并更新所有引用重命名文件的导入。

```bash
grep -r "from.*old_name" src/ tests/
# 手动更新导入路径
```

- [ ] **Step 4: 运行测试验证重命名**

```bash
pytest tests/ -v
```

Expected: 所有测试通过

- [ ] **Step 5: 提交命名统一**

```bash
git add -A
git commit -m "feat(phase4): unify source file naming to PEP8 standard"
```

---

### Task 4.2: 重命名测试文件对应新结构

**Files:**
- Rename: 测试文件匹配被测模块

- [ ] **Step 1: 映射测试文件到新结构**

根据设计文档测试目录重组表:
- test_http_mcp.py → test_app.py (已迁移)
- test_http_server_unit.py → test_http.py (已迁移)
- test_page_isolation.py → test_browser.py (已迁移)
- test_search_pagination.py → test_pagination.py (已迁移)
- test_http_search_unit.py → test_http_client.py (已迁移)

- [ ] **Step 2: 删除旧测试文件(如果已迁移)**

```bash
# 删除已迁移的旧测试文件
rm tests/test_http_mcp.py  # 如果已迁移到tests/api/test_app.py
rm tests/test_http_server_unit.py  # 如果已迁移到tests/api/test_http.py
# ... 其他已迁移的测试
```

- [ ] **Step 3: 运行测试验证测试文件重组**

```bash
pytest tests/ -v --collect-only
```

Expected: 测试收集成功,无文件找不到错误

- [ ] **Step 4: 提交测试文件重组**

```bash
git add -A
git commit -m "feat(phase4): reorganize test files to match new structure"
```

---

### Task 4.3: 更新README.md文档

**Files:**
- Modify: `README.md`

- [ ] **Step 1: 读取当前README.md**

```bash
cat README.md
```

- [ ] **Step 2: 更新目录结构说明**

添加新目录结构章节。

```markdown
## 目录结构

项目采用分层架构组织代码:

```
src/
├── models/          # 数据模型层
│   ├── search.py    # SearchItem, SearchParams, SearchOutcome
│   └── publish.py   # CopiedItem
│
├── services/        # 业务服务层
│   ├── search/      # 搜索服务
│   ├── session/     # 会话管理
│   ├── publish/     # 发布服务
│   └── browser.py   # 浏览器管理
│
├── api/             # 接口层
│   ├── app.py       # XianyuApp统一入口
│   └── mcp/         # MCP服务接口
│
├── utils/           # 工具层
└── settings.py      # 配置管理
```
```

Edit: `README.md` 目录结构章节

- [ ] **Step 3: 更新导入示例**

```markdown
## 开发参考

使用新目录结构的导入方式:

```python
from src import XianyuApp, SearchItem, SearchParams
from src.services.search import SearchService
from src.services.session import SessionManager

async with XianyuApp() as app:
    items = await app.search("机械键盘", rows=10)
```

文件路径:
- 统一入口: `src/api/app.py`
- 搜索服务: `src/services/search/service.py`
- 会话管理: `src/services/session/session_manager.py`
```

Edit: `README.md` 开发参考章节

- [ ] **Step 4: 移除废弃功能说明**

删除run-mcp-native.sh等废弃入口的说明。

- [ ] **Step 5: 提交README更新**

```bash
git add README.md
git commit -m "docs(phase4): update README to reflect new directory structure"
```

---

### Task 4.4: 运行ruff lint检查命名规范

**Files:**
- All Python files

- [ ] **Step 1: 运行ruff lint检查**

```bash
ruff check src/ tests/
```

Expected: 无命名规范相关错误

- [ ] **Step 2: 修复lint发现的问题**

如果有命名不规范,根据ruff提示修复。

- [ ] **Step 3: 提交lint修复**

```bash
git add -A
git commit -m "fix(phase4): resolve ruff lint naming issues"
```

---

### Task 4.5: Phase 4 最终验证

- [ ] **Step 1: 运行完整测试套件**

```bash
pytest tests/ -v --cov=src --cov-report=html
```

Expected: 测试通过率100%,覆盖率不低于Phase 3

- [ ] **Step 2: 验证目录结构完整性**

```bash
tree src/ tests/ -L 3
```

Expected: 目录结构符合设计文档

- [ ] **Step 3: 验证命名规范符合率**

```bash
ruff check src/ tests/ --select N
```

Expected: 命名规范符合率100%

- [ ] **Step 4: 验证README准确性**

对照实际目录结构检查README描述。

- [ ] **Step 5: 提交Phase 4完成标记**

```bash
git tag phase4-naming-complete
git commit --allow-empty -m "feat(phase4): naming standardization complete"
```

---

### Task 4.6: 最终整合提交

- [ ] **Step 1: 合并到master分支**

如果在整个过程中使用了分支,合并回master。

```bash
git checkout master
git merge refactor-structure
```

- [ ] **Step 2: 创建最终版本标签**

```bash
git tag v2.1.0-structure-optimized
```

- [ ] **Step 3: 推送到远程仓库(如果需要)**

```bash
git push origin master --tags
```

- [ ] **Step 4: 清理临时文件**

删除排查报告等临时文件。

```bash
rm cleanup-*.json
git add -A
git commit -m "chore: cleanup temporary investigation reports"
```

---

## 附录: 验证清单

### 测试覆盖率基线记录

Phase 1完成后记录基线覆盖率,后续阶段不低于此基线。

```bash
pytest tests/ --cov=src --cov-report=term | grep "TOTAL"
```

### 循环依赖检查

使用pydeps工具验证:

```bash
pip install pydeps
pydeps src --no-output --show-cycles
```

预期结果: 无循环依赖。

### 导入兼容性检查

验证旧导入路径是否仍可工作(过渡期):

```python
# 测试脚本
try:
    from src.core import XianyuApp  # 旧导入
    print("旧导入兼容性OK")
except ImportError:
    from src.api.app import XianyuApp  # 新导入
    print("新导入OK")
```

---

## 执行时间预估

- Phase 1 (骨架创建): 30分钟
- Phase 2 (代码迁移): 2-3小时(取决于core.py/session.py复杂度)
- Phase 3 (清理): 1小时(子代理排查+清理执行)
- Phase 4 (命名与文档): 30分钟

**总计:** 约4-5小时工作量

---

## 回滚策略

如果某阶段验证失败:

- **Phase 1失败**: 删除新建目录,保持现状
- **Phase 2失败**: 恢复原始文件,删除新模块
- **Phase 3失败**: 从git恢复删除的文件
- **Phase 4失败**: 重命名回原始文件名

每个阶段都有git tag标记,可精确回滚到任意阶段起点。