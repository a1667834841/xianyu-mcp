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
from datetime import datetime, timezone
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
_login_poll_task = None

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




async def shutdown_manager() -> None:
    global _login_poll_task
    if _login_poll_task and not _login_poll_task.done():
        _login_poll_task.cancel()
        try:
            await _login_poll_task
        except asyncio.CancelledError:
            pass
    _login_poll_task = None

    client = get_client()
    try:
        await client.stop_ws_listener()
    except Exception as exc:
        logger.warning(f"[MCP HTTP] WS 自动停止失败，不阻塞服务关闭: {exc}")




async def _auto_login_poll(client, t: str, ck: str, attempts: int = 120, interval: float = 2.0) -> None:
    for _ in range(attempts):
        try:
            result = await client.login_poll(t=t, ck=ck)
            status = result.get("status")
            if status == "CONFIRMED":
                await client.ensure_ws_started(reason="login_confirmed")
                return
            if status in {"EXPIRED", "ERROR"}:
                logger.warning(f"[MCP HTTP] 登录轮询结束: {result}")
                return
        except Exception as exc:
            logger.warning(f"[MCP HTTP] 登录轮询异常，停止后台轮询: {exc}")
            return
        await asyncio.sleep(interval)
    logger.warning("[MCP HTTP] 登录轮询超时")


mcp = FastMCP(
    name="xianyu-mcp",
    host=MCP_HOST,
    port=MCP_PORT,
    message_path="/messages/",
    streamable_http_path="/mcp",
)


@mcp.tool()
async def xianyu_login(user_id: str | None = None) -> str:
    global _login_poll_task
    client = get_client()
    payload = await client.login()
    if payload.get("success") and not payload.get("logged_in") and payload.get("t") and payload.get("ck"):
        if _login_poll_task and not _login_poll_task.done():
            _login_poll_task.cancel()
        _login_poll_task = asyncio.create_task(_auto_login_poll(client, str(payload["t"]), str(payload["ck"])))
        payload["auto_poll"] = True
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
async def xianyu_publish_from_item_url(user_id: str | None = None, item_url: str = "") -> str:
    client = get_client()
    result = await client.publish_from_item_url(item_url=item_url)
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
async def xianyu_create_conversation(user_id: str | None = None, item_url: str = "") -> str:
    client = get_client()
    if "item?id=" in item_url:
        item_id = item_url.split("item?id=")[-1].split("&")[0]
    elif "?id=" in item_url:
        item_id = item_url.split("?id=")[-1].split("&")[0]
    elif "&id=" in item_url:
        item_id = item_url.split("&id=")[-1].split("&")[0]
    else:
        item_id = ""
    if not item_id:
        return json.dumps(
            {
                "success": False,
                "error_code": "INVALID_ITEM_URL",
                "message": "无法从 item_url 提取 item_id",
            },
            ensure_ascii=False,
        )

    result = await client.create_conversation(item_url=item_url)
    if not result:
        return json.dumps(
            {
                "success": False,
                "error_code": "CONVERSATION_CREATE_FAILED",
                "item_id": item_id,
                "message": "创建对话失败",
            },
            ensure_ascii=False,
        )

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
        if not token:
            cached_token = getattr(client.http_client, "_token", "")
            ws_status_getter = getattr(client, "get_ws_status", None)
            ws_status = ws_status_getter() if callable(ws_status_getter) else {}
            if cached_token and ws_status.get("connected"):
                masked_token = _mask_token(cached_token)
                return json.dumps(
                    {
                        "success": True,
                        "access_token": masked_token,
                        "access_token_masked": masked_token,
                        "source": "cache",
                    },
                    ensure_ascii=False,
                )
        if not token:
            return json.dumps(
                {
                    "success": False,
                    "error_code": "ACCESS_TOKEN_UNAVAILABLE",
                    "message": "accessToken 获取失败",
                },
                ensure_ascii=False,
            )
        masked_token = _mask_token(token)
        return json.dumps(
            {"success": True, "access_token": masked_token, "access_token_masked": masked_token},
            ensure_ascii=False,
        )
    except Exception as e:
        return json.dumps(
            {
                "success": False,
                "error_code": "ACCESS_TOKEN_ERROR",
                "message": "accessToken 获取异常",
            },
            ensure_ascii=False,
        )


