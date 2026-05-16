"""
mcp_server/http_server.py - 闲鱼 MCP Server HTTP/SSE 入口
使用 FastMCP 实现 SSE 和 HTTP 传输
"""

import os
import sys
import json
import asyncio
import logging
import hmac
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from dataclasses import asdict
from typing import Dict, List, Any

from dotenv import load_dotenv
load_dotenv()

from mcp.server.fastmcp import FastMCP
from starlette.responses import JSONResponse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.api.client import XianyuApiClient
from src.settings import load_settings
from src.user_manager import UserManager
from src.client_manager import ClientManager
from src.pending_login_manager import PendingLoginManager

logger = logging.getLogger(__name__)

CDP_HOST = os.environ.get("CDP_HOST", "chrome-headless")
CDP_PORT = int(os.environ.get("CDP_PORT", "9222"))
MCP_HOST = os.environ.get("MCP_HOST", "0.0.0.0")
MCP_PORT = int(os.environ.get("MCP_PORT", "8080"))
PENDING_LOGIN_CLIENT_ID = "__pending_login__"

print(f"[MCP HTTP] 服务端口={MCP_PORT}")

_user_manager = None
_client_manager = None
_pending_login_manager = None
_login_poll_task = None


def _unauthorized_response() -> JSONResponse:
    return JSONResponse({"error": "Unauthorized"}, status_code=401)


def _normalize_headers(headers: Any) -> dict[str, str]:
    if headers is None:
        return {}
    try:
        items = headers.items()
    except AttributeError:
        return {}
    return {str(key).lower(): str(value) for key, value in items}


def _is_request_authorized(headers: Any) -> bool:
    settings = load_settings()
    if not settings.mcp.auth_required:
        return True

    normalized_headers = _normalize_headers(headers)
    authorization = normalized_headers.get("authorization", "").strip()
    if not authorization.startswith("Bearer "):
        return False

    token = authorization[len("Bearer "):].strip()
    return bool(token) and hmac.compare_digest(token, settings.mcp.auth_token)


def _should_enforce_auth(path: str) -> bool:
    return (
        path.startswith("/mcp")
        or path.startswith("/sse")
        or path.startswith("/messages/")
        or path.startswith("/rest/")
    )


def _wrap_with_auth(asgi_app):
    async def guarded(scope, receive, send):
        if (
            scope.get("type") == "http"
            and scope.get("method") != "OPTIONS"
            and _should_enforce_auth(scope.get("path", ""))
        ):
            headers = {
                key.decode("latin-1"): value.decode("latin-1")
                for key, value in scope.get("headers", [])
            }
            if not _is_request_authorized(headers):
                response = _unauthorized_response()
                await response(scope, receive, send)
                return
        await asgi_app(scope, receive, send)

    guarded.routes = getattr(asgi_app, "routes", [])
    guarded.router = getattr(asgi_app, "router", None)
    guarded.state = getattr(asgi_app, "state", None)
    return guarded

def get_user_manager():
    global _user_manager
    if _user_manager is None:
        settings = load_settings()
        _user_manager = UserManager(data_root=settings.storage.data_root)
    return _user_manager

def get_client_manager():
    global _client_manager
    if _client_manager is None:
        settings = load_settings()
        _client_manager = ClientManager(
            user_manager=get_user_manager(),
            data_root=settings.storage.data_root,
        )
    return _client_manager


def get_pending_login_manager():
    global _pending_login_manager
    if _pending_login_manager is None:
        _pending_login_manager = PendingLoginManager()
    return _pending_login_manager

def get_client():
    return get_client_manager().get_client("default")

def _resolve_user_id(user_id: str | None) -> str:
    if user_id:
        return user_id
    return str(get_user_manager().get_default_user()["user_id"])


SHANGHAI_TZ = timezone(timedelta(hours=8))


def _now_iso() -> str:
    return datetime.now(SHANGHAI_TZ).strftime("%Y-%m-%d %H:%M:%S")


def _format_display_time(value):
    if not isinstance(value, str) or not value.strip():
        return value
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return value
    return parsed.strftime("%Y-%m-%d %H:%M:%S")


async def _activate_user_runtime(user_id: str, reason: str) -> dict[str, Any]:
    settings = load_settings()
    user = get_user_manager().get_user(user_id)
    client = get_client_manager().get_client(user_id)

    if user.get("keepalive_enabled", True):
        await get_client_manager().start_keepalive(
            user_id,
            settings.keepalive.interval_minutes,
        )

    await client.ensure_ws_started(reason=reason)
    return {
        "ws_auto_start": True,
        "ws_status": client.get_ws_status(),
    }


async def initialize_manager() -> None:
    for user in get_user_manager().list_users():
        if user.get("status") != "active" or not user.get("keepalive_enabled", True):
            continue
        user_id = user["user_id"]
        client = get_client_manager().get_client(user_id)
        try:
            result = await client.check_session()
        except Exception as exc:
            logger.warning(f"[MCP HTTP] 用户 {user_id} 启动时检查会话失败: {exc}")
            get_user_manager().update_user(user_id, status="error")
            continue
        if result.get("valid"):
            try:
                await _activate_user_runtime(user_id, reason="service_start")
            except Exception as exc:
                logger.warning(f"[MCP HTTP] 用户 {user_id} WS 自动启动失败: {exc}")
        else:
            logger.info(f"[MCP HTTP] 用户 {user_id} Cookie 无效，跳过 WS/保活")
            get_user_manager().update_user(user_id, status="expired")




