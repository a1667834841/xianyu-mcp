# 闲鱼 MCP 服务

基于 API 优先架构的闲鱼自动化工具。

## 功能

- **单用户模式**：全局维护一个用户会话
- **API 优先**：搜索、详情、会话管理使用 HTTP MTOP API
- **WebSocket 消息**：实时消息收发
- **浏览器辅助**：登录、发布、验证码恢复等场景可结合浏览器能力

## MCP 工具

| 工具 | 描述 |
|------|------|
| `xianyu_login` | 登录闲鱼账号 |
| `xianyu_check_session` | 检查登录态 |
| `xianyu_refresh_token` | 刷新 Token |
| `xianyu_search` | 搜索商品 |
| `xianyu_suggest_keywords` | 获取搜索联想词 |
| `xianyu_get_detail` | 获取商品详情 |
| `xianyu_publish` | 发布商品 |
| `xianyu_publish_from_item_url` | 按商品链接铺货 |
| `xianyu_create_conversation` | 创建对话 |
| `xianyu_ws_send` | 通过 WebSocket 发送消息 |
| `xianyu_ws_status` | 查看 WebSocket 连接状态 |
| `xianyu_list_conversations` | 获取对话列表 |
| `xianyu_get_messages` | 获取消息历史 |

## 测试

```bash
# 运行所有测试
pytest -v

# 运行单元测试
pytest -v -m unit

# 运行集成测试
pytest -v -m integration
```
