# 跨平台登录二维码展示方案设计

**日期：** 2026-04-06
**状态：** 设计中

---

## 1. 背景与目标

### 1.1 背景

闲鱼助手项目需要支持多环境部署，当前登录流程在不同环境下体验不一致：

| 环境 | 现状 | 问题 |
|------|------|------|
| macOS 桌面 | 浏览器窗口显示二维码 | 体验良好 |
| Linux 桌面（Chrome 容器） | 终端无输出，需手动切换窗口 | 体验差 |
| Linux 服务器（Headless） | 无界面，无法查看二维码 | 无法使用 |
| OpenClaw + 飞书 | 无推送能力 | 无法使用 |

### 1.2 目标

设计统一的二维码获取与返回机制，支持：
1. **桌面环境** - 终端显示 ASCII 二维码或 Base64 图片
2. **服务器环境** - 终端文本输出或图片文件
3. **OpenClaw 环境** - 返回 Base64 数据，通过飞书推送

### 1.3 设计原则

- **统一返回** - `login()` 方法返回完整数据包，调用方按需取用
- **自动检测** - 不检测环境，由调用方决定展示方式
- **降级兼容** - Base64 → ASCII → Text URL，逐级降级

---

## 2. 架构设计

### 2.1 整体流程

```
┌─────────────────────────────────────────────────────────────┐
│                    SessionManager.login()                    │
├─────────────────────────────────────────────────────────────┤
│  1. 导航到登录页 (https://www.goofish.com)                    │
│  2. 直接调用 API (newlogin/qrcode/generate.do)              │
│  3. 获取 codeContent (二维码 URL)                             │
│  4. 使用 qrcode 库从 URL 生成本地二维码图片 → 转 Base64       │
│  5. 生成 ASCII 二维码（可选）                                  │
│  6. 返回完整数据包                                           │
│  7. 等待扫码（限时 30 秒）                                      │
│     ├─ 成功 → 返回 token                                     │
│     └─ 超时 → 返回 expired=True，调用方可重新获取             │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
        ▼                     ▼                     ▼
┌───────────────┐   ┌─────────────────┐   ┌───────────────┐
│   MCP Server  │   │  Linux Terminal │   │  OpenClaw     │
│   (桌面)      │   │   (服务器)      │   │  (飞书)       │
├───────────────┤   ├─────────────────┤   ├───────────────┤
│ 显示 Base64   │   │ 打印 ASCII/Text │   │ 推送 Base64   │
│ 图片或 URL    │   │ URL             │   │ 图片消息      │
└───────────────┘   └─────────────────┘   └───────────────┘
```

### 2.2 数据流

```
passport.goofish.com
       │
       │ 1. 调用 API
       ▼
/newlogin/qrcode/generate.do
       │
       │ 2. 返回 codeContent
       ▼
codeContent: "https://passport.goofish.com/qrcodeCheck.htm?lgToken=xxx"
       │
       │ 3. 使用 qrcode 库本地生成
       ▼
   二维码图片 (PIL)
       │
       │ 4. 转 Base64
       ▼
   Base64 + ASCII + Text
       │
       │ 5. 返回给调用方
       ▼
   MCP Server / OpenClaw
```

---

## 3. 详细设计

### 3.1 直接调用 API 获取二维码

**文件：** `src/session.py`

**方法：** `_get_qr_code()`

**设计说明：**

当前实现**不再使用被动监听 API 响应**的方式，而是**直接调用二维码生成 API**获取数据。这样做的好处是：
1. 更可靠，不依赖页面事件监听
2. 更快速，无需等待页面 JS 执行
3. 更简单，代码逻辑更清晰

