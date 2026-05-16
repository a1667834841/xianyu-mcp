# WS 风控本地调试记录

## 结论

- 风控可稳定复现在 `mtop.taobao.idlemessage.pc.login.token` 这个接口。
- 这个接口属于 WebSocket 初始化前的 `accessToken` 获取阶段，不是 WebSocket RPC 本身。
- 当前失败点不是“自动拖滑块失败”，而是把 `punish` URL 打开后直接进入错误页，页面没有滑块。

## 本次复现步骤

1. 用本地 Chrome profile 登录闲鱼。
2. 通过 `BrowserBridge` 读取浏览器 cookies，并写入独立调试目录。
3. 用调试目录里的 cookies 验证：
   - `check_session()` 返回有效
   - `search()` 返回正常商品列表
4. 做单次 WebSocket 启动验证：
   - `ensure_ws_started()` 可以成功
   - `list_conversations()` / `get_messages()` 也可成功
5. 做更贴近故障的反复 “WS 初始化” 压测。
6. 命中风控后，`accessToken` 接口返回：

```json
{
  "ret": [
    "FAIL_SYS_USER_VALIDATE",
    "RGV587_ERROR::SM::哎哟喂,被挤爆啦,请稍后重试"
  ],
  "data": {
    "url": "https://h5api.m.goofish.com:443//h5/mtop.taobao.idlemessage.pc.login.token/1.0/_____tmd_____/punish?...&action=captcha&pureCaptcha="
  }
}
```

## 现场表现

- 把 `data.url` 直接在本地 Chrome 打开后，没有出现滑块。
- 页面落到“抱歉，页面访问出现了问题”的错误页。
- 这说明当前链路里，`punish` URL 并没有成功转成可交互的验证码页面。

## 推断

- `punish` URL 很可能是一次性、短时效，或者依赖更完整的上下文。
- 仅把服务端请求返回的 `data.url` 拿到浏览器里直接打开，并不足以稳定进入验证码页。
- 当前 `CaptchaHandler -> SliderSolver` 假设“打开 `verification_url` 后就能看到滑块”，这个前提在 WS 风控场景下并不总成立。

## 建议的排查方向

1. 在 `HttpClient._handle_captcha()` 增加“人工调试模式”：
   - 不自动拖动
   - 完整记录 `ret`、`verification_url`、时间戳、cookie 关键字段
2. 在 `BrowserBridge` 里保留风控页现场，不要在失败时立刻 `close_page()`
3. 不要只依赖直接打开 `punish` URL
   - 优先尝试在已登录浏览器上下文里复现同一请求
   - 让浏览器自己拿到挑战页，而不是把服务端返回的 URL 当成最终页面
4. 单独记录 `x5sec` / `sec` 类 cookie 在触发前后的变化，确认真正完成风控解除依赖的是哪一个 cookie

## 可复现命令

```bash
.venv/bin/python scripts/repro_ws_captcha.py \
  --data-dir /Users/wuwenjing/Documents/xianyu-mcp/tmp-debug \
  --iterations 30 \
  --sleep 0.2
```

命中风控时，脚本会打印 `need_captcha: true` 和完整 `punish` URL。
