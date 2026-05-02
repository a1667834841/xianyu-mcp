# WebSocket 消息收发设计文档

## 目标

实现闲鱼 WebSocket 消息收发功能，集成到 MCP 服务。

## 架构

### 组件划分

1. **WebSocketClient** - WebSocket 连接管理
2. **MessageCodec** - 消息编码/解码（基于 myfish message.py）
3. **MCP Tools** - MCP 工具接口

### 数据流

```
用户 → MCP Tool → WebSocketClient → wss://wss-goofish.dingtalk.com/
                                            ↓
                                       消息接收 → SSE 推送 → 用户
```

## WebSocket 连接流程

### 1. 获取 accessToken

调用 API: `mtop.taobao.idlemessage.pc.login.token`

```json
{
  "appKey": "444e9908a51d1cb236a27862abc769c9",
  "deviceId": "<device_id>"
}
```

返回: `accessToken`

### 2. WebSocket 连接

URL: `wss://wss-goofish.dingtalk.com/`

Headers:
```
Cookie: <cookies_str>
Host: wss-goofish.dingtalk.com
Origin: https://www.goofish.com
User-Agent: Mozilla/5.0 ...
```

### 3. 注册消息

```json
{
  "lwp": "/reg",
  "headers": {
    "app-key": "444e9908a51d1cb236a27862abc769c9",
    "token": "<accessToken>",
    "did": "<device_id>",
    "mid": "<random_mid>"
  }
}
```

### 4. 同步状态

```json
{
  "lwp": "/r/SyncStatus/ackDiff",
  "headers": {"mid": "<mid>"},
  "body": [{
    "pipeline": "sync",
    "channel": "sync",
    "topic": "sync",
    "pts": <timestamp>,
    "seq": 0
  }]
}
```

### 5. 心跳

每 15 秒发送: `{"lwp": "/!", "headers": {"mid": "<mid>"}}`

## 消息发送

### 发送消息格式

```json
{
  "lwp": "/r/MessageSend/sendByReceiverScope",
  "headers": {"mid": "<mid>"},
  "body": [
    {
      "uuid": "<uuid>",
      "cid": "<conversation_id>@goofish",
      "conversationType": 1,
      "content": {
        "contentType": 101,
        "custom": {
          "type": 2,
          "data": "<base64_encoded_content>"
        }
      }
    },
    {
      "actualReceivers": ["<target_id>@goofish", "<my_id>@goofish"]
    }
  ]
}
```

### 内容编码

文本消息:
```json
{"contentType": 1, "text": {"text": "消息内容"}}
```

图片消息:
```json
{"contentType": 2, "image": {"pics": [{"url": "...", "width": 100, "height": 100}]}}
```

Base64 编码后放入 `custom.data`。

## 消息接收

### 解析流程

1. 接收 WebSocket 消息
2. 发送 ACK 确认
3. 解析 `syncPushPackage`
4. 解密消息数据（必要时）
5. 解析为 MessageChain
6. 通过 SSE 推送给 MCP 客户端

### ACK 格式

```json
{
  "code": 200,
  "headers": {
    "mid": "<request_mid>",
    "sid": "<request_sid>"
  }
}
```

## MCP 工具设计

### 1. xianyu_start_listener

启动 WebSocket 监听

**参数**: 无

**返回**: 
```json
{"success": true, "message": "监听已启动"}
```

### 2. xianyu_send_message

发送消息

**参数**:
- `target_id`: 目标用户 ID
- `content`: 消息内容
- `image_url`: 图片 URL（可选）
- `conversation_id`: 对话 ID（可选）

**返回**:
```json
{"success": true, "message": "消息已发送"}
```

### 3. xianyu_stop_listener

停止 WebSocket 监听

**参数**: 无

**返回**:
```json
{"success": true, "message": "监听已停止"}
```

### 4. xianyu_get_access_token

获取 accessToken（调试用）

**参数**: 无

**返回**:
```json
{"success": true, "access_token": "..."}
```

## 错误处理

| 错误 | 处理方式 |
|------|---------|
| WebSocket 断开 | 3 秒后自动重连 |
| accessToken 失效 | 重新获取 |
| 消息发送失败 | 返回错误信息 |

## 测试验证

1. 启动监听 → 检查连接状态
2. 发送文本消息 → 验证对方收到
3. 发送图片消息 → 验证图片显示
4. 接收消息 → 验证 SSE 推送

## 文件修改清单

| 文件 | 操作 |
|------|------|
| `src/api/websocket_client.py` | 新建 |
| `src/api/message_codec.py` | 新建 |
| `src/api/client.py` | 修改（添加 WebSocket 方法） |
| `mcp_server/http_server.py` | 修改（添加 MCP 工具） |