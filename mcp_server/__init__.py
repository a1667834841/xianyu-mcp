"""
mcp_server - 闲鱼 MCP Server
通过 stdio 与 Claude 通信，提供闲鱼自动化工具
"""

from .server import run_server

__all__ = ["run_server"]