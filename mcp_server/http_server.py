"""
mcp_server/http_server.py - 闲鱼 MCP Server HTTP/SSE 入口
使用 FastMCP 实现 SSE 和 HTTP 传输
"""

import os
import sys
import json
from contextlib import asynccontextmanager
from dataclasses import asdict

from mcp.server.fastmcp import FastMCP
from starlette.responses import JSONResponse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.browser_pool import BrowserPoolSettings
from src.multi_user_manager import MultiUserManager
from src.multi_user_registry import MultiUserRegistry
from src.settings import load_raw_config

CDP_HOST = os.environ.get("CDP_HOST", "chrome-headless")
CDP_PORT = int(os.environ.get("CDP_PORT", "9222"))
MCP_HOST = os.environ.get("MCP_HOST", "0.0.0.0")
MCP_PORT = int(os.environ.get("MCP_PORT", "8080"))

print(f"[MCP HTTP] 服务端口={MCP_PORT}")

_manager = None


def get_manager():
    global _manager
    if _manager is None:
        pool = BrowserPoolSettings.from_config(load_raw_config())
        registry = MultiUserRegistry(pool)
        _manager = MultiUserManager(pool_settings=pool, registry=registry)
    return _manager


async def initialize_manager() -> None:
    manager = get_manager()
    if hasattr(manager, "ensure_initialized"):
        await manager.ensure_initialized()


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
    entry = get_manager().create_user(display_name)
    return json.dumps(
        {
            "success": True,
            "user_id": entry.user_id,
            "display_name": entry.display_name,
            "slot_id": entry.slot_id,
            "cdp_port": entry.cdp_port,
            "status": entry.status,
        },
        ensure_ascii=False,
    )


@mcp.tool()
async def xianyu_login(user_id: str | None = None) -> str:
    manager = get_manager()
    if user_id is None:
        payload = await manager.debug_login()
    else:
        payload = await manager.login(user_id)
        payload["selected_by"] = "explicit"
        user_status = manager.get_user_status(payload["user_id"])
        payload["slot_id"] = user_status.get("slot_id", "") if user_status else ""
    return json.dumps(payload, ensure_ascii=False)


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
async def xianyu_suggest_keywords(input_words: str = "x") -> str:
    result = await get_manager().suggest_keywords(input_words=input_words)
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
async def xianyu_publish(
    user_id: str,
    item_url: str,
    title: str | None = None,
    description: str | None = None,
    price: float | None = None,
    original_price: float | None = None,
    condition: str = "全新",
) -> str:
    result = await get_manager().publish(
        user_id=user_id,
        item_url=item_url,
        new_title=title,
        new_description=description,
        new_price=price,
        original_price=original_price,
        condition=condition,
    )
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
async def xianyu_get_detail(user_id: str, item_url: str) -> str:
    """获取商品详情。根据商品链接获取标题、描述、价格、分类、图片等信息。

    参数：
    - user_id: 用户ID（必填）
    - item_url: 商品链接，如 https://www.goofish.com/item?id=123456789
    """
    result = await get_manager().get_detail(user_id=user_id, item_url=item_url)
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
async def xianyu_refresh_token(user_id: str) -> str:
    return json.dumps(await get_manager().refresh_token(user_id), ensure_ascii=False)


@mcp.tool()
async def xianyu_check_session(user_id: str) -> str:
    return json.dumps(await get_manager().check_session(user_id), ensure_ascii=False)


@mcp.tool()
async def xianyu_browser_overview(user_id: str | None = None) -> str:
    manager = get_manager()
    try:
        overview = await manager.debug_browser_overview(user_id=user_id)
        response = {"success": True, **overview}
    except RuntimeError as exc:
        response = {"success": False, "message": str(exc)}
    return json.dumps(response, ensure_ascii=False)


@mcp.tool()
async def xianyu_debug_snapshot(
    user_id: str | None = None,
    full_page: bool = True,
) -> str:
    payload = await get_manager().debug_snapshot(user_id=user_id, full_page=full_page)
    return json.dumps(payload, ensure_ascii=False)


async def rest_login(request):
    try:
        data = await request.json() if request.method == "POST" else {}
    except json.JSONDecodeError:
        data = {}
    try:
        result = await get_manager().debug_login(data.get("user_id"))
        return JSONResponse(result)
    except RuntimeError as exc:
        message = str(exc)
        status_code = 409 if message == "no_available_user" else 500
        return JSONResponse(
            {"success": False, "error": message, "message": message},
            status_code=status_code,
        )


async def rest_check_session(request):
    try:
        data = await request.json() if request.method == "POST" else {}
    except json.JSONDecodeError:
        data = {}
    try:
        result = await get_manager().debug_check_session(data.get("user_id"))
        return JSONResponse(
            {
                "success": True,
                "user_id": result["user_id"],
                "slot_id": result["slot_id"],
                "selected_by": result["selected_by"],
                "valid": result["valid"],
                "message": "Cookie 有效" if result["valid"] else "Cookie 已过期",
                "last_updated_at": result.get("last_updated_at"),
            }
        )
    except RuntimeError as exc:
        message = str(exc)
        status_code = 409 if message == "no_available_user" else 500
        return JSONResponse(
            {"success": False, "error": message, "message": message},
            status_code=status_code,
        )


async def rest_search(request):
    data = await request.json()
    try:
        result = await get_manager().debug_search(
            keyword=data.get("keyword", ""),
            user_id=data.get("user_id"),
            rows=data.get("rows", 30),
            min_price=data.get("min_price"),
            max_price=data.get("max_price"),
            free_ship=data.get("free_ship", False),
            sort_field=data.get("sort_field", ""),
            sort_order=data.get("sort_order", ""),
        )
        return JSONResponse(result)
    except RuntimeError as exc:
        message = str(exc)
        status_code = 409 if message == "no_available_user" else 500
        return JSONResponse(
            {"success": False, "error": message, "message": message},
            status_code=status_code,
        )


def build_app():
    from starlette.applications import Starlette
    from starlette.middleware import Middleware
    from starlette.middleware.cors import CORSMiddleware
    from starlette.routing import Mount, Route

    middleware = [
        Middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )
    ]
    rest_routes = [
        Route("/rest/login", rest_login, methods=["GET", "POST"]),
        Route("/rest/check_session", rest_check_session, methods=["GET", "POST"]),
        Route("/rest/search", rest_search, methods=["POST"]),
    ]

    @asynccontextmanager
    async def lifespan(app):
        await initialize_manager()
        yield

    return Starlette(
        routes=rest_routes + [Mount("/", app=mcp.sse_app())],
        middleware=middleware,
        lifespan=lifespan,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(build_app(), host=MCP_HOST, port=MCP_PORT)
