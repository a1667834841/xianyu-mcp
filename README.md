# 闲鱼 MCP Server

闲鱼店铺自动化工作流 - 支持搜索商品、分析对标、仿写文案、自动发布。

## 快速部署

### 前置条件

- Docker & Docker Compose
- Git

### 步骤

```bash
# 1. 克隆项目
git clone https://github.com/a1667834841/xianyu-mcp.git
cd xianyu-mcp

# 2. 配置环境变量
cp .env.example .env

# 3. 拉取镜像并启动
docker compose pull
docker compose up -d

# 4. 验证服务
docker compose ps
curl --max-time 5 http://localhost:8080/sse
```

服务启动后，MCP Server 监听 `http://127.0.0.1:8080/sse`。

## 客户端接入

### OpenCode

详见 [docs/opencode-setup.md](docs/opencode-setup.md)

### Claude Code

详见 [docs/claude-code-setup.md](docs/claude-code-setup.md)

### Skills 安装

详见 [docs/skills-setup.md](docs/skills-setup.md)

## 阿里云镜像

本项目使用阿里云镜像仓库，无需本地构建：

| 服务 | 镜像地址 |
|------|---------|
| MCP Server | `registry.cn-hangzhou.aliyuncs.com/ggball/xianyu-mcp:latest` |
| Browser | `registry.cn-hangzhou.aliyuncs.com/ggball/chrome-headless-shell-zh:multi` |

镜像为公开镜像，无需登录即可拉取。

## 目录结构

```
xianyu-mcp/
├── README.md                    # 主文档
├── docker-compose.yml           # 部署入口
├── opencode.json                # OpenCode MCP 配置
├── .mcp.json                    # Claude Code MCP 配置
├── .env.example                 # 环境变量示例
│
├── docs/                        # 详细文档
│   ├── opencode-setup.md        # OpenCode 安装指南
│   ├── claude-code-setup.md     # Claude Code 安装指南
│   ├── skills-setup.md          # Skills 安装详解
│   ├── docker/README.md         # Docker 部署详解
│   ├── mcp-e2e-regression.md    # 端到端回归手册
│   └── mcp-dev-cheatsheet.md    # MCP 调试手册
│
├── .claude/skills/              # Claude Code Skills
│   ├── xianyu-skill/SKILL.md
│   └── xianyu-hot-product-analysis/SKILL.md
│
├── docker/                      # Docker 构建文件
│   ├── Dockerfile               # MCP Server 镜像
│   └── browser.Dockerfile       # Browser 镜像
│
├── mcp_server/                  # MCP 服务实现
├── src/                         # 核心业务代码
├── scripts/                     # 工具脚本
└── tests/                       # 测试文件
```

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `MCP_PORT` | MCP 服务端口 | `8080` |
| `BROWSER_POOL_SIZE` | Chrome 槽位数 | `2` |
| `XIANYU_KEEPALIVE_ENABLED` | 保活开关 | `true` |
| `XIANYU_HOST_DATA_DIR` | 数据目录 | `./data` |

详见 `.env.example`

## 使用流程

```
部署服务 → 接入客户端 → 登录账号 → 搜索/发布
```

在客户端中使用自然语言：

```
登录闲鱼账号
搜索盲盒商品 rows=5
发布商品 https://www.goofish.com/item?id=xxx 价格150
```

## 文档索引

| 场景 | 文档 |
|------|------|
| 快速部署 | 本文档 |
| OpenCode 接入 | [docs/opencode-setup.md](docs/opencode-setup.md) |
| Claude Code 接入 | [docs/claude-code-setup.md](docs/claude-code-setup.md) |
| Skills 安装 | [docs/skills-setup.md](docs/skills-setup.md) |
| Docker 部署详解 | [docker/README.md](docker/README.md) |
| Skills 技能定义 | [.claude/skills/xianyu-skill/SKILL.md](.claude/skills/xianyu-skill/SKILL.md) |
| 端到端回归 | [docs/mcp-e2e-regression.md](docs/mcp-e2e-regression.md) |
| MCP Dev CLI | [docs/mcp-dev-cheatsheet.md](docs/mcp-dev-cheatsheet.md) |

## 注意事项

- Token 约 24 小时过期，需重新扫码
- 避免短时间大量发布，可能触发风控
- 图片使用需注意版权

## License

MIT
