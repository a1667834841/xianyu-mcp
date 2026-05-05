# 闲鱼 MCP Server Dockerfile
# HTTP/SSE 模式，浏览器通过 CDP 连接外部 Chrome

FROM registry.cn-hangzhou.aliyuncs.com/ggball/xianyu-mcp:latest

WORKDIR /app

# 安装/更新 Python 依赖（在本地基础镜像之上补齐新增依赖）
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 复制最新代码
COPY src/ ./src/
COPY mcp_server/ ./mcp_server/

# 暴露端口
EXPOSE 8080

# 直接启动 HTTP Server
CMD ["python", "-m", "mcp_server.http_server"]
