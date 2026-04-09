"""
server.py - MCP Server 入口
使用 XianyuApp 统一处理所有闲鱼操作
"""

import asyncio
import json
import os
import sys
from typing import Any, Dict, Optional
from dataclasses import asdict

import mcp.server.stdio
import mcp.types as types
from mcp.server import Server
from mcp.server.lowlevel import NotificationOptions
from mcp.server.models import InitializationOptions

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import XianyuApp


# 配置：从环境变量读取 host 和 port，默认使用 localhost:9222
CDP_HOST = os.environ.get("CDP_HOST", "localhost")
CDP_PORT = int(os.environ.get("CDP_PORT", "9222"))


# 创建 MCP Server
server = Server("xianyu-mcp")

# 全局 XianyuApp 实例（懒加载）
_app: Optional[XianyuApp] = None


def get_app() -> XianyuApp:
    """获取或创建 XianyuApp 实例"""
    global _app
    if _app is None:
        from src.browser import AsyncChromeManager

        browser = AsyncChromeManager(
            host=CDP_HOST, port=CDP_PORT, auto_start=(CDP_HOST == "localhost")
        )
        _app = XianyuApp(browser)
        _app.start_background_tasks()
    return _app


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    """列出可用的工具"""
    return [
        types.Tool(
            name="xianyu_login",
            description="扫码登录闲鱼账号，获取 Token。Token 有效期约 24 小时。",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="xianyu_search",
            description="通过关键词搜索闲鱼商品，返回目标数量内的唯一商品列表。",
            inputSchema={
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "搜索关键词"},
                    "rows": {
                        "type": "integer",
                        "description": "目标唯一商品总数，默认 30",
                        "default": 30,
                    },
                    "min_price": {"type": "number", "description": "最低价格（可选）"},
                    "max_price": {"type": "number", "description": "最高价格（可选）"},
                    "free_ship": {
                        "type": "boolean",
                        "description": "是否只看包邮，默认 false",
                        "default": False,
                    },
                    "sort_field": {
                        "type": "string",
                        "description": "排序字段：pub_time（发布时间）或 price（价格）",
                        "enum": ["pub_time", "price", ""],
                        "default": "",
                    },
                    "sort_order": {
                        "type": "string",
                        "description": "排序方向：ASC（升序）或 DESC（降序）",
                        "enum": ["ASC", "DESC", ""],
                        "default": "",
                    },
                },
                "required": ["keyword"],
            },
        ),
        types.Tool(
            name="xianyu_publish",
            description="根据商品链接复制发布商品。自动获取对标商品数据（标题、描述、图片、分类等），填充发布表单。潮玩盲盒等特殊类目会自动保存草稿。",
            inputSchema={
                "type": "object",
                "properties": {
                    "item_url": {
                        "type": "string",
                        "description": "对标商品链接，如 https://www.goofish.com/item?id=123456789",
                    },
                    "new_price": {
                        "type": "number",
                        "description": "新商品价格（可选，默认使用原价）",
                    },
                    "new_description": {
                        "type": "string",
                        "description": "新商品描述（可选，默认使用原描述）",
                    },
                    "condition": {
                        "type": "string",
                        "description": "成色，默认全新",
                        "enum": ["全新", "几乎全新", "9 成新", "8 成新", "7 成新"],
                        "default": "全新",
                    },
                },
                "required": ["item_url"],
            },
        ),
        types.Tool(
            name="xianyu_refresh_token",
            description="刷新闲鱼 Token。通过访问闲鱼首页获取最新的 Token，当 Token 过期或需要更新时调用。",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="xianyu_check_session",
            description="检查闲鱼 Cookie 是否有效。调用用户信息接口验证当前登录状态。",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="xianyu_show_qr",
            description="显示登录二维码。访问闲鱼首页，如果未登录则显示二维码；如果已登录则直接返回。用户扫码后浏览器会自动跳转完成登录。",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> types.CallToolResult:
    """处理工具调用"""

    try:
        if name == "xianyu_login":
            return await handle_login(arguments)

        elif name == "xianyu_search":
            return await handle_search(arguments)

        elif name == "xianyu_publish":
            return await handle_publish(arguments)

        elif name == "xianyu_refresh_token":
            return await handle_refresh_token(arguments)

        elif name == "xianyu_check_session":
            return await handle_check_session(arguments)

        elif name == "xianyu_show_qr":
            return await handle_show_qr(arguments)

        else:
            return types.CallToolResult(
                content=[types.TextContent(type="text", text=f"未知工具：{name}")],
                isError=True,
            )

    except Exception as e:
        import traceback

        return types.CallToolResult(
            content=[
                types.TextContent(
                    type="text", text=f"错误：{str(e)}\n{traceback.format_exc()}"
                )
            ],
            isError=True,
        )


async def handle_login(arguments: dict) -> types.CallToolResult:
    """
    处理登录（兼容旧方法）

    推荐使用新的两步登录方式：
    1. 调用 xianyu_check_session 检查是否已登录
    2. 如果未登录，调用 xianyu_show_qr 显示二维码

    返回：
    - 登录成功：{"success": true, "token": "..."}
    - 需要扫码：{"success": true, "qr_code": {...}, "need_qr": true, "message": "请扫码登录"}
    - 登录失败：{"success": false, "message": "..."}
    """
    app = get_app()
    result = await app.login(timeout=30)

    # login() 方法内部已经显示二维码，这里直接返回结果
    return types.CallToolResult(
        content=[
            types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False))
        ]
    )


