FROM registry.cn-hangzhou.aliyuncs.com/ggball/chrome-headless-shell-zh:latest

WORKDIR /app

RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    bash \
    python3 \
    socat \
    && ln -sf /usr/bin/python3 /usr/local/bin/python \
    && rm -rf /var/lib/apt/lists/*

COPY docker/__init__.py /app/docker/__init__.py
COPY docker/start_browser_pool.py /app/docker/start_browser_pool.py
COPY docker/start-browser-pool.sh /app/docker/start-browser-pool.sh

RUN chmod +x /app/docker/start-browser-pool.sh \
    && mkdir -p /data/browser-pool

ENTRYPOINT ["/bin/bash", "/app/docker/start-browser-pool.sh"]
