"""
mcp_server/http_server.py - 闲鱼 MCP Server HTTP/SSE 入口
使用 FastMCP 实现 SSE 和 HTTP 传输
"""

import os
import sys
import json
import asyncio
import logging
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Dict, List, Any

from mcp.server.fastmcp import FastMCP
from starlette.responses import JSONResponse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.api.client import XianyuApiClient
from src.settings import load_settings

logger = logging.getLogger(__name__)

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
    client = get_client()
    try:
        result = await client.check_session()
    except Exception as exc:
        logger.warning(f"[MCP HTTP] 启动时检查会话失败，跳过 WS 自动启动: {exc}")
        return

    if not result.get("valid"):
        logger.info("[MCP HTTP] Cookie 无效，跳过 WS 自动启动")
        return

    try:
        await client.ensure_ws_started(reason="service_start")
    except Exception as exc:
        logger.warning(f"[MCP HTTP] WS 自动启动失败，不阻塞服务启动: {exc}")


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
    return json.dumps(client.get_ws_status(), ensure_ascii=False)


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
    """获取对话列表（通过 WebSocket LWP 协议）
    
    注意：需要先启动 WebSocket 监听才能使用。
    使用 xianyu_start_listener 启动监听。
    
    Args:
        limit: 返回对话数量上限（默认 20）
    
    Returns:
        对话列表，每个对话包含：
        - cid: 对话 ID
        - peer_user_name: 对方用户名
        - last_message: 最后消息摘要
        - unread_count: 未读消息数
        - item_id: 商品 ID
    """
    client = get_client()
    
    # 检查 WebSocket 是否连接
    if not client.ws_is_connected():
        return json.dumps({
            "success": False,
            "message": "WebSocket 未连接，请先调用 xianyu_start_listener"
        }, ensure_ascii=False)
    
    # 使用 WebSocket LWP 协议获取对话列表
    result = await client.ws_client.get_conversation_list(max_sort_index=None, page_size=limit)
    
    if not result.get("success"):
        return json.dumps(result, ensure_ascii=False)
    
    # 格式化返回
    conversations = []
    for conv in result.get("conversations", []):
        conversations.append({
            "conversation_id": conv.get("cid", ""),
            "user_id": conv.get("cid", ""),  # 闲鱼对话 ID 就是用户 ID
            "user_nick": conv.get("peer_user_name", ""),
            "last_message": conv.get("last_message", ""),
            "last_message_time": conv.get("last_message_time", 0),
            "unread_count": conv.get("unread_count", 0),
            "item_id": conv.get("item_id", ""),
        })
    
    return json.dumps({
        "success": True,
        "conversations": conversations,
        "hasMore": result.get("hasMore", False),
        "count": len(conversations),
    }, ensure_ascii=False, indent=2)


@mcp.tool()
async def xianyu_create_conversation(
    user_id: str | None = None,
    item_url: str = "",
    seller_id: str = "",
) -> str:
    """创建对话（已失效）"""
    return json.dumps({
        "success": False,
        "message": "此 API 已失效，请使用 xianyu_ws_send 直接发送消息"
    }, ensure_ascii=False)


@mcp.tool()
async def xianyu_get_messages(
    user_id: str | None = None,
    conversation_id: str = "",
    limit: int = 50,
) -> str:
    """获取消息历史（通过 WebSocket LWP 协议）
    
    注意：需要先启动 WebSocket 监听才能使用。
    使用 xianyu_start_listener 启动监听。
    
    Args:
        conversation_id: 对话 ID（从 xianyu_list_conversations 获取）
        limit: 返回消息数量上限（默认 50）
    
    Returns:
        消息列表，每个消息包含：
        - message_id: 消息 ID
        - sender_id: 发送者 ID
        - sender_name: 发送者昵称
        - content: 消息内容
        - timestamp: 消息时间戳
    """
    client = get_client()
    
    if not conversation_id:
        return json.dumps({
            "success": False,
            "message": "请提供 conversation_id（从 xianyu_list_conversations 获取）"
        }, ensure_ascii=False)
    
    # 检查 WebSocket 是否连接
    if not client.ws_is_connected():
        return json.dumps({
            "success": False,
            "message": "WebSocket 未连接，请先调用 xianyu_start_listener"
        }, ensure_ascii=False)
    
    # 使用 WebSocket LWP 协议获取消息历史
    result = await client.ws_client.get_message_history(
        chat_id=conversation_id,
        anchor=None,
        count=limit
    )
    
    if not result.get("success"):
        return json.dumps(result, ensure_ascii=False)
    
    # 格式化返回
    messages = []
    for msg in result.get("messages", []):
        messages.append({
            "message_id": msg.get("message_id", ""),
            "sender_id": msg.get("sender_id", ""),
            "sender_name": msg.get("sender_name", ""),
            "content": msg.get("content", ""),
            "content_type": msg.get("content_type", 1),
            "timestamp": msg.get("timestamp", 0),
            "read_status": msg.get("read_status", 0),
        })
    
    return json.dumps({
        "success": True,
        "messages": messages,
        "hasMore": result.get("hasMore", False),
        "nextCursor": result.get("nextCursor", 0),
        "count": len(messages),
    }, ensure_ascii=False, indent=2)