```python
async def _get_qr_code(self, timeout: int = 15) -> Optional[Dict[str, str]]:
    """
    获取二维码数据（直接调用 API）

    Args:
        timeout: 等待 API 响应超时时间（秒）

    Returns:
        二维码数据包：
        - url: str (二维码图片 URL)
        - base64: str (Base64 图片数据，格式 data:image/png;base64,xxx)
        - ascii: str (ASCII 二维码，可选)
        - text: str (纯文本 URL，降级用)
        - ck: str (验证 token，用于后续轮询)
        - t: int (时间戳)

        失败返回 None
    """
    page = self.chrome_manager.page
    if not page:
        return None

    print("[Session] 正在调用 API 获取二维码...")

    try:
        # 直接调用二维码生成 API
        response = await page.request.get(
            'https://passport.goofish.com/newlogin/qrcode/generate.do?appName=xianyu&fromSite=77'
        )

        if response.status != 200:
            print(f"[Session] 调用二维码 API 失败，HTTP {response.status}")
            return None

        # 解析响应
        data = await response.json()

        # 提取二维码数据
        content = data.get('content', {})
        qr_data = content.get('data', {})

        code_content = qr_data.get('codeContent')  # 二维码 URL
        ck = qr_data.get('ck')  # 验证 token
        t = qr_data.get('t')  # 时间戳

        if not code_content:
            print(f"[Session] API 返回数据无效：{data}")
            return None

        # 确保 HTTPS
        if code_content.startswith('http://'):
            code_content = code_content.replace('http://', 'https://')

        print(f"[Session] 已获取二维码 URL: {code_content[:80]}...")

        # 使用 qrcode 库从 URL 生成本地二维码图片并转 Base64
        qr_result = await self._generate_qr_base64(code_content)

        if not qr_result.get('base64'):
            print("[Session] 生成二维码图片失败")
            return None

        # 生成 ASCII 二维码
        ascii_qr = self._generate_ascii_qr(code_content)

        return {
            'url': code_content,
            'base64': qr_result['base64'],
            'ascii': ascii_qr,
            'text': code_content,
            'ck': ck,
            't': t
        }

    except Exception as e:
        print(f"[Session] 获取二维码失败：{e}")
        # 降级方案：从 DOM 获取
        return await self._get_qr_code_from_dom()
```

### 3.2 Base64 图片生成

**方法：** `_generate_qr_base64()`

**设计说明：**

当前实现**不再从 URL 下载图片**，而是使用 `qrcode` 库 + PIL 从 URL **本地生成**二维码图片。这样做的好处是：
1. 更可靠，不依赖外部图片 URL 的可访问性
2. 更快速，无需网络下载
3. 更准确，`codeContent` 本身就是二维码内容，应该直接用它生成

```python
async def _generate_qr_base64(self, content: str) -> Dict[str, str]:
    """
    从 URL 生成二维码图片并转为 Base64

    Args:
        content: 二维码内容（URL）

    Returns:
        {'base64': 'data:image/png;base64,xxx'}
    """
    try:
        import qrcode
        from PIL import Image

        # 生成二维码
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(content)
        qr.make(fit=True)

        # 生成图片
        img = qr.make_image(fill_color="black", back_color="white")

        # 转 Base64
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        img_bytes = buffer.getvalue()
        base64_data = base64.b64encode(img_bytes).decode('utf-8')

        print(f"[Session] 二维码图片已生成，大小：{len(img_bytes)} bytes")

        return {'base64': f'data:image/png;base64,{base64_data}'}

    except ImportError as e:
        print(f"[Session] 生成二维码图片失败：缺少依赖 ({e})")
        return {'base64': ''}
    except Exception as e:
        print(f"[Session] 生成二维码图片失败：{e}")
        return {'base64': ''}
```

### 3.3 ASCII 二维码生成

**方法：** `_generate_ascii_qr()`

```python
def _generate_ascii_qr(self, content: str) -> str:
    """
    生成 ASCII 二维码

    Args:
        content: 二维码内容（URL）

    Returns:
        ASCII 二维码字符串，失败返回空字符串
    """
    try:
        import qrcode
        from qrcode.terminal import print as qr_print
        import io
        import sys

        # 生成二维码
        qr = qrcode.QRCode(version=1, box_size=1, border=1)
        qr.add_data(content)
        qr.make(fit=True)

        # 输出到字符串
        output = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = output
        qr.print_ascii(invert=True)
        ascii_qr = output.getvalue()
        sys.stdout = old_stdout

        return ascii_qr

    except ImportError:
        print("[Session] qrcode 库未安装，跳过 ASCII 二维码生成")
        return ''
    except Exception as e:
        print(f"[Session] 生成 ASCII 二维码失败：{e}")
        return ''
```

