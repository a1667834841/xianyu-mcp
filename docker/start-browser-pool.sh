#!/usr/bin/env bash
set -eu

export POOL_SIZE="${BROWSER_POOL_SIZE:-1}"
export START_PORT="${BROWSER_CDP_START_PORT:-9222}"
export PROFILE_ROOT="${BROWSER_PROFILE_ROOT:-/data/browser-pool}"
export CHROME_BIN="${CHROME_BIN:-google-chrome}"

for i in $(seq 0 $((POOL_SIZE - 1))); do
  port=$((START_PORT + i))
  mapped_port=$((port + 10))
  socat "TCP-LISTEN:${port},bind=0.0.0.0,reuseaddr,fork" "TCP:[::1]:${port}" &
  socat "TCP-LISTEN:${mapped_port},bind=0.0.0.0,reuseaddr,fork" "TCP:[::1]:${port}" &
done

python - <<'PY'
from pathlib import Path
import os
import subprocess
from docker.start_browser_pool import build_chrome_commands

commands = build_chrome_commands(
    pool_size=int(os.environ["POOL_SIZE"]),
    start_port=int(os.environ["START_PORT"]),
    profile_root=Path(os.environ["PROFILE_ROOT"]),
    chrome_bin=os.environ["CHROME_BIN"],
)

procs = [subprocess.Popen(cmd) for cmd in commands]
for proc in procs:
    proc.wait()
PY
