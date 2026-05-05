"""Deprecated stdio entrypoint.

The MCP business tools are exposed only by ``mcp_server.http_server`` over
HTTP/SSE. Running this module starts the HTTP/SSE app for operators that still
reference the old module path, but it intentionally does not define stdio
``list_tools`` or ``call_tool`` handlers.
"""

from mcp_server.http_server import MCP_HOST, MCP_PORT, build_app


def main() -> None:
    import uvicorn

    uvicorn.run(build_app(), host=MCP_HOST, port=MCP_PORT)


if __name__ == "__main__":
    main()