### 3.4 登录方法返回值

**文件：** `src/session.py`

**方法：** `login()`

```python
async def login(self, timeout: int = 30, max_retries: int = 3) -> Dict[str, Any]:
    """
    扫码登录获取 Token

    Args:
        timeout: 单次等待扫码超时时间（秒），默认 30 秒
        max_retries: 最大重试次数，默认 3 次

    Returns:
        字典，包含：
        - success: bool
        - token: str (可选，登录成功时返回)
        - qr_code: Dict (可选，需要扫码时返回)
          - url: str (二维码图片 URL)
          - base64: str (Base64 图片数据)
          - ascii: str (ASCII 二维码)
          - text: str (纯文本 URL)
          - ck: str (验证 token)
        - message: str
        - expired: bool (可选，二维码已过期需要重新获取)
    """
    retry_count = 0

    while retry_count < max_retries:
        # 1. 检查缓存 Cookie
        cached_cookie = self.load_cached_cookie()
        if cached_cookie:
            print("[Session] 发现缓存 Cookie，尝试恢复...")
            await self._restore_cookie(cached_cookie)

            if await self.check_login_status():
                print("[Session] 缓存 Cookie 有效，无需重新登录")
                m_h5_tk = await self.chrome_manager.get_cookie('_m_h5_tk')
                self.full_cookie = cached_cookie
                return {
                    'success': True,
                    'token': m_h5_tk.split('_')[0] if m_h5_tk else None,
                    'message': '缓存 Cookie 有效，已自动恢复'
                }
            else:
                print("[Session] 缓存 Cookie 已失效，需要重新登录")

        # 2. 获取二维码
        print("[Session] 正在获取二维码...")
        qr_data = await self._get_qr_code()

        if not qr_data:
            return {
                'success': False,
                'message': '获取二维码失败，请重试'
            }

        # 3. 返回二维码给调用方
        # 注意：这里不直接打印，由调用方决定展示方式
        return {
            'success': True,
            'qr_code': qr_data,
            'message': '请扫码登录',
            'expired': False
        }

        # 4. 等待扫码（限时 timeout 秒）
        print(f"[Session] 等待扫码（{timeout}秒）...")
        start_time = time.time()

        while time.time() - start_time < timeout:
            if await self.check_login_status():
                print("[Session] 登录成功!")
                full_cookie = await self.chrome_manager.get_full_cookie_string()
                self.save_cookie(full_cookie)
                token = await self.chrome_manager.get_xianyu_token()

                return {
                    'success': True,
                    'token': token,
                    'message': '登录成功'
                }

            await asyncio.sleep(2)

        # 5. 超时处理
        retry_count += 1
        print(f"[Session] 扫码超时（{timeout}秒），尝试重新获取二维码 ({retry_count}/{max_retries})")

    # 6. 超过最大重试次数
    return {
        'success': False,
        'message': f'登录超时，已重试{max_retries}次',
        'expired': True
    }
```

### 3.5 MCP Server 适配

**文件：** `mcp_server/server.py`

**方法：** `handle_login()`

```python
async def handle_login(arguments: dict) -> types.CallToolResult:
    """
    处理登录

    返回：
    - 登录成功：{"success": true, "token": "..."}
    - 需要扫码：{"success": true, "qr_code": {...}, "message": "请扫码登录"}
    - 登录失败：{"success": false, "message": "..."}
    """
    app = get_app()
    result = await app.login(timeout=30, max_retries=1)

    return types.CallToolResult(
        content=[types.TextContent(
            type="text",
            text=json.dumps(result, ensure_ascii=False)
        )]
    )
```

---

## 4. 调用方使用示例

### 4.1 MCP Server（桌面环境）

```python
# 调用登录
result = await handle_login({})
data = json.loads(result.content[0].text)

if data.get('qr_code'):
    qr = data['qr_code']

    # 方案 A: 显示 Base64 图片（如果有图像显示能力）
    show_image(qr['base64'])

    # 方案 B: 终端显示 ASCII 二维码
    if qr.get('ascii'):
        print(qr['ascii'])
    else:
        print(f"二维码 URL: {qr['text']}")

    # 继续轮询检查登录状态...
```

