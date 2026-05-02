# 滑块验证自动处理设计文档

## 背景

闲鱼 API 在高频调用或风控触发时会返回 `FAIL_SYS_USER_VALIDATE`，需要用户完成滑块验证才能继续。现有浏览器容器已修复（CDP 9222 端口可用），可复用进行自动化滑块验证。

## 目标

实现滑块验证自动处理：
- API 返回验证码错误时自动触发
- 复用现有浏览器容器完成验证
- 自动更新 cookies 并重试原请求
- 全流程无需用户干预

## 架构

```
HTTP 请求 → 检测验证码 → 连接浏览器 → 滑块自动化 → 更新 Cookies → 重试请求 → 关闭网页
```

## 流程设计

### 1. 触发检测（http_client.py）

**位置**: `src/api/http_client.py` `_send_request()` 方法

**逻辑**:
```python
async def _send_request(self, api, data, retry_on_captcha=True):
    resp = await self._raw_send_request(api, data)
    
    # 检测验证码触发
    if self._need_captcha(resp) and retry_on_captcha:
        verification_url = resp.get('data', {}).get('url', '')
        
        # 调用滑块验证（最多重试 3 次）
        for attempt in range(3):
            success = await self._handle_captcha(verification_url)
            if success:
                # 重试原请求
                return await self._send_request(api, data, retry_on_captcha=False)
        
        # 验证失败，返回原错误
        return resp
    
    return resp

def _need_captcha(self, resp):
    """检测是否需要滑块验证"""
    keywords = ['FAIL_SYS_USER_VALIDATE', 'RGV587_ERROR::SM::请稍后重试']
    ret = resp.get('ret', [])
    return any(k in str(ret) for k in keywords)
```

### 2. 连接浏览器（browser_bridge.py）

**位置**: `src/api/browser_bridge.py`（现有，需扩展）

**新增方法**:
```python
async def connect_to_browser_pool(self):
    """连接现有浏览器池容器"""
    from playwright.async_api import async_playwright
    
    playwright = await async_playwright().start()
    
    # 连接 CDP 端点（浏览器容器已启动）
    browser = await playwright.chromium.connect_over_cdp(
        "ws://localhost:9222/devtools/browser/..."
    )
    
    # 获取或创建页面
    context = browser.contexts[0] if browser.contexts else await browser.new_context()
    page = context.pages[0] if context.pages else await context.new_page()
    
    self._playwright = playwright
    self._browser = browser
    self._page = page
    
    return page
```

### 3. 滑块自动化（slider_solver.py）

**新建文件**: `src/api/slider_solver.py`

**核心逻辑**:
```python
class SliderSolver:
    """滑块验证自动化"""
    
    async def solve(self, page, verification_url):
        """执行滑块验证"""
        try:
            # 1. 访问验证页面
            await page.goto(verification_url, wait_until="networkidle")
            
            # 2. 处理 iframe（验证码可能在 iframe 中）
            slider_frame = await self._find_slider_frame(page)
            
            # 3. 定位滑块元素
            slider_btn = await slider_frame.query_selector('#nc_1_n1z')  # 滑块按钮
            slider_track = await slider_frame.query_selector('.nc_scale')  # 滑轨
            
            if not slider_btn or not slider_track:
                return False
            
            # 4. 计算滑动距离
            track_box = await slider_track.bounding_box()
            btn_box = await slider_btn.bounding_box()
            distance = track_box['width'] - btn_box['width'] - 10
            
            # 5. 生成人类轨迹
            trajectory = self._generate_human_trajectory(distance)
            
            # 6. 模拟滑动
            await self._simulate_drag(slider_btn, trajectory)
            
            # 7. 检查验证结果
            success = await self._check_result(slider_frame)
            
            return success
            
        except Exception as e:
            logger.error(f"滑块验证失败: {e}")
            return False
    
    def _generate_human_trajectory(self, distance):
        """生成人类滑动轨迹"""
        # 参考 xianyu-super-butler 的轨迹算法
        # 包含：加速段、减速段、抖动、随机延迟
        
        steps = random.randint(15, 25)  # 步数
        
        # 贝塞尔曲线生成轨迹
        trajectory = []
        for i in range(steps):
            t = i / steps
            # 加速阶段（前 70%）
            if t < 0.7:
                x = distance * (1 - math.pow(1 - t / 0.7, 3))
            else:
                # 减速阶段（后 30%）
                x = distance * 0.7 + distance * 0.3 * ((t - 0.7) / 0.3)
            
            # 添加抖动
            y = random.uniform(-2, 2)
            
            # 添加时间延迟
            delay = random.uniform(0.003, 0.008)
            
            trajectory.append((x, y, delay))
        
        return trajectory
    
    async def _simulate_drag(self, element, trajectory):
        """模拟拖动"""
        box = await element.bounding_box()
        start_x = box['x'] + box['width'] / 2
        start_y = box['y'] + box['height'] / 2
        
        # 移动到起点
        await element.hover()
        
        # 模拟滑动
        async def drag():
            for x, y, delay in trajectory:
                await element.hover()
                # 使用 CDP Input.dispatchMouseEvent
                # ...
                await asyncio.sleep(delay)
        
        await drag()
```

