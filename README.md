# 闲鱼助手

闲鱼店铺自动化工作流 - 支持搜索商品、分析对标、仿写文案、自动发布。

## 目录结构

```
xianyu/
├── docker-compose.yml      # 部署入口
├── opencode.json           # OpenCode MCP 配置
├── .env.example            # 环境变量示例
│
├── docker/                 # Docker 构建文件
│   ├── Dockerfile          # MCP Server 镜像
│   └── browser.Dockerfile  # 浏览器容器镜像
│
├── mcp_server/             # MCP 服务实现
│   ├── server.py           # MCP 协议入口
│   └── http_server.py      # HTTP/SSE 服务入口
│
├── src/                    # 核心业务代码
│   ├── core.py             # 主业务逻辑
│   ├── session.py          # 会话管理
│   └── browser.py          # 浏览器控制
│
├── scripts/                # 工具脚本
│   └── mcp-dev             # MCP 调试 CLI
│
├── tests/                  # 测试文件
│
├── docs/                   # 详细文档
│   ├── mcp-e2e-regression.md    # 端到端回归手册
│   ├── opencode-setup.md        # OpenCode 接入
│   ├── claude-code-setup.md     # Claude Code 接入
│   ├── docker/README.md         # Docker 部署详解
│
├── .claude/skills/         # Skills 定义
│   └── xianyu-skill/SKILL.md    # 闲鱼技能文档
│
└── data/                   # 持久化数据（用户登录态）
```

## 使用流程

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   部署服务      │ -> │   接入客户端    │ -> │   业务操作      │
│  docker-compose │    │  OpenCode/      │    │  登录/搜索/     │
│                 │    │  Claude Code    │    │  发布           │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

### 1. 部署服务

```bash
cp .env.example .env
docker compose up -d
docker compose ps
```

### 2. 接入客户端

| 客户端 | 配置文件 | 文档 |
|--------|----------|------|
| OpenCode | `opencode.json` | [docs/opencode-setup.md](docs/opencode-setup.md) |
| Claude Code | `.mcp.json` | [docs/claude-code-setup.md](docs/claude-code-setup.md) |

### 3. 业务操作

在客户端中直接使用自然语言：

```
登录闲鱼账号
搜索盲盒商品 rows=5
发布商品 https://www.goofish.com/item?id=xxx 价格150
```

详细工具说明见 [.claude/skills/xianyu-skill/SKILL.md](.claude/skills/xianyu-skill/SKILL.md)

## 文档索引

| 场景 | 文档 |
|------|------|
| 部署详解 | [docker/README.md](docker/README.md) |
| 端到端回归 | [docs/mcp-e2e-regression.md](docs/mcp-e2e-regression.md) |
| Skills 详细说明 | [.claude/skills/xianyu-skill/SKILL.md](.claude/skills/xianyu-skill/SKILL.md) |
| MCP Dev CLI | [docs/mcp-dev-cheatsheet.md](docs/mcp-dev-cheatsheet.md) |
| 本地调试 | `./scripts/mcp-dev call xianyu_list_users` |

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `MCP_PORT` | MCP 服务端口 | `8080` |
| `BROWSER_POOL_SIZE` | Chrome 槽位数 | `1` |
| `XIANYU_KEEPALIVE_ENABLED` | 保活开关 | `true` |

详见 `.env.example`

## 注意事项

- Token 约 24 小时过期，需重新扫码
- 避免短时间大量发布，可能触发风控
- 图片使用需注意版权

## License

MIT