@mcp.tool()
async def xianyu_list_conversations(user_id: str | None = None, limit: int = 20) -> str:
    """获取对话列表，优先实时 WebSocket RPC，失败或未连接时回退缓存。"""
    client = get_client()

    status = client.get_ws_status()
    if not status.get("connected"):
        conversations = _format_cached_conversations(client, limit)
        if conversations:
            return json.dumps(
                {
                    "success": True,
                    "source": "cache",
                    "status": status.get("status", "disconnected"),
                    "conversations": conversations,
                    "hasMore": False,
                    "count": len(conversations),
                },
                ensure_ascii=False,
                indent=2,
            )

        current = status.get("status", "disconnected")
        message = status.get("last_error") or (
            "WebSocket 正在初始化，暂无缓存对话" if current == "starting" else "WebSocket 未连接，暂无缓存对话"
        )
        return json.dumps(
            {
                "success": False,
                "status": current,
                "message": message,
                "conversations": [],
            },
            ensure_ascii=False,
        )
    
    # 使用 WebSocket LWP 协议获取对话列表
    try:
        result = await client.ws_client.get_conversation_list(max_sort_index=None, page_size=limit)
    except Exception as exc:
        result = {"success": False, "message": str(exc)}
    
    if not result.get("success"):
        conversations = _format_cached_conversations(client, limit)
        if conversations:
            return json.dumps(
                {
                    "success": True,
                    "source": "cache",
                    "fallback_reason": result.get("error") or result.get("message"),
                    "conversations": conversations,
                    "hasMore": False,
                    "count": len(conversations),
                },
                ensure_ascii=False,
                indent=2,
            )
        reason = result.get("error") or result.get("message") or "WebSocket RPC 获取对话失败"
        return json.dumps(
            {
                "success": False,
                "source": "websocket",
                "message": reason,
                "conversations": [],
                "count": 0,
            },
            ensure_ascii=False,
        )
    
    # 格式化返回
    conversations = []
    for conv in result.get("conversations", []):
        conversations.append(_format_rpc_conversation(conv))
    
    return json.dumps({
        "success": True,
        "source": "websocket",
        "conversations": conversations,
        "hasMore": result.get("hasMore", False),
        "count": len(conversations),
    }, ensure_ascii=False, indent=2)


@mcp.tool()
async def xianyu_get_messages(
    user_id: str | None = None,
    conversation_id: str | int = "",
    limit: int = 50,
) -> str:
    """获取消息历史，优先实时 WebSocket RPC，失败或未连接时回退缓存。"""
    client = get_client()
    
    conversation_id = str(conversation_id) if conversation_id else ""

    if not conversation_id:
        return json.dumps({
            "success": False,
            "error_code": "MISSING_CONVERSATION_ID",
            "message": "请提供 conversation_id（从 xianyu_list_conversations 获取）"
        }, ensure_ascii=False)
    
    # 检查 WebSocket 是否连接
    if not client.ws_is_connected():
        messages = _format_cached_messages(client, conversation_id, limit)
        if messages:
            return json.dumps(
                {
                    "success": True,
                    "source": "cache",
                    "messages": messages,
                    "hasMore": False,
                    "nextCursor": 0,
                    "count": len(messages),
                },
                ensure_ascii=False,
                indent=2,
            )
        status = client.get_ws_status() if hasattr(client, "get_ws_status") else {}
        current = status.get("status", "disconnected")
        message = status.get("last_error") or (
            "WebSocket 正在初始化，暂无缓存消息" if current == "starting" else "WebSocket 未连接，暂无缓存消息"
        )
        return json.dumps({
            "success": False,
            "status": current,
            "message": message,
            "messages": [],
            "count": 0,
        }, ensure_ascii=False)
    
    # 使用 WebSocket LWP 协议获取消息历史
    try:
        result = await client.ws_client.get_message_history(
            chat_id=conversation_id,
            anchor=None,
            count=limit
        )
    except Exception as exc:
        result = {"success": False, "message": str(exc)}
    
    if not result.get("success"):
        messages = _format_cached_messages(client, conversation_id, limit)
        if messages:
            return json.dumps(
                {
                    "success": True,
                    "source": "cache",
                    "fallback_reason": result.get("error") or result.get("message"),
                    "messages": messages,
                    "hasMore": False,
                    "nextCursor": 0,
                    "count": len(messages),
                },
                ensure_ascii=False,
                indent=2,
            )
        reason = result.get("error") or result.get("message") or "WebSocket RPC 获取消息失败"
        return json.dumps(
            {
                "success": False,
                "source": "websocket",
                "message": reason,
                "messages": [],
                "count": 0,
            },
            ensure_ascii=False,
        )
    
    # 格式化返回
    messages = []
    for msg in result.get("messages", []):
        messages.append(_format_rpc_message(msg))
    
    return json.dumps({
        "success": True,
        "source": "websocket",
        "messages": messages,
        "hasMore": result.get("hasMore", False),
        "nextCursor": result.get("nextCursor", 0),
        "count": len(messages),
    }, ensure_ascii=False, indent=2)


