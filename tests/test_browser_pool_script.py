from docker import start_browser_pool


def test_build_chrome_command_binds_public_debug_port(tmp_path):
    command = start_browser_pool.build_chrome_command(
        start_port=9222,
        profile_root=tmp_path / "browser-pool",
        chrome_bin="google-chrome",
    )

    assert command[0] == "google-chrome"
    assert "--remote-debugging-address=0.0.0.0" in command
    assert "--remote-debugging-port=9222" in command
    assert any("slot-1/profile" in arg for arg in command)


def test_run_browser_pool_starts_single_chrome_without_socat(tmp_path, capsys):
    events: list[str] = []

    class FakeProc:
        def __init__(self, name: str):
            self.name = name

        def wait(self):
            events.append(f"wait:{self.name}")

    def fake_popen(cmd: list[str]):
        port_arg = next(
            arg for arg in cmd if arg.startswith("--remote-debugging-port=")
        )
        port = port_arg.split("=", 1)[1]
        events.append(f"start:chrome:{port}")
        return FakeProc(f"chrome:{port}")

    def fake_wait_for_port(
        port: int, host: str = "127.0.0.1", timeout: float = 30.0
    ) -> bool:
        events.append(f"ready:{host}:{port}")
        return True

    start_browser_pool.run_browser_pool(
        pool_size=3,
        start_port=9222,
        profile_root=tmp_path / "browser-pool",
        chrome_bin="google-chrome",
        popen=fake_popen,
        wait_for_port=fake_wait_for_port,
    )

    captured = capsys.readouterr()
    assert "Browser pool size 3 requested; forcing single browser slot" in captured.out
    assert events == [
        "start:chrome:9222",
        "ready:127.0.0.1:9222",
        "wait:chrome:9222",
    ]
