# 闲鱼 MCP 服务

基于 API 优先架构的闲鱼自动化工具，当前以 HTTP MTOP + WebSocket 为主，浏览器仅用于验证码恢复等辅助场景。

## 当前能力

- **多用户模式**：用户数据保存在 `data_root/<user_id>/user.json`，默认使用第一个 `active` 用户，而不是单独的总表 `user.json`。
- **登录与用户入库分两步**：`xianyu_show_qrcode` 或 `xianyu_login` 获取二维码与临时凭证，扫码确认后再通过 `xianyu_add_user(t, ck)` 正式创建用户。
- **API 优先**：搜索、详情、发布、Token 刷新都走 HTTP API。
- **WebSocket 消息能力**：支持会话创建、消息发送、会话列表、消息历史。
- **缓存回退**：`xianyu_list_conversations` 与 `xianyu_get_messages` 在 WebSocket 未连接或 RPC 失败时，会优先回退到本地缓存结果。
- **保活机制**：服务启动后会为 `active` 且 `keepalive_enabled=true` 的用户自动检查会话、刷新 Token，并尝试自动启动 WebSocket。
- **浏览器辅助**：当前主要用于验证码恢复和 Cookie 补救，不是发布主链路依赖。

## 与代码现状对齐后的说明

- README 之前写“发布可结合浏览器能力”，但当前 `xianyu_publish` 和 `xianyu_publish_from_item_url` 都是纯 HTTP 发布路径，没有浏览器发布兜底。
- README 之前写“删除用户”，但 `xianyu_delete_user` 的实际行为是停掉该用户保活/WebSocket，并把用户状态标记为 `disabled`，不会物理删除目录。
- 消息相关接口不是只返回实时结果；当 WebSocket 未连接或失败时，会返回缓存数据，并在响应里标记 `source: cache`。
- 铺货发布会解析源商品链接，优先取规格最低价，没有规格时退回主价格。
- 发布价格当前按“元”传入并发送，支持小数价格。

## MCP 工具

| 工具 | 描述 | 当前行为说明 |
|------|------|-------------|
| `xianyu_show_qrcode` | 获取登录二维码 | 始终创建待确认登录会话，返回 `t`、`ck` 后续用于 `xianyu_add_user` |
| `xianyu_login` | 登录闲鱼账号 | 若当前账号 Cookie 有效则直接返回已登录；否则返回二维码信息，并为指定用户启动后台轮询 |
| `xianyu_add_user` | 确认扫码并正式创建用户 | 只有扫码确认完成后才会把账号写入多用户目录 |
| `xianyu_check_session` | 检查登录态 | 指定 `user_id` 时检查单用户；不传时汇总所有 `active` 用户 |
| `xianyu_refresh_token` | 刷新 Token | 仅走 HTTP 路径 |
| `xianyu_search` | 搜索商品 | 支持 `rows`、价格区间、包邮、排序等参数 |
| `xianyu_suggest_keywords` | 获取搜索联想词 | 直接调用 HTTP 接口 |
| `xianyu_get_detail` | 获取商品详情 | 通过商品链接提取 `item_id` 后查询详情 |
| `xianyu_publish` | 发布商品 | 纯 HTTP 发布，价格参数按“元”传入，支持小数 |
| `xianyu_publish_from_item_url` | 按商品链接铺货 | 自动解析图片、标题、价格并调用发布接口 |
| `xianyu_create_conversation` | 创建对话 | 依赖 WebSocket 创建对话，成功后自动发送默认问候语 |
| `xianyu_ws_send` | 通过 WebSocket 发送消息 | 发送前会确保 WebSocket 已启动 |
| `xianyu_ws_status` | 查看 WebSocket 连接状态 | 返回连接状态、错误信息、启动时间 |
| `xianyu_list_conversations` | 获取对话列表 | 优先走 WebSocket RPC，失败时回退缓存 |
| `xianyu_get_messages` | 获取消息历史 | 优先走 WebSocket RPC，失败时回退缓存 |
| `xianyu_list_users` | 列出所有用户 | 会附带运行态信息，如 `ws_connected`、`keepalive_running` |
| `xianyu_delete_user` | 禁用用户 | 实际是标记为 `disabled`，并停止该用户保活/WS |

## 已知限制

- `xianyu_create_conversation` 目前要求 WebSocket 可用；这里没有 HTTP 创建对话兜底。
- `xianyu_list_conversations` / `xianyu_get_messages` 的缓存回退依赖本地 WebSocket 缓存，服务刚启动且尚无缓存时可能直接返回失败。
- `xianyu_delete_user` 不会删除本地用户目录、Cookie 或历史缓存，只是禁用账号。
- 浏览器依赖主要集中在验证码处理；如果远端 CDP/Playwright 不可用，验证码恢复能力会受影响。

## 测试

```bash
# 运行所有测试
pytest -v

# 运行 HttpClient 测试
pytest tests/test_api_http_client.py -q

# 运行 HTTP Server 单元测试
pytest tests/test_http_server_unit.py -q

# 运行多用户与铺货相关测试
pytest tests/test_api_client.py tests/test_sourcing_service.py -k "publish_from_item_url or sourcing_service" -q
```
