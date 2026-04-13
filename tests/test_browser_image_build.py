from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_browser_service_exposes_cdp_and_mcp_ports_from_shared_namespace():
    compose = yaml.safe_load(
        (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    )

    browser = compose["services"]["browser"]

    assert (
        "BROWSER_INTERNAL_CDP_START_PORT=${BROWSER_INTERNAL_CDP_START_PORT:-9322}"
        not in browser["environment"]
    )
    assert "BROWSER_POOL_SIZE=${BROWSER_POOL_SIZE:-1}" in browser["environment"]
    assert browser["ports"] == [
        "${BROWSER_PORT_1:-9222}:9222",
        "${MCP_HOST_PORT:-8080}:8080",
    ]


def test_browser_dockerfile_no_longer_installs_socat():
    dockerfile = (REPO_ROOT / "docker" / "browser.Dockerfile").read_text(
        encoding="utf-8"
    )

    assert "socat" not in dockerfile


def test_browser_pool_startup_script_only_delegates_to_python_module():
    script = (REPO_ROOT / "docker" / "start-browser-pool.sh").read_text(
        encoding="utf-8"
    )
    module = (REPO_ROOT / "docker" / "start_browser_pool.py").read_text(
        encoding="utf-8"
    )

    assert "python -m docker.start_browser_pool" in script
    assert "socat" not in module
    assert "remote-debugging-address=0.0.0.0" in module


def test_mcp_service_mounts_multi_user_data_roots():
    compose = yaml.safe_load(
        (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    )

    mcp_server = compose["services"]["mcp-server"]
    volumes = mcp_server["volumes"]

    assert "${XIANYU_HOST_DATA_DIR:-./data}/users:/data/users" in volumes
    assert "${XIANYU_HOST_DATA_DIR:-./data}/registry:/data/registry" in volumes
    assert "container_name" not in mcp_server
    assert mcp_server["network_mode"] == "service:browser"
    assert "ports" not in mcp_server
    assert "BROWSER_POOL_SIZE=${BROWSER_POOL_SIZE:-1}" in mcp_server["environment"]
    assert "CDP_HOST=${CDP_HOST:-127.0.0.1}" in mcp_server["environment"]
    assert (
        "BROWSER_CDP_START_PORT=${BROWSER_CDP_START_PORT:-9222}"
        in mcp_server["environment"]
    )
