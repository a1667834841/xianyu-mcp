# 项目目录结构优化设计文档

**日期**: 2026-04-09
**状态**: 待审核
**目标**: 优化项目目录结构,提高代码可维护性和组织清晰度

---

## 一、背景与目标

### 当前问题

项目存在以下代码组织问题:

1. **目录结构分散** - 功能相关代码分散在不同目录,缺乏清晰的层次划分
2. **存在冗余代码** - 包含未使用的代码和测试,增加维护负担
3. **核心文件过大** - `core.py` (1532行) 和 `session.py` (1063行) 过大,难以维护
4. **命名不规范** - 文件命名风格不一致,缺乏统一标准

### 优化目标

按优先级排序:

1. **目录结构优化** - 按层级聚集(models/services/api),让代码更加聚焦和模块化
2. **删除冗余代码** - 激进清理所有未使用的代码和测试
3. **大文件拆分** - 按功能拆分,每个文件负责一个独立功能
4. **命名规范化** - 统一文件命名风格,遵循Python PEP8规范

---

## 二、设计方案

### 2.1 新目录结构设计

基于"按层级聚集"原则,设计如下目录结构:

```
src/
├── models/              # 数据模型层
│   ├── __init__.py
│   ├── search.py       # SearchItem, SearchParams, SearchOutcome
│   ├── publish.py      # CopiedItem
│   └── session.py      # Session相关数据类(如有)
│
├── services/           # 业务服务层
│   ├── __init__.py
│   ├── search/         # 搜索服务模块
│   │   ├── __init__.py
│   │   ├── service.py        # 搜索主服务(SearchService类)
│   │   ├── http_client.py    # HTTP API搜索实现
│   │   ├── browser_impl.py   # 浏览器搜索实现
│   │   └── pagination.py     # 分页逻辑(如有)
│   │
│   ├── session/        # 会话服务模块
│   │   ├── __init__.py
│   │   ├── manager.py         # SessionManager核心
│   │   ├── login.py           # 登录逻辑(login函数)
│   │   ├── token.py           # Token刷新逻辑(refresh_token)
│   │   └── keepalive.py       # 保活服务
│   │
│   ├── publish/        # 发布服务模块
│   │   ├── __init__.py
│   │   ├── service.py         # 发布主服务(PublishService类)
│   │   ├── detail_fetcher.py  # 商品详情获取(get_detail)
│   │   └── copier.py          # 商品复制逻辑
│   │
│   └── browser.py      # 浏览器管理服务
│
├── api/                # 接口层
│   ├── __init__.py
│   ├── app.py          # XianyuApp统一入口
│   └── mcp/            # MCP服务接口
│       ├── __init__.py
│       ├── server.py   # MCP Server
│       └── http.py     # HTTP接口
│
├── utils/              # 工具层(保持现有)
│   ├── __init__.py
│   └── r2_uploader.py
│
└── settings.py         # 配置管理(保持现有)
```

**关键变化:**

- `core.py` 拆分到多个service模块 + 保留入口在 `api/app.py`
- `session.py` 拆分到 `services/session/` 目录下的4个文件
- 数据类统一提取到 `models` 目录
- MCP Server从独立 `mcp_server` 目录移入 `api/mcp/`,保持接口层统一

---

### 2.2 未使用代码清理策略

基于"激进清理"原则,执行以下清理:

**清理范围:**

1. **已废弃的旧入口文件**
   - `run-mcp-native.sh` - 旧版本地调试入口(README已标注"不推荐")

2. **未使用的测试文件**
   - 需通过子代理排查:
     - 测试已废弃功能的测试文件
     - 重复测试相同功能的测试文件
     - 临时调试性质的测试文件

3. **未使用的工具代码**
   - 通过子代理排查每个文件的每个函数是否被引用
   - 特别关注:
     - `utils/r2_uploader.py` - 是否所有功能都在使用
     - `browser.py` 中是否有未使用的浏览器操作方法
     - `settings.py` 中是否有未使用的配置项