async def shutdown_manager() -> None:
    global _login_poll_task
    if _login_poll_task and not _login_poll_task.done():
        _login_poll_task.cancel()
        try:
            await _login_poll_task
        except asyncio.CancelledError:
            pass
    _login_poll_task = None

    try:
        await get_client_manager().shutdown()
    except Exception as exc:
        logger.warning(f"[MCP HTTP] ClientManager 关闭异常: {exc}")




async def _auto_login_poll(client, t: str, ck: str, attempts: int = 120, interval: float = 2.0) -> None:
    for _ in range(attempts):
        try:
            result = await client.login_poll(t=t, ck=ck)
            status = result.get("status")
            if status == "CONFIRMED":
                await _activate_user_runtime(client.user_id, reason="login_confirmed")
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
async def xianyu_show_qrcode() -> str:
    client = get_client_manager().get_client(PENDING_LOGIN_CLIENT_ID)
    payload = await client.show_qrcode()
    qr_code = payload.get("qr_code")
    qr_code_public_url = ""
    if isinstance(qr_code, dict):
        qr_code_public_url = str(qr_code.get("public_url") or "")
        qr_code.pop("url", None)
    if payload.get("success") and not payload.get("logged_in") and payload.get("t") and payload.get("ck"):
        get_pending_login_manager().create_session(
            t=str(payload["t"]),
            ck=str(payload["ck"]),
            qr_code_url=qr_code_public_url or str(payload.get("qr_code_url", "")),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        )
        payload["phase"] = "login_required"
    return json.dumps(payload, ensure_ascii=False)


@mcp.tool()
async def xianyu_login(user_id: str | None = None) -> str:
    global _login_poll_task
    resolved = _resolve_user_id(user_id)
    client = get_client_manager().get_client(resolved)
    payload = await client.login()
    if payload.get("success") and not payload.get("logged_in") and payload.get("t") and payload.get("ck"):
        if _login_poll_task and not _login_poll_task.done():
            _login_poll_task.cancel()
        _login_poll_task = asyncio.create_task(_auto_login_poll(client, str(payload["t"]), str(payload["ck"])))
        payload["auto_poll"] = True
    return json.dumps(payload, ensure_ascii=False)


@mcp.tool()
async def xianyu_check_session(user_id: str | None = None) -> str:
    if user_id:
        client = get_client_manager().get_client(user_id)
        result = await client.check_session()
        return json.dumps(result, ensure_ascii=False)

    sessions = []
    user_manager = get_user_manager()
    for user in get_user_manager().list_users():
        uid = user["user_id"]
        status = user.get("status", "")
        if status == "disabled":
            session = {
                "valid": False,
                "message": "用户已禁用，未执行会话检查",
            }
        else:
            client = get_client_manager().get_client(uid)
            session = await client.check_session()
            next_status = "active" if session.get("valid") else "expired"
            if status != next_status:
                user_manager.update_user(uid, status=next_status)
                status = next_status
        sessions.append({
            "user_id": uid,
            "username": user.get("username", ""),
            "status": status,
            **session,
        })
    return json.dumps({"success": True, "sessions": sessions}, ensure_ascii=False)


@mcp.tool()
async def xianyu_refresh_token(user_id: str | None = None) -> str:
    resolved = _resolve_user_id(user_id)
    client = get_client_manager().get_client(resolved)
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
    resolved = _resolve_user_id(user_id)
    client = get_client_manager().get_client(resolved)
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
async def xianyu_suggest_keywords(user_id: str | None = None, input_words: str = "x") -> str:
    resolved = _resolve_user_id(user_id)
    client = get_client_manager().get_client(resolved)
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
    resolved = _resolve_user_id(user_id)
    client = get_client_manager().get_client(resolved)
    
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
    resolved = _resolve_user_id(user_id)
    client = get_client_manager().get_client(resolved)
    result = await client.get_detail(item_url=item_url)
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
async def xianyu_publish_from_item_url(user_id: str | None = None, item_url: str = "") -> str:
    resolved = _resolve_user_id(user_id)
    client = get_client_manager().get_client(resolved)
    result = await client.publish_from_item_url(item_url=item_url)
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
async def xianyu_create_conversation(user_id: str | None = None, item_url: str = "") -> str:
    resolved = _resolve_user_id(user_id)
    client = get_client_manager().get_client(resolved)
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
    resolved = _resolve_user_id(user_id)
    client = get_client_manager().get_client(resolved)
    if not target_id:
        return json.dumps({"success": False, "message": "需要提供 target_id"}, ensure_ascii=False)
    result = await client.ws_send_message(target_id, content, image_url, conversation_id)
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
async def xianyu_ws_status(user_id: str | None = None) -> str:
    """检查 WebSocket 连接状态"""
    resolved = _resolve_user_id(user_id)
    client = get_client_manager().get_client(resolved)
    payload = client.get_ws_status()
    payload["started_at"] = _format_display_time(payload.get("started_at"))
    return json.dumps(payload, ensure_ascii=False)


