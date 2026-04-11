"""
mcp_server/http_server.py - 闲鱼 MCP Server HTTP/SSE 入口
使用 FastMCP 实现 SSE 和 HTTP 传输
"""

import os
import sys
import json
from dataclasses import asdict

from mcp.server.fastmcp import FastMCP

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import XianyuApp
from src.browser import AsyncChromeManager

# 配置：从环境变量读取
CDP_HOST = os.environ.get("CDP_HOST", "chrome-headless")
CDP_PORT = int(os.environ.get("CDP_PORT", "9222"))
MCP_HOST = os.environ.get("MCP_HOST", "0.0.0.0")
MCP_PORT = int(os.environ.get("MCP_PORT", "8080"))

print(f"[MCP HTTP] 服务端口={MCP_PORT}")

# 全局 MultiUserManager 实例（懒加载）
_manager = None


def get_manager():
    """获取或创建 MultiUserManager 实例"""
    global _manager
    if _manager is None:
        from src.browser_pool import BrowserPoolSettings
        from src.multi_user_manager import MultiUserManager
        from src.multi_user_registry import MultiUserRegistry
        from src.settings import load_raw_config

        raw = load_raw_config()
        pool = BrowserPoolSettings.from_config(raw)
        registry = MultiUserRegistry(pool)
        _manager = MultiUserManager(pool_settings=pool, registry=registry)
    return _manager


# 全局 XianyuApp 实例（懒加载）- 用于单用户操作
_app = None


def get_app():
    """获取或创建 XianyuApp 实例（单用户模式兼容）"""
    global _app
    if _app is None:
        browser = AsyncChromeManager(
            host=CDP_HOST,
            port=CDP_PORT,
            auto_start=False,
        )
        _app = XianyuApp(browser)
        _app.start_background_tasks()
    return _app


# 创建 FastMCP 服务
mcp = FastMCP(
    name="xianyu-mcp",
    host=MCP_HOST,
    port=MCP_PORT,
    sse_path="/sse",
    message_path="/messages/",
    streamable_http_path="/mcp",
)


@mcp.tool()
async def xianyu_create_user(display_name: str | None = None) -> str:
    entry = get_manager().create_user(display_name=display_name)
    return json.dumps(
        {
            "success": True,
            "user_id": entry.user_id,
            "slot_id": entry.slot_id,
            "cdp_port": entry.cdp_port,
            "status": entry.status,
        },
        ensure_ascii=False,
    )


@mcp.tool()
async def xianyu_list_users() -> str:
    return json.dumps(
        {"success": True, "users": get_manager().list_user_statuses()},
        ensure_ascii=False,
    )


@mcp.tool()
async def xianyu_get_user_status(user_id: str) -> str:
    return json.dumps(
        {"success": True, **get_manager().get_user_status(user_id)}, ensure_ascii=False
    )


@mcp.tool()
async def xianyu_login(user_id: str) -> str:
    """
    扫码登录闲鱼账号，获取 Token。Token 有效期约 24 小时。

    返回：
    - 登录成功：{"success": true, "token": "..."}
    - 需要扫码：{"success": true, "qr_code": {...}, "need_qr": true, "message": "请扫码登录"}
    - 登录失败：{"success": false, "message": "..."}
    """
    return json.dumps(await get_manager().login(user_id), ensure_ascii=False)


