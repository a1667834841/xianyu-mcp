from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_browser_service_builds_from_local_dockerfile():
    compose = yaml.safe_load(
        (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    )

    browser = compose["services"]["browser"]

    assert browser["build"]["context"] == "."
    assert browser["build"]["dockerfile"] == "docker/browser.Dockerfile"
    assert "container_name" not in browser
    assert (
        "CHROME_BIN=${CHROME_BIN:-/headless-shell/headless-shell}"
        in browser["environment"]
    )


def test_browser_dockerfile_copies_pool_scripts_into_image():
    dockerfile = (REPO_ROOT / "docker" / "browser.Dockerfile").read_text(
        encoding="utf-8"
    )

    assert (
        "COPY docker/start-browser-pool.sh /app/docker/start-browser-pool.sh"
        in dockerfile
    )
    assert (
        "COPY docker/start_browser_pool.py /app/docker/start_browser_pool.py"
        in dockerfile
    )
    assert "socat" in dockerfile


def test_browser_pool_startup_script_forwards_cdp_ports():
    script = (REPO_ROOT / "docker" / "start-browser-pool.sh").read_text(
        encoding="utf-8"
    )

    assert "socat" in script
    assert "TCP-LISTEN" in script
    assert "TCP:[::1]:${port}" in script
    assert "mapped_port=$((port + 10))" in script


def test_mcp_service_mounts_multi_user_data_roots():
    compose = yaml.safe_load(
        (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    )

    mcp_server = compose["services"]["mcp-server"]
    volumes = mcp_server["volumes"]

    assert "${XIANYU_HOST_DATA_DIR:-./data}/users:/data/users" in volumes
    assert "${XIANYU_HOST_DATA_DIR:-./data}/registry:/data/registry" in volumes
    assert "container_name" not in mcp_server
    assert "BROWSER_POOL_SIZE=${BROWSER_POOL_SIZE:-1}" in mcp_server["environment"]
    assert (
        "BROWSER_CDP_START_PORT=${BROWSER_CDP_START_PORT:-9222}"
        in mcp_server["environment"]
    )
