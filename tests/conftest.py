import pytest
import asyncio
from pathlib import Path
import sys

project_root = Path(__file__).parent.parent
src_path = project_root / "src"
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(src_path))


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
    from browser import AsyncChromeManager

    manager = AsyncChromeManager()
    await manager.ensure_running()
    yield manager
    await manager.close()


@pytest.fixture
async def xianyu_app():
    """获取 XianyuApp 实例（重构后的统一入口）"""
    from core import XianyuApp

    app = XianyuApp()
    await app.browser.ensure_running()
    yield app
    await app.browser.close()
