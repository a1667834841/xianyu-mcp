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

from src.api.client import XianyuApiClient
from src.settings import load_settings

CDP_HOST = os.environ.get("CDP_HOST", "chrome-headless")
CDP_PORT = int(os.environ.get("CDP_PORT", "9222"))
MCP_HOST = os.environ.get("MCP_HOST", "0.0.0.0")
MCP_PORT = int(os.environ.get("MCP_PORT", "8080"))

print(f"[MCP HTTP] 服务端口={MCP_PORT}")

_client = None

def get_client():
    global _client
    if _client is None:
        _client = XianyuApiClient()
    return _client


async def initialize_manager() -> None:
    pass


mcp = FastMCP(
    name="xianyu-mcp",
    host=MCP_HOST,
    port=MCP_PORT,
    message_path="/messages/",
    streamable_http_path="/mcp",
)


@mcp.tool()
async def xianyu_login(user_id: str | None = None) -> str:
    client = get_client()
    payload = await client.login()
    return json.dumps(payload, ensure_ascii=False)


@mcp.tool()
async def xianyu_check_session(user_id: str | None = None) -> str:
    client = get_client()
    result = await client.check_session()
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
async def xianyu_refresh_token(user_id: str | None = None) -> str:
    client = get_client()
    result = await client.refresh_token()
    return json.dumps(result, ensure_ascii=False)


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
    client = get_client()
    result = await client.search(
        keyword=keyword,
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
    client = get_client()
    result = await client.http_client.suggest_keywords(input_words=input_words)
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
async def xianyu_publish(
    user_id: str | None = None,
    item_url: str = "",
    title: str | None = None,
    description: str | None = None,
    price: float | None = None,
    original_price: float | None = None,
    condition: str = "全新",
) -> str:
    client = get_client()
    result = await client.publish(
        item_url=item_url,
        new_title=title,
        new_description=description,
        new_price=price,
        original_price=original_price,
        condition=condition,
    )
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
async def xianyu_get_detail(user_id: str | None = None, item_url: str = "") -> str:
    client = get_client()
    result = await client.get_detail(item_url=item_url)
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
async def xianyu_browser_overview(user_id: str | None = None) -> str:
    client = get_client()
    try:
        overview = await client.browser_bridge.browser_overview()
        response = {"success": True, **overview}
    except RuntimeError as exc:
        response = {"success": False, "message": str(exc)}
    return json.dumps(response, ensure_ascii=False)


@mcp.tool()
async def xianyu_debug_snapshot(
    user_id: str | None = None,
    full_page: bool = True,
) -> str:
    client = get_client()
    try:
        payload = await client.browser_bridge.debug_snapshot(full_page=full_page)
        return json.dumps(payload, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


async def rest_login(request):
    try:
        data = await request.json() if request.method == "POST" else {}
    except json.JSONDecodeError:
        data = {}
    try:
        client = get_client()
        result = await client.login()
        return JSONResponse(result)
    except RuntimeError as exc:
        message = str(exc)
        status_code = 500
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
        client = get_client()
        result = await client.check_session()
        return JSONResponse(
            {
                "success": True,
                "valid": result.get("valid", False),
                "message": "Cookie 有效" if result.get("valid") else "Cookie 已过期",
                "last_updated_at": result.get("last_updated_at"),
            }
        )
    except RuntimeError as exc:
        message = str(exc)
        status_code = 500
        return JSONResponse(
            {"success": False, "error": message, "message": message},
            status_code=status_code,
        )


async def rest_search(request):
    data = await request.json()
    try:
        client = get_client()
        result = await client.search(
            keyword=data.get("keyword", ""),
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
        status_code = 500
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