4. **设计文档处理**
   - **保留**: `specs/` 目录下已实现功能的设计文档
   - **归档**: 移动到 `docs/archive/` 目录(未实现或不计划实现的spec)

**清理流程:**

- **阶段1**: 子代理排查 - 3个子代理并行排查(src/tests/docs)
- **阶段2**: 生成清理清单 - 主代理汇总分析结果
- **阶段3**: 执行清理 - 删除确认无用的文件/函数
- **阶段4**: 验证清理 - 运行测试确保核心功能不受影响
- **阶段5**: 更新README - 同步更新文档,移除废弃功能说明

**清理验证标准:**

- 核心功能测试必须100%通过
- 导入关系无断裂
- README中列出的所有功能仍可正常使用

---

### 2.3 大文件拆分详细设计

#### core.py (1532行) 拆分方案

**拆分目标:**

- 提取数据类到 `src/models/`
- 搜索功能拆分到 `src/services/search/`
- 发布功能拆分到 `src/services/publish/`
- 保留统一入口在 `src/api/app.py`

**拆分结果分布:**

```
core.py拆分后:
├── models/search.py          (~50行)  - SearchItem, SearchParams, SearchOutcome
├── models/publish.py         (~40行)  - CopiedItem
├── services/search/
│   ├── service.py            (~300行) - SearchService类,搜索主逻辑
│   ├── http_client.py        (~360行) - HTTP API搜索实现(合并http_search.py)
│   └── browser_impl.py       (~200行) - 浏览器搜索实现
├── services/publish/
│   ├── service.py            (~400行) - PublishService类,发布主逻辑
│   ├── detail_fetcher.py     (~150行) - get_detail功能
│   └── copier.py             (~150行) - 商品复制逻辑
└── api/app.py                (~100行) - XianyuApp统一入口
```

**拆分原则:**

- 每个Service文件控制在200-400行
- 保持功能独立性,减少交叉依赖
- XianyuApp作为Facade模式,组合调用各Service

#### session.py (1063行) 拆分方案

**拆分目标:**

- 登录逻辑独立到 `login.py`
- Token刷新逻辑独立到 `token.py`
- 会话管理核心保留在 `manager.py`
- 保活服务从 `keepalive.py` 归入session模块目录

**拆分结果分布:**

```
session.py拆分后:
├── services/session/
│   ├── manager.py            (~500行) - SessionManager核心,cookie管理
│   ├── login.py              (~250行) - login函数,二维码登录流程
│   ├── token.py              (~200行) - refresh_token, check_cookie_valid
│   └── keepalive.py          (~95行)  - 保活服务(迁移进来)
```

**拆分原则:**

- SessionManager保持核心管理职责
- login和token作为独立功能模块
- keepalive从独立文件移入session目录,保持模块完整性

---

### 2.4 文件命名规范化设计

#### 命名规范标准

采用Python PEP8文件命名约定:

- **模块文件**: 小写字母+下划线,如 `search_service.py`
- **类文件**: 模块名与主类名对应,如 `session_manager.py` 对应 `SessionManager`
- **测试文件**: `test_<模块名>.py`,与被测模块对应
- **工具文件**: 功能描述性命名,如 `r2_uploader.py`

#### 需调整的文件命名

```
当前命名                    → 目标命名                   | 问题说明
─────────────────────────────────────────────────────────────────────
src/core.py                 → api/app.py                 | core含义不明确
src/browser.py              → services/browser.py       | browser是服务层
src/http_search.py          → services/search/http_client.py | 更准确描述
src/keepalive.py            → services/session/keepalive.py | 归入session模块

tests/test_http_mcp.py      → tests/api/test_app.py     | 对应被测模块
tests/test_http_server_unit.py → tests/api/test_http.py | 对应http接口
tests/test_page_isolation.py   → tests/services/test_browser.py | 浏览器隔离测试
tests/test_search_pagination.py → tests/services/search/test_pagination.py
tests/test_http_search_unit.py  → tests/services/search/test_http_client.py
```

#### 测试目录重组