def _format_rpc_conversation(conv: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "conversation_id": conv.get("cid", ""),
        "user_id": conv.get("cid", ""),
        "user_nick": conv.get("peer_user_name", ""),
        "last_message": conv.get("last_message", ""),
        "last_message_time": conv.get("last_message_time", 0),
        "unread_count": conv.get("unread_count", 0),
        "item_id": conv.get("item_id", ""),
    }


def _mask_token(token: str) -> str:
    if len(token) <= 20:
        return token[:4] + "..." if len(token) > 4 else "..."
    return token[:20] + "..."


def _format_cached_conversations(client, limit: int) -> List[Dict[str, Any]]:
    try:
        conversations = client.ws_client.cache.get_conversations(limit)
    except Exception as exc:
        logger.warning(f"读取缓存对话失败: {exc}")
        return []

    return [
        {
            "conversation_id": conv.conversation_id,
            "user_id": conv.user_id,
            "user_nick": conv.user_nick,
            "last_message": conv.last_message,
            "last_message_time": conv.last_message_time,
            "unread_count": conv.unread_count,
            "item_id": conv.item_id or "",
        }
        for conv in conversations
    ]


def _format_rpc_message(msg: Dict[str, Any]) -> Dict[str, Any]:
    ts = msg.get("timestamp", 0)
    send_time = ""
    if ts:
        if ts > 1e12:
            ts = ts / 1000
        try:
            send_time = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            pass
    return {
        "message_id": msg.get("message_id", ""),
        "sender_id": msg.get("sender_id", ""),
        "sender_nick": msg.get("sender_name", ""),
        "receiver_id": msg.get("receiver_id", ""),
        "receiver_nick": msg.get("receiver_name", ""),
        "content": msg.get("content", ""),
        "content_type": msg.get("content_type", 1),
        "send_time": send_time,
        "read_status": msg.get("read_status", 0),
    }


def _format_cached_messages(client, conversation_id: str, limit: int) -> List[Dict[str, Any]]:
    try:
        messages = client.ws_client.cache.get_messages(conversation_id, limit)
    except Exception as exc:
        logger.warning(f"读取缓存消息失败: {exc}")
        return []

    result = []
    for msg in messages:
        content = msg.content
        if hasattr(content, "text"):
            content_value = content.text
            content_type = 1
        elif hasattr(content, "image_url"):
            content_value = content.image_url
            content_type = 2
        elif hasattr(content, "audio_url"):
            content_value = content.audio_url
            content_type = 3
        else:
            content_value = ""
            content_type = 0

        ts = msg.timestamp
        send_time = ""
        if ts:
            if ts > 1e12:
                ts = ts / 1000
            try:
                send_time = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                pass

        result.append(
            {
                "message_id": msg.message_id,
                "sender_id": msg.sender_id,
                "sender_nick": msg.sender_nick,
                "receiver_id": msg.receiver_id,
                "receiver_nick": msg.receiver_nick,
                "content": content_value,
                "content_type": content_type,
                "send_time": send_time,
                "read_status": 1 if msg.is_read else 0,
            }
        )
    return result


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
        if result.get("status") == "CONFIRMED":
            await client.ensure_ws_started(reason="login_confirmed")
            result["ws_auto_start"] = True
            result["ws_status"] = client.get_ws_status()
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
    sse_app = mcp.sse_app()
    streamable_http_app = mcp.streamable_http_app()

    @asynccontextmanager
    async def lifespan(app):
        async with streamable_http_app.router.lifespan_context(streamable_http_app):
            await initialize_manager()
            yield
            await shutdown_manager()
            await asyncio.sleep(0.5)

    return Starlette(
        routes=(
            rest_routes
            + list(sse_app.routes)
            + list(streamable_http_app.routes)
        ),
        middleware=middleware,
        lifespan=lifespan,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(build_app(), host=MCP_HOST, port=MCP_PORT)
