#!/usr/bin/env bash
set -eu

export POOL_SIZE="${BROWSER_POOL_SIZE:-1}"
export START_PORT="${BROWSER_CDP_START_PORT:-9222}"
export PROFILE_ROOT="${BROWSER_PROFILE_ROOT:-/data/browser-pool}"
export CHROME_BIN="${CHROME_BIN:-google-chrome}"

python - <<'PY'
import socket
import time
import os
import subprocess
from pathlib import Path
from docker.start_browser_pool import build_chrome_commands

pool_size = int(os.environ["POOL_SIZE"])
start_port = int(os.environ["START_PORT"])
profile_root = Path(os.environ["PROFILE_ROOT"])
chrome_bin = os.environ["CHROME_BIN"]

commands = build_chrome_commands(
    pool_size=pool_size,
    start_port=start_port,
    profile_root=profile_root,
    chrome_bin=chrome_bin,
)

procs = [subprocess.Popen(cmd) for cmd in commands]

def wait_for_port(port: int, host: str = "::1", timeout: float = 30.0) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        try:
            sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
            sock.settimeout(1)
            sock.connect((host, port))
            sock.close()
            return True
        except (socket.error, OSError):
            time.sleep(0.5)
    return False

for i in range(pool_size):
    port = start_port + i
    if wait_for_port(port):
        print(f"Chrome ready on port {port}")
    else:
        print(f"WARNING: Chrome port {port} not ready after timeout")

for proc in procs:
    proc.wait()
PY

for i in $(seq 0 $((POOL_SIZE - 1))); do
  port=$((START_PORT + i))
  mapped_port=$((port + 10))
  socat "TCP-LISTEN:${port},bind=0.0.0.0,reuseaddr,fork" "TCP:[::1]:${port}" &
  socat "TCP-LISTEN:${mapped_port},bind=0.0.0.0,reuseaddr,fork" "TCP:[::1]:${port}" &
done

wait