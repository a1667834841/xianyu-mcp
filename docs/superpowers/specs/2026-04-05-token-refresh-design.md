# Token 刷新与会话管理设计文档

## 1. 概述

### 1.1 背景
当前项目中 token 管理分散在 `login.py` 和 `browser.py` 中，缺乏统一的会话管理机制。需要添加：
- 主动刷新 token 的能力（通过刷新闲鱼网页）
- 检查 cookie 是否有效的能力（调用用户信息接口）

### 1.2 目标
- 提供统一的 token 和会话状态管理
- 支持主动刷新 token
- 支持检查 cookie 有效性

---

## 2. 架构设计

### 2.1 模块结构
```
src/
  session.py          # 新建：会话管理器
  login.py            # 修改：依赖 SessionManager
  browser.py          # 修改：添加获取完整 cookie 的方法
```

### 2.2 组件关系
```
┌─────────────────┐
│  SessionManager │
├─────────────────┤
│ - chrome_manager│
│ - token         │
│ - full_cookie   │
├─────────────────┤
│ + refresh_token()      # 刷新 token
│ + check_cookie_valid() # 检查 cookie 有效性
│ + get_token()          # 获取 token
│ + get_full_cookie()    # 获取完整 cookie
└─────────────────┘
         │
         ▼
┌─────────────────┐
│ AsyncChromeManager│
├─────────────────┤
│ + get_all_cookies()  # 新增：获取所有 cookie
│ + get_cookie()       # 已有：获取指定 cookie
└─────────────────┘
```

---

## 3. API 设计

### 3.1 SessionManager 类

```python
class SessionManager:
    """闲鱼会话管理器"""
    
    def __init__(self, chrome_manager: Optional[AsyncChromeManager] = None):
        """初始化会话管理器"""
        
    async def refresh_token(self) -> Dict[str, str]:
        """
        刷新 token - 通过访问闲鱼首页获取最新 token
        
        Returns:
            字典：{"token": "...", "full_cookie": "..."}
            失败返回 None 或抛出异常
        """
        
    async def check_cookie_valid(self) -> bool:
        """
        检查 cookie 是否有效 - 调用用户信息接口
        
        接口：mtop.idle.web.user.page.nav
        成功响应：ret[0] 包含 "SUCCESS"
        
        Returns:
            bool: cookie 是否有效
        """
        
    async def get_token(self) -> Optional[str]:
        """获取当前 token（从内存或浏览器）"""
        
    async def get_full_cookie(self) -> Optional[str]:
        """获取完整 cookie（从内存或浏览器）"""
```

### 3.2 AsyncChromeManager 扩展

```python
class AsyncChromeManager:
    # 新增方法
    async def get_all_cookies(self) -> List[Dict]:
        """获取所有 cookie"""
        
    async def get_full_cookie_string(self) -> str:
        """获取完整 cookie 字符串（用于 API 请求）"""
```

---

## 4. 详细设计

### 4.1 refresh_token() 实现

```python
async def refresh_token(self) -> Dict[str, str]:
    # 1. 导航到闲鱼首页
    await self.chrome_manager.navigate("https://www.goofish.com")
    
    # 2. 等待页面加载完成
    await asyncio.sleep(2)
    
    # 3. 从浏览器获取最新 cookie
    token = await self.chrome_manager.get_xianyu_token()
    full_cookie = await self.chrome_manager.get_cookie("_m_h5_tk")
    
    # 4. 更新内存中的 token
    if token:
        self.token = token
        self.full_cookie = full_cookie
    
    # 5. 返回结果
    return {
        "token": token,
        "full_cookie": full_cookie
    }
```

### 4.2 check_cookie_valid() 实现

```python
async def check_cookie_valid(self) -> bool:
    # 1. 构建请求
    api_url = "https://h5api.m.goofish.com/h5/mtop.idle.web.user.page.nav/1.0/"
    data = {}
    
    # 2. 生成签名参数
    sign_params = self._generate_sign(data)
    
    # 3. 设置请求头
    headers = {
        "accept": "application/json",
        "content-type": "application/x-www-form-urlencoded",
        "cookie": f"_m_h5_tk={self.full_cookie}"
    }
    
    # 4. 发送请求
    response = requests.get(api_url, params=sign_params, headers=headers)
    result = response.json()
    
    # 5. 判断是否成功
    ret = result.get("ret", [])
    if ret and "SUCCESS" in ret[0]:
        return True
    return False
```

### 4.3 接口参数详解

从 curl 命令提取的参数：

```python
API_CONFIG = {
    "api": "mtop.idle.web.user.page.nav",
    "version": "1.0",
    "jsv": "2.7.2",
    "appKey": "34839810",
    "dataType": "json",
    "timeout": "20000",
    "sessionOption": "AutoLoginOnly",
    "accountSite": "xianyu",
    "type": "originaljson",
}
```

