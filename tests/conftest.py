import pytest
import asyncio
from pathlib import Path
import sys
import requests

project_root = Path(__file__).parent.parent.resolve()
src_path = project_root / "src"
sys.path.insert(0, str(project_root))


@pytest.fixture(scope="session")
def test_token():
    """获取测试 Token（从缓存文件加载）"""
    token_file = Path.home() / ".claude" / "xianyu-tokens" / "token.json"
    if token_file.exists():
        import json

        data = json.loads(token_file.read_text())
        return data.get("token")
    return None


@pytest.fixture
async def browser():
    """获取浏览器实例（异步）"""
    from src.browser import AsyncChromeManager

    manager = AsyncChromeManager()
    await manager.ensure_running()
    yield manager
    await manager.close()


@pytest.fixture
async def xianyu_app():
    """获取 XianyuApp 实例（重构后的统一入口）"""
    from src.core import XianyuApp

    app = XianyuApp()
    await app.browser.ensure_running()
    yield app
    await app.browser.close()


@pytest.fixture(scope="module")
def session_id():
    """获取 MCP SSE session_id（用于 HTTP MCP 测试）"""
    # 尝试连接到已运行的 MCP Server
    try:
        resp = requests.get('http://localhost:8080/sse', stream=True, timeout=5)
        if resp.status_code == 200:
            for line in resp.iter_lines(decode_unicode=True):
                if line and 'session_id=' in line:
                    sid = line.split('session_id=')[1]
                    return sid
    except Exception as e:
        pytest.skip(f"MCP Server 未运行或无法连接: {e}")

    pytest.skip("无法获取 session_id，请确保 MCP Server 正在运行")
