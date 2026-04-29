# 闲鱼 MCP Server 基础镜像
# 包含稳定的系统依赖和 Python 依赖，业务镜像只复制应用代码。

FROM python:3.11-slim

WORKDIR /app

ENV TZ=Asia/Shanghai

ARG PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple

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

COPY requirements.txt .
RUN pip install --no-cache-dir --index-url ${PIP_INDEX_URL} -r requirements.txt

RUN mkdir -p /data/tokens /data/chrome-profile
