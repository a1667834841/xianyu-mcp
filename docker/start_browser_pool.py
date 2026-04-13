from __future__ import annotations

import os
import socket
import subprocess
import time
from pathlib import Path
from typing import Callable


def build_chrome_command(
    start_port: int, profile_root: Path, chrome_bin: str
) -> list[str]:
    slot_id = "slot-1"
    profile_dir = profile_root / slot_id / "profile"
    return [
        chrome_bin,
        f"--user-data-dir={profile_dir}",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--remote-debugging-address=0.0.0.0",
        f"--remote-debugging-port={start_port}",
        "about:blank",
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
    start_port: int,
    profile_root: Path,
    chrome_bin: str,
    *,
    popen: Callable[[list[str]], object] = subprocess.Popen,
    wait_for_port: Callable[[int, str, float], bool] = wait_for_port,
) -> None:
    if pool_size != 1:
        print(f"Browser pool size {pool_size} requested; forcing single browser slot")

    chrome_command = build_chrome_command(
        start_port=start_port,
        profile_root=profile_root,
        chrome_bin=chrome_bin,
    )
    chrome_proc = popen(chrome_command)

    if wait_for_port(start_port):
        print(f"Chrome ready on port {start_port}")
    else:
        print(f"WARNING: Chrome port {start_port} not ready after timeout")

    chrome_proc.wait()


def main() -> None:
    run_browser_pool(
        pool_size=int(os.environ.get("BROWSER_POOL_SIZE", "1")),
        start_port=int(os.environ.get("BROWSER_CDP_START_PORT", "9222")),
        profile_root=Path(os.environ.get("BROWSER_PROFILE_ROOT", "/data/browser-pool")),
        chrome_bin=os.environ.get("CHROME_BIN", "google-chrome"),
    )


if __name__ == "__main__":
    main()
