from __future__ import annotations

from pathlib import Path


def build_chrome_commands(
    pool_size: int, start_port: int, profile_root: Path, chrome_bin: str
) -> list[list[str]]:
    commands = []
    for index in range(pool_size):
        slot_id = f"slot-{index + 1}"
        profile_dir = profile_root / slot_id / "profile"
        commands.append(
            [
                chrome_bin,
                f"--user-data-dir={profile_dir}",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--remote-debugging-address=::1",
                f"--remote-debugging-port={start_port + index}",
                "about:blank",
            ]
        )
    return commands
