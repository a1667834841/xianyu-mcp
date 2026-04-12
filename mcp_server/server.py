import asyncio
import json
import os
import sys
from dataclasses import asdict

import mcp.server.stdio
import mcp.types as types
from mcp.server import Server
from mcp.server.lowlevel import NotificationOptions
from mcp.server.models import InitializationOptions

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp_server.http_server import get_manager


server = Server("xianyu-mcp")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="xianyu_create_user",
            description="创建新用户",
            inputSchema={
                "type": "object",
                "properties": {"display_name": {"type": "string"}},
                "required": [],
            },
        ),
        types.Tool(
            name="xianyu_list_users",
            description="查看全部用户",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="xianyu_get_user_status",
            description="查看单个用户状态",
            inputSchema={
                "type": "object",
                "properties": {"user_id": {"type": "string"}},
                "required": ["user_id"],
            },
        ),
        types.Tool(
            name="xianyu_login",
            description="登录或返回二维码",
            inputSchema={
                "type": "object",
                "properties": {"user_id": {"type": "string"}},
                "required": [],
            },
        ),
        types.Tool(
            name="xianyu_search",
            description="搜索商品",
            inputSchema={
                "type": "object",
                "properties": {
                    "keyword": {"type": "string"},
                    "user_id": {"type": "string"},
                    "rows": {"type": "integer", "default": 30},
                    "min_price": {"type": "number"},
                    "max_price": {"type": "number"},
                    "free_ship": {"type": "boolean", "default": False},
                    "sort_field": {"type": "string"},
                    "sort_order": {"type": "string"},
                },
                "required": ["keyword"],
            },
        ),
        types.Tool(
            name="xianyu_publish",
            description="复制发布商品",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "item_url": {"type": "string"},
                    "new_price": {"type": "number"},
                    "new_description": {"type": "string"},
                    "condition": {"type": "string", "default": "全新"},
                },
                "required": ["user_id", "item_url"],
            },
        ),
        types.Tool(
            name="xianyu_get_detail",
            description="获取商品详情",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "item_url": {"type": "string"},
                },
                "required": ["user_id", "item_url"],
            },
        ),
        types.Tool(
            name="xianyu_refresh_token",
            description="刷新 token",
            inputSchema={
                "type": "object",
                "properties": {"user_id": {"type": "string"}},
                "required": ["user_id"],
            },
        ),
        types.Tool(
            name="xianyu_check_session",
            description="检查登录态",
            inputSchema={
                "type": "object",
                "properties": {"user_id": {"type": "string"}},
                "required": ["user_id"],
            },
        ),
        types.Tool(
            name="xianyu_browser_overview",
            description="获取浏览器概览",
            inputSchema={
                "type": "object",
                "properties": {"user_id": {"type": "string"}},
                "required": [],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> types.CallToolResult:
    manager = get_manager()
    try:
        if name == "xianyu_create_user":
            entry = manager.create_user(arguments.get("display_name"))
            payload = {
                "success": True,
                "user_id": entry.user_id,
                "slot_id": entry.slot_id,
                "cdp_port": entry.cdp_port,
                "status": entry.status,
            }
        elif name == "xianyu_list_users":
            payload = {"success": True, "users": manager.list_user_statuses()}
        elif name == "xianyu_get_user_status":
            payload = {"success": True, **manager.get_user_status(arguments["user_id"])}
        elif name == "xianyu_login":
            payload = await manager.debug_login(arguments.get("user_id"))
        elif name == "xianyu_search":
            payload = await manager.debug_search(
                keyword=arguments["keyword"],
                user_id=arguments.get("user_id"),
                rows=arguments.get("rows", 30),
                min_price=arguments.get("min_price"),
                max_price=arguments.get("max_price"),
                free_ship=arguments.get("free_ship", False),
                sort_field=arguments.get("sort_field", ""),
                sort_order=arguments.get("sort_order", ""),
            )
        elif name == "xianyu_publish":
            payload = await manager.publish(
                arguments["user_id"],
                arguments["item_url"],
                new_price=arguments.get("new_price"),
                new_description=arguments.get("new_description"),
                condition=arguments.get("condition", "全新"),
            )
        elif name == "xianyu_get_detail":
            payload = await manager.get_detail(
                arguments["user_id"],
                arguments["item_url"],
            )
        elif name == "xianyu_refresh_token":
            payload = await manager.refresh_token(arguments["user_id"])
        elif name == "xianyu_check_session":
            payload = await manager.check_session(arguments["user_id"])
        elif name == "xianyu_browser_overview":
            payload = {
                "success": True,
                **(await manager.debug_browser_overview(arguments.get("user_id"))),
            }
        else:
            return types.CallToolResult(
                content=[types.TextContent(type="text", text=f"未知工具：{name}")],
                isError=True,
            )
        return types.CallToolResult(
            content=[
                types.TextContent(
                    type="text", text=json.dumps(payload, ensure_ascii=False)
                )
            ]
        )
    except Exception as exc:
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=str(exc))], isError=True
        )


async def run_server():
    manager = get_manager()
    if hasattr(manager, "ensure_initialized"):
        await manager.ensure_initialized()
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="xianyu-mcp",
                server_version="2.0.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )
