# 两步登录设计方案

**日期：** 2026-04-06
**状态：** 已完成

---

## 1. 背景与目标

### 1.1 背景

当前登录流程存在的问题：

1. **二维码与页面不一致** - 主动调用 API 生成的二维码与页面触发的二维码可能不一致，导致扫码后浏览器无法自动登录
2. **轮询逻辑复杂** - 登录方法内部包含轮询等待逻辑，代码复杂且容易超时
3. **职责不清晰** - 登录方法同时负责获取二维码、显示二维码、等待扫码、检查登录状态

### 1.2 目标

重新设计登录流程，实现：

1. **二维码一致性** - 确保显示的二维码与页面触发的一致，扫码后浏览器自动跳转
2. **简化逻辑** - 移除轮询等待，由调用方自行决定何时检查登录状态
3. **职责分离** - 登录方法只负责检测和显示，检查登录状态由单独方法处理

---

## 2. 设计原则

### 2.1 监听页面触发

**核心变化：** `_get_qr_code()` 从"主动调用 API"改为"监听页面触发的 API"

**原因：**
- 闲鱼页面在访问时会自动触发 `newlogin/qrcode/generate.do` 接口
- 每次触发都会生成新的二维码
- 如果主动调用 API，生成的二维码与页面不一致，扫码后浏览器无法自动登录

**实现方式：**
```python
# 1. 先设置监听器
page.on('response', on_response)

# 2. 再导航到页面（会触发接口）
await page.navigate('https://www.goofish.com')

# 3. 等待并捕获响应
await capture_event.wait()
```

### 2.2 不等待扫码

**核心变化：** `login()` 显示二维码后立即返回，不等待用户扫码

**原因：**
- 用户扫码后，浏览器页面会自动跳转完成登录
- 不需要轮询检查，调用方可在扫码后调用 `check_session()` 确认

**返回格式：**
```json
{
  "success": true,
  "logged_in": false,
  "qr_code": {...},
  "message": "请扫码登录。扫码后浏览器会自动跳转，然后请调用 check_session 确认登录状态"
}
```

### 2.3 统一入口

**核心变化：** `login()` 方法统一处理所有登录场景

**流程：**
```
访问闲鱼首页 → 检查是否已登录 → 已登录返回 token / 未登录显示二维码
```

---

## 3. 架构设计

### 3.1 整体流程

```
┌─────────────────────────────────────────────────────────────┐
│                      xianyu_login                            │
├─────────────────────────────────────────────────────────────┤
│  1. 设置监听器 (page.on('response'))                          │
│  2. 导航到闲鱼首页 (https://www.goofish.com)                 │
│  3. 检查是否已登录 (check_login_status())                    │
│     ├─ 已登录 → 返回 token                                    │
│     └─ 未登录 → 继续                                          │
│  4. 点击登录按钮（如果需要）                                   │
│  5. 监听页面触发的二维码 API                                  │
│  6. 生成二维码图片 (Base64 + ASCII)                           │
│  7. 显示二维码并返回数据                                      │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    用户扫码（浏览器自动跳转）
                              │
                              ▼
                    调用 xianyu_check_session 确认

```

### 3.2 数据流

```
┌──────────────────┐
│  访问闲鱼首页     │
└────────┬─────────┘
         │
         │ 页面自动触发
         ▼
┌──────────────────────────┐
│  newlogin/qrcode/        │
│  generate.do             │
└────────┬─────────────────┘
         │
         │ 监听器捕获
         ▼
┌──────────────────────────┐
│  codeContent (URL)       │
│  ck (验证 token)          │
│  t (时间戳)               │
└────────┬─────────────────┘
         │
         │ 使用 qrcode 库生成
         ▼
┌──────────────────────────┐
│  Base64 图片              │
│  ASCII 二维码              │
│  Text URL                 │
└────────┬─────────────────┘
         │
         │ 返回给调用方
         ▼
┌──────────────────────────┐
│  终端显示 / 推送图片       │
└──────────────────────────┘
```

---

## 4. 详细设计

### 4.1 SessionManager.login()

**文件：** `src/session.py`

