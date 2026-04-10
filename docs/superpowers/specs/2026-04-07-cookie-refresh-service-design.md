# Cookie 轮询刷新服务设计

## 需求

1. **轮询刷新 Cookie**：每 30 分钟自动刷新 Cookie 并保存到文件
2. **独立服务**：作为独立后台进程运行，不影响主程序
3. **状态可见**：同时输出到控制台和日志文件

## 设计

### 文件结构

```
~/.claude/xianyu-tokens/
├── token.json          # Cookie 文件（已有）
└── refresh.log         # 新增：轮询日志
```

### 配置项

| 配置项 | 默认值 | 说明 |
|-------|-------|------|
| 轮询间隔 | 30 分钟 | 可配置 |
| Cookie 文件路径 | `~/.claude/xianyu-tokens/token.json` | 固定 |
| 日志文件路径 | `~/.claude/xianyu-tokens/refresh.log` | 固定 |
| Chrome CDP 地址 | localhost:9222 | 可配置 |

### 核心逻辑

```
1. 启动服务
2. 连接到 Chrome 浏览器（通过 CDP）
3. 立即执行一次 Cookie 刷新（获取最新状态）
4. 进入轮询循环：
   - 等待 30 分钟
   - 访问闲鱼首页 (https://www.goofish.com)
   - 获取完整 Cookie 字符串
   - 保存到 token.json
   - 记录日志
5. 循环直到被终止
```

### 日志格式

```
[2026-04-07 12:00:00] Cookie 刷新成功，下次刷新时间: 12:30:00
[2026-04-07 12:30:00] Cookie 刷新成功，下次刷新时间: 13:00:00
[2026-04-07 12:30:00] Cookie 刷新失败: 连接超时，重试中...
```

### 启动方式

```bash
# 命令行启动
python -m src.utils.cookie_refresher --interval 30

# 或作为后台服务
nohup python -m src.utils.cookie_refresher --interval 30 > /dev/null 2>&1 &
```

### 错误处理

1. **浏览器未启动**：等待浏览器启动后再尝试
2. **刷新失败**：记录错误日志，继续下次轮询
3. **Cookie 过期**：刷新后如果无效，记录警告但继续轮询

---

## 搜索问题修复

### 问题分析

搜索 100 个商品只返回 30 个的原因：

在 `_BrowserSearchImpl.search()` 中，响应监听器 `page.on("response", ...)` 在第一次设置后，翻页操作可能无法正确捕获新页面的 API 响应。

### 修复方案

在 `_next_page()` 方法中，翻页后重新设置响应监听器，确保能捕获新页面的搜索 API 响应。

```python
async def _next_page(self, page: int):
    """翻页（优化速度）"""
    # ... 翻页逻辑 ...

    # 翻页后重新设置响应监听器
    self._response_event.clear()
    self._captured_responses = []
    await self._setup_response_listener()
```

---

## 实施步骤

1. 创建 `src/utils/cookie_refresher.py` - 轮询刷新服务
2. 修改 `src/core.py` - 修复翻页时响应监听器问题
3. 更新 `config.json` - 添加轮询间隔配置项
4. 更新 README - 添加使用说明
