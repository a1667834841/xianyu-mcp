# 闲鱼助手

闲鱼店铺自动化工作流 - 支持搜索商品、分析对标、仿写文案、自动发布。

## 功能

- **登录能力** (`xianyu-login`) - 扫码登录获取 Token，Cookie 快照持久化到用户目录
- **后台保活** - MCP Server 启动后在独立 `keepalive_page` 上按间隔刷新首页，自动落盘最新 Cookie
- **搜索能力** (`xianyu-search`) - 优先使用页面上下文内的 sign 感知 API 搜索，失败时自动回退到页面交互搜索；返回结果包含 `stop_reason`、`engine_used`、`fallback_reason`、`pages_fetched`
- **发布能力** (`xianyu-publish`) - 根据对标商品链接自动复制并发布
- **会话管理** (`xianyu-check-session`, `xianyu-refresh-token`) - Cookie 校验和 Token 刷新

## 持久化目录

- 浏览器 Profile: `/data/users/<user_id>/chrome-profile`
- Cookie 快照: `/data/users/<user_id>/tokens/token.json`

Docker 环境可通过以下变量控制：

- `XIANYU_HOST_DATA_DIR`
- `XIANYU_USER_ID`
- `XIANYU_KEEPALIVE_ENABLED`
- `XIANYU_KEEPALIVE_INTERVAL_MINUTES`
- `XIANYU_SEARCH_MAX_STALE_PAGES`

## 快速开始

### 1. 准备环境

```bash
cp .env.example .env
# 按需填写 Cloudflare R2 配置；如果已有 .env，保留现有内容即可
```

### 2. 启动服务

```bash
docker compose up -d
docker compose ps
```

### 3. 验证服务

```bash
curl --max-time 5 http://localhost:8080/sse
curl --max-time 5 http://localhost:8080/rest/check_session
```

### 4. 首次登录

首次使用时调用 `xianyu_login` 获取二维码，扫码后再调用 `xianyu_check_session` 确认登录状态。

## MCP + Skills 接入

服务启动后，可接入闲鱼 MCP Server 和 Skills，详见安装文档：

| 客户端 | 安装文档 | 说明 |
|--------|----------|------|
| [OpenCode](docs/opencode-setup.md) | 接入闲鱼 MCP Server 并加载闲鱼 Skills | 配置文件：`opencode.json` |
| [Claude Code](docs/claude-code-setup.md) | 接入闲鱼 MCP Server 并加载闲鱼 Skills | 配置文件：`.mcp.json` 或 `~/.claude.json` |

**核心配置：**
- MCP 端点：`http://127.0.0.1:8080/sse`
- Skills：项目已包含 `.claude/skills/xianyu-skill/SKILL.md`，自动被发现

### 兼容/调试模式

如需旧版本地调试，可参考仓库内旧入口自行运行，但这不是推荐部署方式。

## 可选：使用远程镜像部署

```bash
docker login --username=ggball0227 registry.cn-hangzhou.aliyuncs.com
docker compose pull
docker compose up -d
```

默认镜像：`registry.cn-hangzhou.aliyuncs.com/ggball/xianyu-mcp:latest`

## 注意事项

1. **浏览器要求** - 需要安装 Google Chrome
2. **Token 有效期** - Token 约 24 小时过期，过期需重新扫码
3. **发布频率** - 避免短时间内大量发布，可能触发风控
4. **图片版权** - 使用对标商品图片时请确保合规

## 开发参考

面向直接调用或二次开发：

- 统一入口：`XianyuApp`
- 常用方法：`login`、`search`、`publish`、`refresh_token`、`check_session`
- MCP 服务入口：`mcp_server/server.py`
- 详细底层实现见 `src/` 与 `tests/`

简例：

```python
from xianyu import XianyuApp

async with XianyuApp() as app:
    await app.login()
    items = await app.search("机械键盘", rows=10)
```

### 可用工具

| 工具名称 | 功能描述 | 参数 |
|---------|---------|------|
| `xianyu_login` | 扫码登录获取 Token，支持跨平台二维码返回（Base64/ASCII/Text/公网URL） | 无 |
| `xianyu_search` | 搜索商品 | `keyword`, `rows`, `min_price`, `max_price`, `free_ship`, `sort_field`, `sort_order` |
| `xianyu_publish` | 根据链接复制发布 | `item_url`, `new_price`, `new_description`, `condition` |

### 使用示例

在 Claude Code 中：

```
帮我搜索 5 个哭娃系列商品
```

```
根据这个商品链接发布商品：https://www.goofish.com/item?id=xxx，价格改成 150 元
```

```
帮我登录闲鱼账号
```

**登录返回值说明：**

登录成功后返回二维码数据包：

```json
{
  "success": true,
  "qr_code": {
    "url": "https://passport.goofish.com/qrcodeCheck.htm?lgToken=xxx",
    "public_url": "https://img.ggball.top/xianyu/qr-xxx.png",
    "text": "https://..."
  },
  "message": "请扫码登录"
}
```

**扫码方式：**
- 访问 `public_url` 打开二维码图片，用闲鱼 APP 扫码

**终端环境登录示例：**

```bash
# 调用登录
python -c "from xianyu import login; import asyncio; asyncio.run(login())"

# 输出：
============================================================
                    请打开闲鱼 APP 扫码登录
============================================================

█▀▀▀▀▀▀▀█  █▀█▀█  █▀▀▀▀▀▀█
█ ███ █  ▀█▄▀▄▀█  █ ███ █
█▀▀▀▀▀▀▀█  ▀█▄█▀  █▀▀▀▀▀▀▀█

============================================================
提示：如果无法扫码，请复制下方 URL 到浏览器打开
https://passport.goofish.com/qrcodeCheck.htm?lgToken=xxx
============================================================
```

## License

MIT
