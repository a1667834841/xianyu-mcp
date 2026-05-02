"""
mcp_server/http_server.py - 闲鱼 MCP Server HTTP/SSE 入口
使用 FastMCP 实现 SSE 和 HTTP 传输
"""

import os
import sys
import json
import asyncio
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
    images_paths: str = "",
    title: str = "",
    current_price: float | None = None,
    original_price: float | None = None,
    shipping: str = "包邮",
    self_pickup: bool = False,
    post_price: float = 0,
) -> str:
    """发布商品到闲鱼
    
    Args:
        images_paths: 图片路径，多个用逗号分隔
        title: 商品标题
        current_price: 当前价格
        original_price: 原价
        shipping: 物流选项（包邮/按距离计费/一口价/无需邮寄）
        self_pickup: 是否支持自提
        post_price: 物流费用（一口价时使用）
    """
    client = get_client()
    
    # 解析图片路径
    paths = [p.strip() for p in images_paths.split(",") if p.strip()]
    if not paths:
        return json.dumps({"success": False, "message": "需要提供图片路径"}, ensure_ascii=False)
    
    price_dict = None
    if current_price or original_price:
        price_dict = {
            "current_price": current_price or 0,
            "original_price": original_price or 0,
        }
    
    result = await client.publish(
        images_paths=paths,
        title=title,
        price=price_dict,
        shipping=shipping,
        self_pickup=self_pickup,
        post_price=post_price,
    )
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
async def xianyu_get_detail(user_id: str | None = None, item_url: str = "") -> str:
    client = get_client()
    result = await client.get_detail(item_url=item_url)
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
async def xianyu_start_listener(user_id: str | None = None) -> str:
    """启动 WebSocket 消息监听"""
    client = get_client()
    result = await client.start_ws_listener()
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
async def xianyu_stop_listener(user_id: str | None = None) -> str:
    """停止 WebSocket 消息监听"""
    client = get_client()
    result = await client.stop_ws_listener()
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
async def xianyu_ws_send(user_id: str | None = None, target_id: str = "", content: str = "", image_url: str = "", conversation_id: str = "") -> str:
    """通过 WebSocket 发送消息"""
    client = get_client()
    if not target_id:
        return json.dumps({"success": False, "message": "需要提供 target_id"}, ensure_ascii=False)
    result = await client.ws_send_message(target_id, content, image_url, conversation_id)
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
async def xianyu_ws_status(user_id: str | None = None) -> str:
    """检查 WebSocket 连接状态"""
    client = get_client()
    connected = client.ws_is_connected()
    return json.dumps({"connected": connected}, ensure_ascii=False)


@mcp.tool()
async def xianyu_get_access_token(user_id: str | None = None) -> str:
    """获取 WebSocket accessToken"""
    client = get_client()
    try:
        token = await client.http_client.get_access_token()
        return json.dumps({"success": True, "access_token": token[:20] + "..." if token else ""}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "message": str(e)}, ensure_ascii=False)


@mcp.tool()
async def xianyu_list_conversations(user_id: str | None = None, limit: int = 20) -> str:
    """获取对话列表"""
    client = get_client()
    conversations = await client.list_conversations(limit=limit)
    result = [
        {
            "conversation_id": c.conversation_id,
            "user_id": c.user_id,
            "user_nick": c.user_nick,
            "last_message": c.last_message,
            "unread_count": c.unread_count,
        }
        for c in conversations
    ]
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
async def xianyu_create_conversation(
    user_id: str | None = None,
    item_url: str = "",
    seller_id: str = "",
) -> str:
    """创建对话"""
    client = get_client()
    conversation_id = await client.create_conversation(item_url=item_url, seller_id=seller_id)
    return json.dumps({"success": True, "conversation_id": conversation_id}, ensure_ascii=False)


@mcp.tool()
async def xianyu_get_messages(
    user_id: str | None = None,
    conversation_id: str = "",
    limit: int = 50,
) -> str:
    """获取消息历史"""
    client = get_client()
    result = await client.get_messages(conversation_id=conversation_id, limit=limit)
    messages = []
    for msg in result.get("messages", []):
        content = msg.content
        if content.type == "text":
            messages.append({
                "message_id": msg.message_id,
                "sender_id": msg.sender_id,
                "content": content.text,
                "timestamp": msg.timestamp,
            })
        elif content.type == "image":
            messages.append({
                "message_id": msg.message_id,
                "sender_id": msg.sender_id,
                "image_url": content.image_url,
                "timestamp": msg.timestamp,
            })
    return json.dumps({"messages": messages, "has_more": result.get("has_more")}, ensure_ascii=False, indent=2)


@mcp.tool()
async def xianyu_send_message(
    user_id: str | None = None,
    conversation_id: str = "",
    content: str = "",
    image_url: str = "",
) -> str:
    """发送消息"""
    client = get_client()
    result = await client.send_message(
        conversation_id=conversation_id,
        content=content,
        image_url=image_url,
    )
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


async def rest_login_poll(request):
    try:
        data = await request.json() if request.method == "POST" else {}
    except json.JSONDecodeError:
        data = {}
    try:
        client = get_client()
        t = data.get("t", "")
        ck = data.get("ck", "")
        if not t or not ck:
            return JSONResponse(
                {"success": False, "message": "缺少 t 或 ck 参数"},
                status_code=400,
            )
        result = await client.login_poll(t=t, ck=ck)
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
        Route("/rest/login_poll", rest_login_poll, methods=["POST"]),
        Route("/rest/check_session", rest_check_session, methods=["GET", "POST"]),
        Route("/rest/search", rest_search, methods=["POST"]),
    ]

    @asynccontextmanager
    async def lifespan(app):
        await initialize_manager()
        yield
        await asyncio.sleep(0.5)

    return Starlette(
        routes=rest_routes + list(mcp.sse_app().routes),
        middleware=middleware,
        lifespan=lifespan,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(build_app(), host=MCP_HOST, port=MCP_PORT)