### 4.2 OpenClaw + 飞书

```python
# 调用登录
result = await xianyu_login()
data = result['result']

if data.get('qr_code'):
    qr = data['qr_code']

    # 发送 Base64 图片到飞书
    await feishu_send_image(qr['base64'])

    # 或发送 URL 卡片
    await feishu_send_card(
        title="闲鱼登录二维码",
        url=qr['text']
    )
```

### 4.3 Linux 服务器（Headless）

```python
# 调用登录
result = await session.login()

if result.get('qr_code'):
    qr = result['qr_code']

    # 终端显示 ASCII 二维码
    if qr.get('ascii'):
        print(qr['ascii'])

    # 或保存图片文件
    if qr.get('base64'):
        import base64
        img_data = qr['base64'].split(',')[1]
        with open('/tmp/qr_login.png', 'wb') as f:
            f.write(base64.b64decode(img_data))
        print(f"二维码已保存：/tmp/qr_login.png")
```

---

## 5. 依赖要求

### 5.1 必需依赖

| 库 | 用途 | 是否必需 |
|----|------|----------|
| `playwright` | 浏览器自动化，下载图片 | 是 |
| `base64` | Base64 编码 | 是（Python 内置） |

### 5.2 可选依赖

| 库 | 用途 | 安装命令 |
|----|------|----------|
| `qrcode` | 生成 ASCII 二维码 | `pip install qrcode[pil]` |
| `PIL` | 图片处理 | `pip install pillow` |
| `term_image` | 终端图像显示 | `pip install term-image` |

---

## 6. 错误处理

### 6.1 异常情况

| 异常 | 处理方式 |
|------|----------|
| API 响应超时 | 返回 `expired=True`，调用方可重试 |
| 图片下载失败 | 返回 `base64=''`，降级使用 URL |
| ASCII 生成失败 | 返回 `ascii=''`，降级使用 Text URL |
| 浏览器未启动 | 返回 `success=False` |

### 6.2 降级链

```
Base64 图片 → ASCII 二维码 → Text URL
     ↓              ↓
  (最优)      (终端友好)    (最降级)
```

---

## 7. 后续优化（可选）

### 7.1 使用 `ck` 字段轮询

当前设计使用 `check_login_status()` 检查登录状态，后续可优化为：

```python
async def _check_qr_scan_status(self, ck: str) -> str:
    """
    使用 ck 轮询扫码状态

    Returns:
        'waiting' - 等待扫码
        'scanned' - 已扫码，待确认
        'confirmed' - 已确认登录
        'expired' - 二维码已过期
    """
```

### 7.2 二维码缓存

- 首次获取后缓存二维码 URL
- 一定时间内重复调用 `login()` 返回相同二维码
- 避免频繁请求接口

---

## 8. 验证计划

### 8.1 单元测试

- [x] `_get_qr_code()` 正确调用 API 获取二维码
- [x] `_generate_qr_base64()` 正确生成二维码图片并转 Base64
- [x] `_generate_ascii_qr()` 正确生成 ASCII 码
- [x] `login()` 返回值结构正确

### 8.2 集成测试

- [ ] macOS 桌面：MCP Server 显示二维码
- [ ] Linux 终端：ASCII 二维码显示
- [ ] 图片保存：Base64 转图片文件
- [ ] 超时重试：30 秒超时后重新获取

---

## 9. 文件变更清单

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `src/session.py` | 修改 | 新增 `_get_qr_code()`, 修改 `login()` 返回值 |
| `mcp_server/server.py` | 修改 | `handle_login()` 返回完整数据包 |
| `requirements.txt` | 可选 | 添加 `qrcode[pil]` 依赖 |

---

## 10. 总结

本设计通过统一的二维码数据包返回机制，支持多环境下的闲鱼登录场景：

1. **统一接口** - `login()` 返回完整数据包
2. **多种格式** - Base64 / ASCII / Text，逐级降级
3. **环境无关** - 调用方自行决定展示方式
4. **超时重试** - 30 秒超时后重新获取二维码