@mcp.tool()
async def xianyu_send_message(
    user_id: str | None = None,
    conversation_id: str = "",
    content: str = "",
    image_url: str = "",
) -> str:
    """发送消息（已失效，请使用 xianyu_ws_send）"""
    return json.dumps({
        "success": False,
        "message": "此 API 已失效，请使用 xianyu_ws_send 直接发送消息"
    }, ensure_ascii=False)


@mcp.tool()
async def xianyu_browser_overview(user_id: str | None = None) -> str:
    """获取浏览器概览"""
    client = get_client()
    try:
        # 直接从 browser 获取，browser_bridge 没有 browser_overview 方法
        from src.browser import AsyncChromeManager
        from src.settings import load_settings
        
        settings = load_settings()
        browser = AsyncChromeManager(settings=settings)
        
        if not await browser.ensure_running():
            return json.dumps({"success": False, "message": "浏览器未连接"}, ensure_ascii=False)
        
        overview = await browser.get_browser_overview()
        response = {"success": True, **overview}
        await browser.close()
    except Exception as exc:
        response = {"success": False, "message": str(exc)}
    return json.dumps(response, ensure_ascii=False)


@mcp.tool()
async def xianyu_debug_snapshot(
    user_id: str | None = None,
    full_page: bool = True,
) -> str:
    """调试截图"""
    try:
        from src.browser import AsyncChromeManager
        from src.browser_debugger import BrowserDebugger
        from src.settings import load_settings
        
        settings = load_settings()
        browser = AsyncChromeManager(settings=settings)
        
        if not await browser.ensure_running():
            return json.dumps({"success": False, "message": "浏览器未连接"}, ensure_ascii=False)
        
        debugger = BrowserDebugger(browser)
        payload = await debugger.capture_snapshot(
            user_id=user_id or "default",
            slot_id="0",
            selected_by="manual",
            full_page=full_page,
        )
        await browser.close()
        return json.dumps(payload, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


@mcp.tool()
def xianyu_get_cached_conversations(limit: int = 20) -> List[Dict[str, Any]]:
    """获取本地缓存的对话列表
    
    返回 WebSocket 连接后收到的所有对话，按最后消息时间降序排序。
    
    Args:
        limit: 返回对话数量上限（默认 20）
    
    Returns:
        对话列表，每个对话包含：
        - conversation_id: 对话 ID
        - user_id: 用户 ID
        - user_nick: 用户昵称
        - last_message: 最后消息摘要
        - last_message_time: 最后消息时间戳
        - unread_count: 未读消息数
    """
    try:
        client = get_client()
        conversations = client.ws_client.cache.get_conversations(limit)
        
        result = []
        for conv in conversations:
            result.append({
                "conversation_id": conv.conversation_id,
                "user_id": conv.user_id,
                "user_nick": conv.user_nick,
                "last_message": conv.last_message,
                "last_message_time": conv.last_message_time,
                "unread_count": conv.unread_count,
            })
        
        return result
    except Exception as e:
        logger.error(f"获取缓存对话失败: {e}")
        return []


@mcp.tool()
def xianyu_get_cached_messages(conversation_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    """获取对话的消息历史（本地缓存）
    
    从本地缓存中获取指定对话的消息历史，按时间降序排序。
    
    Args:
        conversation_id: 对话 ID（从 xianyu_get_cached_conversations 获取）
        limit: 返回消息数量上限（默认 50）
    
    Returns:
        消息列表，每个消息包含：
        - message_id: 消息 ID
        - sender_id: 发送者 ID
        - receiver_id: 接收者 ID
        - content: 消息内容（{"type": "text", "text": "..."} 或 {"type": "image", "image_url": "..."}）
        - timestamp: 消息时间戳
        - is_read: 是否已读
    """
    try:
        client = get_client()
        messages = client.ws_client.cache.get_messages(conversation_id, limit)
        
        result = []
        for msg in messages:
            content_dict = {}
            if hasattr(msg.content, 'text'):
                content_dict = {"type": "text", "text": msg.content.text}
            elif hasattr(msg.content, 'image_url'):
                content_dict = {"type": "image", "image_url": msg.content.image_url}
            elif hasattr(msg.content, 'audio_url'):
                content_dict = {"type": "audio", "audio_url": msg.content.audio_url}
            
            result.append({
                "message_id": msg.message_id,
                "sender_id": msg.sender_id,
                "receiver_id": msg.receiver_id,
                "content": content_dict,
                "timestamp": msg.timestamp,
                "is_read": msg.is_read,
            })
        
        return result
    except Exception as e:
        logger.error(f"获取缓存消息失败: {e}")
        return []


@mcp.tool()
def xianyu_clear_cache() -> Dict[str, Any]:
    """清空对话缓存
    
    清空所有本地缓存的对话和消息数据。
    
    Returns:
        {"success": True} 表示清空成功
    """
    try:
        client = get_client()
        client.ws_client.cache.clear()
        return {"success": True}
    except Exception as e:
        logger.error(f"清空缓存失败: {e}")
        return {"success": False, "message": str(e)}


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
