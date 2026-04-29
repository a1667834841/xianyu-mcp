# 闲鱼 MCP Server Dockerfile
# HTTP/SSE 模式，浏览器通过 CDP 连接外部 Chrome

ARG XIANYU_MCP_BASE_IMAGE=registry.cn-hangzhou.aliyuncs.com/ggball/xianyu-mcp-base:latest
FROM ${XIANYU_MCP_BASE_IMAGE}

WORKDIR /app

# 复制代码
COPY src/ ./src/
COPY mcp_server/ ./mcp_server/

# 暴露端口
EXPOSE 8080

# 直接启动 HTTP Server
CMD ["python", "-m", "mcp_server.http_server"]