@mcp.tool()
async def xianyu_list_conversations(user_id: str | None = None, limit: int = 20) -> str:
    """获取对话列表，优先实时 WebSocket RPC，失败或未连接时回退缓存。"""
    resolved = _resolve_user_id(user_id)
    client = get_client_manager().get_client(resolved)

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
    resolved = _resolve_user_id(user_id)
    client = get_client_manager().get_client(resolved)
    
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


@mcp.tool()
async def xianyu_add_user(t: str, ck: str) -> str:
    pending_login_manager = get_pending_login_manager()
    try:
        pending_login_manager.get_session(t=t, ck=ck)
    except ValueError as exc:
        message = str(exc)
        phase = "expired" if "expired" in message.lower() else "error"
        return json.dumps(
            {
                "success": False,
                "phase": phase,
                "message": message,
            },
            ensure_ascii=False,
        )

    client = get_client_manager().get_client(PENDING_LOGIN_CLIENT_ID)
    poll_result = await client.login_poll(t=t, ck=ck)
    status = poll_result.get("status")

    if status != "CONFIRMED":
        if status == "EXPIRED":
            pending_login_manager.delete_session(t=t, ck=ck)
        phase = "expired" if status == "EXPIRED" else "waiting_for_scan"
        return json.dumps({"success": False, "phase": phase, **poll_result}, ensure_ascii=False)

    session_result = await client.check_session()
    if not session_result.get("valid"):
        return json.dumps(
            {
                "success": False,
                "phase": "error",
                "message": session_result.get("message") or "登录态校验失败",
                "session": session_result,
            },
            ensure_ascii=False,
        )

    identity = client.http_client.get_authenticated_user_identity()
    nickname = await client.http_client.fetch_user_nickname()
    username = nickname or identity["username"] or identity["user_id"]

    user_manager = get_user_manager()
    try:
        existing_user = user_manager.get_user(identity["user_id"])
    except ValueError:
        existing_user = None

    if existing_user and existing_user.get("status") != "disabled":
        existing_client = get_client_manager().get_client(identity["user_id"])
        await get_client_manager().stop_user(identity["user_id"])
        await existing_client.initialize(
            cookies=client.http_client.cookies,
            device_id=client.http_client.device_id,
        )
        existing_client.http_client._save_auth(client.http_client.cookies)
        refreshed_user = user_manager.update_user(
            identity["user_id"],
            username=username,
            status="active",
            last_login_at=_now_iso(),
        )
        runtime = await _activate_user_runtime(
            identity["user_id"],
            reason="login_confirmed",
        )
        pending_login_manager.delete_session(t=t, ck=ck)
        return json.dumps(
            {
                "success": True,
                "phase": "already_exists",
                "message": "用户已存在，已刷新登录态",
                "user": refreshed_user,
                **runtime,
            },
            ensure_ascii=False,
        )

    try:
        user = user_manager.add_user(
            user_id=identity["user_id"],
            username=username,
        )
    except ValueError as exc:
        pending_login_manager.delete_session(t=t, ck=ck)
        return json.dumps(
            {
                "success": False,
                "phase": "error",
                "message": str(exc),
            },
            ensure_ascii=False,
        )

    user_manager.update_user(identity["user_id"], last_login_at=_now_iso())
    created_client = get_client_manager().get_client(identity["user_id"])
    await created_client.initialize(
        cookies=client.http_client.cookies,
        device_id=client.http_client.device_id,
    )
    created_client.http_client._save_auth(client.http_client.cookies)
    runtime = await _activate_user_runtime(
        identity["user_id"],
        reason="login_confirmed",
    )
    pending_login_manager.delete_session(t=t, ck=ck)
    return json.dumps(
        {
            "success": True,
            "phase": "completed",
            "user": user,
            **runtime,
        },
        ensure_ascii=False,
    )


@mcp.tool()
async def xianyu_list_users() -> str:
    users = []
    for user in get_user_manager().list_users():
        uid = user["user_id"]
        runtime = {
            "ws_connected": False,
            "keepalive_running": get_client_manager().has_keepalive_task(uid),
        }
        if get_client_manager().has_client(uid):
            runtime["ws_connected"] = get_client_manager().get_client(uid).ws_is_connected()
        users.append({**user, **runtime})
    return json.dumps({"success": True, "users": users}, ensure_ascii=False)


@mcp.tool()
async def xianyu_delete_user(user_id: str) -> str:
    await get_client_manager().stop_user(user_id)
    payload = get_user_manager().disable_user(user_id)
    return json.dumps(payload, ensure_ascii=False)


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

    load_settings()

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

    app = Starlette(
        routes=(
            rest_routes
            + list(sse_app.routes)
            + list(streamable_http_app.routes)
        ),
        middleware=middleware,
        lifespan=lifespan,
    )
    return _wrap_with_auth(app)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(build_app(), host=MCP_HOST, port=MCP_PORT)
