from __future__ import annotations

import os
import socket
import subprocess
import time
from pathlib import Path
from typing import Callable


def build_chrome_command(
    internal_port: int, profile_root: Path, chrome_bin: str
) -> list[str]:
    """构建 Chrome 命令（监听内部端口）"""
    slot_id = "slot-1"
    profile_dir = profile_root / slot_id / "profile"
    return [
        chrome_bin,
        f"--user-data-dir={profile_dir}",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--remote-debugging-address=127.0.0.1",  # Chrome 只支持 127.0.0.1
        f"--remote-debugging-port={internal_port}",
        "about:blank",
    ]


def build_socat_command(external_port: int, internal_port: int) -> list[str]:
    """构建 socat 代理命令（转发外部端口到内部端口）"""
    return [
        "socat",
        f"TCP4-LISTEN:{external_port},fork,reuseaddr,bind=0.0.0.0",
        f"TCP4:127.0.0.1:{internal_port}",
    ]


def wait_for_port(port: int, host: str = "127.0.0.1", timeout: float = 30.0) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            sock.connect((host, port))
            sock.close()
            return True
        except (socket.error, OSError):
            time.sleep(0.5)
    return False


def run_browser_pool(
    pool_size: int,
    external_port: int,
    internal_port: int,
    profile_root: Path,
    chrome_bin: str,
    *,
    popen: Callable[[list[str]], object] = subprocess.Popen,
    wait_for_port: Callable[[int, str, float], bool] = wait_for_port,
) -> None:
    """运行浏览器池：启动 socat 代理 + Chrome"""
    if pool_size != 1:
        print(f"Browser pool size {pool_size} requested; forcing single browser slot")

    # 1. 启动 socat 代理（转发外部端口到内部端口）
    socat_cmd = build_socat_command(external_port, internal_port)
    print(f"Starting socat: {external_port} -> {internal_port}")
    socat_proc = popen(socat_cmd)
    
    # 2. 启动 Chrome（监听内部端口）
    chrome_cmd = build_chrome_command(
        internal_port=internal_port,
        profile_root=profile_root,
        chrome_bin=chrome_bin,
    )
    print(f"Starting Chrome on internal port {internal_port}")
    chrome_proc = popen(chrome_cmd)

    # 3. 等待端口就绪
    if wait_for_port(internal_port, "127.0.0.1"):
        print(f"Chrome ready on internal port {internal_port}")
    else:
        print(f"WARNING: Chrome internal port {internal_port} not ready after timeout")

    if wait_for_port(external_port, "0.0.0.0"):
        print(f"Socat proxy ready on external port {external_port}")
    else:
        print(f"WARNING: Socat external port {external_port} not ready after timeout")

    print(f"CDP endpoint: http://0.0.0.0:{external_port}")

    # 4. 等待 Chrome 进程
    chrome_proc.wait()
    
    # 清理 socat
    socat_proc.terminate()


def main() -> None:
    external_port = int(os.environ.get("BROWSER_CDP_START_PORT", "9222"))
    internal_port = int(os.environ.get("BROWSER_INTERNAL_CDP_PORT", "9322"))
    
    run_browser_pool(
        pool_size=int(os.environ.get("BROWSER_POOL_SIZE", "1")),
        external_port=external_port,
        internal_port=internal_port,
        profile_root=Path(os.environ.get("BROWSER_PROFILE_ROOT", "/data/browser-pool")),
        chrome_bin=os.environ.get("CHROME_BIN", "/headless-shell/headless-shell"),
    )


if __name__ == "__main__":
    main()
