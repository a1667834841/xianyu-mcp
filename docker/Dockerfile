# 闲鱼 MCP Server Dockerfile
# HTTP/SSE 模式，浏览器通过 CDP 连接外部 Chrome

FROM python:3.11-slim

WORKDIR /app

ENV TZ=Asia/Shanghai

# 安装系统依赖（Playwright 需要的库 + curl 用于健康检查）
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxkbcommon0 \
    libatspi2.0-0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    tzdata \
    curl \
    && ln -snf /usr/share/zoneinfo/${TZ} /etc/localtime \
    && printf '%s\n' "${TZ}" > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制代码
COPY src/ ./src/
COPY mcp_server/ ./mcp_server/

# 创建数据目录
RUN mkdir -p /data/tokens /data/chrome-profile

# 暴露端口
EXPOSE 8080

# 直接启动 HTTP Server（不再需要 entrypoint.sh）
CMD ["python", "-m", "mcp_server.http_server"]