```
tests/
├── models/              # 数据模型测试
│   ├── test_search.py
│   └── test_publish.py
│
├── services/            # 服务层测试
│   ├── search/
│   │   ├── test_service.py
│   │   ├── test_http_client.py
│   │   └── test_pagination.py
│   ├── session/
│   │   ├── test_manager.py
│   │   ├── test_login.py
│   │   ├── test_token.py
│   │   └── test_keepalive.py
│   ├── publish/
│   │   ├── test_service.py
│   │   └── test_detail_fetcher.py
│   └── test_browser.py
│
├── api/                 # 接口层测试
│   ├── test_app.py
│   └── test_http.py
│
└── conftest.py          # 测试配置(保持)
```

---

## 三、实施方案

采用**分阶段渐进重构方案A**,共4个阶段,每个阶段包含"补充单测→验证通过→继续"的质量保障流程。

### 阶段1: 建立新目录结构骨架

**任务:**
- 创建新目录结构(models/services/api)
- 创建各目录的 `__init__.py`
- 不移动代码,只建立骨架

**验证:**
- 目录结构符合设计
- `__init__.py` 文件创建完成
- 运行现有测试,确保无影响

### 阶段2: 代码迁移与拆分

**任务:**
- 迁移数据类到 `models/`
- 拆分 `core.py` 到各服务模块
- 拆分 `session.py` 到session子模块
- 迁移browser.py和keepalive.py
- 调整所有导入关系

**验证:**
- 运行测试,补充缺失的单测
- 所有导入关系正确
- 核心功能可正常调用

### 阶段3: 清理未使用代码

**任务:**
- 执行子代理排查(src/tests/docs)
- 删除确认无用的文件和函数
- 归档过时的设计文档
- 调整测试文件以匹配新结构

**验证:**
- 运行完整测试套件
- 测试覆盖率不低于重构前
- 导入关系无断裂

### 阶段4: 统一命名与文档更新

**任务:**
- 统一文件命名(按规范表)
- 重命名测试文件
- 更新README.md
- 更新导入示例和文档路径

**验证:**
- 文件命名符合PEP8规范
- 测试文件与被测模块一一对应
- README文档准确反映新结构

---

## 四、依赖关系设计

### 模块依赖关系

```
api/app.py
  ├── import models.* (数据类)
  ├── import services.search.SearchService
  ├── import services.publish.PublishService
  └── import services.session.SessionManager

services/search/service.py
  ├── import models.search.*
  ├── import services.session.SessionManager
  └── import services.browser.AsyncChromeManager

services/publish/service.py
  ├── import models.publish.*
  ├── import services.session.SessionManager
  └── import services.browser.AsyncChromeManager

services/session/manager.py
  └── import services.browser.AsyncChromeManager
```

### 测试依赖关系

每个测试模块只测试对应的业务模块:
- `tests/models/test_search.py` → 测试 `models/search.py`
- `tests/services/search/test_service.py` → 测试 `services/search/service.py`
- `tests/api/test_app.py` → 测试 `api/app.py`

---

## 五、风险与对策

### 风险1: 导入关系断裂

**对策:**
- 使用Python导入检查工具验证
- 每阶段运行测试验证
- 保留原导入路径一段时间,逐步迁移

### 集险2: 测试覆盖不足

**对策:**
- 每阶段强制补充单测
- 测试覆盖率不低于重构前
- 使用pytest-cov监控覆盖率

### 风险3: 功能丢失

**对策:**
- 激进清理前确认功能已废弃
- README功能清单作为验证基准
- 运行完整测试套件验证

---

## 六、预期成果

### 代码组织成果

- 目录结构清晰,按层级聚集
- 每个文件控制在200-400行
- 文件命名统一规范
- 删除所有冗余代码

### 可维护性提升

- 功能边界清晰,易于定位
- 模块职责明确,易于扩展
- 测试组织有序,易于维护
- 文档准确反映代码结构

### 质量保障

- 测试覆盖率保持或提升
- 所有核心功能正常工作
- 导入关系清晰无断裂
- README文档准确更新