async def handle_search(arguments: dict) -> types.CallToolResult:
    """处理搜索"""
    app = get_app()

    # 确保浏览器已连接
    await app.browser.ensure_running()

    outcome = await app.search_with_meta(
        keyword=arguments["keyword"],
        rows=arguments.get("rows", 30),
        min_price=arguments.get("min_price"),
        max_price=arguments.get("max_price"),
        free_ship=arguments.get("free_ship", False),
        sort_field=arguments.get("sort_field", ""),
        sort_order=arguments.get("sort_order", ""),
    )

    items = [asdict(item) for item in outcome.items]

    result = {
        "success": True,
        "requested": outcome.requested_rows,
        "total": outcome.returned_rows,
        "stop_reason": outcome.stop_reason,
        "stale_pages": outcome.stale_pages,
        "items": items,
        "engine_used": outcome.engine_used,
        "fallback_reason": outcome.fallback_reason,
        "pages_fetched": outcome.pages_fetched,
    }

    return types.CallToolResult(
        content=[
            types.TextContent(
                type="text", text=json.dumps(result, ensure_ascii=False, indent=2)
            )
        ]
    )


async def handle_publish(arguments: dict) -> types.CallToolResult:
    """处理发布"""
    app = get_app()

    # 确保浏览器已连接
    await app.browser.ensure_running()

    result = await app.publish(
        item_url=arguments["item_url"],
        new_price=arguments.get("new_price"),
        new_description=arguments.get("new_description"),
        condition=arguments.get("condition", "全新"),
    )

    # 提取关键信息返回
    response = {
        "success": result.get("success"),
        "item_id": result.get("item_id"),
        "error": result.get("error"),
        "message": "表单填充完成，请检查浏览器窗口"
        if result.get("success")
        else result.get("error"),
    }

    if result.get("item_data"):
        item_data = result["item_data"]
        response["captured_item"] = {
            "title": item_data.get("title", "")[:50],
            "price": item_data.get("min_price"),
            "images": len(item_data.get("image_urls", [])),
            "category": item_data.get("category"),
        }

    return types.CallToolResult(
        content=[
            types.TextContent(
                type="text", text=json.dumps(response, ensure_ascii=False)
            )
        ]
    )


async def handle_refresh_token(arguments: dict) -> types.CallToolResult:
    """处理刷新 token"""
    app = get_app()
    result = await app.refresh_token()

    if result:
        response = {
            "success": True,
            "token": result["token"],
            "full_cookie": result["full_cookie"],
            "message": "Token 刷新成功",
        }
    else:
        response = {
            "success": False,
            "message": "Token 刷新失败，请检查浏览器是否已登录",
        }

    return types.CallToolResult(
        content=[
            types.TextContent(
                type="text", text=json.dumps(response, ensure_ascii=False)
            )
        ]
    )


async def handle_check_session(arguments: dict) -> types.CallToolResult:
    """处理检查会话"""
    app = get_app()
    session_status = await app.check_session()
    is_valid = session_status["valid"]

    response = {
        "success": True,
        "valid": is_valid,
        "message": "Cookie 有效" if is_valid else "Cookie 已过期，需要重新登录",
        "last_updated_at": session_status.get("last_updated_at"),
    }

    return types.CallToolResult(
        content=[
            types.TextContent(
                type="text", text=json.dumps(response, ensure_ascii=False)
            )
        ]
    )


async def handle_show_qr(arguments: dict) -> types.CallToolResult:
    """
    处理显示二维码

    访问闲鱼首页，如果未登录则显示二维码；如果已登录则直接返回。
    用户扫码后浏览器会自动跳转完成登录。
    """
    app = get_app()
    result = await app.show_qr_code()

    return types.CallToolResult(
        content=[
            types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False))
        ]
    )


async def run_server():
    """运行 MCP Server"""
    print(f"[MCP] 启动闲鱼 MCP Server，CDP: {CDP_HOST}:{CDP_PORT}")

    app = None
    try:
        app = get_app()
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
    finally:
        if app is not None:
            try:
                await app.stop_background_tasks()
            except Exception:
                # Must not crash shutdown.
                import traceback

                print(f"[MCP] stop_background_tasks failed:\n{traceback.format_exc()}")


if __name__ == "__main__":
    asyncio.run(run_server())
