import asyncio
import json
import os
import sys

import mcp.server.stdio
import mcp.types as types
from mcp.server import Server
from mcp.server.lowlevel import NotificationOptions
from mcp.server.models import InitializationOptions

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp_server.http_server import get_client


server = Server("xianyu-mcp")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="xianyu_login",
            description="登录闲鱼账号，返回二维码 URL",
            inputSchema={
                "type": "object",
                "properties": {
                    "timeout": {"type": "integer", "default": 300}
                },
                "required": [],
            },
        ),
        types.Tool(
            name="xianyu_check_session",
            description="检查当前用户登录态是否有效",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="xianyu_refresh_token",
            description="刷新登录 Token，优先 HTTP，失败降级浏览器",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="xianyu_search",
            description="搜索商品，使用 HTTP MTOP API",
            inputSchema={
                "type": "object",
                "properties": {
                    "keyword": {"type": "string"},
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
            name="xianyu_suggest_keywords",
            description="获取搜索联想词",
            inputSchema={
                "type": "object",
                "properties": {
                    "input_words": {"type": "string", "default": "x"},
                },
                "required": [],
            },
        ),
        types.Tool(
            name="xianyu_get_detail",
            description="获取商品详情，使用 HTTP MTOP API",
            inputSchema={
                "type": "object",
                "properties": {
                    "item_url": {"type": "string"},
                },
                "required": ["item_url"],
            },
        ),
        types.Tool(
            name="xianyu_publish",
            description="发布商品，优先 HTTP，失败降级浏览器",
            inputSchema={
                "type": "object",
                "properties": {
                    "item_url": {"type": "string"},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "price": {"type": "number"},
                    "original_price": {"type": "number"},
                    "condition": {"type": "string", "default": "全新"},
                },
                "required": ["item_url"],
            },
        ),
        types.Tool(
            name="xianyu_create_conversation",
            description="创建对话，通过商品链接与卖家发起对话",
            inputSchema={
                "type": "object",
                "properties": {
                    "item_url": {"type": "string"},
                    "seller_id": {"type": "string"},
                },
                "required": ["item_url"],
            },
        ),
        types.Tool(
            name="xianyu_list_conversations",
            description="获取对话列表",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 20},
                    "offset": {"type": "integer", "default": 0},
                },
                "required": [],
            },
        ),
        types.Tool(
            name="xianyu_get_messages",
            description="获取对话的消息历史记录",
            inputSchema={
                "type": "object",
                "properties": {
                    "conversation_id": {"type": "string"},
                    "limit": {"type": "integer", "default": 50},
                    "before_timestamp": {"type": "integer"},
                },
                "required": ["conversation_id"],
            },
        ),
        types.Tool(
            name="xianyu_send_message",
            description="发送消息到指定对话，支持文本和图片",
            inputSchema={
                "type": "object",
                "properties": {
                    "conversation_id": {"type": "string"},
                    "content": {"type": "string"},
                    "image_url": {"type": "string"},
                },
                "required": ["conversation_id"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> types.CallToolResult:
    client = get_client()
    try:
        if name == "xianyu_login":
            payload = await client.login(timeout=arguments.get("timeout", 300))
        elif name == "xianyu_check_session":
            payload = await client.check_session()
        elif name == "xianyu_refresh_token":
            payload = await client.refresh_token()
        elif name == "xianyu_search":
            items = await client.search(
                keyword=arguments["keyword"],
                rows=arguments.get("rows", 30),
                min_price=arguments.get("min_price"),
                max_price=arguments.get("max_price"),
                free_ship=arguments.get("free_ship", False),
                sort_field=arguments.get("sort_field", ""),
                sort_order=arguments.get("sort_order", ""),
            )
            payload = {"items": items, "total": len(items), "engine_used": "http_api"}
        elif name == "xianyu_suggest_keywords":
            payload = {"keywords": []}
        elif name == "xianyu_get_detail":
            payload = await client.get_detail(arguments["item_url"])
        elif name == "xianyu_publish":
            payload = await client.publish(
                item_url=arguments["item_url"],
                new_title=arguments.get("title"),
                new_description=arguments.get("description"),
                new_price=arguments.get("price"),
                original_price=arguments.get("original_price"),
                condition=arguments.get("condition", "全新"),
            )
        elif name == "xianyu_create_conversation":
            conv_id = await client.create_conversation(
                item_url=arguments["item_url"],
                seller_id=arguments.get("seller_id", ""),
            )
            payload = {
                "success": True,
                "conversation_id": conv_id,
                "message": "对话创建成功" if conv_id else "创建失败",
            }
        elif name == "xianyu_list_conversations":
            conversations = await client.list_conversations(
                limit=arguments.get("limit", 20),
                offset=arguments.get("offset", 0),
            )
            payload = {
                "conversations": [vars(c) for c in conversations],
                "total": len(conversations),
            }
        elif name == "xianyu_get_messages":
            payload = await client.get_messages(
                conversation_id=arguments["conversation_id"],
                limit=arguments.get("limit", 50),
                before_timestamp=arguments.get("before_timestamp"),
            )
            payload["messages"] = [vars(m) for m in payload["messages"]]
        elif name == "xianyu_send_message":
            success = await client.send_message(
                conversation_id=arguments["conversation_id"],
                content=arguments.get("content", ""),
                image_url=arguments.get("image_url", ""),
            )
            payload = {
                "success": success,
                "message_id": "msg_" + str(hash(arguments["conversation_id"]))[-6:],
                "message": "消息发送成功" if success else "发送失败",
            }
        else:
            return types.CallToolResult(
                content=[types.TextContent(type="text", text=f"未知工具：{name}")],
                isError=True,
            )
        return types.CallToolResult(
            content=[
                types.TextContent(
                    type="text", text=json.dumps(payload, ensure_ascii=False, default=str)
                )
            ]
        )
    except Exception as exc:
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=str(exc))], isError=True
        )


async def run_server():
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="xianyu-mcp",
                server_version="3.0.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(run_server())