```python
async def login(self, timeout: int = 30) -> Dict[str, Any]:
    """
    登录流程：
    1. 访问闲鱼首页
    2. 检查是否已登录 → 已登录则直接返回
    3. 未登录则获取并显示二维码
    4. 返回二维码数据（不等待扫码）
    """
    # 确保浏览器运行
    if not await self.chrome_manager.ensure_running():
        return {'success': False, 'message': '浏览器启动失败'}

    # 设置二维码 API 监听器（在导航之前）
    page = self.chrome_manager.page
    capture_event = asyncio.Event()
    captured_data = {}

    async def process_response(response):
        url = response.url
        if 'newlogin/qrcode/generate.do' in url:
            data = await response.json()
            # 提取 codeContent, ck, t
            ...
            captured_data.update({...})
            capture_event.set()

    page.on('response', lambda r: asyncio.create_task(process_response(r)))

    # 访问闲鱼首页
    await self.chrome_manager.navigate("https://www.goofish.com")
    await asyncio.sleep(2)

    # 检查是否已登录
    if await self.check_login_status():
        return {
            'success': True,
            'logged_in': True,
            'token': ...,
            'message': '已登录'
        }

    # 点击登录按钮触发二维码
    login_btn = page.locator("button", has_text="登录").first
    await login_btn.click()
    await asyncio.sleep(2)

    # 等待二维码 API 响应
    await asyncio.wait_for(capture_event.wait(), timeout=timeout)

    # 生成并显示二维码
    qr_result = await self._generate_qr_base64(captured_data['url'])
    ascii_qr = self._generate_ascii_qr(captured_data['url'])

    # 返回二维码数据（不等待扫码）
    return {
        'success': True,
        'logged_in': False,
        'qr_code': {...},
        'message': '请扫码登录。扫码后浏览器会自动跳转...'
    }
```

### 4.2 SessionManager.check_login_status()

**文件：** `src/session.py`

```python
async def check_login_status(self) -> bool:
    """
    检查登录状态 - 调用用户信息接口

    接口：mtop.idle.web.user.page.nav
    成功响应：ret[0] 包含 "SUCCESS" 且返回用户信息
    """
    # 调用 API 检查
    # 成功返回 True，失败返回 False
```

### 4.3 MCP Server 工具

**文件：** `mcp_server/server.py`

| 工具 | 功能 |
|------|------|
| `xianyu_check_session` | 检查 Cookie 是否有效 |
| `xianyu_login` | 访问闲鱼，已登录则返回 token，未登录则显示二维码 |
| `xianyu_show_qr` | 显示登录二维码（复用 login()） |

---

## 5. 使用示例

### 5.1 MCP Server 完整流程

```
# 步骤 1: 检查登录状态
调用 xianyu_check_session
→ {"success": true, "valid": false, "message": "Cookie 已过期"}

# 步骤 2: 登录（显示二维码）
调用 xianyu_login
→ 终端显示 ASCII 二维码
→ {"success": true, "logged_in": false, "qr_code": {...}}

# 步骤 3: 用户扫码（浏览器自动跳转）

# 步骤 4: 确认登录成功
调用 xianyu_check_session
→ {"success": true, "valid": true, "message": "Cookie 有效"}
```

### 5.2 Python API

```python
from xianyu import XianyuApp

async with XianyuApp() as app:
    # 登录
    result = await app.login(timeout=15)
    
    if result['logged_in']:
        print(f"已登录，token: {result['token']}")
    else:
        print("请扫码登录")
        # 用户扫码后...
        
    # 确认登录状态
    is_valid = await app.check_session()
    if is_valid:
        print("登录成功")
    
    # 搜索商品
    items = await app.search("机械键盘", rows=10)
```

---

## 6. 错误处理

| 异常 | 处理方式 |
|------|----------|
| 监听超时 | 返回 `{'success': False, 'message': '获取二维码超时'}` |
| 浏览器启动失败 | 返回 `{'success': False, 'message': '浏览器启动失败'}` |
| 页面导航失败 | 返回 `{'success': False, 'message': '访问页面失败'}` |
| API 解析失败 | 继续等待下一次响应 |

---

## 7. 文件变更清单

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `src/session.py` | 修改 | `_get_qr_code()` 改为监听，`login()` 简化 |
| `src/core.py` | 修改 | `XianyuApp.login()` 签名变更 |
| `mcp_server/server.py` | 修改 | 添加 `xianyu_show_qr` 工具 |
| `.claude/skills/xianyu-mcp-server/SKILL.md` | 修改 | 更新工具说明 |

---

## 8. 总结

新设计通过**监听页面触发**确保二维码一致性，通过**不等待扫码**简化逻辑，通过**统一入口**明确职责。

**核心变化：**
1. `_get_qr_code()` 从"主动调用 API"改为"监听页面触发"
2. `login()` 显示二维码后立即返回，不等待扫码
3. 调用方在扫码后调用 `check_session()` 确认登录状态