@mcp.tool()
async def xianyu_search(
    keyword: str,
    user_id: str | None = None,
    rows: int = 30,
    min_price: float | None = None,
    max_price: float | None = None,
    free_ship: bool = False,
    sort_field: str = "",
    sort_order: str = "",
) -> str:
    """
    通过关键词搜索闲鱼商品，返回目标数量内的唯一商品列表。

    Args:
        keyword: 搜索关键词
        user_id: 用户 ID（可选，默认使用就绪用户）
        rows: 目标唯一商品总数，默认 30
        min_price: 最低价格（可选）
        max_price: 最高价格（可选）
        free_ship: 是否只看包邮，默认 false
        sort_field: 排序字段：pub_time（发布时间）或 price（价格）
        sort_order: 排序方向：ASC（升序）或 DESC（降序）
    """
    result = await get_manager().search(
        keyword=keyword,
        user_id=user_id,
        rows=rows,
        min_price=min_price,
        max_price=max_price,
        free_ship=free_ship,
        sort_field=sort_field,
        sort_order=sort_order,
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
async def xianyu_publish(
    user_id: str,
    item_url: str,
    new_price: float | None = None,
    new_description: str | None = None,
    condition: str = "全新",
) -> str:
    """
    根据商品链接复制发布商品。自动获取对标商品数据（标题、描述、图片、分类等），填充发布表单。潮玩盲盒等特殊类目会自动保存草稿。

    Args:
        user_id: 用户 ID
        item_url: 对标商品链接，如 https://www.goofish.com/item?id=123456789
        new_price: 新商品价格（可选，默认使用原价）
        new_description: 新商品描述（可选，默认使用原描述）
        condition: 成色，默认全新，可选值：全新、几乎全新、9 成新、8 成新、7 成新
    """
    result = await get_manager().publish(
        user_id=user_id,
        item_url=item_url,
        new_price=new_price,
        new_description=new_description,
        condition=condition,
    )
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
async def xianyu_refresh_token(user_id: str) -> str:
    """
    刷新闲鱼 Token。通过访问闲鱼首页获取最新的 Token，当 Token 过期或需要更新时调用。
    """
    return json.dumps(await get_manager().refresh_token(user_id), ensure_ascii=False)


@mcp.tool()
async def xianyu_check_session(user_id: str) -> str:
    """
    检查闲鱼 Cookie 是否有效。调用用户信息接口验证当前登录状态。
    """
    return json.dumps(await get_manager().check_session(user_id), ensure_ascii=False)


@mcp.tool()
async def xianyu_browser_overview() -> str:
    """
    获取当前浏览器 context 数量，以及各 context 下页面标题和 URL。
    """
    app = get_app()

    try:
        overview = await app.browser_overview()
        response = {"success": True, **overview}
    except RuntimeError as exc:
        response = {"success": False, "message": str(exc)}

    return json.dumps(response, ensure_ascii=False)


@mcp.tool()
async def xianyu_show_qr(user_id: str) -> str:
    """
    显示登录二维码。访问闲鱼首页，如果未登录则显示二维码；如果已登录则直接返回。用户扫码后浏览器会自动跳转完成登录。
    """
    return json.dumps(await get_manager().show_qr(user_id), ensure_ascii=False)


if __name__ == "__main__":
    import asyncio
    from starlette.applications import Starlette
    from starlette.routing import Route, Mount
    from starlette.responses import JSONResponse

    print(f"[MCP HTTP] 启动闲鱼 MCP Server (SSE 模式)")
    print(f"[MCP HTTP] SSE 端点: http://{MCP_HOST}:{MCP_PORT}/sse")
    print(f"[MCP HTTP] HTTP 端点: http://{MCP_HOST}:{MCP_PORT}/mcp")

    # 创建简单的 REST endpoints 用于调试
    async def rest_show_qr(request):
        """REST endpoint: 显示二维码"""
        try:
            app = get_app()
            result = await app.show_qr_code()
            return JSONResponse(result)
        except Exception as e:
            return JSONResponse({"success": False, "message": str(e)}, status_code=500)

    async def rest_check_session(request):
        """REST endpoint: 检查会话"""
        try:
            app = get_app()
            session_status = await app.check_session()
            is_valid = session_status["valid"]
            return JSONResponse(
                {
                    "success": True,
                    "valid": is_valid,
                    "message": "Cookie 有效" if is_valid else "Cookie 已过期",
                    "last_updated_at": session_status.get("last_updated_at"),
                }
            )
        except Exception as e:
            return JSONResponse({"success": False, "message": str(e)}, status_code=500)

    async def rest_search(request):
        """REST endpoint: 搜索商品"""
        try:
            data = await request.json()
            app = get_app()
            await app.browser.ensure_running()
            outcome = await app.search_with_meta(
                keyword=data.get("keyword", ""),
                rows=data.get("rows", 30),
                min_price=data.get("min_price"),
                max_price=data.get("max_price"),
                free_ship=data.get("free_ship", False),
                sort_field=data.get("sort_field", ""),
                sort_order=data.get("sort_order", ""),
            )
            items = [asdict(item) for item in outcome.items]
            return JSONResponse(
                {
                    "success": True,
                    "requested": outcome.requested_rows,
                    "total": outcome.returned_rows,
                    "stop_reason": outcome.stop_reason,
                    "stale_pages": outcome.stale_pages,
                    "items": items,
                }
            )
        except Exception as e:
            return JSONResponse({"success": False, "message": str(e)}, status_code=500)

    # 添加REST路由
    rest_routes = [
        Route("/rest/show_qr", rest_show_qr, methods=["GET", "POST"]),
        Route("/rest/check_session", rest_check_session, methods=["GET", "POST"]),
        Route("/rest/search", rest_search, methods=["POST"]),
    ]

    # 使用自定义Starlette app包装MCP
    from starlette.middleware import Middleware
    from starlette.middleware.cors import CORSMiddleware

    middleware = [
        Middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )
    ]

    # 获取MCP的ASGI app
    mcp_app = mcp.sse_app()

    # 组合路由
    app = Starlette(
        routes=rest_routes + [Mount("/", app=mcp_app)], middleware=middleware
    )

    import uvicorn

    uvicorn.run(app, host=MCP_HOST, port=MCP_PORT)