### 4. 更新 Cookies（captcha_handler.py）

**新建文件**: `src/api/captcha_handler.py`

**协调逻辑**:
```python
class CaptchaHandler:
    """滑块验证协调器"""
    
    async def handle(self, http_client, verification_url):
        """处理滑块验证"""
        from .browser_bridge import BrowserBridge
        from .slider_solver import SliderSolver
        
        bridge = BrowserBridge()
        
        try:
            # 1. 连接浏览器
            page = await bridge.connect_to_browser_pool()
            if not page:
                return False
            
            # 2. 执行滑块验证
            solver = SliderSolver()
            success = await solver.solve(page, verification_url)
            
            if success:
                # 3. 获取新 cookies
                cookies = await bridge.get_cookies()
                
                # 4. 更新 http_client cookies
                http_client.cookies.update(cookies)
                
                # 5. 保存到 auth.json
                http_client._save_cookies()
                
                logger.info("滑块验证成功，cookies 已更新")
            
            return success
            
        finally:
            # 6. 关闭验证页面
            await bridge.close_captcha_page()
            
            # 7. 断开连接（不关闭浏览器容器）
            await bridge.disconnect()
```

### 5. 关闭网页（browser_bridge.py）

**新增方法**:
```python
async def close_captcha_page(self):
    """关闭验证页面（不关闭浏览器容器）"""
    if self._page and self._page.url != "about:blank":
        try:
            # 导航到空白页（释放资源）
            await self._page.goto("about:blank")
            logger.info("验证页面已关闭")
        except Exception as e:
            logger.warning(f"关闭页面失败: {e}")

async def disconnect(self):
    """断开连接（保留浏览器容器运行）"""
    # 不关闭 browser，只释放 playwright 资源
    if self._playwright:
        await self._playwright.stop()
        self._playwright = None
        self._browser = None
        self._page = None
```

## 文件结构

```
src/api/
├── http_client.py       # [修改] 添加验证码检测和触发
├── browser_bridge.py    # [扩展] 添加 CDP 连接和页面管理
├── captcha_handler.py   # [新建] 滑块验证协调器
├── slider_solver.py     # [新建] 滑块自动化核心算法
└── types.py             # [不变] 类型定义
```

## 关键技术点

### iframe 处理

验证码可能在 iframe 中，需遍历 frames：

```python
async def _find_slider_frame(self, page):
    """查找包含滑块的 frame"""
    for frame in page.frames:
        try:
            slider = await frame.query_selector('#nc_1_n1z')
            if slider:
                return frame
        except:
            continue
    return page  # 不在 iframe 中
```

### 反检测脚本

注入脚本隐藏自动化特征：

```python
async def _inject_stealth_script(self, page):
    """注入反检测脚本"""
    await page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });
        
        window.chrome = {
            runtime: {}
        };
        
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5]
        });
    """)
```

### 轨迹生成算法

参考 xianyu-super-butler 的轨迹参数：

| 参数 | 范围 | 说明 |
|------|------|------|
| 步数 | 15-25 | 模拟人类滑动次数 |
| 基础延迟 | 3-8ms | 每步延迟 |
| X 抖动 | ±2px | 横向抖动 |
| Y 抖动 | ±2px | 纵向抖动 |
| 加速比例 | 70% | 前 70% 加速 |

## 错误处理

| 错误 | 处理 |
|------|------|
| 浏览器连接失败 | 返回 False，保持原错误 |
| 滑块定位失败 | 重试 3 次，返回 False |
| 验证结果失败 | 重试 3 次，返回 False |
| Cookie 获取失败 | 返回 False，保持原错误 |

## 测试策略

### 单元测试

- `test_slider_solver.py` - 轨迹生成、iframe 查找
- `test_captcha_handler.py` - 协调流程 mock

### 集成测试

- 触发真实验证码 URL → 自动完成 → 验证 cookies 更新

## 资源复用

| 资源 | 状态 | 复用方式 |
|------|------|---------|
| 浏览器容器 | ✅ 已修复 | CDP 连接 ws://localhost:9222 |
| browser.py | ✅ 已有 | 复用 CDP 连接逻辑 |
| browser_bridge.py | ✅ 已有 | 扩展页面管理方法 |

## 风险

| 风险 | 影响 | 缓解 |
|------|------|------|
| 滑块算法检测 | 验证失败 | 优化轨迹算法 |
| 浏览器容器故障 | 无法验证 | 添加健康检查 |
| iframe 结构变化 | 定位失败 | 多选择器兜底 |