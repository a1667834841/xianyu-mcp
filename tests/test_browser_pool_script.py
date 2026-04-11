from pathlib import Path

from docker import start_browser_pool


def test_build_chrome_commands_uses_pool_size_and_incrementing_ports(tmp_path):
    commands = start_browser_pool.build_chrome_commands(
        pool_size=3,
        start_port=9222,
        profile_root=tmp_path / "browser-pool",
        chrome_bin="google-chrome",
    )

    assert commands[0][-2] == "--remote-debugging-port=9222"
    assert commands[1][-2] == "--remote-debugging-port=9223"
    assert commands[2][-2] == "--remote-debugging-port=9224"
    assert any("slot-1/profile" in arg for arg in commands[0])
    assert any("slot-2/profile" in arg for arg in commands[1])
    assert any("slot-3/profile" in arg for arg in commands[2])
    assert "--no-sandbox" in commands[0]
    assert "--no-sandbox" in commands[1]
    assert "--no-sandbox" in commands[2]
    assert "--remote-debugging-address=0.0.0.0" in commands[0]
    assert "--remote-debugging-address=0.0.0.0" in commands[1]
    assert "--remote-debugging-address=0.0.0.0" in commands[2]