---

## 5. 使用示例

### 5.1 刷新 token

```python
async with SessionManager() as session:
    result = await session.refresh_token()
    if result:
        print(f"新 token: {result['token']}")
        print(f"完整 cookie: {result['full_cookie']}")
```

### 5.2 检查 cookie 有效性

```python
session = SessionManager()
is_valid = await session.check_cookie_valid()
if is_valid:
    print("Cookie 有效")
else:
    print("Cookie 已过期，需要重新登录")
```

### 5.3 完整工作流

```python
async with SessionManager() as session:
    # 检查 cookie 是否有效
    if not await session.check_cookie_valid():
        # 刷新 token
        result = await session.refresh_token()
        
        # 再次检查
        if not await session.check_cookie_valid():
            # 需要重新登录
            print("需要重新登录")
```

---

## 6. 错误处理

### 6.1 refresh_token() 错误

| 错误类型 | 处理方式 |
|---------|---------|
| 浏览器未启动 | 抛出 `RuntimeError("浏览器未启动")` |
| 页面导航失败 | 返回 `None` |
| 无法获取 token | 返回 `None` |

### 6.2 check_cookie_valid() 错误

| 错误类型 | 处理方式 |
|---------|---------|
| 网络错误 | 返回 `False` |
| Token 格式错误 | 返回 `False` |
| API 返回错误 | 返回 `False` |

---

## 7. 错误处理

### 7.1 新增依赖
- 无（仅使用现有依赖）

### 7.2 模块依赖
- `session.py` → `browser.py`
- `login.py` → `session.py`（可选）

---

## 8. 测试计划

### 8.1 单元测试

```python
# test_session.py
class TestSessionManager:
    def test_refresh_token(self):
        """测试刷新 token"""
        
    def test_check_cookie_valid(self):
        """测试检查 cookie 有效性"""
        
    def test_check_cookie_invalid(self):
        """测试无效 cookie"""
```

### 8.2 集成测试

```python
# test_integration.py
class TestIntegration:
    def test_session_workflow(self):
        """测试完整会话工作流"""
```

---

## 9. MCP 工具设计

### 9.1 新增工具列表

在现有 MCP Server 中添加两个新工具：

```python
# mcp_server/server.py 中添加
types.Tool(
    name="xianyu_refresh_token",
    description="刷新闲鱼 Token。通过访问闲鱼首页获取最新的 Token，当 Token 过期或需要更新时调用。",
    inputSchema={
        "type": "object",
        "properties": {},
        "required": []
    }
)

types.Tool(
    name="xianyu_check_session",
    description="检查闲鱼 Cookie 是否有效。调用用户信息接口验证当前登录状态。",
    inputSchema={
        "type": "object",
        "properties": {},
        "required": []
    }
)
```

### 9.2 工具处理函数

```python
async def handle_refresh_token(arguments: dict) -> types.CallToolResult:
    """处理刷新 token"""
    from src.session import SessionManager
    
    manager = get_chrome_manager()
    session = SessionManager(chrome_manager=manager)
    
    result = await session.refresh_token()
    
    if result:
        response = {
            "success": True,
            "token": result["token"],
            "message": "Token 刷新成功"
        }
    else:
        response = {
            "success": False,
            "message": "Token 刷新失败，请检查浏览器是否已登录"
        }
    
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=json.dumps(response, ensure_ascii=False))]
    )


async def handle_check_session(arguments: dict) -> types.CallToolResult:
    """处理检查会话"""
    from src.session import SessionManager
    
    manager = get_chrome_manager()
    session = SessionManager(chrome_manager=manager)
    
    is_valid = await session.check_cookie_valid()
    
    response = {
        "success": True,
        "valid": is_valid,
        "message": "Cookie 有效" if is_valid else "Cookie 已过期，需要重新登录"
    }
    
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=json.dumps(response, ensure_ascii=False))]
    )
```

### 9.3 使用示例

**刷新 Token:**
```
/tools/call xianyu_refresh_token {}
```

**检查会话:**
```
/tools/call xianyu_check_session {}
```

### 9.4 与现有工具的协同

```
┌─────────────────────────────────────────────────────┐
│                  完整工作流示例                       │
├─────────────────────────────────────────────────────┤
│ 1. xianyu_check_session  → 检查 cookie 是否有效        │
│    ├─ 有效 → 继续操作                                  │
│    └─ 无效 → 2. xianyu_refresh_token → 刷新 token     │
│                ├─ 成功 → 继续操作                      │
│                └─ 失败 → 3. xianyu_login → 重新登录   │
│ 4. xianyu_search / xianyu_publish → 执行实际操作      │
└─────────────────────────────────────────────────────┘
```

## 10. 后续扩展

### 10.1 可能的扩展
- 自动刷新机制（token 过期前自动刷新）
- Token 缓存管理
- 多账号会话管理
