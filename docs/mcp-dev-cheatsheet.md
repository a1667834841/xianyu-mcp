# mcp-dev 速查表

`scripts/mcp-dev` 用于直接调用本地 MCP 方法，避免反复手写临时 Python 或 `docker exec`。

## 基本格式

```bash
./scripts/mcp-dev call <tool-name> [--key value ...]
```

参数规则：

- `--user-id user-001` -> `user_id="user-001"`
- `--rows 5` -> `rows=5`
- `--free-ship true` -> `free_ship=true`
- `--max-price null` -> `max_price=null`

## 默认目标

默认请求地址：

```bash
http://127.0.0.1:${MCP_HOST_PORT:-8080}/mcp
```

如果该 `/mcp` 地址返回 `404`，脚本会自动回退到对应的 `/sse` 流程。

也可以手动指定目标：

```bash
MCP_DEV_URL=http://127.0.0.1:18090/mcp ./scripts/mcp-dev call xianyu_list_users
```

## 最常用命令

查看用户和槽位：

```bash
./scripts/mcp-dev call xianyu_list_users
```

查看单个用户状态：

```bash
./scripts/mcp-dev call xianyu_get_user_status --user-id user-001
```

检查登录态：

```bash
./scripts/mcp-dev call xianyu_check_session --user-id user-001
```

生成二维码：

```bash
./scripts/mcp-dev call xianyu_show_qr --user-id user-001
```

指定用户搜索：

```bash
./scripts/mcp-dev call xianyu_search --user-id user-001 --keyword 机械键盘 --rows 5
```

指定用户发布：

```bash
./scripts/mcp-dev call xianyu_publish --user-id user-001 --item-url "https://www.goofish.com/item?id=123"
```

## E2E 栈

如果要调用 E2E 栈，带上 `MCP_DEV_URL`：

```bash
MCP_DEV_URL=http://127.0.0.1:18090/mcp ./scripts/mcp-dev call xianyu_list_users
MCP_DEV_URL=http://127.0.0.1:18090/mcp ./scripts/mcp-dev call xianyu_check_session --user-id user-001
MCP_DEV_URL=http://127.0.0.1:18090/mcp ./scripts/mcp-dev call xianyu_show_qr --user-id user-001
MCP_DEV_URL=http://127.0.0.1:18090/mcp ./scripts/mcp-dev call xianyu_search --user-id user-001 --keyword 机械键盘 --rows 5
```

## 推荐测试流程

1. 看当前用户和槽位

```bash
./scripts/mcp-dev call xianyu_list_users
```

2. 查目标用户登录态

```bash
./scripts/mcp-dev call xianyu_check_session --user-id user-001
```

3. 如果失效，重新出二维码

```bash
./scripts/mcp-dev call xianyu_show_qr --user-id user-001
```

4. 扫码后再次确认

```bash
./scripts/mcp-dev call xianyu_check_session --user-id user-001
```

5. 跑一次真实搜索验证业务可用

```bash
./scripts/mcp-dev call xianyu_search --user-id user-001 --keyword 机械键盘 --rows 3
```

## 当前环境注意事项

- 主栈如果没有完整 R2 凭证，`xianyu_show_qr` 可能只返回原始 `qrcodeCheck` 链接
- 如果需要 `https://img.ggball.top/...` 这种公网二维码，优先用带 `MCP_DEV_URL=http://127.0.0.1:18090/mcp` 的 E2E 栈
